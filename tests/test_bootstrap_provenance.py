"""Synthetic byte/graph tests only. No real certificate or package is authenticated."""
import copy
import hashlib
import importlib.util
import json
import lzma
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

BASE = Path(__file__).resolve().parent / "native/external_vm/s4"
LOCK = "f4034660aa04de28123ccaf80fd6d12d2d7eb9c8f2d29e5043f1f4511fe16618"

# Exact paragraph from pinned noble:universe Packages.xz (SHA256
# ba9057fa1b91438cc8a1d26808d00c85389fe101d0c1496254df97236405599a).
# Paragraph SHA256: cc5e0f3e743b85c3b3cb47dcc276f142b156c16b4dd9f35be19d78f09ec7e7d0.
# Public metadata only; no btm package is downloaded or executed.
BTM_PARAGRAPH = b"""Package: btm
Architecture: amd64
Version: 0.9.6-4
Built-Using: rust-ahash-0.7 (= 0.7.7-2), rust-nix (= 0.26.2-1), rust-option-ext (= 0.2.0-1), rustc (= 1.75.0+dfsg0ubuntu1-0ubuntu1)
Multi-Arch: allowed
Priority: optional
Section: universe/utils
Origin: Ubuntu
Maintainer: Ubuntu Developers <ubuntu-devel-discuss@lists.ubuntu.com>
Original-Maintainer: Jonas Smedegaard <dr@jones.dk>
Bugs: https://bugs.launchpad.net/ubuntu/+filebug
Installed-Size: 4799
Depends: libc6 (>= 2.38), libgcc-s1 (>= 4.2)
Suggests: bash-completion
Filename: pool/universe/b/btm/btm_0.9.6-4_amd64.deb
Size: 1607224
MD5sum: 5af6a25fa3b1bb766aecbc7a290670e7
SHA1: 5a8e3563ffc958d5a7b1dff8b97300eb03b1cd02
SHA256: 62b3c95436097e45edeebd72396831938df40de055d2e0dd9fcf276639314799
SHA512: 29806c67d9f74461eedadb488a94bf66d478cda15f33c44fbbc2c710902455fff875d38cada331c1aea84fc2fc6d7bf80aecb0c415273a70751a7ce543ff5518
Homepage: https://clementtsang.github.io/bottom
Description: customizable graphical process/system monitor for the terminal
X-Cargo-Built-Using:
 rust-addr2line (= 0.21.0-2), rust-adler (= 1.0.2-2), rust-ahash-0.7 (= 0.7.7-2), rust-aho-corasick (= 1.1.2-1), rust-anstream (= 0.6.7-1), rust-anstyle (= 1.0.4-1), rust-anstyle-parse (= 0.2.1-1), rust-anstyle-query (= 1.0.0-1), rust-anyhow (= 1.0.75-1), rust-assert-cmd (= 2.0.12-1), rust-backtrace (= 0.3.69-2), rust-bitflags-1 (= 1.3.2-5), rust-bitflags (= 2.4.2-1), rust-bstr (= 1.7.0-2build1), rust-cassowary (= 0.3.0-2), rust-cfg-if (= 1.0.0-1), rust-clap-builder (= 4.4.18-1), rust-clap (= 4.4.18-1), rust-clap-lex (= 0.6.0-2), rust-colorchoice (= 1.0.0-1), rust-concat-string (= 1.0.1-1), rust-crossbeam-deque (= 0.8.5-1), rust-crossbeam-epoch (= 0.9.18-1), rust-crossbeam-utils (= 0.8.19-1), rust-crossterm (= 0.27.0-3), rust-ctrlc (= 3.4.2-1), rust-difflib (= 0.4.0-1), rust-dirs (= 5.0.1-1), rust-dirs-sys (= 0.4.1-1), rust-doc-comment (= 0.3.3-1), rust-either (= 1.9.0-1), rust-float-cmp (= 0.9.0-1), rust-getrandom (= 0.2.10-1), rust-gimli (= 0.28.1-2), rust-hashbrown (= 0.12.3-1), rust-humantime (= 2.1.0-1), rust-indexmap (= 1.9.3-2), rust-itertools (= 0.10.5-1), rust-itoa (= 1.0.9-1), rust-kstring (= 2.0.0-1), rust-lazycell (= 1.3.0-3), rust-libc (= 0.2.152-1), rust-libloading (= 0.7.4-1), rust-linux-raw-sys (= 0.4.12-1), rust-lock-api (= 0.4.11-1), rust-log (= 0.4.20-2), rust-memchr (= 2.7.1-1), rust-miniz-oxide (= 0.7.1-1), rust-mio (= 0.8.10-1), rust-nix (= 0.26.2-1), rust-normalize-line-endings (= 0.3.0-1), rust-num-traits (= 0.2.15-1), rust-nvml-wrapper (= 0.9.0-1), rust-nvml-wrapper-sys (= 0.7.0-1), rust-object (= 0.32.2-1), rust-once-cell (= 1.19.0-1), rust-option-ext (= 0.2.0-1), rust-parking-lot-core (= 0.9.9-1), rust-parking-lot (= 0.12.1-2build1), rust-predicates-core (= 1.0.6-1), rust-predicates (= 3.0.3-1), rust-predicates-tree (= 1.0.7-1), rust-ratatui (= 0.23.0-4), rust-rayon-core (= 1.12.1-1), rust-rayon (= 1.8.1-1), rust-regex-automata (= 0.4.3-1build2), rust-regex (= 1.10.2-2build2), rust-regex-syntax (= 0.8.2-1), rust-rustc-demangle (= 0.1.21-1), rust-rustix (= 0.38.30-1), rust-scopeguard (= 1.1.0-1), rust-serde (= 1.0.195-1), rust-serde-spanned (= 0.6.4-1), rust-signal-hook (= 0.3.17-1), rust-signal-hook-mio (= 0.2.3-2), rust-signal-hook-registry (= 1.4.0-1), rust-smallvec (= 1.11.2-1), rust-starship-battery (= 0.8.2-1), rust-static-assertions (= 1.1.0-1), rust-strsim (= 0.10.0-1), rust-strum (= 0.25.0-1), rust-sysinfo (= 0.28.4-4), rust-terminal-size (= 0.3.0-2), rust-termtree (= 0.4.1-1), rust-thiserror (= 1.0.50-1), rust-time-core (= 0.1.1-1), rust-time (= 0.3.23-2), rust-toml-datetime (= 0.6.5-1), rust-toml-edit (= 0.21.0-2), rust-typenum (= 1.16.0-2), rust-unicode-segmentation (= 1.10.1-1), rust-unicode-width (= 0.1.11-1), rust-uom (= 0.35.0-1), rust-utf8parse (= 0.2.1-1), rust-wait-timeout (= 0.2.0-1), rust-winnow (= 0.5.15-1), rustc (= 1.75.0+dfsg0ubuntu1-0ubuntu1),
Description-md5: e39e31ca350d6a0cb1ee1479936064f3
"""



def fixture():
    """Fictional reference data; patched only at the reference-loading boundary."""
    artifacts, descriptors = {}, []
    snapshot = "https://fixtures.invalid/ubuntu/20000101T000000Z"
    source = "https://fixtures.invalid/keyring.git"
    masters = [c * 40 for c in "ABC"]
    primary, signing = "D" * 40, "E" * 40

    def artifact(name, raw, origin):
        artifacts[name] = raw
        descriptors.append(dict(id=name, source=origin, sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw)))
        return name

    pins = dict(schema_version=1, lock_sha256=LOCK, ubuntu_snapshot=snapshot,
                ubuntu_anchor="F" * 40, ubuntu_anchor_source="https://fixtures.invalid/anchor",
                indexes={}, tools={}, arch=dict(source_url=source, master_source="https://fixtures.invalid/masters",
                tag="fixture", commit="1" * 40, tag_sha256=hashlib.sha256(b"tag").hexdigest(), tag_bytes=3,
                masters={}, signers=[dict(primary=primary, signing=signing, first_signature=1700, last_signature=1800)]))
    packages, records = [], []
    for name in ("gpgv", "zstd", "makepkg", "runtime-base"):
        payload = ("synthetic-package-" + name).encode()
        filename = "pool/" + name + ".deb"
        artifact("package-" + name, payload, snapshot + "/" + filename)
        records.append("Package: " + name + "\nVersion: 1\nArchitecture: amd64\nFilename: " + filename +
                       "\nSize: " + str(len(payload)) + "\nSHA256: " + hashlib.sha256(payload).hexdigest() + "\n")
        packages.append(dict(name=name, version="1", index="test:main", artifact="package-" + name))
        if name != "runtime-base":
            tool = "vercmp" if name == "makepkg" else name
            pins["tools"][tool] = dict(package=name, version="1", index="test:main", filename=filename,
                package_sha256=hashlib.sha256(payload).hexdigest(), package_bytes=len(payload), path="/usr/bin/" + tool)
    index = lzma.compress("\n".join(records).encode())
    index_hash = hashlib.sha256(index).hexdigest()
    release = ("-----BEGIN PGP SIGNED MESSAGE-----\nHash: SHA512\n\nDate: Thu, 01 Jan 1970 00:20:00 +0000\n"
               "Valid-Until: Thu, 01 Jan 1970 01:23:20 +0000\nSHA256:\n " + index_hash + " " +
               str(len(index)) + " main/binary-amd64/Packages.xz\n-----BEGIN PGP SIGNATURE-----\n\n" +
               "c3ludGhldGljLW5vdC1hLXNpZ25hdHVyZQ==\n-----END PGP SIGNATURE-----\n").encode()
    release_url, index_url = snapshot + "/dists/test/InRelease", snapshot + "/dists/test/main/binary-amd64/Packages.xz"
    artifact("release", release, release_url)
    artifact("index", index, index_url)
    pins["indexes"]["test:main"] = dict(suite="test", component="main", release_url=release_url,
        release_sha256=hashlib.sha256(release).hexdigest(), release_bytes=len(release), index_url=index_url,
        index_path="main/binary-amd64/Packages.xz", index_sha256=index_hash, index_bytes=len(index))
    files = []
    for name in ("gpgv", "zstd", "vercmp", "ld", "libc"):
        role = "tool" if name in ("gpgv", "zstd", "vercmp") else "interpreter" if name == "ld" else "library"
        package = pins["tools"][name]["package"] if role == "tool" else "runtime-base"
        path = "/usr/bin/" + name if role == "tool" else "/lib64/ld.so" if name == "ld" else "/usr/lib/libc.so"
        artifact("file-" + name, ("synthetic-ELF-" + name).encode(), snapshot + "/pool/" + package + ".deb#" + path)
        files.append(dict(id=name, path=path, package=package, role=role, artifact="file-" + name,
                          interpreter="ld" if role == "tool" else None, needed=["libc"] if role == "tool" else []))
    tag_url = source.removesuffix(".git") + "/-/tags/fixture"
    artifact("tag", b"tag", tag_url)
    master_rows, certifications = [], []
    prefix = source.removesuffix(".git") + "/-/raw/" + "1" * 40 + "/keyring/"
    for number, fingerprint in enumerate(masters):
        raw = ("synthetic-master-" + fingerprint).encode()
        name = "master-" + str(number)
        artifact(name, raw, prefix + "main/" + fingerprint + ".asc")
        pins["arch"]["masters"][fingerprint] = dict(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw),
                                                   path="keyring/main/" + fingerprint + ".asc")
        master_rows.append(dict(fingerprint=fingerprint, artifact=name))
        name = "cert-" + str(number)
        artifact(name, b"synthetic-certification", prefix + "packager/cert-" + str(number) + ".asc")
        certifications.append(dict(master=fingerprint, subject=primary, uid="fixture@example.invalid",
            artifact=name, created=1200, expires=5000, revoked=False))
    artifact("binding", b"synthetic-binding", prefix + "packager/binding.asc")
    signer = dict(primary=primary, signing=signing, primary_created=1000, signing_created=1100,
                  primary_expires=5000, signing_expires=5000, first_signature=1700, last_signature=1800,
                  revoked=False, certifications=certifications,
                  binding=dict(primary=primary, signing=signing, artifact="binding", created=1300, expires=5000, revoked=False),
                  lifecycle=dict(status="active", observed_at=1999, revocation_checked_at=1999, source=source))
    manifest = dict(schema_version=1, lock_sha256=LOCK, observed_at=2000, artifacts=descriptors,
        ubuntu=dict(anchor=pins["ubuntu_anchor"], anchor_source=pins["ubuntu_anchor_source"],
                    indexes=[dict(id="test:main", release="release", index="index")], packages=packages,
                    files=files, tools={name: name for name in ("gpgv", "zstd", "vercmp")}),
        arch=dict(source_url=source, master_source=pins["arch"]["master_source"], tag="fixture", commit="1"*40,
                  tag_artifact="tag", masters=master_rows, signers=[signer]))
    return manifest, artifacts, pins


class BootstrapProvenance(unittest.TestCase):
    def setUp(self):
        self.manifest, self.artifacts, self.pins = fixture()

    def module(self):
        path = BASE / "bootstrap_provenance.py"
        self.assertTrue(path.is_file(), "sealed bootstrap provenance checker is missing")
        sys.path.insert(0, str(BASE))
        try:
            spec = importlib.util.spec_from_file_location("sealed_bootstrap_review", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
        finally:
            sys.path.remove(str(BASE))

    def review(self, manifest=None, artifacts=None, now=2000):
        module = self.module()
        with patch.object(module, "load_pins", return_value=copy.deepcopy(self.pins)):
            return module.review(json.dumps(self.manifest if manifest is None else manifest).encode(),
                                 self.artifacts if artifacts is None else artifacts, now_epoch=now)

    def rejected(self, fragment):
        result = self.review()
        self.assertEqual(result["status"], "rejected", result)
        self.assertIn(fragment, result["errors"][0])
        self.assertFalse(result["consistency_checked"])
        self.assertFalse(result["accepted"])
        self.assertFalse(result["execution_authorized"])
        self.assertFalse(result["trust_policy_activation_allowed"])

    def replace_index(self, plain):
        """Rebind fictional metadata receipts so parsing, not hash drift, decides."""
        old = self.artifacts["index"]
        raw = lzma.compress(plain)
        release = self.artifacts["release"].replace(
            hashlib.sha256(old).hexdigest().encode() + b" " + str(len(old)).encode(),
            hashlib.sha256(raw).hexdigest().encode() + b" " + str(len(raw)).encode())
        self.artifacts.update(index=raw, release=release)
        pin = self.pins["indexes"]["test:main"]
        for name, value in (("index", raw), ("release", release)):
            digest = hashlib.sha256(value).hexdigest()
            next(r for r in self.manifest["artifacts"] if r["id"] == name).update(sha256=digest, bytes=len(value))
            pin.update({name + "_sha256": digest, name + "_bytes": len(value)})

    def test_consistent_synthetic_chain_still_has_no_crypto_or_execution_authority(self):
        result = self.review()
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["accepted"])
        self.assertFalse(result["execution_authorized"])
        self.assertFalse(result["trust_policy_activation_allowed"])
        self.assertFalse(result["real_certificate_set_validated"])
        self.assertIn("ubuntu_inrelease_signature_unverified", result["gaps"])
        self.assertIn("arch_certifications_and_bindings_unverified", result["gaps"])
        self.assertIn("tool_package_membership_unverified", result["gaps"])
        self.assertIn("elf_runtime_closure_unverified", result["gaps"])
        self.assertEqual(result, self.review())

    def test_caller_verified_assertions_never_substitute_for_proof(self):
        for target in ("root", "ubuntu", "arch", "binding", "lifecycle"):
            with self.subTest(target=target):
                self.manifest, self.artifacts, self.pins = fixture()
                row = self.manifest if target == "root" else self.manifest[target] if target in ("ubuntu", "arch") else self.manifest["arch"]["signers"][0][target]
                row["verified"] = True
                self.rejected("fields")

    def test_wrong_lock_anchor_snapshot_and_arch_source_identities_are_rejected(self):
        mutations = [lambda m: m.update(lock_sha256="0"*64),
                     lambda m: m["ubuntu"].update(anchor="0"*40),
                     lambda m: m["ubuntu"].update(anchor_source="https://attacker.invalid"),
                     lambda m: m["arch"].update(commit="0"*40),
                     lambda m: m["arch"].update(source_url="https://attacker.invalid")]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                self.manifest, self.artifacts, self.pins = fixture()
                mutate(self.manifest)
                self.rejected("identity")

    def test_pinned_artifact_hash_size_and_source_are_checked_against_bytes(self):
        for field, value in (("sha256", "0"*64), ("bytes", 1), ("source", "https://attacker.invalid")):
            with self.subTest(field=field):
                self.manifest, self.artifacts, self.pins = fixture()
                next(r for r in self.manifest["artifacts"] if r["id"] == "release")[field] = value
                self.rejected("artifact")

    def test_missing_inrelease_and_signature_armour_are_not_admitted(self):
        del self.artifacts["release"]
        self.rejected("artifact")
        self.manifest, self.artifacts, self.pins = fixture()
        self.artifacts["release"] = self.artifacts["release"].split(b"-----BEGIN PGP SIGNATURE-----")[0]
        raw = self.artifacts["release"]
        row = next(r for r in self.manifest["artifacts"] if r["id"] == "release")
        row.update(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
        self.pins["indexes"]["test:main"].update(release_sha256=row["sha256"], release_bytes=len(raw))
        self.rejected("InRelease")

    def test_release_hash_table_must_bind_the_exact_index(self):
        raw = self.artifacts["release"].replace(self.pins["indexes"]["test:main"]["index_sha256"].encode(), b"0"*64)
        self.artifacts["release"] = raw
        row = next(r for r in self.manifest["artifacts"] if r["id"] == "release")
        row["sha256"] = self.pins["indexes"]["test:main"]["release_sha256"] = hashlib.sha256(raw).hexdigest()
        self.rejected("index binding")

    def test_expired_or_future_inrelease_metadata_is_rejected_even_with_matching_hashes(self):
        changes = [(b"Thu, 01 Jan 1970 00:20:00 +0000", b"Thu, 01 Jan 1970 02:00:00 +0000"),
                   (b"Thu, 01 Jan 1970 01:23:20 +0000", b"Thu, 01 Jan 1970 00:30:00 +0000")]
        for old, new in changes:
            with self.subTest(new=new):
                self.manifest, self.artifacts, self.pins = fixture()
                raw = self.artifacts["release"].replace(old, new)
                self.artifacts["release"] = raw
                row = next(r for r in self.manifest["artifacts"] if r["id"] == "release")
                row.update(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
                self.pins["indexes"]["test:main"].update(release_sha256=row["sha256"], release_bytes=len(raw))
                self.rejected("InRelease timestamp")

    def test_correct_master_bytes_cannot_be_relabelled_as_another_source(self):
        row = next(r for r in self.manifest["artifacts"] if r["id"] == "master-0")
        row["source"] = row["source"].rsplit("/", 1)[0] + "/wrong.asc"
        self.rejected("artifact pinned")

    def test_empty_runtime_binary_is_not_a_binary_receipt(self):
        self.artifacts["file-gpgv"] = b""
        next(r for r in self.manifest["artifacts"] if r["id"] == "file-gpgv").update(sha256=hashlib.sha256(b"").hexdigest(), bytes=0)
        self.rejected("runtime empty")

    def test_package_index_and_payload_hash_changes_are_rejected(self):
        for name in ("index", "package-gpgv", "file-gpgv"):
            with self.subTest(name=name):
                self.manifest, self.artifacts, self.pins = fixture()
                self.artifacts[name] += b"changed"
                self.rejected("artifact")

    def test_self_consistent_replaced_payload_still_disagrees_with_index(self):
        raw = b"replaced package"
        self.artifacts["package-gpgv"] = raw
        next(r for r in self.manifest["artifacts"] if r["id"] == "package-gpgv").update(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
        self.rejected("package binding")

    def test_concatenated_xz_metadata_streams_and_padding_preserve_package_records(self):
        module = self.module()
        raw = self.artifacts["index"] + b"\0" * 4 + lzma.compress(b"") + b"\0" * 4
        try:
            records = module.package_records(raw)
        except ValueError as error:
            self.fail("valid concatenated metadata was refused: " + str(error))
        self.assertEqual(set(records), {(name, "1", "amd64") for name in ("gpgv", "zstd", "makepkg", "runtime-base")})

    def test_index_expansion_budget_is_shared_across_all_streams(self):
        module = self.module()
        with patch.object(module, "MAX_INDEX_EXPANSION", 64, create=True):
            with self.assertRaisesRegex(ValueError, "aggregate index expansion budget"):
                module.package_records(lzma.compress(b"x" * 40) + lzma.compress(b"y" * 40))

    def test_trailing_junk_and_misaligned_xz_padding_are_rejected(self):
        module = self.module()
        for suffix in (b"junk", b"\0", b"\0" * 5):
            with self.subTest(suffix=suffix), self.assertRaises(ValueError):
                module.package_records(self.artifacts["index"] + suffix)

    def test_empty_optional_deb822_fields_are_valid_but_identity_fields_must_be_present(self):
        module = self.module()
        raw = lzma.decompress(self.artifacts["index"])
        optional = raw.replace(b"Package: gpgv\n", b"Package: gpgv\nX-Cargo-Built-Using:\n")
        try:
            records = module.package_records(lzma.compress(optional))
        except ValueError as error:
            self.fail("valid optional Deb822 field was refused: " + str(error))
        self.assertIn(("gpgv", "1", "amd64"), records)
        missing_version = raw.replace(b"Version: 1\n", b"Version:\n", 1)
        with self.assertRaisesRegex(ValueError, "identity missing"):
            module.package_records(lzma.compress(missing_version))

    def test_deb822_package_and_lowercase_package_are_duplicate_fields(self):
        raw = lzma.decompress(self.artifacts["index"])
        self.replace_index(raw.replace(b"Package: gpgv\n", b"Package: gpgv\npackage: different\n", 1))
        self.rejected("duplicate")

    def test_deb822_mixed_case_duplicates_include_all_security_relevant_fields(self):
        duplicates = (b"pAcKaGe: different", b"vErSiOn: 2", b"aRcHiTeCtUrE: all",
                      b"fIlEnAmE: pool/other.deb", b"sIzE: 1", b"sHa256: " + b"0" * 64,
                      b"dEpEnDs: other")
        for duplicate in duplicates:
            with self.subTest(duplicate=duplicate):
                self.manifest, self.artifacts, self.pins = fixture()
                raw = lzma.decompress(self.artifacts["index"])
                self.replace_index(raw.replace(b"Package: gpgv\n",
                    b"Package: gpgv\nDepends: runtime-base\n" + duplicate + b"\n", 1))
                self.rejected("duplicate")

    def test_deb822_singleton_continuations_are_explicitly_rejected(self):
        for field in (b"Package", b"Version", b"Architecture", b"Filename", b"Size", b"SHA256", b"Depends"):
            for prefix in (b" ", b"\t"):
                with self.subTest(field=field, prefix=prefix):
                    self.manifest, self.artifacts, self.pins = fixture()
                    raw = lzma.decompress(self.artifacts["index"]).replace(
                        b"Package: gpgv\n", b"Package: gpgv\nDepends: runtime-base\n", 1)
                    declaration = next(line for line in raw.splitlines() if line.startswith(field + b":"))
                    self.replace_index(raw.replace(declaration + b"\n", declaration + b"\n" + prefix + b"extra-content\n", 1))
                    self.rejected("continuation")

    def test_deb822_optional_multiline_fields_are_retained_and_remain_sealed(self):
        module = self.module()
        for field in (b"Description", b"X-Example"):
            with self.subTest(field=field):
                self.manifest, self.artifacts, self.pins = fixture()
                raw = lzma.decompress(self.artifacts["index"])
                self.replace_index(raw.replace(b"Package: gpgv\n",
                    b"Package: gpgv\n" + field + b": synopsis\n continuation\n\tsecond line\n", 1))
                records = module.package_records(self.artifacts["index"])
                self.assertEqual(records["gpgv", "1", "amd64"][field.decode().lower()],
                                 "synopsis\n continuation\n\tsecond line")
                result = self.review()
                self.assertEqual(result["status"], "blocked", result)
                self.assertTrue(result["consistency_checked"])
                for flag in ("accepted", "execution_authorized", "trust_policy_activation_allowed"):
                    self.assertFalse(result[flag])

    def test_real_btm_paragraph_preserves_cargo_continuation_and_package_identity(self):
        self.assertEqual(hashlib.sha256(BTM_PARAGRAPH).hexdigest(),
                         "cc5e0f3e743b85c3b3cb47dcc276f142b156c16b4dd9f35be19d78f09ec7e7d0")
        records = self.module().package_records(lzma.compress(BTM_PARAGRAPH))
        self.assertEqual(set(records), {("btm", "0.9.6-4", "amd64")})
        record = records["btm", "0.9.6-4", "amd64"]
        self.assertEqual(record["Filename"], "pool/universe/b/btm/btm_0.9.6-4_amd64.deb")
        self.assertEqual(record["SHA256"], "62b3c95436097e45edeebd72396831938df40de055d2e0dd9fcf276639314799")
        self.assertEqual(record["Size"], "1607224")
        self.assertEqual(record["Depends"], "libc6 (>= 2.38), libgcc-s1 (>= 4.2)")
        cargo = BTM_PARAGRAPH.split(b"X-Cargo-Built-Using:", 1)[1].split(b"\nDescription-md5:", 1)[0]
        self.assertEqual(record["x-cargo-built-using"], cargo.decode())
        self.assertEqual(record["description-md5"], "e39e31ca350d6a0cb1ee1479936064f3")

    def test_indented_forged_identity_fields_stay_optional_content(self):
        module = self.module()
        forged = (b" Package: attacker\n\tVersion: 2\n Architecture: all\n Filename: pool/evil.deb\n"
                  b" SHA256: " + b"0" * 64 + b"\n Size: 1\n Depends: attacker\n")
        raw = lzma.decompress(self.artifacts["index"])
        self.replace_index(raw.replace(b"Package: gpgv\n", b"Package: gpgv\nX-Example:\n" + forged, 1))
        records = module.package_records(self.artifacts["index"])
        record = records["gpgv", "1", "amd64"]
        self.assertEqual(record["Package"], "gpgv")
        self.assertEqual(record["Version"], "1")
        self.assertEqual(record["Architecture"], "amd64")
        self.assertEqual(record["Filename"], "pool/gpgv.deb")
        self.assertEqual(record["SHA256"], hashlib.sha256(b"synthetic-package-gpgv").hexdigest())
        self.assertEqual(record["Size"], "22")
        self.assertNotIn("Depends", record)
        self.assertEqual(record["x-example"], "\n" + forged.decode().rstrip("\n"))
        result = self.review()
        self.assertEqual(result["status"], "blocked", result)
        self.assertTrue(result["consistency_checked"])
        for flag in ("accepted", "execution_authorized", "trust_policy_activation_allowed"):
            self.assertFalse(result[flag])

    def test_optional_continuations_cannot_hide_duplicate_fields(self):
        for duplicate in (b"x-eXaMpLe: replacement", b"pAcKaGe: attacker"):
            with self.subTest(duplicate=duplicate):
                self.manifest, self.artifacts, self.pins = fixture()
                raw = lzma.decompress(self.artifacts["index"])
                self.replace_index(raw.replace(b"Package: gpgv\n",
                    b"Package: gpgv\nX-Example: original\n continuation\n" + duplicate + b"\n", 1))
                self.rejected("duplicate")

    def test_optional_whitespace_only_or_malformed_continuations_are_rejected(self):
        for suffix in (b" \n", b"\t\n", b" \t \n", b" continuation\nnot-a-field\n",
                       b" continuation\nBad Field: value\n"):
            with self.subTest(suffix=suffix):
                self.manifest, self.artifacts, self.pins = fixture()
                raw = lzma.decompress(self.artifacts["index"])
                self.replace_index(raw.replace(b"Package: gpgv\n", b"Package: gpgv\nX-Example:\n" + suffix, 1))
                self.rejected("package index")

    def test_optional_continuations_preserve_index_resource_budgets(self):
        module = self.module()
        raw = lzma.compress(BTM_PARAGRAPH)
        with patch.object(module, "MAX_ARTIFACT", len(raw)):
            self.assertIn(("btm", "0.9.6-4", "amd64"), module.package_records(raw))
        with patch.object(module, "MAX_ARTIFACT", len(raw) - 1):
            with self.assertRaisesRegex(ValueError, "package index input budget"):
                module.package_records(raw)
        with patch.object(module, "MAX_INDEX_EXPANSION", len(BTM_PARAGRAPH)):
            self.assertIn(("btm", "0.9.6-4", "amd64"), module.package_records(raw))
            with self.assertRaisesRegex(ValueError, "aggregate index expansion budget"):
                module.package_records(raw + lzma.compress(b"x"))
        with patch.object(module, "MAX_INDEX_EXPANSION", len(BTM_PARAGRAPH) - 1):
            with self.assertRaisesRegex(ValueError, "aggregate index expansion budget"):
                module.package_records(raw)
        with patch.object(module, "MAX_PACKAGE_RECORDS", 1):
            self.assertIn(("btm", "0.9.6-4", "amd64"), module.package_records(raw))
            with self.assertRaisesRegex(ValueError, "package index record budget"):
                module.package_records(lzma.compress(BTM_PARAGRAPH + b"\n" + lzma.decompress(self.artifacts["index"])))
        with self.assertRaisesRegex(ValueError, "stream identity/budget"):
            module.package_records(raw * 17)

    def test_optional_continuation_control_characters_are_rejected(self):
        for control in ("\x00", "\v", "\f", "\r", "\x1c", "\x1d", "\x1e", "\x7f", "\x85", "\u2028", "\u2029"):
            with self.subTest(control=repr(control)):
                self.manifest, self.artifacts, self.pins = fixture()
                raw = lzma.decompress(self.artifacts["index"])
                self.replace_index(raw.replace(b"Package: gpgv\n",
                    b"Package: gpgv\nX-Example: value\n continuation" + control.encode() + b"suffix\n", 1))
                self.rejected("control or line separator")

    def test_deb822_orphan_and_whitespace_only_continuations_are_rejected(self):
        for prefix in (b" orphan\n", b"\torphan\n", b" \n\n", b"\t\n\n"):
            with self.subTest(prefix=prefix):
                self.manifest, self.artifacts, self.pins = fixture()
                self.replace_index(prefix + lzma.decompress(self.artifacts["index"]))
                self.rejected("continuation")

    def test_deb822_malformed_declarations_hashes_sizes_and_identities_are_rejected(self):
        raw = lzma.decompress(self.artifacts["index"])
        size = next(line for line in raw.splitlines() if line.startswith(b"Size:"))
        digest = next(line for line in raw.splitlines() if line.startswith(b"SHA256:"))
        mutations = ((b"Package: gpgv", b"Package gpgv"), (b"Package: gpgv", b"Package : gpgv"),
                     (b"Package: gpgv", b"Package@: gpgv"), (b"Package: gpgv", b"Package:"),
                     (b"Version: 1", b"Version:"), (b"Architecture: amd64", b"Architecture:"),
                     (size, b"Size: -1"), (size, b"Size: 1.5"), (size, b"Size:"))
        mutations += tuple((digest, b"SHA256: " + value) for value in (b"", b"g" * 64, b"0" * 63, b"0" * 65))
        for old, new in mutations:
            with self.subTest(new=new):
                self.manifest, self.artifacts, self.pins = fixture()
                self.assertIn(old, raw)
                self.replace_index(raw.replace(old, new, 1))
                result = self.review()
                self.assertEqual(result["status"], "rejected", result)
                self.assertTrue(result["errors"])
                for flag in ("consistency_checked", "accepted", "execution_authorized", "trust_policy_activation_allowed"):
                    self.assertFalse(result[flag])

    def test_deb822_duplicate_package_records_are_rejected(self):
        raw = lzma.decompress(self.artifacts["index"])
        self.replace_index(raw + b"\n" + raw.split(b"\n\n", 1)[0] + b"\n")
        self.rejected("duplicate package index identity")

    def test_deb822_unsupported_line_separators_and_controls_are_rejected(self):
        for separator in ("\v", "\f", "\x1c", "\x1d", "\x1e", "\r", "\x85", "\u2028", "\u2029", "\x00", "\x7f"):
            for location in ("identity", "optional"):
                with self.subTest(separator=repr(separator), location=location):
                    self.manifest, self.artifacts, self.pins = fixture()
                    raw = lzma.decompress(self.artifacts["index"])
                    if location == "identity":
                        raw = raw.replace(b"Package: gpgv\nVersion:",
                            b"Package: gpgv" + separator.encode() + b"Version:", 1)
                    else:
                        raw = raw.replace(b"Package: gpgv\n", b"Package: gpgv\nX-Example: value" +
                            separator.encode() + b"X-Other: value\n", 1)
                    self.replace_index(raw)
                    self.rejected("package index")

    def test_deb822_ordinary_case_insensitive_fields_remain_consistent_but_sealed(self):
        raw = lzma.decompress(self.artifacts["index"])
        lower = b"\n".join(line.partition(b":")[0].lower() + b":" + line.partition(b":")[2]
                            if b":" in line else line for line in raw.split(b"\n"))
        self.replace_index(lower)
        result = self.review()
        self.assertEqual(result["status"], "blocked", result)
        self.assertTrue(result["consistency_checked"])
        self.assertEqual(result["counts"]["packages"], 4)
        for flag in ("accepted", "execution_authorized", "trust_policy_activation_allowed", "real_certificate_set_validated"):
            self.assertFalse(result[flag])

    def test_missing_loader_library_or_owning_package_is_rejected(self):
        for target in ("ld", "libc", "runtime-base"):
            with self.subTest(target=target):
                self.manifest, self.artifacts, self.pins = fixture()
                if target == "runtime-base":
                    self.manifest["ubuntu"]["packages"] = [p for p in self.manifest["ubuntu"]["packages"] if p["name"] != target]
                else:
                    self.manifest["ubuntu"]["files"] = [p for p in self.manifest["ubuntu"]["files"] if p["id"] != target]
                self.rejected("runtime")

    def test_incomplete_or_duplicate_declared_dependencies_are_rejected(self):
        self.manifest["ubuntu"]["files"][0]["needed"] = ["not-present"]
        self.rejected("runtime")
        self.manifest["ubuntu"]["files"][0]["needed"] = ["libc", "libc"]
        self.rejected("duplicate")

    def test_unknown_expired_and_revoked_signers_are_rejected(self):
        for field, value in (("primary", "0"*40), ("signing", "0"*40), ("revoked", True),
                             ("primary_expires", 1600), ("signing_expires", 1600)):
            with self.subTest(field=field):
                self.manifest, self.artifacts, self.pins = fixture()
                self.manifest["arch"]["signers"][0][field] = value
                self.rejected("signer")

    def test_certifications_need_three_distinct_masters_on_the_same_uid(self):
        signer = self.manifest["arch"]["signers"][0]
        signer["certifications"].pop()
        self.rejected("certification")
        self.manifest, self.artifacts, self.pins = fixture()
        self.manifest["arch"]["signers"][0]["certifications"][-1]["uid"] = "different@example.invalid"
        self.rejected("certification")

    def test_invalid_expired_revoked_and_duplicate_certifications_are_rejected(self):
        for field, value in (("master", "0"*40), ("subject", "0"*40), ("expires", 1600), ("revoked", True), ("created", 2500)):
            with self.subTest(field=field):
                self.manifest, self.artifacts, self.pins = fixture()
                self.manifest["arch"]["signers"][0]["certifications"][0][field] = value
                self.rejected("certification")
        self.manifest, self.artifacts, self.pins = fixture()
        certs = self.manifest["arch"]["signers"][0]["certifications"]
        certs.append(copy.deepcopy(certs[0]))
        self.rejected("duplicate")

    def test_missing_conflicting_or_revoked_subkey_binding_is_rejected(self):
        for change in (None, dict(primary="0"*40), dict(signing="0"*40), dict(revoked=True), dict(expires=1600), dict(created=2500)):
            with self.subTest(change=change):
                self.manifest, self.artifacts, self.pins = fixture()
                signer = self.manifest["arch"]["signers"][0]
                if change is None: signer["binding"] = None
                else: signer["binding"].update(change)
                self.rejected("binding")

    def test_empty_certification_and_binding_bytes_are_missing_evidence(self):
        for name in ("cert-0", "binding"):
            with self.subTest(name=name):
                self.manifest, self.artifacts, self.pins = fixture()
                self.artifacts[name] = b""
                next(r for r in self.manifest["artifacts"] if r["id"] == name).update(sha256=hashlib.sha256(b"").hexdigest(), bytes=0)
                self.rejected("empty key evidence")

    def test_duplicate_signers_and_artifacts_are_rejected(self):
        self.manifest["arch"]["signers"].append(copy.deepcopy(self.manifest["arch"]["signers"][0]))
        self.rejected("duplicate")
        self.manifest, self.artifacts, self.pins = fixture()
        self.manifest["artifacts"].append(copy.deepcopy(self.manifest["artifacts"][0]))
        self.rejected("duplicate")

    def test_missing_unknown_stale_and_conflicting_lifecycle_evidence_is_rejected(self):
        for change in (dict(status="unknown"), dict(status="revoked"), dict(observed_at=2500),
                       dict(revocation_checked_at=2500), dict(source="https://attacker.invalid")):
            with self.subTest(change=change):
                self.manifest, self.artifacts, self.pins = fixture()
                self.manifest["arch"]["signers"][0]["lifecycle"].update(change)
                self.rejected("lifecycle")
        self.manifest, self.artifacts, self.pins = fixture()
        del self.manifest["arch"]["signers"][0]["lifecycle"]["revocation_checked_at"]
        self.rejected("fields")
        self.manifest, self.artifacts, self.pins = fixture()
        result = self.review(now=100000)
        self.assertEqual(result["status"], "rejected")
        self.assertIn("stale", result["errors"][0])

    def test_conflicting_key_and_signature_timestamps_are_rejected(self):
        for field, value in (("primary_created", 1750), ("signing_created", 1750),
                             ("first_signature", 1801), ("last_signature", 2500)):
            with self.subTest(field=field):
                self.manifest, self.artifacts, self.pins = fixture()
                self.manifest["arch"]["signers"][0][field] = value
                self.rejected("signer")

    def test_lifecycle_review_cannot_precede_its_revocation_check(self):
        self.manifest["arch"]["signers"][0]["lifecycle"].update(observed_at=1900, revocation_checked_at=1999)
        self.rejected("lifecycle")

    def test_review_receipt_cannot_activate_existing_s4_policy(self):
        before = (BASE / "trust-policy.json").read_bytes()
        result = self.review()
        self.manifest["activate_trust_policy"] = result
        self.rejected("fields")
        self.assertEqual((BASE / "trust-policy.json").read_bytes(), before)
        self.assertEqual(json.loads(before)["status"], "pending-review")

    def test_cli_refuses_activation_without_reading_the_supplied_path(self):
        module = self.module()
        result = subprocess.run([sys.executable, "-B", str(Path(module.__file__)), "--activate", "/missing-policy"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 78)
        receipt = json.loads(result.stdout)
        self.assertFalse(receipt["execution_authorized"])
        self.assertIn("sealed", receipt["errors"][0])

    def test_bounded_json_rejects_duplicate_keys_nonfinite_numbers_and_extra_artifacts(self):
        module = self.module()
        for raw in (b'{"schema_version":1,"schema_version":1}', b'{"x":NaN}', b' ' * (512*1024+1)):
            with self.subTest(raw=raw[:30]):
                result = module.review(raw, {}, now_epoch=2000)
                self.assertEqual(result["status"], "rejected")
                self.assertFalse(result["execution_authorized"])
                self.assertLess(len(module.encode_result(result)), 65536)
        self.artifacts["extra"] = b"unrequested"
        self.rejected("artifact")
