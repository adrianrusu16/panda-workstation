"""Enrollment must not turn arbitrary paths or ambiguous records into writes."""

import copy
import importlib
import json
import os
from pathlib import Path
import sys
import unittest

from live_fixture_support import COMMON, fixture, tree
sys.path.insert(0, str(COMMON))


class EnrollmentContracts(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec("enrollment"), "B1 enrollment model missing")
        self.api = importlib.import_module("enrollment")
        self.root = fixture(self)

    def test_enrollment_records_distinct_source_and_hook_fingerprints(self):
        record = self.api.enroll_fixture(self.root, version="1.3.1")
        self.assertEqual(record.component, "ghostty")
        self.assertEqual(record.paths["target"], "config/panda/generated/ghostty.conf")
        self.assertNotEqual(record.fingerprints["source"]["inode"], record.fingerprints["hook"]["inode"])
        before = tree(self.root)
        self.assertEqual(self.api.enroll_fixture(self.root, version="1.3.1"), record)
        self.assertEqual(tree(self.root), before)

    def test_missing_conflicting_or_drifted_inputs_never_enroll(self):
        hook = self.root / "config/ghostty/config.ghostty"
        hook.write_bytes(b"different\n")
        before = tree(self.root)
        with self.assertRaises(ValueError):
            self.api.enroll_fixture(self.root, version="1.3.1")
        self.assertEqual(tree(self.root), before)

    def test_strict_versioned_records_reject_ambiguous_fields(self):
        record = self.api.enroll_fixture(self.root, version="1.3.1").to_dict()
        changes = [("schema_version", True), ("component", "kitty"), ("critical", False),
                   ("application_version", "1.2.0"), ("purpose", "live"), ("extra", 1)]
        for key, value in changes:
            with self.subTest(key=key):
                changed = copy.deepcopy(record)
                changed[key] = value
                with self.assertRaises(ValueError):
                    self.api.Enrollment.from_dict(changed)
        for field, value in (("mode", 0o666), ("size", 65537), ("mtime_ns", 2**63),
                             ("nlink", 2), ("sha256", "invalid"), ("uid", -1)):
            changed = copy.deepcopy(record)
            changed["fingerprints"]["hook"][field] = value
            with self.assertRaises(ValueError):
                self.api.Enrollment.from_dict(changed)
        changed = copy.deepcopy(record)
        changed["paths"]["target"] = "/home/other/.config/ghostty/config.ghostty"
        with self.assertRaises(ValueError):
            self.api.Enrollment.from_dict(changed)
        with self.assertRaises(ValueError):
            self.api.decode_record(b'{"schema_version":1,"schema_version":1}')

    def test_real_and_phase3a_roots_cannot_be_enrolled(self):
        for root in (Path.home(), Path(os.environ["XDG_CONFIG_HOME"]),
                     Path("/home/adrian/.config"), self.root / ".." / self.root.name,
                     Path("/tmp/panda-theme-fixture-other")):
            with self.subTest(root=root):
                before = tree(self.root)
                with self.assertRaises(ValueError):
                    self.api.enroll_fixture(root, version="1.3.1")
                self.assertEqual(tree(self.root), before)

    def test_invalid_version_or_ownership_has_no_enrollment_side_effects(self):
        for version in (None, "", "1.3.2", "1.3.1-2.2"):
            before = tree(self.root)
            with self.assertRaises(ValueError):
                self.api.enroll_fixture(self.root, version=version)
            self.assertEqual(tree(self.root), before)
        self.root.chmod(0o755)
        before = tree(self.root)
        with self.assertRaises(ValueError):
            self.api.enroll_fixture(self.root, version="1.3.1")
        self.assertEqual(tree(self.root), before)
