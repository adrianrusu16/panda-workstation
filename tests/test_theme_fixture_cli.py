"""Explicit opt-in fixture CLI; ordinary live commands remain disabled."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "theme/panda/common/cli.py"
ENTRY = ROOT / "theme/panda/common/scripts/panda-theme.fish"


class FixtureCLIContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="panda-theme-fixture-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = {**os.environ, "HOME": str(self.root / "home"),
                    "XDG_CONFIG_HOME": str(self.root / "config"),
                    "XDG_STATE_HOME": str(self.root / "state"),
                    "XDG_DATA_HOME": str(self.root / "data"),
                    "XDG_CACHE_HOME": str(self.root / "cache"), "PYTHONDONTWRITEBYTECODE": "1"}

    def call(self, *args, fish=False):
        command = ["fish", "--no-config", str(ENTRY)] if fish else [sys.executable, "-B", str(CLI)]
        return subprocess.run([*command, *args], env=self.env, cwd="/tmp", capture_output=True, text=True, timeout=10)

    def tree(self):
        return {str(p.relative_to(self.root)): (p.read_bytes(), p.stat().st_mode, p.stat().st_mtime_ns)
                for p in self.root.rglob("*") if p.is_file()}

    def enroll(self):
        result = self.call("init-fixture", "--fixture-root", str(self.root), "--allow-fixture-writes")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_fixture_apply_requires_both_explicit_root_and_opt_in(self):
        for args in (("init-fixture", "--fixture-root", str(self.root)),
                     ("gothic", "--allow-fixture-writes"),
                     ("gothic", "--fixture-root", str(self.root))):
            result = self.call(*args)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(self.tree(), {})
        self.enroll()
        result = self.call("wave", "--fixture-root", str(self.root), "--allow-fixture-writes", "--no-time")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("fixture", result.stdout)
        self.assertIn("pandawave", result.stdout)
        self.assertIn("unverified", result.stdout)

    def test_fixture_dry_run_lists_managed_changes_without_any_writes(self):
        self.enroll()
        before = self.tree()
        result = self.call("gothic", "--fixture-root", str(self.root), "--dry-run", "--no-time")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("config/panda/generated/ghostty.conf", result.stdout)
        self.assertIn("not applied", result.stdout)
        self.assertEqual(self.tree(), before)
        self.assertFalse((self.root / "state").exists())

    def test_fixture_status_reason_and_recovery_report_runtime_unverified(self):
        self.enroll()
        result = self.call("auto", "--fixture-root", str(self.root), "--allow-fixture-writes", "--focus", "--no-time")
        self.assertEqual(result.returncode, 0, result.stderr)
        status = self.call("status", "--fixture-root", str(self.root))
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertIn("focus context", status.stdout)
        self.assertIn("unverified", status.stdout)
        before = self.tree()
        doctor = self.call("doctor", "--fixture-root", str(self.root))
        self.assertEqual(doctor.returncode, 0, doctor.stderr)
        self.assertIn("Phase 3B", doctor.stdout)
        self.assertIn("pending", doctor.stdout)
        self.assertEqual(self.tree(), before)
        recovered = self.call("doctor", "--recover", "--fixture-root", str(self.root), "--allow-fixture-writes")
        self.assertEqual(recovered.returncode, 0, recovered.stderr)
        self.assertNotEqual(self.call("doctor", "--recover").returncode, 0)

    def test_live_rejection_and_invalid_option_combinations_do_not_write(self):
        self.enroll()
        before = self.tree()
        for args in (("cyber",), ("doctor", "--allow-fixture-writes"),
                     ("status", "--recover"),
                     ("wave", "--fixture-root", str(self.root), "--allow-fixture-writes", "--state", "/tmp/other"),
                     ("init-fixture", "--fixture-root", str(self.root), "--allow-fixture-writes", "--dry-run"),
                     ("doctor", "--fixture-root", str(self.root), "--allow-fixture-writes")):
            with self.subTest(args=args):
                result = self.call(*args)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.tree(), before)
                self.assertNotIn("Traceback", result.stderr)

    def test_fish_wrapper_forwards_fixture_options_and_negative_status(self):
        # Initialize Fish startup separately; it creates XDG files on its own.
        subprocess.run(["fish", "--no-config", "-c", "true"], env=self.env,
                       capture_output=True, check=True)
        self.enroll()
        result = self.call("cyber", "--fixture-root", str(self.root), "--allow-fixture-writes", "--no-time", fish=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("cyber", result.stdout)
        self.assertNotEqual(self.call("cyber", fish=True).returncode, 0)


if __name__ == "__main__":
    unittest.main()
