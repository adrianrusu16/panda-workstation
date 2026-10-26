"""Read-only CLI, explicit fixtures and SVG escaping."""
import hashlib
import importlib
from unittest.mock import patch
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "theme/panda/common/desktop_cli.py"
ENTRY = ROOT / "theme/panda/common/scripts/panda-desktop.fish"
FIXTURE = ROOT / "tests/fixtures/desktop/fhd.json"


class DesktopCLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="panda-desktop-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fixture = self.root / "fixture.json"
        self.fixture.write_bytes(FIXTURE.read_bytes())
        self.env = {**os.environ, "HOME": str(self.root), "XDG_CONFIG_HOME": str(self.root / "config"),
                    "XDG_DATA_HOME": str(self.root / "data"), "XDG_CACHE_HOME": str(self.root / "cache"),
                    "XDG_STATE_HOME": str(self.root / "state"), "PYTHONDONTWRITEBYTECODE": "1",
                    "DBUS_SESSION_BUS_ADDRESS": "disabled-for-offline-test"}
        subprocess.run(["fish", "--no-config", "-c", "true"], env=self.env, check=True, capture_output=True)

    def call(self, *args, fish=False):
        command = ["fish", "--no-config", str(ENTRY)] if fish else [sys.executable, "-B", str(CLI)]
        return subprocess.run([*command, *args], cwd="/tmp", env=self.env, capture_output=True, text=True, timeout=5)

    def snapshot(self):
        return {str(p.relative_to(self.root)): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_ino,
                    p.stat().st_mode, p.stat().st_mtime_ns)
                for p in self.root.rglob("*") if p.is_file()}

    def test_json_commands_and_fish_wrapper_are_deterministic_without_writes(self):
        before = self.snapshot()
        for command in ("dry-run", "validate", "packages"):
            with self.subTest(command=command):
                result = self.call(command, "--fixture", str(self.fixture))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)["scope"], "offline-only")
                again = self.call(command, "--fixture", str(self.fixture), fish=True)
                self.assertEqual(again.returncode, 0, again.stderr)
                self.assertEqual(json.loads(result.stdout), json.loads(again.stdout))
                self.assertEqual(self.snapshot(), before)
        self.assertFalse((self.root / ".config/plasma-org.kde.plasma.desktop-appletsrc").exists())

    def test_live_apply_unknown_options_and_missing_fixture_are_rejected(self):
        before = self.snapshot()
        for args in ((), ("apply",), ("dry-run", "--fixture", str(self.fixture), "--apply"),
                     ("preview", "--fixture", str(self.fixture), "--resolution", "fhd", "--scale", "1.5", "--presentation", "expanded")):
            result = self.call(*args)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("Traceback", result.stderr)
            self.assertNotIn("<svg", result.stdout)
            self.assertEqual(self.snapshot(), before)

    def test_malformed_duplicate_json_nonregular_and_symlink_inputs_fail(self):
        self.fixture.write_text('{"schema_version":1,"schema_version":1}')
        self.assertNotEqual(self.call("--fixture", str(self.fixture)).returncode, 0)
        self.fixture.write_bytes(FIXTURE.read_bytes())
        link = self.root / "link"
        link.symlink_to(self.fixture)
        for path in (link, self.root):
            result = self.call("--fixture", str(path))
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("Traceback", result.stderr)
        fifo = self.root / "fifo"
        os.mkfifo(fifo)
        self.assertNotEqual(self.call("--fixture", str(fifo)).returncode, 0)

    def test_preview_is_valid_svg_with_explicit_unverified_label_and_escaped_text(self):
        fixture = json.loads(self.fixture.read_text())
        fixture["providers"]["media"] = '<script>alert("fixture")</script> & long title'
        self.fixture.write_text(json.dumps(fixture))
        result = self.call("preview", "--fixture", str(self.fixture), "--resolution", "qhd", "--scale", "1.25", "--flavor", "wave")
        self.assertEqual(result.returncode, 0, result.stderr)
        root = ET.fromstring(result.stdout)
        self.assertEqual(root.tag, "{http://www.w3.org/2000/svg}svg")
        self.assertEqual(root.attrib["viewBox"], "0 0 2048 1152")
        self.assertIn("unverified", result.stdout.lower())
        self.assertNotIn("<script>", result.stdout)
        self.assertIn("&lt;script&gt;", result.stdout)


    def test_replaced_input_path_is_refused_even_when_open_descriptor_is_stable(self):
        sys.path.insert(0, str(CLI.parent))
        io_module = importlib.import_module("desktop_io")
        original_read = io_module.os.read
        replaced = False
        def replace_path_after_read(fd, size):
            nonlocal replaced
            data = original_read(fd, size)
            if not replaced:
                replacement = self.root / "replacement.json"
                replacement.write_bytes(FIXTURE.read_bytes())
                replacement.replace(self.fixture)
                replaced = True
            return data
        with patch.object(io_module.os, "read", replace_path_after_read):
            with self.assertRaisesRegex(ValueError, "changed"):
                io_module.read_regular(self.fixture)


    def test_huge_json_integers_are_cleanly_refused(self):
        for location in ("scale", "geometry"):
            fixture = json.loads(FIXTURE.read_text())
            if location == "scale":
                fixture["output"]["scale"] = 10 ** 400
            else:
                fixture["applets"][0]["geometry"] = [0, 0, 10 ** 400, 10]
            self.fixture.write_text(json.dumps(fixture))
            result = self.call("--fixture", str(self.fixture))
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("Traceback", result.stderr)

    def test_xml_forbidden_provider_characters_are_refused(self):
        fixture = json.loads(FIXTURE.read_text())
        for value in ("A\\uffffB", "A\\ud800B"):
            fixture["providers"]["clock"] = json.loads('"' + value + '"')
            self.fixture.write_text(json.dumps(fixture))
            result = self.call("preview", "--fixture", str(self.fixture))
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("Traceback", result.stderr)
            self.assertEqual(result.stdout, "")

    def test_nan_and_oversized_fixture_fail_cleanly(self):
        self.fixture.write_text('{"bad":NaN}')
        self.assertNotEqual(self.call("--fixture", str(self.fixture)).returncode, 0)
        self.fixture.write_bytes(b" " * (1024 * 1024 + 1))
        result = self.call("--fixture", str(self.fixture))
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
