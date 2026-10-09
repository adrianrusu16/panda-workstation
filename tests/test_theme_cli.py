"""Real CLI/Fish processes: selection-only output and zero fixture writes."""

from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime
import importlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
COMMON = ROOT / "theme/panda/common"
CLI = COMMON / "cli.py"
FISH = COMMON / "scripts/panda-theme.fish"
sys.path.insert(0, str(COMMON))


class ThemeCLIContracts(unittest.TestCase):
    def setUp(self):
        self.assertTrue(CLI.is_file(), "Phase 2 preview CLI is not implemented")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.config = self.home / "config"
        self.env = {**os.environ, "HOME": str(self.home), "XDG_CONFIG_HOME": str(self.config),
                    "XDG_STATE_HOME": str(self.home / "state"),
                    "XDG_DATA_HOME": str(self.home / "data"),
                    "XDG_CACHE_HOME": str(self.home / "cache"), "PYTHONDONTWRITEBYTECODE": "1"}
        self.state = self.config / "panda/theme-state.toml"
        (self.home / "unrelated").write_bytes(b"preserve me\x00")

    def fixture(self, mode="manual", active="gothic", last_manual="gothic", context=""):
        self.state.parent.mkdir(parents=True)
        self.state.write_text(f'mode = "{mode}"\nactive = "{active}"\n'
                              f'last_manual = "{last_manual}"\ncontext = "{context}"\n')

    def snapshot(self):
        return {str(p.relative_to(self.home)):
                ("link", os.readlink(p)) if p.is_symlink() else
                ("dir", p.stat().st_mode, p.stat().st_mtime_ns) if p.is_dir() else
                ("file", p.read_bytes(), p.stat().st_mode, p.stat().st_mtime_ns)
                for p in self.home.rglob("*")}

    def run_cli(self, *args, fish=False, env=None):
        if fish:
            # Fish creates its own XDG directories even for `--no-config -c true`.
            # Establish shell startup separately, then measure the actual entry.
            startup = subprocess.run(["fish", "--no-config", "-c", "true"],
                                     env=env or self.env, capture_output=True, text=True)
            self.assertEqual(startup.returncode, 0, startup.stderr)
        before = self.snapshot()
        command = ["fish", "--no-config", str(FISH)] if fish else [sys.executable, "-B", str(CLI)]
        result = subprocess.run([*command, *args], cwd=self.home,
                                env=env or self.env, capture_output=True, text=True, timeout=10)
        self.assertEqual(self.snapshot(), before, result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        return result

    def test_list_has_exact_five_manifest_names_and_wave_alias(self):
        result = self.run_cli("list")
        self.assertEqual(result.returncode, 0, result.stderr)
        for name in ("Panda Minimal", "Panda Cyber", "Panda Gothic", "Panda Hybrid", "PandaWave Pulse"):
            self.assertIn(name, result.stdout)
        self.assertIn("wave", result.stdout)
        self.assertEqual(len([line for line in result.stdout.splitlines() if "Panda " in line
                              or "PandaWave" in line]), 5)

    def test_absent_status_does_not_invent_active_theme(self):
        result = self.run_cli("status")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("mode: unset", result.stdout)
        self.assertIn("recorded active: none", result.stdout)
        self.assertIn("live appearance: unverified", result.stdout)

    def test_status_reports_legacy_reason_unavailable_and_redacts_context(self):
        self.fixture(context="/private/project/SECRET")
        result = self.run_cli("status")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("mode: manual", result.stdout)
        self.assertIn("recorded active: gothic", result.stdout)
        self.assertIn("reason: historical reason unavailable", result.stdout)
        self.assertNotIn("SECRET", result.stdout + result.stderr)

    def test_auto_explain_is_repeatable_and_manual_mode_blocks_candidate(self):
        self.fixture()
        args = ("auto", "--explain", "--project", "pandawave", "--gaming", "--focus", "--no-time")
        result = self.run_cli(*args)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, self.run_cli(*args).stdout)
        for text in ("candidate: pandawave", "source: project", "reason: PandaWave project context",
                     "manual blocks candidate: yes", "effective selection: gothic", "mode: manual"):
            self.assertIn(text, result.stdout)

    def test_auto_dry_run_explicitly_proposes_return_without_persisting(self):
        self.fixture()
        result = self.run_cli("auto", "--dry-run", "--focus", "--no-time")
        self.assertEqual(result.returncode, 0, result.stderr)
        for text in ("proposed mode: auto", "selected candidate: minimal", "last manual: gothic",
                     "not applied; state unchanged"):
            self.assertIn(text, result.stdout)

    def test_manual_names_and_cycles_are_only_candidates(self):
        for command, want in (("minimal", "minimal"), ("cyber", "cyber"),
                              ("gothic", "gothic"), ("hybrid", "hybrid"),
                              ("wave", "pandawave"), ("pandawave", "pandawave"),
                              ("next", "minimal"), ("previous", "pandawave")):
            result = self.run_cli(command, "--dry-run", "--no-time")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(f"selected candidate: {want}", result.stdout)
            self.assertIn("proposed mode: manual", result.stdout)
            self.assertIn("not applied; state unchanged", result.stdout)

    def test_all_live_commands_fail_before_writes(self):
        self.fixture()
        for command in ("minimal", "cyber", "gothic", "hybrid", "wave", "pandawave",
                        "auto", "next", "previous"):
            result = self.run_cli(command)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Phase 3", result.stderr)
            self.assertIn("--dry-run", result.stderr)

    def test_unknown_commands_and_malformed_context_fail_without_echoing_values(self):
        self.fixture()
        for args in (("unknown",), ("auto", "--dry-run", "--special", "unknown"),
                     ("auto", "--explain", "--project", "/private/SECRET"),
                     ("auto", "--explain", "--now", "bad-clock"),
                     ("auto", "--explain", "--now", "2026-10-09T07:00", "--no-time"),
                     ("cyber", "--explain"), ("status", "--dry-run")):
            result = self.run_cli(*args)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("SECRET", result.stdout + result.stderr)

    def test_malformed_state_fails_without_partial_changes(self):
        self.fixture()
        for content in ('mode = "broken"\n', "mode = " + "[" * 2000 + "0" + "]" * 2000,
                        "mode = " + "1" * 5000):
            self.state.write_text(content)
            for args in (("status",), ("doctor",), ("auto", "--explain"), ("wave", "--dry-run")):
                result = self.run_cli(*args)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("ERROR", result.stderr)

    def test_doctor_reports_only_verified_selection_components(self):
        result = self.run_cli("doctor")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("palettes: 5 valid", result.stdout)
        self.assertIn("state: absent", result.stdout)
        self.assertIn("application adapters: deferred to Phase 3", result.stdout)

    def test_injected_clock_changes_auto_preview_at_boundary(self):
        api = importlib.import_module("cli")
        for hour, want in ((17, "hybrid"), (18, "cyber"), (21, "gothic")):
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = api.main(["auto", "--explain", "--state", str(self.state)],
                                now_provider=lambda: datetime(2026, 10, 9, hour))
            self.assertEqual(code, 0, err.getvalue())
            self.assertIn(f"candidate: {want}", out.getvalue())

    def test_relative_xdg_is_rejected_and_missing_xdg_uses_temporary_home(self):
        bad = self.run_cli("status", env={**self.env, "XDG_CONFIG_HOME": "relative"})
        self.assertNotEqual(bad.returncode, 0)
        env = dict(self.env)
        del env["XDG_CONFIG_HOME"]
        self.assertEqual(self.run_cli("status", env=env).returncode, 0)

    def test_cli_refuses_symlink_state_or_config_parent(self):
        self.fixture()
        target = self.home / "original"
        self.state.rename(target)
        self.state.symlink_to(target)
        self.assertNotEqual(self.run_cli("status").returncode, 0)
        self.state.unlink()
        self.state.parent.rmdir()
        self.state.parent.symlink_to(self.home, target_is_directory=True)
        self.assertNotEqual(self.run_cli("status").returncode, 0)

    def test_fish_entry_forwards_arguments_and_failure_status_from_any_directory(self):
        self.assertTrue(FISH.is_file(), "Fish selection preview entry is missing")
        good = self.run_cli("auto", "--explain", "--now", "2026-10-09T18:00:00+03:00", fish=True)
        self.assertEqual(good.returncode, 0, good.stderr)
        self.assertIn("candidate: cyber", good.stdout)
        self.assertNotEqual(self.run_cli("cyber", fish=True).returncode, 0)


if __name__ == "__main__":
    unittest.main()
