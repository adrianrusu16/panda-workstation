"""Real filesystem transactions with injected failures and process interruption."""

import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

COMMON = Path(__file__).resolve().parents[1] / "theme/panda/common"
sys.path.insert(0, str(COMMON))
from selection import Decision
from state import ThemeState, read_state


def snapshot(root):
    return {str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mode, p.stat().st_mtime_ns)
            for p in root.rglob("*") if p.is_file() and not p.is_symlink()
            and "panda-transactions" not in p.parts}


class TransactionContracts(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec("transaction"), "Phase 3A transaction missing")
        self.api = importlib.import_module("transaction")
        self.fs = importlib.import_module("fixture_fs")
        self.temp = tempfile.TemporaryDirectory(prefix="panda-theme-fixture-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fs.initialize_fixture(self.root)
        self.config, self.state = self.root / "config", self.root / "state"
        self.candidate = ThemeState("manual", "gothic", "gothic", "legacy")
        self.original = ThemeState("manual", "hybrid", "hybrid", "legacy")

    def switch(self, candidate=None, **options):
        return self.api.switch_theme(candidate or self.candidate, self.config, self.state, **options)

    def establish(self):
        self.assertTrue(self.switch(self.original).success)

    def test_success_commits_four_fields_and_separate_reason_after_verification(self):
        from adapters.shell import ShellAdapter
        before_commit = []
        original_verify = ShellAdapter.verify

        def verify(adapter, prepared):
            before_commit.append(read_state(self.config / "panda/theme-state.toml"))
            return original_verify(adapter, prepared)

        with patch.object(ShellAdapter, "verify", verify):
            result = self.switch()
        self.assertTrue(result.success, result.warnings)
        self.assertEqual(result.active, "gothic")
        self.assertTrue(before_commit)
        self.assertTrue(all(value is None for value in before_commit))
        self.assertEqual(read_state(self.config / "panda/theme-state.toml"), self.candidate)
        import tomllib
        reason = tomllib.loads((self.config / "panda/theme-decision.toml").read_text())
        self.assertEqual(reason["active"], "gothic")
        self.assertEqual(reason["reason"], "explicit manual command")
        self.assertTrue(any("unverified" in warning for warning in result.warnings))

    def test_repeat_keeps_managed_bytes_modes_and_timestamps(self):
        self.assertTrue(self.switch().success)
        before = snapshot(self.root)
        self.assertTrue(self.switch().success)
        self.assertEqual(snapshot(self.root), before)

    def test_planning_and_dry_run_create_no_files_locks_or_backups(self):
        before = snapshot(self.root)
        tree = sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*"))
        plan = self.api.prepare_switch(self.candidate, self.config, self.state)
        self.assertGreaterEqual(len(plan.entries), 9)
        self.assertEqual(snapshot(self.root), before)
        self.assertEqual(sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*")), tree)

    def test_render_failure_leaves_every_target_untouched(self):
        from adapters.terminals import TerminalAdapter
        before = snapshot(self.root)
        with patch.object(TerminalAdapter, "prepare", side_effect=ValueError("render failure")):
            result = self.switch()
        self.assertFalse(result.success)
        self.assertEqual(snapshot(self.root), before)
        self.assertFalse((self.state / "panda-transactions").exists())

    def test_apply_verify_refresh_and_state_commit_failures_restore_old_snapshot(self):
        from adapters.shell import ShellAdapter
        from adapters.base import Outcome
        self.establish()
        before = snapshot(self.root)
        for method in ("apply", "verify", "refresh"):
            with self.subTest(method=method):
                with patch.object(ShellAdapter, method, return_value=Outcome(False, "controlled failure")):
                    result = self.switch()
                self.assertFalse(result.success)
                self.assertEqual(result.active, "hybrid")
                self.assertEqual(result.rollback_status, "restored")
                self.assertEqual(snapshot(self.root), before)
        original_write = self.fs.FixtureFS.replace

        def fail_commit(fs, relative, image, **kwargs):
            if relative == "config/panda/theme-state.toml" and image and b"gothic" in image.content:
                raise OSError("state commit failed")
            return original_write(fs, relative, image, **kwargs)

        with patch.object(self.fs.FixtureFS, "replace", fail_commit):
            result = self.switch()
        self.assertFalse(result.success)
        self.assertEqual(snapshot(self.root), before)

    def test_rollback_removes_only_new_files_and_preserves_unrelated_content(self):
        from adapters.shell import ShellAdapter
        from adapters.base import Outcome
        self.config.mkdir()
        unrelated = self.config / "kitty.conf"
        unrelated.write_bytes(b"user font and workflow\x00")
        before = snapshot(self.root)
        with patch.object(ShellAdapter, "verify", return_value=Outcome(False, "failure")):
            result = self.switch()
        self.assertFalse(result.success)
        self.assertEqual(snapshot(self.root), before)
        self.assertFalse((self.config / "panda").exists())

    def test_stale_plan_external_edits_are_rejected_before_target_writes(self):
        self.establish()
        plan = self.api.prepare_switch(self.candidate, self.config, self.state)
        target = self.config / "panda/generated/kitty.conf"
        target.write_bytes(b"external edit")
        before = snapshot(self.root)
        result = self.switch(plan=plan)
        self.assertFalse(result.success)
        self.assertEqual(snapshot(self.root), before)

    def test_supplied_plans_are_preview_only_and_rejected_without_any_writes(self):
        from dataclasses import replace
        variants = {
            "stripped execution": lambda p: replace(p, prepared=(), adapters=()),
            "valid preview": lambda p: p,
            "empty adapters": lambda p: replace(p, adapters=()),
            "missing prepared item": lambda p: replace(p, prepared=p.prepared[1:]),
            "missing entry": lambda p: replace(p, entries=p.entries[1:]),
            "reordered entries": lambda p: replace(p, entries=tuple(reversed(p.entries))),
            "reordered adapters": lambda p: replace(p, adapters=tuple(reversed(p.adapters))),
            "mismatched rendered data": lambda p: replace(p, prepared=(replace(p.prepared[0], content=b"forged"), *p.prepared[1:])),
            "mismatched target": lambda p: replace(p, prepared=(replace(p.prepared[0], relative="config/unrelated"), *p.prepared[1:])),
            "mismatched image": lambda p: replace(p, entries=(replace(p.entries[0], after=replace(p.entries[0].after, content=b"forged")), *p.entries[1:])),
            "mismatched metadata": lambda p: replace(p, entries=(replace(p.entries[0], after=replace(p.entries[0].after, mode=0o666)), *p.entries[1:])),
            "mismatched candidate": lambda p: replace(p, candidate=self.original),
            "mismatched cleanup": lambda p: replace(p, created_dirs=("config/unrelated",)),
        }
        for label, mutate in variants.items():
            with self.subTest(plan=label), tempfile.TemporaryDirectory(prefix="panda-theme-fixture-", dir="/tmp") as directory:
                root = Path(directory)
                self.fs.initialize_fixture(root)
                config, state = root / "config", root / "state"
                supplied = mutate(self.api.prepare_switch(self.candidate, config, state))
                before = snapshot(root)
                tree = sorted(str(p.relative_to(root)) for p in root.rglob("*"))
                result = self.api.switch_theme(self.candidate, config, state, plan=supplied)
                self.assertFalse(result.success)
                self.assertEqual(result.rollback_status, "not-started")
                self.assertEqual(snapshot(root), before)
                self.assertEqual(sorted(str(p.relative_to(root)) for p in root.rglob("*")), tree)
                self.assertIsNone(read_state(config / "panda/theme-state.toml"))
                self.assertFalse((state / "panda-transactions").exists())

    def test_preview_then_fresh_transaction_applies_all_six_fragments(self):
        preview = self.api.prepare_switch(self.candidate, self.config, self.state)
        self.assertEqual(len(preview.prepared), 6)
        result = self.switch()
        self.assertTrue(result.success, result.warnings)
        self.assertEqual(read_state(self.config / "panda/theme-state.toml"), self.candidate)
        for item in preview.prepared:
            self.assertEqual((self.root / item.relative).read_bytes(), item.content)
        journal = json.loads((self.state / "panda-transactions/journal.json").read_bytes())
        self.assertEqual(journal["payload"]["phase"], "committed")

    def test_fresh_plan_rechecks_external_edits_under_lock_before_target_writes(self):
        from contextlib import contextmanager
        self.establish()
        target = self.config / "panda/generated/kitty.conf"
        lock = self.api._lock
        expected = None

        @contextmanager
        def changed_under_lock(fs):
            nonlocal expected
            with lock(fs):
                target.write_bytes(b"edit after preparation")
                expected = snapshot(self.root)
                yield

        with patch.object(self.api, "_lock", changed_under_lock):
            result = self.switch()
        self.assertFalse(result.success)
        self.assertEqual(result.rollback_status, "not-started")
        self.assertEqual(snapshot(self.root), expected)
        self.assertEqual(read_state(self.config / "panda/theme-state.toml"), self.original)

    def test_external_edit_during_failure_is_never_overwritten_by_restore(self):
        from adapters.shell import ShellAdapter
        from adapters.base import Outcome
        self.establish()

        def fail(adapter, prepared):
            (self.config / "panda/generated/ghostty.conf").write_bytes(b"later user edit")
            return Outcome(False, "verification failed")

        with patch.object(ShellAdapter, "verify", fail):
            result = self.switch()
        self.assertFalse(result.success)
        self.assertEqual(result.rollback_status, "incomplete")
        self.assertEqual((self.config / "panda/generated/ghostty.conf").read_bytes(), b"later user edit")
        self.assertEqual(read_state(self.config / "panda/theme-state.toml"), self.original)
        self.assertTrue((self.state / "panda-transactions/journal.json").is_file())
        self.assertFalse(self.api.recover(self.config, self.state).success)

    def test_symlink_parent_file_directory_fifo_and_hardlink_conflicts_fail_without_writes(self):
        self.establish()
        path = self.config / "panda/generated/kitty.conf"
        original = path.read_bytes()
        outside = self.root / "unrelated"
        outside.write_bytes(b"untouched")
        for kind in ("symlink", "directory", "fifo", "hardlink"):
            with self.subTest(kind=kind):
                path.unlink()
                if kind == "symlink":
                    path.symlink_to(outside)
                elif kind == "directory":
                    path.mkdir()
                elif kind == "fifo":
                    os.mkfifo(path)
                else:
                    os.link(outside, path)
                result = self.switch()
                self.assertFalse(result.success)
                self.assertEqual(outside.read_bytes(), b"untouched")
                if kind == "directory":
                    path.rmdir()
                else:
                    path.unlink()
                path.write_bytes(original)
        generated = self.config / "panda/generated"
        saved = self.config / "panda/saved"
        generated.rename(saved)
        generated.symlink_to(saved, target_is_directory=True)
        before = snapshot(saved)
        self.assertFalse(self.switch().success)
        self.assertEqual(snapshot(saved), before)

    def test_unknown_ownership_and_malformed_state_fail_before_any_mutation(self):
        target = self.config / "panda/generated/kitty.conf"
        target.parent.mkdir(parents=True)
        target.write_text("unowned data")
        before = snapshot(self.root)
        self.assertFalse(self.switch().success)
        self.assertEqual(snapshot(self.root), before)
        target.unlink()
        state = self.config / "panda/theme-state.toml"
        state.write_text("mode = [")
        before = snapshot(self.root)
        self.assertFalse(self.switch().success)
        self.assertEqual(snapshot(self.root), before)

    def test_read_only_target_is_diagnostic_and_preserves_permissions(self):
        self.establish()
        target = self.config / "panda/generated/kitty.conf"
        target.chmod(0o400)
        before = snapshot(self.root)
        result = self.switch()
        self.assertFalse(result.success)
        self.assertEqual(result.active, "hybrid", "failed preparation must retain the established selection")
        self.assertEqual(snapshot(self.root), before)

    def test_lock_prevents_a_second_process_transaction(self):
        self.establish()
        import fcntl
        lock = self.state / "panda-transactions/lock"
        with lock.open("rb") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            code = ("import sys; sys.path.insert(0, sys.argv[1]); from transaction import switch_theme; "
                    "from state import ThemeState; from pathlib import Path; "
                    "r=switch_theme(ThemeState('manual','gothic','gothic','legacy'), "
                    "Path(sys.argv[2])/'config',Path(sys.argv[2])/'state'); "
                    "print(r.success); print(r.warnings)")
            result = subprocess.run([sys.executable, "-B", "-c", code, str(COMMON), str(self.root)],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("False", result.stdout)
            self.assertIn("locked", result.stdout)
            self.assertEqual(read_state(self.config / "panda/theme-state.toml"), self.original)

    def test_process_exit_after_replace_is_recovered_in_a_new_process(self):
        self.establish()
        before = snapshot(self.root)
        code = """import os, sys
sys.path.insert(0, sys.argv[1])
from pathlib import Path
from fixture_fs import FixtureFS
from transaction import switch_theme
from state import ThemeState
original = FixtureFS.replace
def interrupted(fs, relative, image, **kwargs):
    original(fs, relative, image, **kwargs)
    if relative == 'config/panda/generated/kitty.conf':
        os._exit(73)
FixtureFS.replace = interrupted
root = Path(sys.argv[2])
switch_theme(ThemeState('manual','gothic','gothic','legacy'), root/'config', root/'state')
"""
        result = subprocess.run([sys.executable, "-B", "-c", code, str(COMMON), str(self.root)],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 73, result.stderr)
        self.assertFalse(self.switch().success, "interrupted journal must block new transactions")
        recovered = self.api.recover(self.config, self.state)
        self.assertTrue(recovered.success, recovered.warnings)
        self.assertEqual(snapshot(self.root), before)

    def test_missing_corrupt_or_traversing_journal_never_authorizes_restore(self):
        self.establish()
        journal = self.state / "panda-transactions/journal.json"
        original = journal.read_bytes()
        for content in (b"broken", b"{}", b'{"entries":[{"path":"../../outside"}]}'):
            journal.write_bytes(content)
            before = snapshot(self.root)
            result = self.api.recover(self.config, self.state)
            self.assertFalse(result.success)
            self.assertEqual(snapshot(self.root), before)
        journal.write_bytes(original)
        journal.unlink()
        self.assertTrue(self.api.recover(self.config, self.state).success)

    def test_roots_and_low_level_paths_cannot_escape_enrollment(self):
        for config in (Path.home() / ".config", self.root / "config/../config", self.root / "other"):
            with self.subTest(config=config):
                self.assertFalse(self.api.switch_theme(self.candidate, config, self.state).success)
        with self.fs.FixtureFS(self.root) as fs:
            for relative in ("../outside", "/tmp/outside", "config/../../outside", "config//bad"):
                with self.subTest(relative=relative), self.assertRaises(ValueError):
                    fs.read(relative)
        with tempfile.TemporaryDirectory(prefix="unapproved-") as directory:
            with self.assertRaises(ValueError):
                self.fs.initialize_fixture(Path(directory))
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_auto_reason_must_match_candidate_and_preserves_last_manual(self):
        candidate = ThemeState("auto", "pandawave", "gothic", "legacy")
        decision = Decision("pandawave", "PandaWave project context", "project")
        self.assertTrue(self.switch(candidate, decision=decision).success)
        self.assertEqual(read_state(self.config / "panda/theme-state.toml"), candidate)
        before = snapshot(self.root)
        self.assertFalse(self.switch(candidate, decision=Decision("cyber", "gaming context", "gaming")).success)
        self.assertEqual(snapshot(self.root), before)

    def test_late_external_edit_after_refresh_blocks_state_commit(self):
        from adapters.shell import ShellAdapter
        self.establish()
        original_refresh = ShellAdapter.refresh

        def refresh(adapter):
            if adapter.component == "fish":
                (self.config / "panda/generated/kitty.conf").write_bytes(b"edit after validation")
            return original_refresh(adapter)

        with patch.object(ShellAdapter, "refresh", refresh):
            result = self.switch()
        self.assertFalse(result.success)
        self.assertEqual(read_state(self.config / "panda/theme-state.toml"), self.original)
        self.assertEqual((self.config / "panda/generated/kitty.conf").read_bytes(), b"edit after validation")

    def test_failed_restore_is_distinct_and_a_retained_backup_can_be_recovered(self):
        from adapters.shell import ShellAdapter
        from adapters.base import Outcome
        self.establish()
        before = snapshot(self.root)
        with patch.object(ShellAdapter, "verify", return_value=Outcome(False, "verify failed")), \
                patch.object(ShellAdapter, "restore", return_value=Outcome(False, "restore failed")):
            result = self.switch()
        self.assertFalse(result.success)
        self.assertEqual(result.rollback_status, "incomplete")
        self.assertTrue(self.api.recover(self.config, self.state).success)
        self.assertEqual(snapshot(self.root), before)

    def test_keyboard_interrupt_restores_before_propagating(self):
        from adapters.shell import ShellAdapter
        self.establish()
        before = snapshot(self.root)
        with patch.object(ShellAdapter, "apply", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.switch()
        self.assertEqual(snapshot(self.root), before)

    def test_final_journal_commit_failure_restores_state_and_reason(self):
        self.establish()
        before = snapshot(self.root)
        write = self.api._journal

        def journal(fs, entries, directories, phase):
            if phase == "committed":
                raise OSError("journal commit failed")
            return write(fs, entries, directories, phase)

        with patch.object(self.api, "_journal", journal):
            result = self.switch()
        self.assertFalse(result.success)
        self.assertEqual(result.rollback_status, "restored")
        self.assertEqual(snapshot(self.root), before)

    def test_missing_optional_fixture_target_is_explicit_but_required_absence_fails(self):
        from adapters.base import Outcome
        adapters = self.api.default_adapters()
        adapters[-1].critical = False
        adapters[-1].probe = lambda: Outcome(False, "missing")
        result = self.switch(adapters=adapters)
        self.assertTrue(result.success, result.warnings)
        self.assertTrue(any("fish: optional target unavailable; not verified" in warning for warning in result.warnings))
        self.assertFalse((self.config / "panda/generated/fish.fish").exists())
        adapters[-1].critical = True
        before = snapshot(self.root)
        self.assertFalse(self.switch(adapters=adapters).success)
        self.assertEqual(snapshot(self.root), before)

    def test_root_symlink_read_only_directory_and_unapproved_destinations_are_rejected(self):
        from adapters.terminals import TerminalAdapter
        from dataclasses import replace
        original = TerminalAdapter.prepare

        def escape(adapter, theme, staging):
            return replace(original(adapter, theme, staging), relative="config/unrelated")

        before = snapshot(self.root)
        with patch.object(TerminalAdapter, "prepare", escape):
            self.assertFalse(self.switch().success)
        self.assertEqual(snapshot(self.root), before)
        self.config.mkdir()
        self.config.chmod(0o500)
        self.assertFalse(self.switch().success)
        self.config.chmod(0o700)
        alias = self.root.parent / (self.root.name + "-alias")
        alias.symlink_to(self.root, target_is_directory=True)
        self.addCleanup(alias.unlink)
        self.assertFalse(self.api.switch_theme(self.candidate, alias / "config", alias / "state").success)

    def test_metadata_edits_lock_symlinks_and_journal_symlinks_do_not_authorize_writes(self):
        self.establish()
        unrelated = self.root / "unrelated"
        unrelated.write_bytes(b"outside remains")
        for name in ("lock", "journal.json"):
            path = self.state / "panda-transactions" / name
            original = path.read_bytes()
            path.unlink()
            path.symlink_to(unrelated)
            before = snapshot(self.root)
            self.assertFalse(self.switch().success)
            self.assertEqual(snapshot(self.root), before)
            self.assertTrue(path.is_symlink())
            path.unlink()
            path.write_bytes(original)
            path.chmod(0o600)

    def test_safe_existing_modes_are_preserved_and_legacy_state_is_not_migrated(self):
        self.config.mkdir()
        (self.config / "panda").mkdir()
        path = self.config / "panda/theme-state.toml"
        path.write_text('mode="manual"\nactive="hybrid"\nlast_manual="hybrid"\ncontext="legacy"\n')
        path.chmod(0o640)
        result = self.switch()
        self.assertTrue(result.success, result.warnings)
        self.assertEqual(path.stat().st_mode & 0o777, 0o640)
        import tomllib
        self.assertEqual(set(tomllib.loads(path.read_text())), {"mode", "active", "last_manual", "context"})

    def test_recovery_rejects_validly_encoded_but_incomplete_backup_metadata(self):
        import hashlib
        self.establish()
        journal = self.state / "panda-transactions/journal.json"
        original = json.loads(journal.read_bytes())
        for mutation in ("duplicate", "absolute", "missing-image", "invalid-mode"):
            data = json.loads(json.dumps(original["payload"]))
            data["phase"] = "prepared"
            if mutation == "duplicate":
                data["entries"][0] = data["entries"][1]
            elif mutation == "absolute":
                data["entries"][0]["path"] = "/tmp/outside"
            elif mutation == "missing-image":
                data["entries"][0]["after"] = None
            else:
                data["entries"][0]["after"]["mode"] = -1
            encoded = (json.dumps(data, sort_keys=True, indent=2) + "\n").encode()
            journal.write_text(json.dumps({"payload": data, "sha256": hashlib.sha256(encoded).hexdigest()}))
            before = snapshot(self.root)
            self.assertFalse(self.api.recover(self.config, self.state).success)
            self.assertEqual(snapshot(self.root), before)

    def test_oversized_sidecar_is_rejected_before_an_unrecoverable_snapshot(self):
        self.establish()
        reason = self.config / "panda/theme-decision.toml"
        reason.write_bytes(reason.read_bytes() + b" " * 70000)
        before = snapshot(self.root)
        self.assertFalse(self.switch().success)
        self.assertEqual(snapshot(self.root), before)

    def test_no_available_components_cannot_establish_a_successful_selection(self):
        from adapters.base import Outcome
        adapters = self.api.default_adapters()
        for adapter in adapters:
            adapter.critical = False
            adapter.probe = lambda: Outcome(False, "not available")
        result = self.switch(adapters=adapters)
        self.assertFalse(result.success)
        self.assertFalse((self.config / "panda/theme-state.toml").exists())

    def test_oversized_proposed_state_or_reason_fails_before_any_writes(self):
        before = snapshot(self.root)
        for candidate, decision in (
                (ThemeState("auto", "hybrid", "", ""), Decision("hybrid", "x" * 70000, "fallback")),
                (ThemeState("manual", "hybrid", "hybrid", "x" * 70000), None)):
            with self.subTest(context=len(candidate.context)):
                result = self.switch(candidate, decision=decision)
                self.assertFalse(result.success)
                self.assertEqual(result.rollback_status, "not-started")
                self.assertEqual(snapshot(self.root), before)
                self.assertFalse((self.state / "panda-transactions").exists())

    def test_recovery_refuses_semantically_incomplete_backup_even_with_valid_checksum(self):
        import hashlib
        self.assertTrue(self.switch().success)
        journal = self.state / "panda-transactions/journal.json"
        data = json.loads(journal.read_bytes())["payload"]
        data["phase"] = "prepared"
        data["entries"] = [entry for entry in data["entries"] if entry["path"] != "config/panda/generated/ghostty.conf"]
        encoded = (json.dumps(data, sort_keys=True, indent=2) + "\n").encode()
        journal.write_text(json.dumps({"payload": data, "sha256": hashlib.sha256(encoded).hexdigest()}))
        before = snapshot(self.root)
        result = self.api.recover(self.config, self.state)
        self.assertFalse(result.success)
        self.assertEqual(snapshot(self.root), before)

    def test_recovery_timestamp_overflow_is_refused_before_any_restoration(self):
        import hashlib
        self.establish()
        self.assertTrue(self.switch().success)
        journal = self.state / "panda-transactions/journal.json"
        data = json.loads(journal.read_bytes())["payload"]
        data["phase"] = "prepared"
        data["entries"][0]["before"]["mtime_ns"] = 10 ** 40
        encoded = (json.dumps(data, sort_keys=True, indent=2) + "\n").encode()
        journal.write_text(json.dumps({"payload": data, "sha256": hashlib.sha256(encoded).hexdigest()}))
        before = snapshot(self.root)
        result = self.api.recover(self.config, self.state)
        self.assertFalse(result.success)
        self.assertEqual(snapshot(self.root), before)

    def test_unsupported_original_mode_is_rejected_before_journaling(self):
        self.establish()
        (self.config / "panda/generated/ghostty.conf").chmod(0o4600)
        before = snapshot(self.root)
        result = self.switch()
        self.assertFalse(result.success)
        self.assertEqual(snapshot(self.root), before)

    def test_rejected_directory_traversals_close_their_open_descriptors(self):
        self.config.mkdir()
        self.config.chmod(0o500)
        with self.fs.FixtureFS(self.root) as fs:
            before = len(list(Path("/proc/self/fd").iterdir()))
            for _ in range(10):
                with self.assertRaises(ValueError):
                    fs.read("config/panda/theme-state.toml")
            self.assertEqual(len(list(Path("/proc/self/fd").iterdir())), before)
        self.config.chmod(0o700)


if __name__ == "__main__":
    unittest.main()
