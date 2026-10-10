"""B1 file capabilities cannot be broadened by paths, flags or filesystem tricks."""

import importlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from live_fixture_support import COMMON, fixture, tree
sys.path.insert(0, str(COMMON))


class LivePathContracts(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec("live_fs"), "B1 filesystem missing")
        self.fs = importlib.import_module("live_fs")
        self.enrollment = importlib.import_module("enrollment")
        self.root = fixture(self)

    def enroll(self):
        self.enrollment.enroll_fixture(self.root, version="1.3.1")

    def test_unenrolled_or_phase3a_marker_confers_no_capability(self):
        before = tree(self.root)
        with self.assertRaises(ValueError):
            self.fs.SimulatedLiveFS(self.root)
        self.assertEqual(tree(self.root), before)
        (self.root / ".panda-theme-fixture.json").write_bytes(
            b'{"schema_version":1,"purpose":"panda-theme-phase3a"}\n')
        before = tree(self.root)
        with self.assertRaises(ValueError):
            self.fs.SimulatedLiveFS(self.root)
        self.assertEqual(tree(self.root), before)

    def test_only_fragment_and_simulation_metadata_are_writable(self):
        self.enroll()
        from fixture_fs import new_image
        with self.fs.SimulatedLiveFS(self.root) as fs:
            for path in ("config/ghostty/config.ghostty", "source/home/dot_config/ghostty/config.ghostty",
                         "config/panda/theme-state.toml", "config/panda/generated/kitty.conf",
                         "config/panda/generated/../ghostty.conf", str(self.root / "other"), "other"):
                before = tree(self.root)
                with self.assertRaises(ValueError):
                    fs.replace(path, new_image(b"unsafe"), expected=None)
                self.assertEqual(tree(self.root), before)
            fs.replace(self.fs.TARGET, new_image(b"safe"), expected=None)
            self.assertEqual((self.root / self.fs.TARGET).read_bytes(), b"safe")

    def test_unsafe_target_types_and_modes_are_refused_without_writes(self):
        self.enroll()
        target = self.root / self.fs.TARGET
        target.parent.mkdir(mode=0o700, parents=True)
        for kind in ("symlink", "hardlink", "fifo", "directory", "world-writable", "xattr"):
            with self.subTest(kind=kind):
                if kind == "symlink": target.symlink_to(self.root / "config/ghostty/config.ghostty")
                elif kind == "hardlink": os.link(self.root / "config/ghostty/config.ghostty", target)
                elif kind == "fifo": os.mkfifo(target)
                elif kind == "directory": target.mkdir()
                else:
                    target.write_bytes(b"old")
                    target.chmod(0o666 if kind == "world-writable" else 0o600)
                    if kind == "xattr": os.setxattr(target, "user.panda-test", b"metadata")
                before = tree(self.root)
                with self.fs.SimulatedLiveFS(self.root) as fs:
                    with self.assertRaises(ValueError): fs.read(self.fs.TARGET)
                self.assertEqual(tree(self.root), before)
                if target.is_dir() and not target.is_symlink(): target.rmdir()
                else: target.unlink()

    def test_ancestor_links_and_swapped_parents_are_refused(self):
        self.enroll()
        from fixture_fs import new_image
        panda = self.root / "config/panda"
        panda.mkdir(mode=0o700)
        generated = panda / "generated"
        generated.mkdir(mode=0o700)
        with self.fs.SimulatedLiveFS(self.root) as fs:
            self.assertIsNone(fs.read(self.fs.TARGET))
            generated.rename(panda / "old")
            generated.mkdir(mode=0o700)
            before = tree(self.root)
            with self.assertRaises(ValueError):
                fs.replace(self.fs.TARGET, new_image(b"unsafe"), expected=None)
            self.assertEqual(tree(self.root), before)
        generated.rmdir()
        generated.symlink_to(panda / "old", target_is_directory=True)
        before = tree(self.root)
        with self.fs.SimulatedLiveFS(self.root) as fs:
            with self.assertRaises(ValueError): fs.read(self.fs.TARGET)
        self.assertEqual(tree(self.root), before)

    def test_expected_image_and_owner_checks_preserve_external_content(self):
        self.enroll()
        from fixture_fs import new_image
        with self.fs.SimulatedLiveFS(self.root) as fs:
            fs.replace(self.fs.TARGET, new_image(b"old"), expected=None)
            old = fs.read(self.fs.TARGET)
            (self.root / self.fs.TARGET).write_bytes(b"external")
            before = tree(self.root)
            with self.assertRaises(ValueError):
                fs.replace(self.fs.TARGET, new_image(b"new"), expected=old)
            self.assertEqual(tree(self.root), before)
            with patch("live_fs.os.getuid", return_value=os.getuid()+1):
                with self.assertRaises(ValueError): fs.read(self.fs.TARGET)

    def test_copied_enrollment_cannot_authorize_another_root(self):
        self.enroll()
        with tempfile.TemporaryDirectory(prefix="panda-theme-b1-", dir="/tmp") as temporary:
            other = Path(temporary)
            (other / self.fs.MARKER).write_bytes((self.root / self.fs.MARKER).read_bytes())
            (other / self.fs.MARKER).chmod(0o600)
            before = tree(other)
            with self.assertRaises(ValueError): self.fs.SimulatedLiveFS(other)
            self.assertEqual(tree(other), before)

    def test_negative_mode_never_reaches_replacement(self):
        self.enroll()
        from fixture_fs import FileImage
        before = tree(self.root)
        with self.fs.SimulatedLiveFS(self.root) as fs:
            with self.assertRaises(ValueError):
                fs.replace(self.fs.TARGET, FileImage(b"invalid", -128, 0, 0), expected=None)
        self.assertEqual(tree(self.root), before)
