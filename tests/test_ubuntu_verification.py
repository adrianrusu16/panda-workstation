"""Protocol doubles only: synthetic successes authenticate no real certificate set."""
import copy
import hashlib
import importlib
import json
import lzma
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch
from test_ubuntu_artifacts import synthetic_deb, synthetic_elf

S4 = Path(__file__).resolve().parent / "native/external_vm/s4"
FPR = "F6ECB3762474EDA9D21B7022871920D1991BC93C"
NOW = 1793292751


def runner_context():
    return dict(GITHUB_ACTIONS="true", RUNNER_ENVIRONMENT="github-hosted", RUNNER_OS="Linux",
                RUNNER_ARCH="X64", ImageOS="ubuntu24", ImageVersion="20261026.354.1",
                GITHUB_REPOSITORY="adrianrusu16/panda-workstation", GITHUB_REF="refs/heads/main",
                GITHUB_EVENT_NAME="workflow_dispatch", GITHUB_SHA="a"*40, REVIEWED_SOURCE_SHA="a"*40,
                GITHUB_RUN_ID="123", GITHUB_RUN_ATTEMPT="1", GITHUB_JOB="verify", RUNNER_NAME="Hosted Agent")


def status(fpr=FPR):
    return ("[GNUPG:] NEWSIG\n[GNUPG:] KEY_CONSIDERED "+fpr+" 0\n"
            "[GNUPG:] SIG_ID aWQ= 2026-10-29 1793290000\n"
            "[GNUPG:] GOODSIG "+fpr[-16:]+" Ubuntu Archive Automatic Signing Key\n"
            "[GNUPG:] VALIDSIG "+fpr+" 2026-10-29 1793290000 0 4 0 1 10 01 "+fpr+"\n").encode()


def protocol_fixture():
    """Fictional package/index/key bytes plus a verifier double, never real crypto."""
    modulus = (1 << 4095) + 1
    key = b"\x04" + (1700000000).to_bytes(4, "big") + b"\x01\x10\x00" + modulus.to_bytes(512, "big") + b"\x00\x11\x01\x00\x01"
    keyring = b"\xc6\xff" + len(key).to_bytes(4, "big") + key
    fpr = hashlib.sha1(b"\x99"+len(key).to_bytes(2, "big")+key).hexdigest().upper()
    pins = dict(schema_version=1, classification="synthetic test references", image_version="20261026.354.1",
                anchor=fpr, anchor_sources=["https://fixtures.invalid/anchor"],
                keyring_sha256=hashlib.sha256(keyring).hexdigest(), image_reference={}, tools={}, packages={}, files={}, links={})
    bootstrap = dict(lock_sha256="f4034660aa04de28123ccaf80fd6d12d2d7eb9c8f2d29e5043f1f4511fe16618",
                     ubuntu_snapshot="https://fixtures.invalid/ubuntu/20261029T000000Z", ubuntu_anchor=fpr,
                     ubuntu_anchor_source="https://fixtures.invalid/anchor", indexes={}, tools={}, arch={})
    blobs, records = {}, []
    paths = ["/usr/bin/"+name for name in ("gpgv", "zstd", "vercmp")]
    loader = "/usr/lib/x86_64-linux-gnu/ld.so"
    library_names = ["lib"+str(i)+".so" for i in range(9)]
    owners = ("gpgv", "zstd", "makepkg", "libc6", "base-files", "libassuan0", "libbz2-1.0",
              "libgcrypt20", "libgpg-error0", "libnpth0t64", "zlib1g", "liblzma5", "liblz4-1")
    for i, path in enumerate(paths+[loader]+["/usr/lib/x86_64-linux-gnu/"+name for name in library_names]):
        package = owners[i]
        needed = library_names if i == 0 else []
        interp = "/lib64/ld.so" if i < 3 else None
        raw = synthetic_elf(needed, interp, Path(path).name if i >= 3 else None)
        links = {"lib": "usr/lib", "lib64": "usr/lib/x86_64-linux-gnu"} if package == "base-files" else {}
        payload = synthetic_deb(package, {path.lstrip("/"): raw}, links)
        filename = "pool/"+package+".deb"
        row = dict(package=package, version="1", architecture="amd64", filename=filename,
                   sha256=hashlib.sha256(payload).hexdigest(), size=str(len(payload)), index="noble:main")
        pins["packages"][package] = row
        pins["files"][path] = dict(package=package, sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw),
                                   needed=needed, interpreter=interp)
        blobs["package-"+package] = payload
        records.append("\n".join(key+": "+row[key.lower()] for key in ("Package", "Version", "Architecture", "Filename", "SHA256", "Size")))
        if i < 3:
            name = "vercmp" if package == "makepkg" else package
            pins["tools"][name] = path
            bootstrap["tools"][name] = dict(package=package, version="1", index="noble:main", filename=filename,
                package_sha256=row["sha256"], package_bytes=int(row["size"]), path=path)
    pins["links"] = {"/lib": dict(kind="symlink", target="usr/lib", package="base-files"),
                     "/lib64": dict(kind="symlink", target="usr/lib/x86_64-linux-gnu", package="base-files")}
    plain = ("\n\n".join(records)+"\n").encode()
    index = lzma.compress(plain)
    bodies = {}
    for suite in ("noble", "noble-security", "noble-updates"):
        body = ("Origin: Ubuntu\nSuite: "+suite+"\nCodename: noble\nDate: Thu, 29 Oct 2026 00:00:00 UTC\n"
                "Architectures: amd64\nComponents: main universe\nSHA256:\n"+
                "".join(" "+hashlib.sha256(content).hexdigest()+" "+str(len(content))+" "+component+"/binary-amd64/Packages"+suffix+"\n"
                        for component in (("main", "universe") if suite == "noble" else ("main",))
                        for suffix, content in ((".xz", index), ("", plain)))).encode()
        release = b"-----BEGIN PGP SIGNED MESSAGE-----\nHash: SHA512\n\n"+body+b"-----BEGIN PGP SIGNATURE-----\n\nsynthetic-not-a-signature\n-----END PGP SIGNATURE-----\n"
        blobs["release-"+suite] = release; bodies[release] = body
        for component in (("main", "universe") if suite == "noble" else ("main",)):
            identity = suite+":"+component
            bootstrap["indexes"][identity] = dict(suite=suite, component=component,
                release_url=bootstrap["ubuntu_snapshot"]+"/dists/"+suite+"/InRelease",
                release_sha256=hashlib.sha256(release).hexdigest(), release_bytes=len(release),
                index_url=bootstrap["ubuntu_snapshot"]+"/dists/"+suite+"/"+component+"/binary-amd64/Packages.xz",
                index_sha256=hashlib.sha256(index).hexdigest(), index_bytes=len(index), index_path=component+"/binary-amd64/Packages.xz")
            blobs["index-"+suite+"-"+component] = index
    def verifier(raw, ring):
        if not ring:
            failure = ("[GNUPG:] NEWSIG\n[GNUPG:] ERRSIG "+fpr[-16:]+" 1 10 01 1793290000 9 "+fpr+"\n[GNUPG:] NO_PUBKEY "+fpr[-16:]+"\n").encode()
            return 2, failure, b""
        if raw not in bodies:
            return 1, ("[GNUPG:] NEWSIG\n[GNUPG:] BADSIG "+fpr[-16:]+" name\n").encode(), b""
        return 0, status(fpr), bodies[raw]
    files = {}
    for path, ref in pins["files"].items():
        if path == "/usr/bin/vercmp": continue
        files[path] = dict(sha256=ref["sha256"], bytes=ref["bytes"], mode=0o755, uid=0,
            package=ref["package"], elf=dict(machine=62, bits=64, interpreter=ref["interpreter"],
            needed=ref["needed"], soname=Path(path).name if path not in paths else None,
            required_versions={}, provided_versions=[], build_ids=[]),
            interpreter=loader if ref["interpreter"] else None,
            needed={name: "/usr/lib/x86_64-linux-gnu/"+name for name in ref["needed"]})
    files["/usr/bin/python3.12"] = dict(sha256="a"*64, bytes=100, mode=0o755, uid=0,
        package="python3.12-minimal", elf=dict(machine=62, bits=64, interpreter=None, needed=[], soname=None,
        required_versions={}, provided_versions=[], build_ids=[]),
        interpreter=None, needed={})
    toolchain = dict(tools={"gpgv": "/usr/bin/gpgv", "zstd": "/usr/bin/zstd", "python": "/usr/bin/python3.12"},
        extensions=[], files=files, source_hashes={name: "b"*64 for name in
            ("ubuntu_bootstrap_runner.py", "ubuntu_verification.py", "ubuntu_artifacts.py", "ubuntu_packets.py", "ubuntu-verification.pins.json",
             "bootstrap_provenance.py", "bootstrap-provenance.pins.json", "common.py")},
        keyring=dict(path="/usr/share/keyrings/ubuntu-archive-keyring.gpg", mode=0o644, uid=0,
                     bytes=len(keyring), sha256=pins["keyring_sha256"], package="ubuntu-keyring"),
        packages={**{row["package"]: dict(version="1", architecture="amd64") for row in files.values()},
                  "python3.12-minimal": dict(version="3.12-synthetic", architecture="amd64"),
                  "ubuntu-keyring": dict(version="2023.11.28.1", architecture="all")},
        loader=dict(files=[dict(path=path, present=path!="/etc/ld.so.preload", bytes=100 if path!="/etc/ld.so.preload" else None,
                               sha256="c"*64 if path!="/etc/ld.so.preload" else None) for path in
                           ("/etc/ld.so.preload", "/etc/ld.so.cache", "/etc/ld.so.conf", "/etc/ssl/certs/ca-certificates.crt")],
                    preload_absent_or_empty=True, hwcaps_variants=[], actual_mappings_verified=False,
                    cache_interpretation="delegated host assumption"))
    return pins, bootstrap, blobs, keyring, verifier, toolchain


class UbuntuVerification(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(S4)); self.addCleanup(sys.path.remove, str(S4))
        self.assertTrue((S4/"ubuntu_verification.py").is_file(), "Ubuntu verification protocol missing")
        self.api = importlib.import_module("ubuntu_verification")

    def test_runner_records_actual_identity_without_hardware_attestation(self):
        result = self.api.runner_identity(runner_context(), b"ID=ubuntu\nVERSION_ID=24.04\n")
        self.assertEqual(result["image_version"], "20261026.354.1")
        self.assertEqual(result["job"]["run_id"], "123")
        self.assertEqual(result["job"]["runner_name"], "Hosted Agent")
        self.assertFalse(result["hardware_attested"])

    def test_image_identity_missing_source_and_host_assumptions_fail_closed(self):
        for key, value in (("ImageVersion", "20261027.1.0"), ("ImageVersion", ""),
                           ("RUNNER_ENVIRONMENT", "self-hosted"), ("RUNNER_ARCH", "ARM64"),
                           ("GITHUB_ACTIONS", "false"), ("GITHUB_REF", "refs/heads/feature"),
                           ("REVIEWED_SOURCE_SHA", "b"*40), ("GITHUB_RUN_ID", ""),
                           ("GITHUB_EVENT_NAME", "push"), ("LD_PRELOAD", "/tmp/evil.so"),
                           ("PYTHONPATH", "/tmp")):
            with self.subTest(key=key):
                context = runner_context(); context[key] = value
                with self.assertRaises(ValueError): self.api.runner_identity(context, b"ID=ubuntu\nVERSION_ID=24.04\n")
        with self.assertRaises(ValueError): self.api.runner_identity(runner_context(), b"ID=cachyos\nVERSION_ID=24.04\n")

    def test_full_signer_identity_algorithms_and_expiration_are_checked(self):
        value = self.api.signature_status(0, status(), FPR, NOW)
        self.assertEqual(value["fingerprint"], FPR)
        self.assertEqual(value["primary_fingerprint"], FPR)
        self.assertEqual(value["hash_algorithm"], "SHA512")
        self.assertEqual(value["status_sha256"], hashlib.sha256(status()).hexdigest())
        changes = [(b" 1 10 01 ", b" 1 2 01 "), (b" 1 10 01 ", b" 1 10 00 "),
                   (b"1793290000 0 4", b"1793290000 1793290001 4"),
                   (FPR.encode()+b"\n", b"B"*40+b"\n"),
                   (b"1793290000", b"1993290000")]
        for old, new in changes:
            with self.subTest(new=new), self.assertRaises(ValueError):
                self.api.signature_status(0, status().replace(old, new), FPR, NOW)
        with self.assertRaises(ValueError): self.api.signature_status(0, status("B"*40), FPR, NOW)

    def test_bad_expired_revoked_unknown_and_incomplete_signature_status_reject(self):
        for failure in (b"BADSIG", b"EXPSIG", b"EXPKEYSIG", b"REVKEYSIG", b"ERRSIG", b"NO_PUBKEY", b"KEYREVOKED", b"UNKNOWN"):
            with self.subTest(failure=failure), self.assertRaises(ValueError):
                self.api.signature_status(0, status()+b"[GNUPG:] "+failure+b" data\n", FPR, NOW)
        for value in (status().replace(b"[GNUPG:] VALIDSIG", b"not-status VALIDSIG"),
                      b"[GNUPG:] GOODSIG "+FPR[-16:].encode()+b" name\n", status()+status(),
                      status().replace(b"[GNUPG:] NEWSIG\n", b""), status()+b"x"*17000,
                      status().replace(b" name", b"\r name")):
            if value == status(): continue
            with self.subTest(size=len(value)), self.assertRaises(ValueError):
                self.api.signature_status(0, value, FPR, NOW)
        with self.assertRaises(ValueError): self.api.signature_status(1, status(), FPR, NOW)

    def test_negative_probes_require_actual_signature_failure_not_missing_evidence(self):
        bad = ("[GNUPG:] NEWSIG\n[GNUPG:] BADSIG "+FPR[-16:]+" name\n").encode()
        missing = ("[GNUPG:] NEWSIG\n[GNUPG:] ERRSIG "+FPR[-16:]+" 1 10 01 1793290000 9 "+FPR+
                   "\n[GNUPG:] NO_PUBKEY "+FPR[-16:]+"\n").encode()
        self.api.negative_status(1, bad, "altered-content", FPR)
        self.api.negative_status(2, missing, "empty-keyring", FPR)
        for code, raw, case in ((0, bad, "altered-content"), (1, b"", "altered-content"),
                                (2, b"missing executable", "empty-keyring"), (1, status(), "altered-content")):
            with self.subTest(case=case), self.assertRaises(ValueError): self.api.negative_status(code, raw, case, FPR)

    def test_loader_preload_missing_inventory_and_hwcaps_fail_closed(self):
        files = {"/etc/ld.so.preload": None, "/etc/ld.so.cache": b"cache",
                 "/etc/ld.so.conf": b"include /etc/ld.so.conf.d/*.conf\n",
                 "/etc/ssl/certs/ca-certificates.crt": b"certificates"}
        value = self.api.loader_configuration(files, [])
        self.assertFalse(value["actual_mappings_verified"])
        for mutate in (lambda d: d.update({"/etc/ld.so.preload": b"evil.so"}),
                       lambda d: d.pop("/etc/ld.so.cache"),
                       lambda d: d.update({"/etc/ld.so.cache": None})):
            changed = copy.deepcopy(files); mutate(changed)
            with self.assertRaises(ValueError): self.api.loader_configuration(changed, [])
        with self.assertRaises(ValueError): self.api.loader_configuration(files, ["x86-64-v3/libc.so.6"])

    def test_authenticated_release_parser_retains_missing_valid_until_as_unresolved(self):
        body = ("Origin: Ubuntu\nSuite: noble\nCodename: noble\nDate: Thu, 29 Oct 2026 00:00:00 UTC\n"
                "Architectures: amd64\nComponents: main universe\nSHA256:\n "+"a"*64+" 12 main/binary-amd64/Packages.xz\n").encode()
        hashes, metadata = self.api.release_content(body, "noble", NOW)
        self.assertEqual(hashes["main/binary-amd64/Packages.xz"], ("a"*64, 12))
        self.assertIsNone(metadata["valid_until"])
        self.assertFalse(metadata["freshness_policy_established"])
        for value in (body.replace(b"Suite: noble", b"Suite: wrong"), body+b"date: duplicate\n",
                      body.replace(b" 12 main", b" 12 ../main"), body.replace(b"SHA256:", b"SHA256:\r")):
            with self.subTest(sha=hashlib.sha256(value).hexdigest()), self.assertRaises(ValueError):
                self.api.release_content(value, "noble", NOW)

    def test_checked_in_references_are_observations_and_match_frozen_bootstrap_identity(self):
        pins, bootstrap = self.api.load_references()
        self.assertEqual(pins["image_version"], "20261026.354.1")
        self.assertEqual(pins["anchor"], bootstrap["ubuntu_anchor"])
        self.assertEqual(len(pins["files"]), 13)
        self.assertEqual(len(pins["packages"]), 13)
        self.assertIn("not a trust policy", pins["classification"])

    def test_keyring_fingerprint_algorithm_packet_bounds_and_revocation_observations(self):
        pins, _, _, ring, _, _ = protocol_fixture()
        value = self.api.keyring_anchor(ring, pins["anchor"], pins["keyring_sha256"], NOW)
        self.assertEqual(value["rsa_bits"], 4096)
        self.assertFalse(value["key_lifecycle_verified"])
        for raw, fingerprint, digest in ((ring, FPR, pins["keyring_sha256"]),
                                         (ring, pins["anchor"], "0"*64),
                                         (ring[:-1], pins["anchor"], hashlib.sha256(ring[:-1]).hexdigest()),
                                         (ring+b"\xc2\x02\x04\x20", pins["anchor"], hashlib.sha256(ring+b"\xc2\x02\x04\x20").hexdigest())):
            with self.subTest(size=len(raw)), self.assertRaises(ValueError):
                self.api.keyring_anchor(raw, fingerprint, digest, NOW)

    def test_canonical_receipt_budget_and_no_authority_are_unconditional(self):
        value = {"z": 1, "a": [2, 3]}
        self.assertEqual(self.api.canonical(value), b'{"a":[2,3],"z":1}\n')
        with self.assertRaises(ValueError): self.api.canonical({"bad": float("nan")})
        with self.assertRaises(ValueError): self.api.canonical({"huge": "x"*200000})
        with self.assertRaises(ValueError): self.api.validate_receipts(b'{"verified":true}')

    def synthetic_run(self, mutate=None):
        pins, bootstrap, blobs, keyring, verifier, toolchain = protocol_fixture()
        if mutate: mutate(blobs, toolchain)
        def acquire(identity, url, size): return blobs[identity]
        with patch.object(self.api, "load_references", return_value=(pins, bootstrap)), \
             patch.object(self.api.consistency, "load_pins", return_value=bootstrap):
            return self.api.verify_ubuntu(runner_context(), b"ID=ubuntu\nVERSION_ID=24.04\n", NOW,
                                          keyring, toolchain, acquire, verifier, None)

    def validate_bundle(self, bundle):
        pins, bootstrap, *_ = protocol_fixture()
        with patch.object(self.api, "load_references", return_value=(pins, bootstrap)):
            return self.api.validate_receipts(self.api.canonical(bundle, self.api.MAX_RECEIPTS))

    def test_synthetic_full_chain_produces_deterministic_non_authorizing_receipts(self):
        bundle = self.synthetic_run()
        self.assertEqual(bundle, self.synthetic_run())
        check = self.validate_bundle(bundle)
        self.assertTrue(check["consistency_checked"])
        for key in ("accepted", "execution_authorized", "trust_policy_activation_allowed"):
            self.assertFalse(check[key])
            self.assertFalse(bundle["receipts"]["authorization-state"]["data"][key])
        signatures = bundle["receipts"]["inrelease-signatures"]["data"]
        self.assertEqual(set(signatures), {"noble", "noble-security", "noble-updates"})
        self.assertEqual(len(bundle["receipts"]["elf-closure"]["data"]["files"]), 13)
        self.assertEqual(bundle["receipts"]["consistency-review"]["data"]["errors"], ["arch fields"])

    def test_job_identity_and_assessment_context_do_not_change_content_receipts(self):
        first = self.synthetic_run()
        changed = runner_context(); changed["GITHUB_RUN_ID"] = "456"; changed["RUNNER_NAME"] = "Other Hosted Agent"
        pins, bootstrap, blobs, ring, verifier, toolchain = protocol_fixture()
        with patch.object(self.api, "load_references", return_value=(pins, bootstrap)), \
             patch.object(self.api.consistency, "load_pins", return_value=bootstrap):
            second = self.api.verify_ubuntu(changed, b"ID=ubuntu\nVERSION_ID=24.04\n", NOW+1,
                ring, toolchain, lambda name,url,size: blobs[name], verifier, None)
        self.assertEqual(first, second)

    def test_full_chain_rejects_package_hash_missing_dependency_and_environment_evidence(self):
        for mutate in (lambda b,t: b.update({"package-gpgv": b"forged"}),
                       lambda b,t: t["files"].pop("/usr/bin/gpgv"),
                       lambda b,t: t["files"]["/usr/bin/zstd"].update(sha256="0"*64),
                       lambda b,t: t["files"]["/usr/bin/gpgv"]["elf"].update(needed=["missing.so"]),
                       lambda b,t: t["files"]["/usr/bin/gpgv"].update(uid=False),
                       lambda b,t: t["files"]["/usr/bin/gpgv"].update(package="unowned"),
                       lambda b,t: t["files"]["/usr/bin/gpgv"]["elf"].update(build_ids=["deadbeef"]),
                       lambda b,t: t["keyring"].update(uid=1000),
                       lambda b,t: t["keyring"].update(sha256="0"*64),
                       lambda b,t: t.pop("keyring"),
                       lambda b,t: t.pop("loader"),
                       lambda b,t: b.pop("index-noble-universe")):
            with self.subTest(mutate=mutate), self.assertRaises(ValueError): self.synthetic_run(mutate)

    def test_identical_verifier_bytes_cannot_claim_different_elf_dependencies(self):
        def erase(blobs, toolchain):
            row = toolchain["files"]["/usr/bin/gpgv"]
            row.update(interpreter=None, needed={})
            row["elf"].update(interpreter=None, needed=[])
            toolchain["extensions"] = [path for path in toolchain["files"] if path not in toolchain["tools"].values()]
        with self.assertRaises(ValueError): self.synthetic_run(erase)

    def test_verifier_edges_require_matching_soname_and_symbol_versions(self):
        def swap(blobs, toolchain):
            edges = toolchain["files"]["/usr/bin/gpgv"]["needed"]
            edges["lib0.so"], edges["lib1.so"] = edges["lib1.so"], edges["lib0.so"]
        def versions(blobs, toolchain):
            toolchain["files"]["/usr/bin/gpgv"]["elf"]["required_versions"] = {"lib0.so": ["MISSING_VERSION"]}
        for mutate in (swap, versions):
            with self.subTest(mutate=mutate), self.assertRaises(ValueError): self.synthetic_run(mutate)

    def test_incomplete_loader_source_and_environment_receipts_are_rejected(self):
        for change in (lambda r: r["verification-toolchain"]["data"].update(source_hashes={"x": "not-a-hash"}),
                       lambda r: r["verification-toolchain"]["data"]["loader"].update(files=[{"path": row["path"]} for row in r["verification-toolchain"]["data"]["loader"]["files"]]),
                       lambda r: r["verification-toolchain"]["data"]["loader"]["files"].append(r["verification-toolchain"]["data"]["loader"]["files"][0]),
                       lambda r: r["runner-environment"]["data"].pop("runner_arch"),
                       lambda r: r["archive-anchor"]["data"].pop("rsa_bits")):
            with self.subTest(change=change):
                bundle = self.synthetic_run(); change(bundle["receipts"])
                bundle["manifest"] = {name: hashlib.sha256(self.api.canonical(row)).hexdigest() for name,row in bundle["receipts"].items()}
                with self.assertRaises(ValueError): self.validate_bundle(bundle)

    def test_incomplete_tampered_or_authorizing_receipts_are_rejected_even_with_new_hashes(self):
        for change in (lambda r: r.pop("package-membership"),
                       lambda r: r["inrelease-signatures"].update(data={}),
                       lambda r: r["verification-toolchain"].update(data={}),
                       lambda r: r["elf-closure"]["data"]["files"].pop("/usr/bin/vercmp"),
                       lambda r: r["authorization-state"]["data"].update(accepted=True),
                       lambda r: r["authorization-state"]["data"].update(hardware_attested=True)):
            with self.subTest(change=change):
                bundle = self.synthetic_run(); change(bundle["receipts"])
                bundle["manifest"] = {name: hashlib.sha256(self.api.canonical(row)).hexdigest() for name,row in bundle["receipts"].items()}
                with self.assertRaises(ValueError): self.validate_bundle(bundle)

    def test_receipt_graph_and_package_relationships_reject_rehashed_forgery(self):
        for change in (lambda r: r["elf-closure"]["data"].update(edges=[]),
                       lambda r: r["elf-closure"]["data"].update(links={}),
                       lambda r: r["elf-closure"]["data"]["edges"][0].update(target="/missing"),
                       lambda r: r["package-membership"]["data"]["gpgv"].update(selected_members=[]),
                       lambda r: r["elf-closure"]["data"]["files"]["/usr/bin/gpgv"]["elf"].update(needed=[])):
            with self.subTest(change=change):
                bundle = self.synthetic_run(); change(bundle["receipts"])
                bundle["manifest"] = {name: hashlib.sha256(self.api.canonical(row)).hexdigest() for name,row in bundle["receipts"].items()}
                with self.assertRaises(ValueError): self.validate_bundle(bundle)
