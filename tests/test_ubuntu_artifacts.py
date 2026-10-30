"""Synthetic archive/ELF bytes only. No package, loader or executable is run."""
import copy
import hashlib
import importlib
import io
import lzma
from pathlib import Path
import struct
import sys
import tarfile
import unittest
from unittest.mock import patch

S4 = Path(__file__).resolve().parent / "native/external_vm/s4"


def synthetic_elf(needed=(), interpreter=None, soname=None, rpath=None, required=(), provided=()):
    """Small independently constructed ELF64 dynamic-table fixture, never executable."""
    strings = bytearray(b"\0")
    def name(value):
        offset = len(strings)
        strings.extend(value.encode() + b"\0")
        return offset
    tags = [(1, name(value)) for value in needed]
    if soname: tags.append((14, name(soname)))
    if rpath: tags.append((29, name(rpath)))
    version_bytes = bytearray(256)
    if required:
        provider, version = required
        struct.pack_into("<HHIII", version_bytes, 0, 1, 1, name(provider), 16, 0)
        struct.pack_into("<IHHII", version_bytes, 16, 0, 0, 2, name(version), 0)
        tags += [(0x6ffffffe, 0x400600), (0x6fffffff, 1)]
    if provided:
        struct.pack_into("<HHHHIII", version_bytes, 128, 1, 0, 2, 1, 0, 20, 0)
        struct.pack_into("<II", version_bytes, 148, name(provided[0]), 0)
        tags += [(0x6ffffffc, 0x400680), (0x6ffffffd, 1)]
    tags += [(5, 0x400400), (10, len(strings)), (0, 0)]
    raw = bytearray(2048)
    raw[:16] = b"\x7fELF\x02\x01\x01" + b"\0" * 9
    count = 3 if interpreter else 2
    struct.pack_into("<HHIQQQIHHHHHH", raw, 16, 3, 62, 1, 0, 64, 0, 0, 64, 56, count, 0, 0, 0)
    struct.pack_into("<IIQQQQQQ", raw, 64, 1, 5, 0, 0x400000, 0, len(raw), len(raw), 4096)
    struct.pack_into("<IIQQQQQQ", raw, 120, 2, 4, 512, 0x400200, 0, len(tags)*16, len(tags)*16, 8)
    if interpreter:
        value = interpreter.encode() + b"\0"
        raw[384:384+len(value)] = value
        struct.pack_into("<IIQQQQQQ", raw, 176, 3, 4, 384, 0x400180, 0, len(value), len(value), 1)
    for i, item in enumerate(tags): struct.pack_into("<qQ", raw, 512+16*i, *item)
    raw[1024:1024+len(strings)] = strings
    raw[1536:1792] = version_bytes
    return bytes(raw)


def synthetic_deb(package="sample", files=None, links=None):
    files = files or {"usr/bin/sample": b"data"}
    def archive(entries, symlinks=None):
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode="w", format=tarfile.USTAR_FORMAT) as tar:
            for path, content in entries.items():
                member = tarfile.TarInfo("./"+path); member.size = len(content); member.mode = 0o644
                tar.addfile(member, io.BytesIO(content))
            for path, target in (symlinks or {}).items():
                member = tarfile.TarInfo("./"+path); member.type = tarfile.SYMTYPE; member.linkname = target
                tar.addfile(member)
        return output.getvalue()
    parts = {"debian-binary": b"2.0\n", "control.tar.xz": lzma.compress(archive({"control":
        ("Package: "+package+"\nVersion: 1\nArchitecture: amd64\n").encode()})),
        "data.tar.xz": lzma.compress(archive(files, links))}
    result = bytearray(b"!<arch>\n")
    for name, raw in parts.items():
        header = f"{name+'/':<16}{0:<12}{0:<6}{0:<6}{'100644':<8}{len(raw):<10}`\n".encode()
        assert len(header) == 60
        result.extend(header+raw+(b"\n" if len(raw)%2 else b""))
    return bytes(result)


class UbuntuArtifacts(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(S4))
        self.addCleanup(sys.path.remove, str(S4))
        self.assertTrue((S4/"ubuntu_artifacts.py").is_file(), "bounded Ubuntu artifact reader missing")
        self.api = importlib.import_module("ubuntu_artifacts")

    def test_elf_reads_interpreter_libraries_and_symbol_versions_without_execution(self):
        raw = synthetic_elf(["libc.so.6"], "/lib64/ld.so", required=("libc.so.6", "GLIBC_2.38"))
        value = self.api.elf_info(raw)
        self.assertEqual(value["interpreter"], "/lib64/ld.so")
        self.assertEqual(value["needed"], ["libc.so.6"])
        self.assertEqual(value["required_versions"], {"libc.so.6": ["GLIBC_2.38"]})
        self.assertEqual(self.api.elf_info(synthetic_elf(provided=["GLIBC_2.38"]))["provided_versions"], ["GLIBC_2.38"])

    def test_elf_rejects_wrong_architecture_truncation_search_override_and_duplicate_needed(self):
        wrong = bytearray(synthetic_elf()); struct.pack_into("<H", wrong, 18, 183)
        for raw in (bytes(wrong), synthetic_elf()[:100], synthetic_elf(rpath="/tmp"),
                    synthetic_elf(["libc.so.6", "libc.so.6"])):
            with self.subTest(sha=hashlib.sha256(raw).hexdigest()), self.assertRaises(ValueError):
                self.api.elf_info(raw)

    def test_package_members_hash_selected_regular_data_and_preserve_symlinks(self):
        raw = synthetic_deb(links={"usr/bin/alias": "sample"})
        control, nodes, content = self.api.package_members(raw, "sample", {"/usr/bin/sample"}, None)
        self.assertEqual(control["package"], "sample")
        self.assertEqual(content, {"/usr/bin/sample": b"data"})
        self.assertEqual(nodes["/usr/bin/sample"]["sha256"], hashlib.sha256(b"data").hexdigest())
        self.assertEqual(nodes["/usr/bin/alias"]["target"], "sample")

    def test_package_rejects_unsafe_members_identity_and_expansion_excess(self):
        for raw, package in ((synthetic_deb(files={"../escape": b"x"}), "sample"),
                             (synthetic_deb(), "different"), (b"not-ar", "sample")):
            with self.subTest(package=package), self.assertRaises(ValueError):
                self.api.package_members(raw, package, set(), None)
        with patch.object(self.api, "MAX_EXPANSION", 100), self.assertRaises(ValueError):
            self.api.package_members(synthetic_deb(), "sample", set(), None)

    def test_links_resolve_ancestors_before_leaf_and_reject_cycles_and_escape(self):
        nodes = {"/lib": {"kind": "symlink", "target": "usr/lib", "package": "base"},
                 "/usr/lib/libc.so": {"kind": "file", "package": "libc"}}
        path, links = self.api.resolve_path(nodes, "/lib/libc.so")
        self.assertEqual(path, "/usr/lib/libc.so")
        self.assertEqual(links, ["/lib"])
        for link in ("/lib", "../../outside"):
            with self.subTest(link=link), self.assertRaises(ValueError):
                self.api.resolve_path({"/lib": {"kind": "symlink", "target": link}}, "/lib/libc.so")
        shadowed = {"/usr": {"kind": "symlink", "target": "/evil"},
                    "/usr/bin/gpgv": {"kind": "file"}}
        with self.assertRaises(ValueError): self.api.resolve_path(shadowed, "/usr/bin/gpgv")

    def test_archive_member_count_is_bounded(self):
        with patch.object(self.api, "MAX_MEMBERS", 1), self.assertRaises(ValueError):
            self.api.package_members(synthetic_deb(files={"a": b"x", "b": b"y"}), "sample", set(), None)

    def test_parent_components_follow_symlink_traversal_order(self):
        nodes = {"/a": dict(kind="symlink", target="/x/y"),
                 "/x/y": dict(kind="directory"), "/x/lib": dict(kind="file"),
                 "/lib": dict(kind="file"),
                 "/alias": dict(kind="symlink", target="a/../lib")}
        for request, links in (("/a/../lib", ["/a"]), ("/alias", ["/alias", "/a"])):
            with self.subTest(request=request):
                self.assertEqual(self.api.resolve_path(nodes, request), ("/x/lib", links))
        for request in ("/a/../../../lib", "/lib/../lib", "/alias/child"):
            with self.subTest(request=request), self.assertRaises(ValueError):
                self.api.resolve_path(nodes, request)

    def test_elf_version_or_program_header_counts_are_bounded(self):
        raw = bytearray(synthetic_elf())
        struct.pack_into("<H", raw, 56, 65535)
        with self.assertRaises(ValueError): self.api.elf_info(bytes(raw))

    def test_complete_runtime_graph_checks_all_thirteen_files_and_directory_aliases(self):
        contents, references, nodes = {}, {}, {}
        loader = "/usr/lib/x86_64-linux-gnu/ld.so"
        paths = ["/usr/bin/"+name for name in ("gpgv", "zstd", "vercmp")]
        libraries = ["lib"+str(i)+".so" for i in range(9)]
        for path in paths+[loader]+["/usr/lib/x86_64-linux-gnu/"+name for name in libraries]:
            soname = Path(path).name if path not in paths else None
            needed = libraries if path == paths[0] else []
            interp = "/lib64/ld.so" if path in paths else None
            raw = synthetic_elf(needed, interp, soname)
            contents[path] = raw
            references[path] = dict(package="sample", sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw),
                                    needed=needed, interpreter=interp)
            nodes[path] = dict(kind="file", package="sample")
        links = {"/lib": dict(kind="symlink", target="usr/lib", package="base"),
                 "/lib64": dict(kind="symlink", target="usr/lib/x86_64-linux-gnu", package="base")}
        nodes.update(links)
        tools = dict(zip(("gpgv", "zstd", "vercmp"), paths))
        value = self.api.runtime_closure(nodes, contents, references, links, tools)
        self.assertTrue(value["closure_complete"])
        self.assertEqual(len(value["files"]), 13)
        self.assertFalse(value["actual_candidate_mappings_verified"])
        for name in (loader, "/usr/lib/x86_64-linux-gnu/lib0.so"):
            broken = dict(contents); broken.pop(name)
            with self.assertRaises(ValueError): self.api.runtime_closure(nodes, broken, references, links, tools)
        changed = copy.deepcopy(references); changed[paths[0]]["needed"] = ["libmissing.so"]
        with self.assertRaises(ValueError): self.api.runtime_closure(nodes, contents, changed, links, tools)
        changed = copy.deepcopy(nodes); changed[loader]["package"] = "unowned"
        with self.assertRaises(ValueError): self.api.runtime_closure(changed, contents, references, links, tools)
