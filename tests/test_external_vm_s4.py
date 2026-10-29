"""S4 pure admission tests. Never invoke assembly, tools, packages or native code."""
import copy
import importlib
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "tests/native/external_vm/s4"


def member(name, kind=tarfile.REGTYPE, size=1, link=""):
    value = tarfile.TarInfo(name)
    value.type, value.size, value.linkname, value.mode = kind, size, link, 0o644
    return value


class Authentication(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(BASE))
        self.auth = importlib.import_module("authenticate")

    def tearDown(self):
        sys.path.remove(str(BASE))

    def test_pending_trust_refuses_before_any_payload_or_tool_access(self):
        policy = json.loads((BASE / "trust-policy.json").read_text())
        with self.assertRaisesRegex(ValueError, "reviewed trust root"):
            self.auth.check_policy(policy)
        with self.assertRaisesRegex(ValueError, "reviewed trust root"):
            self.auth.authenticate_set(Path("/missing-lock"),BASE/"trust-policy.json",
                Path("/missing-keyring"),Path("/missing-cache"),{},Path("/missing-output"))

    def test_review_cannot_omit_lifecycle_tool_or_full_fingerprint_decisions(self):
        policy = dict(schema_version=1, status="reviewed", lock_sha256=self.auth.LOCK_SHA256,
                      keyring_sha256="a"*64, review_reference="review-1", reviewed_at_epoch=1800000000,
                      signers=self.signers(),
                      tools={name: {"sha256": "c"*64} for name in ("gpgv", "zstd", "vercmp")})
        self.auth.check_policy(policy)
        mutations = (
            ("missing lifecycle", lambda p: p["signers"][0].pop("lifecycle_review"), "lifecycle fields"),
            ("unreviewed lifecycle", lambda p: p["signers"][0].update(lifecycle_review="pending"), "lifecycle review"),
            ("missing tool", lambda p: p["tools"].pop("vercmp"), "tool receipts"),
            ("malformed tool hash", lambda p: p["tools"]["gpgv"].update(sha256="short"), "tool hash"),
            ("short signing fingerprint", lambda p: p["signers"][0].update(signing_fingerprint="A"*16), "full signer fingerprint"),
            ("short primary fingerprint", lambda p: p["signers"][0].update(primary_fingerprint="B"*16), "full signer fingerprint"),
            ("unreviewed time window", lambda p: p["signers"][0].update(valid_until=1800000001), "acceptance window"),
        )
        for name, mutate, message in mutations:
            changed = copy.deepcopy(policy)
            mutate(changed)
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, message):
                self.auth.check_policy(changed)

    def status(self, fingerprint="A"*40, primary="B"*40):
        return ("[GNUPG:] GOODSIG 123 packager\n[GNUPG:] VALIDSIG " + fingerprint +
                " 2026-10-01 1790812800 0 4 0 22 10 00 " + primary + "\n")

    def signers(self):
        return [dict(signing_fingerprint="A"*40, primary_fingerprint="B"*40,
                     valid_from=1700000000, valid_until=1800000000,
                     lifecycle_review="accepted-no-known-revocation")]

    def test_validsig_requires_full_primary_and_signing_identity_and_safe_algorithm(self):
        result = self.auth.signature_status(self.status(), self.signers(), 1800000000)
        self.assertEqual(result["primary_fingerprint"], "B"*40)
        for status in (self.status(primary="C"*40), self.status(fingerprint="C"*40),
                       self.status().replace("22 10 00", "22 2 00"),
                       self.status() + self.status(), "[GNUPG:] GOODSIG 123 person\n"):
            with self.subTest(status=status), self.assertRaises(ValueError):
                self.auth.signature_status(status, self.signers(), 1800000000)

    def test_bad_expired_revoked_error_status_and_out_of_review_window_refuse(self):
        for flag in ("BADSIG", "ERRSIG", "EXPKEYSIG", "EXPSIG", "REVKEYSIG", "NO_PUBKEY", "FAILURE"):
            with self.subTest(flag=flag), self.assertRaises(ValueError):
                self.auth.signature_status(self.status()+"[GNUPG:] "+flag+" bad\n", self.signers(), 1800000000)
        with self.assertRaises(ValueError):
            self.auth.signature_status(self.status(), self.signers(), 1750000000)

    def row(self):
        return dict(name="app", version="1:2.0-1", architecture="any", build_epoch=1700000000,
                    depends=["libfoo.so=2-64"], provides=["virtual=2"], source_base="app")

    def info(self):
        return b"pkgname = app\npkgbase = app\npkgver = 1:2.0-1\narch = any\nbuilddate = 1700000000\ndepend = libfoo.so=2-64\nprovides = virtual=2\n"

    def test_signed_metadata_must_match_locked_identity_versions_and_dependencies(self):
        self.auth.check_pkginfo(self.info(), self.row())
        for old,new in ((b"app",b"other"),(b"1:2.0-1",b"2.0-1"),
                        (b"2-64",b"1-64"),(b"1700000000",b"1700000001")):
            with self.subTest(old=old), self.assertRaises(ValueError):
                self.auth.check_pkginfo(self.info().replace(old,new), self.row())
        with self.assertRaises(ValueError):
            self.auth.check_pkginfo(self.info()+b"pkgname = app\n", self.row())

    def test_signed_metadata_closure_is_recomputed_with_real_arch_version_semantics(self):
        lock = json.loads((BASE.parent / "packages.lock.json").read_text())
        metadata = {p["name"]:p for p in lock["packages"]}
        # Equal-only comparisons suffice for this pure graph test. The real
        # verifier supplies the hash-pinned Arch vercmp tool, never this lambda.
        calls = []
        def compare(a,b):
            calls.append((a,b))
            return 0
        self.auth.check_closure(lock, metadata, compare)
        self.assertTrue(calls)
        bad = copy.deepcopy(metadata)
        bad["glibc"]["depends"] = ["missing-provider"]
        with self.assertRaises(ValueError):
            self.auth.check_closure(lock,bad,compare)
        with self.assertRaises(ValueError):
            self.auth.check_closure(lock,metadata,lambda a,b:-1)


class ArchiveAdmission(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0,str(BASE))
        self.arc = importlib.import_module("archives")

    def tearDown(self):
        sys.path.remove(str(BASE))

    def plan(self, rows):
        return self.arc.plan_members(rows)

    def test_canonical_paths_only_and_no_duplicate_aliases(self):
        for name in ("/etc/passwd", "../escape", "usr/../etc/x", "usr//x", "usr/./x", "x\\y", "x\ny"):
            with self.subTest(name=name),self.assertRaises(ValueError):
                self.plan({"one":[member(name)]})
        with self.assertRaises(ValueError):
            self.plan({"one":[member("./usr/x"),member("usr/x")]})

    def test_shared_directories_are_allowed_and_file_collisions_always_refuse(self):
        plan = self.plan({"one":[member("usr",tarfile.DIRTYPE,0),member("usr/a")],
                          "two":[member("usr",tarfile.DIRTYPE,0),member("usr/b")]})
        self.assertEqual(plan["expanded_bytes"],2)
        with self.assertRaisesRegex(ValueError,"collision"):
            self.plan({"one":[member("usr/a")],"two":[member("usr/a")]})
        with self.assertRaises(ValueError):
            self.plan({"one":[member("usr/a"),member("usr/a/b")]})

    def test_symlinks_cannot_escape_cycle_or_be_a_write_parent_in_any_order(self):
        for rows in ([member("usr/a",tarfile.SYMTYPE,0,"../../escape")],
                     [member("usr/a",tarfile.SYMTYPE,0,"/etc/passwd")],
                     [member("usr/a",tarfile.SYMTYPE,0,"b"),member("usr/b",tarfile.SYMTYPE,0,"a")],
                     [member("usr/a",tarfile.SYMTYPE,0,"b"),member("usr/a/child")]):
            with self.subTest(rows=[m.name for m in rows]),self.assertRaises(ValueError):
                self.plan({"one":list(reversed(rows))})

    def test_relative_links_inside_root_are_created_last_and_can_be_dangling(self):
        plan=self.plan({"one":[member("bin",tarfile.SYMTYPE,0,"usr/bin"),member("usr/bin/app")]})
        self.assertEqual(plan["entries"]["bin"]["kind"],"symlink")

    def test_symlink_dotdot_is_resolved_after_link_expansion(self):
        rows=[member("a",tarfile.SYMTYPE,0,"deep/path"),
              member("deep/path",tarfile.DIRTYPE,0),
              member("other",tarfile.SYMTYPE,0,"a/../target")]
        plan=self.plan({"one":rows})
        self.assertEqual(plan["entries"]["other"]["resolved_target"],"deep/target")

    def test_links_into_dynamic_mountpoints_are_refused(self):
        for target in ("../proc/self/fd/1","../dev/stdout","../sys/kernel","../run/session","../tmp/x"):
            with self.subTest(target=target),self.assertRaises(ValueError):
                self.plan({"one":[member("usr/x",tarfile.SYMTYPE,0,target)]})

    def test_hardlinks_are_same_archive_direct_regular_targets_and_become_copies(self):
        plan=self.plan({"one":[member("usr/a",size=3),member("usr/b",tarfile.LNKTYPE,0,"usr/a")]})
        self.assertEqual(plan["expanded_bytes"],6)
        self.assertEqual(plan["entries"]["usr/b"]["kind"],"copy")
        for rows in ({"one":[member("usr/b",tarfile.LNKTYPE,0,"usr/a")],"two":[member("usr/a")]},
                     {"one":[member("usr/a",tarfile.SYMTYPE,0,"c"),member("usr/b",tarfile.LNKTYPE,0,"usr/a")]},
                     {"one":[member("usr/b",tarfile.LNKTYPE,0,"../a")]},
                     {"one":[member("usr/b",tarfile.LNKTYPE,0,".PKGINFO"),member(".PKGINFO")]}):
            with self.subTest(rows=rows),self.assertRaises(ValueError):
                self.plan(rows)

    def test_metadata_is_never_installed_and_special_files_sparse_and_budgets_refuse(self):
        plan=self.plan({"one":[member(".PKGINFO"),member(".INSTALL"),member("usr/app")]})
        self.assertNotIn(".INSTALL",plan["entries"])
        for item in (member("dev/x",tarfile.CHRTYPE,0),member("pipe",tarfile.FIFOTYPE,0),
                     member("out/file"),member("huge",size=3*1024**3)):
            with self.subTest(name=item.name),self.assertRaises(ValueError):
                self.plan({"one":[item]})
        sparse=member("usr/sparse"); sparse.sparse=[(0,1)]
        with self.assertRaises(ValueError):
            self.plan({"one":[sparse]})


class Stages(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0,str(BASE))
        self.harness=importlib.import_module("harness")

    def tearDown(self):
        sys.path.remove(str(BASE))

    def test_stage_plan_is_bound_to_preserved_inputs_and_has_no_execution_path(self):
        value=self.harness.stage_plan(ROOT)
        self.assertEqual([s["phase"] for s in value["stages"]],
                         ["preparation","build","capture","evidence-export"])
        self.assertFalse(value["execution_enabled"])
        self.assertFalse(value["capture_enabled"])
        self.assertEqual(value["frame_count"],1)

    def test_build_cannot_claim_capture_and_capture_always_refuses(self):
        with self.assertRaises(ValueError):
            self.harness.require_stage("build",{})
        with self.assertRaisesRegex(ValueError,"sealed"):
            self.harness.require_stage("capture",{"authentication":True,"assembly":True,"build":True})

    def test_export_is_sealed_before_any_filesystem_access(self):
        class NoIO:
            def __fspath__(self):
                raise AssertionError("sealed export attempted filesystem access")

            def __truediv__(self, name):
                raise AssertionError("sealed export attempted source access")

        files={"stdout.txt":{"kind":"regular","bytes":0,"sha256":"0"*64}}
        for status in ("prepared","assembled-not-built","built-not-captured",
                       "failed-setup","failed-build","captured"):
            with self.subTest(status=status), self.assertRaisesRegex(ValueError,"export remains sealed"):
                self.harness.export_evidence(NoIO(),NoIO(),files,status)

    def test_export_stage_cannot_be_enabled_by_a_claimed_reap_receipt(self):
        for receipts in ({},{"producer_reaped":True}):
            with self.subTest(receipts=receipts), self.assertRaisesRegex(ValueError,"export remains sealed"):
                self.harness.require_stage("evidence-export",receipts)

    def test_export_rejects_unknown_names_links_oversize_and_fake_success(self):
        self.harness.check_export_manifest({"stdout.txt":{"kind":"regular","bytes":0,"sha256":"0"*64}},"failed-setup")
        for files,status in (({"../secret":{"kind":"regular","bytes":1,"sha256":"0"*64}},"failed-setup"),
                             ({"stdout.txt":{"kind":"symlink","bytes":0,"sha256":"0"*64}},"failed-setup"),
                             ({"stdout.txt":{"kind":"regular","bytes":2*1024**2,"sha256":"0"*64}},"failed-setup"),
                             ({"stdout.txt":{"kind":"regular","bytes":0,"sha256":"0"*64}},"captured")):
            with self.subTest(files=files),self.assertRaises(ValueError):
                self.harness.check_export_manifest(files,status)


class PrivateIO(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0,str(BASE))
        self.common=importlib.import_module("common")

    def tearDown(self):
        sys.path.remove(str(BASE))

    def test_private_output_rejects_a_symlink_parent(self):
        with tempfile.TemporaryDirectory() as temporary:
            base=Path(temporary)
            (base/"real").mkdir(mode=0o700)
            (base/"alias").symlink_to("real",target_is_directory=True)
            with self.assertRaises((OSError,ValueError)):
                self.common.new_private(base/"alias"/"output")

    def test_held_output_descriptor_survives_ancestor_substitution(self):
        with tempfile.TemporaryDirectory() as temporary:
            base=Path(temporary)
            (base/"parent").mkdir(mode=0o700)
            (base/"other").mkdir(mode=0o700)
            (base/"input").write_bytes(b"safe")
            with self.common.new_private(base/"parent"/"output") as private:
                (base/"parent").rename(base/"moved")
                (base/"parent").symlink_to("other",target_is_directory=True)
                self.common.private_copy(base/"input",private/"file",self.common.sha256(b"safe"),4)
                self.assertEqual(self.common.read_bounded(private/"file",4),b"safe")
            self.assertEqual((base/"moved"/"output"/"file").read_bytes(),b"safe")
            self.assertFalse((base/"other"/"output").exists())


if __name__ == "__main__":
    unittest.main()
