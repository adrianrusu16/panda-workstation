"""Source seals, transport/process doubles and private synthetic receipt files only."""
import contextlib
import hashlib
import importlib
import io
import json
from pathlib import Path, PurePosixPath
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from test_ubuntu_artifacts import synthetic_elf

S4 = Path(__file__).resolve().parent / "native/external_vm/s4"
ROOT = S4.parents[3]


class UbuntuBootstrapRunner(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(S4)); self.addCleanup(sys.path.remove, str(S4))
        self.assertTrue((S4/"ubuntu_bootstrap_runner.py").is_file(), "sealed hosted Ubuntu runner missing")
        self.api = importlib.import_module("ubuntu_bootstrap_runner")

    def fictional_inventory(self, change=None):
        """Run the real inventory/parser/validator against an entirely virtual host."""
        library = "/usr/lib/x86_64-linux-gnu/"
        first, second, loader = (library+name for name in ("libfirst.so.1.2", "libsecond.so.2.3", "ld-fixture.so"))
        extension = "/usr/lib/python3.12/lib-dynload/_fixture.so"
        interp = "/lib64/ld-fixture.so"
        data = {
            "/usr/bin/gpgv": synthetic_elf(["libfirst.so.1"], interp, required=("libfirst.so.1", "FIRST_1")),
            "/usr/bin/zstd": synthetic_elf(["libsecond.so.2"], interp),
            "/usr/bin/python3.12": synthetic_elf(["libfirst.so.1"], interp),
            extension: synthetic_elf(["libsecond.so.2"]),
            first: synthetic_elf(["libsecond.so.2"], soname="libfirst.so.1", required=("libsecond.so.2", "SECOND_2"), provided=["FIRST_1"]),
            second: synthetic_elf(soname="libsecond.so.2", provided=["SECOND_2"]),
            loader: synthetic_elf(soname="ld-fixture.so"),
            self.api.KEYRING: b"fictional archive keyring; not cryptographic evidence",
            "/etc/ld.so.cache": b"fictional cache", "/etc/ld.so.conf": b"include /etc/ld.so.conf.d/*.conf\n",
            "/etc/ssl/certs/ca-certificates.crt": b"fictional CA bundle",
        }
        aliases = {interp: loader}
        for directory in self.api.LIB_DIRS[:2]:
            aliases[directory+"/libfirst.so.1"] = first
            aliases[directory+"/libsecond.so.2"] = second
        for path in (first, second, loader): aliases[path.removeprefix("/usr")] = path
        owners = {"/usr/bin/gpgv": "gpgv", "/usr/bin/zstd": "zstd", "/usr/bin/python3.12": "python3.12-minimal",
                  extension: "libpython3.12-stdlib", first: "libfirst", second: "libsecond", loader: "libloader",
                  self.api.KEYRING: "ubuntu-keyring"}
        packages = {name: dict(version="1", architecture="amd64") for name in owners.values()}
        packages["ubuntu-keyring"] = dict(version="2023.11.28.1", architecture="all")
        for name in packages:
            data["/var/lib/dpkg/info/"+name+".list"] = ("\n".join(path for path, owner in owners.items() if owner == name)+"\n").encode()
        data["/var/lib/dpkg/status"] = "\n\n".join("Package: "+name+"\nStatus: install ok installed\nVersion: "+row["version"]+
            "\nArchitecture: "+row["architecture"] for name, row in packages.items()).encode()
        pins = dict(tools=dict(self.api.TOOLS), keyring_sha256=hashlib.sha256(data[self.api.KEYRING]).hexdigest(),
            packages=packages, files={path: dict(sha256=hashlib.sha256(data[path]).hexdigest(), bytes=len(data[path]),
            needed=[name], interpreter=interp) for path, name in
            (("/usr/bin/gpgv", "libfirst.so.1"), ("/usr/bin/zstd", "libsecond.so.2"))})
        metadata = {}
        if change: change(data, aliases, metadata)

        def canonical_path(path):
            path = str(path)
            if path in aliases: return aliases[path]
            return "/usr"+path if path.startswith(("/lib/", "/lib64/", "/bin/", "/sbin/")) else path

        class VirtualPath(PurePosixPath):
            def resolve(self, strict=False):
                path = canonical_path(self)
                if strict and path not in data: raise FileNotFoundError(path)
                return VirtualPath(path)
            def is_dir(self): return str(self) == "/etc/ld.so.conf.d"
            def is_symlink(self): return str(self) in aliases
            def exists(self): return str(self) in data
            def glob(self, pattern):
                return [VirtualPath(path) for path in sorted(data) if VirtualPath(path).parent == self and VirtualPath(path).match(pattern)]

        def read(path, limit, *, optional=False):
            if not isinstance(path, (str, PurePosixPath)):
                raise AssertionError("dependency traversal requires path strings, not file records")
            canonical = canonical_path(path)
            if canonical not in data:
                if optional: return None
                raise FileNotFoundError(canonical)
            raw = data[canonical]
            if len(raw) > limit: raise ValueError("fictional file budget")
            return dict(dict(path=canonical, raw=raw, mode=0o755, uid=0), **metadata.get(canonical, {}))

        def source(path, limit):
            self.assertIn(path.name, self.api.protocol.SOURCE_NAMES)
            return ("fictional source: "+path.name).encode()

        with patch.object(self.api, "Path", VirtualPath), \
             patch.object(self.api, "sys", SimpleNamespace(executable="/usr/bin/python3.12", modules={"fixture": SimpleNamespace(__file__=extension)})), \
             patch.object(self.api, "system_file", side_effect=read), \
             patch.object(self.api, "read_bounded", side_effect=source), \
             patch.object(self.api.protocol, "load_references", return_value=(pins, None)), \
             patch.object(self.api.subprocess, "Popen", side_effect=AssertionError("native process reached")), \
             patch.object(self.api, "download", side_effect=AssertionError("network reached")):
            inventory = self.api.inventory_toolchain()
        return inventory, pins

    def test_complete_preinstalled_traversal_uses_canonical_paths_and_passes_validation(self):
        inventory, pins = self.fictional_inventory()
        self.assertEqual(set(inventory["files"]), {"/usr/bin/gpgv", "/usr/bin/zstd", "/usr/bin/python3.12",
            "/usr/lib/python3.12/lib-dynload/_fixture.so", "/usr/lib/x86_64-linux-gnu/libfirst.so.1.2",
            "/usr/lib/x86_64-linux-gnu/libsecond.so.2.3", "/usr/lib/x86_64-linux-gnu/ld-fixture.so"})
        self.assertEqual(inventory["files"]["/usr/bin/gpgv"]["needed"], {"libfirst.so.1": "/usr/lib/x86_64-linux-gnu/libfirst.so.1.2"})
        self.assertEqual(inventory["files"]["/usr/lib/x86_64-linux-gnu/libfirst.so.1.2"]["needed"],
                         {"libsecond.so.2": "/usr/lib/x86_64-linux-gnu/libsecond.so.2.3"})
        for row in inventory["files"].values():
            self.assertTrue(all(type(target) is str and target.startswith("/") for target in row["needed"].values()))
            self.assertIn(row["package"], inventory["packages"])
        self.assertEqual(self.api.protocol.verify_toolchain(inventory, pins), inventory)

    def test_complete_preinstalled_traversal_rejects_unresolved_ambiguous_or_contradictory_libraries(self):
        first = "/usr/lib/x86_64-linux-gnu/libfirst.so.1.2"
        def missing(data, aliases, metadata): data.pop(first)
        def ambiguous(data, aliases, metadata): data["/usr/lib64/libfirst.so.1"] = data[first]
        def soname(data, aliases, metadata): data[first] = synthetic_elf(soname="libwrong.so", provided=["FIRST_1"])
        def versions(data, aliases, metadata): data[first] = synthetic_elf(soname="libfirst.so.1")
        def ownership(data, aliases, metadata): metadata[first] = dict(uid=1000)
        for mutate, error in ((missing, "missing/ambiguous"), (ambiguous, "missing/ambiguous"),
                              (soname, "SONAME"), (versions, "symbol version"), (ownership, "ownership")):
            with self.subTest(mutate=mutate), self.assertRaisesRegex(ValueError, error):
                self.fictional_inventory(mutate)

    def test_cli_and_hosted_api_refuse_before_any_files_network_or_process_probe(self):
        with patch.object(self.api, "capture_host", side_effect=AssertionError("host probe reached")), \
             patch.object(self.api, "download", side_effect=AssertionError("network reached")), \
             patch.object(self.api.subprocess, "Popen", side_effect=AssertionError("process reached")):
            output = io.StringIO()
            with contextlib.redirect_stdout(output): self.assertEqual(self.api.main([]), 78)
            receipt = json.loads(output.getvalue())
            self.assertFalse(receipt["execution_authorized"])
            self.assertFalse(receipt["trust_policy_activation_allowed"])
            with self.assertRaisesRegex(ValueError, "sealed"):
                self.api.authenticate_hosted()

    def test_workflow_template_cannot_be_recognized_or_dispatch_jobs(self):
        path = ROOT/".github/workflows/panda-ubuntu-bootstrap-verification.yml.disabled"
        self.assertTrue(path.is_file())
        text = path.read_text()
        self.assertIn("runs-on: ubuntu-24.04", text)
        self.assertIn("if: ${{ false }}", text)
        self.assertIn("20261026.354.1", text)
        for active in (ROOT/".github/workflows").glob("*.y*ml"):
            self.assertNotIn("ubuntu_bootstrap_runner.py", active.read_text())
        for forbidden in ("apt-get", "sudo ", "docker run", "ubuntu-latest", "secrets.", "assemble(", "authenticate_set("):
            self.assertNotIn(forbidden, text)

    def test_redirects_must_remain_in_the_exact_snapshot_prefix(self):
        handler = self.api.SnapshotRedirect("https://snapshot.ubuntu.com/ubuntu/20261029T000000Z/")
        for url in ("http://snapshot.ubuntu.com/ubuntu/20261029T000000Z/a", "https://attacker.invalid/a",
                    "https://snapshot.ubuntu.com/ubuntu/20261029T000000Z/../private", "https://snapshot.ubuntu.com/ubuntu/20261029T000000Z/a?x=y"):
            with self.subTest(url=url), self.assertRaises(ValueError): handler.check(url)

    def test_download_reads_exact_budget_and_does_not_accept_oversize_response(self):
        class Response(io.BytesIO):
            def geturl(self): return "https://snapshot.ubuntu.com/ubuntu/20261029T000000Z/file"
        class Opener:
            def open(self, request, timeout): return Response(b"12345")
        with self.assertRaisesRegex(ValueError, "size"):
            self.api.download("https://snapshot.ubuntu.com/ubuntu/20261029T000000Z/file", 4, Opener())
        self.assertEqual(self.api.download("https://snapshot.ubuntu.com/ubuntu/20261029T000000Z/file", 5, Opener()), b"12345")

    def test_real_process_adapter_never_accepts_candidate_paths(self):
        with tempfile.TemporaryDirectory() as name, \
             patch.object(self.api.subprocess, "Popen", side_effect=AssertionError("process reached")):
            with self.assertRaises(ValueError):
                self.api.invoke("/tmp/gpgv", [], Path(name), None, 100)

    def test_runner_application_version_is_observed_from_ancestry_not_guessed(self):
        row = self.api.runner_application(["/usr/bin/python3.12", "/home/runner/runners/2.338.0/bin/Runner.Worker"])
        self.assertEqual(row["version"], "2.338.0")
        self.assertEqual(row["basis"], "observed runner ancestor executable path")
        self.assertIsNone(self.api.runner_application(["/usr/bin/python3.12"])["version"])
        with self.assertRaises(ValueError):
            self.api.runner_application(["/home/runner/runners/2.338.0/bin/Runner.Worker",
                                         "/home/runner/runners/2.337.0/bin/Runner.Listener"])

    def test_dpkg_ownership_requires_one_installed_owner_per_inventory_file(self):
        packages = {"libc6": dict(version="1", architecture="amd64")}
        aliases = {"/lib/libc.so.6": "/usr/lib/libc.so.6"}
        lists = {"libc6:amd64.list": b"/.\n/lib/libc.so.6\n"}
        self.assertEqual(self.api.package_owners(aliases, packages, lists), {"/usr/lib/libc.so.6": "libc6"})
        self.assertEqual(self.api.package_owners(aliases, packages,
            {**lists, "libc6:i386.list": b"/lib/i386-linux-gnu/libc.so.6\n"}), {"/usr/lib/libc.so.6": "libc6"})
        for manifests in ({}, {"unknown.list": b"/lib/libc.so.6\n"},
                          {**lists, "libc6.list": b"/lib/libc.so.6\n"},
                          {"libc6:amd64.list": b"/lib/libc.so.6\x00\n"}):
            with self.subTest(manifests=manifests), self.assertRaises(ValueError):
                self.api.package_owners(aliases, packages, manifests)

    def test_dpkg_metadata_does_not_confuse_foreign_and_native_package_instances(self):
        identities = [(name, "amd64") for name in ("gpgv", "zstd", "python3.12-minimal", "libpython3.12-stdlib", "libc6")]
        identities += [("ubuntu-keyring", "all"), ("libc6", "i386")]
        raw = "\n\n".join("Package: "+name+"\nStatus: install ok installed\nVersion: 1\nArchitecture: "+arch
                            for name, arch in identities).encode()
        with patch.object(self.api, "system_file", return_value={"raw": raw}):
            rows = self.api.package_metadata()
        self.assertEqual(rows["libc6"]["architecture"], "amd64")
        self.assertEqual(rows["libc6:i386"]["architecture"], "i386")
