"""Review exports and generator are deterministic, labelled and explicit."""
import hashlib
import importlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "theme/panda/common"))


class VisualExportTests(unittest.TestCase):
    def test_planned_exports_parse_and_repeat_byte_for_byte(self):
        export = importlib.import_module("desktop_visual_export")
        first, report = export.make_exports()
        second, again = export.make_exports()
        self.assertEqual(report, again)
        self.assertEqual(first, second)
        for flavor in ("minimal", "cyber", "gothic", "hybrid", "wave"):
            for prefix in ("fhd-compact-", "qhd-expanded-"):
                self.assertIn(prefix + flavor + ".svg", first)
                self.assertIn(prefix + flavor + ".png", first)
        self.assertIn("cyber-composition.png", first)
        self.assertIn("five-flavor-comparison.png", first)
        for name, data in first.items():
            if name.endswith(".svg"):
                ET.fromstring(data)
                self.assertIn(b"SYNTHETIC OFFLINE DESIGN", data)
            elif name.endswith(".png"):
                self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertEqual(report["bounds_failures"], [])
        self.assertEqual(report["geometry_accepts"], 55)
        self.assertEqual(report["expected_refusals"], 5)

    def test_missing_optional_measurement_tooling_returns_clean_refusal(self):
        import builtins
        from io import StringIO
        from unittest.mock import patch
        export = importlib.import_module("desktop_visual_export")
        original = builtins.__import__
        def missing(name, *args, **kwargs):
            if name == "gi":
                raise ModuleNotFoundError("GI deliberately unavailable")
            return original(name, *args, **kwargs)
        with tempfile.TemporaryDirectory(prefix="panda-visual-missing-tool-") as td:
            out = Path(td)/"not-created"
            diagnostic = StringIO()
            with patch("builtins.__import__",side_effect=missing), patch("sys.stderr",diagnostic):
                self.assertEqual(export.main(["--output-dir",str(out)]),1)
            self.assertIn("requires existing PyGObject/librsvg",diagnostic.getvalue())
            self.assertNotIn("Traceback",diagnostic.getvalue())
            self.assertFalse(out.exists())

    def test_export_is_idempotent_and_refuses_symlink_or_conflicting_objects(self):
        export = importlib.import_module("desktop_visual_export")
        with tempfile.TemporaryDirectory(prefix="panda-visual-export-") as td:
            out = Path(td) / "review"
            files = {"example.svg": b"<svg/>"}
            export.write_exports(out, files)
            before = (out / "example.svg").stat()
            export.write_exports(out, files)
            after = (out / "example.svg").stat()
            self.assertEqual((before.st_ino, before.st_mtime_ns), (after.st_ino, after.st_mtime_ns))
            (out / "example.svg").unlink()
            sentinel = Path(td) / "sentinel"
            sentinel.write_bytes(b"preserve")
            (out / "example.svg").symlink_to(sentinel)
            with self.assertRaises((ValueError, OSError)):
                export.write_exports(out, files)
            self.assertEqual(sentinel.read_bytes(), b"preserve")
            (out / "example.svg").unlink()
            (out / "example.svg").write_bytes(b"operator content")
            with self.assertRaises(ValueError):
                export.write_exports(out, files)
            self.assertEqual((out / "example.svg").read_bytes(), b"operator content")

if __name__ == "__main__":
    unittest.main()
