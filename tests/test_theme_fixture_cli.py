"""Explicit opt-in fixture CLI; ordinary live commands remain disabled."""

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "theme/panda/common/cli.py"
ENTRY = ROOT / "theme/panda/common/scripts/panda-theme.fish"
sys.path.insert(0, str(CLI.parent))
import cli
import transaction
from fixture_fs import FixtureFS
from state import read_state


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

    def incomplete_rollback(self, *, corrupt_state=False):
        self.enroll()
        established = self.call("hybrid", "--fixture-root", str(self.root), "--allow-fixture-writes", "--no-time")
        self.assertEqual(established.returncode, 0, established.stderr)
        journal, replace = transaction._journal, FixtureFS.replace

        def fail_committed_journal(fs, entries, directories, phase):
            if phase == "committed":
                raise OSError("injected journal commit failure")
            return journal(fs, entries, directories, phase)

        def fail_state_restore(fs, relative, image, **options):
            if relative == transaction.STATE and image is not None and b"hybrid" in image.content:
                if corrupt_state:
                    (self.root / relative).write_bytes(b"invalid TOML; private fixture text")
                raise OSError("injected state restoration failure")
            return replace(fs, relative, image, **options)

        output, errors = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, self.env), \
                patch.object(transaction, "_journal", fail_committed_journal), \
                patch.object(FixtureFS, "replace", fail_state_restore), \
                redirect_stdout(output), redirect_stderr(errors):
            status = cli.main(["gothic", "--fixture-root", str(self.root), "--allow-fixture-writes", "--no-time"])
        return status, output.getvalue(), errors.getvalue()

    def test_incomplete_rollback_distinguishes_last_good_from_actual_recorded_state(self):
        status, output, errors = self.incomplete_rollback()
        self.assertEqual(status, 1, errors)
        self.assertIn("fixture transaction: failed", output)
        self.assertIn("fixture last known-good selection: hybrid", output)
        self.assertIn("fixture recorded active: gothic", output)
        self.assertNotIn("fixture recorded active: hybrid", output)
        self.assertIn("transaction unverified", output)
        self.assertIn("rollback: incomplete", output)
        self.assertIn("transaction failed (OSError)", output)
        self.assertIn("restoration incomplete; backup retained", output)
        self.assertEqual(read_state(self.root / transaction.STATE).active, "gothic")
        journal = json.loads((self.root / transaction.JOURNAL).read_bytes())
        self.assertEqual(journal["payload"]["phase"], "incomplete")
        recovered = transaction.recover(self.root / "config", self.root / "state")
        self.assertTrue(recovered.success, recovered.warnings)
        self.assertEqual(read_state(self.root / transaction.STATE).active, "hybrid")

    def test_failed_reporting_read_keeps_original_failure_and_retained_backup(self):
        status, output, errors = self.incomplete_rollback(corrupt_state=True)
        self.assertEqual(status, 1, errors)
        self.assertIn("fixture last known-good selection: hybrid", output)
        self.assertIn("fixture recorded active: unknown/unverified", output)
        self.assertNotIn("fixture recorded active: hybrid", output)
        self.assertNotIn("private fixture text", output + errors)
        self.assertIn("rollback: incomplete", output)
        self.assertIn("transaction failed (OSError)", output)
        self.assertIn("restoration incomplete; backup retained", output)
        before = self.tree()
        self.assertFalse(transaction.recover(self.root / "config", self.root / "state").success)
        self.assertEqual(self.tree(), before)

    def test_success_reports_correct_recorded_state(self):
        self.enroll()
        result = self.call("gothic", "--fixture-root", str(self.root), "--allow-fixture-writes", "--no-time")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("fixture transaction: verified", result.stdout)
        self.assertIn("fixture recorded active: gothic", result.stdout)
        self.assertNotIn("fixture last known-good selection:", result.stdout)
        self.assertEqual(read_state(self.root / transaction.STATE).active, "gothic")


if __name__ == "__main__":
    unittest.main()
