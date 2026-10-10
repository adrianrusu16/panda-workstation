"""Ghostty-only simulated transactions, failure injection and fresh-process recovery."""

import copy
import errno
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from live_fixture_support import COMMON, fixture, tree
sys.path.insert(0, str(COMMON))
from state import ThemeState


class LiveTransactionContracts(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec("live_transaction"), "B1 transaction missing")
        self.api = importlib.import_module("live_transaction")
        self.fs = importlib.import_module("live_fs")
        self.enrollment = importlib.import_module("enrollment")
        self.root = fixture(self)
        self.enrollment.enroll_fixture(self.root, version="1.3.1")
        self.candidate = ThemeState("manual", "gothic", "gothic", "")
        self.old = ThemeState("manual", "hybrid", "hybrid", "")

    def switch(self, candidate=None, **kwargs):
        return self.api.switch_simulated(candidate or self.candidate, self.root, **kwargs)

    def managed(self):
        with self.fs.SimulatedLiveFS(self.root) as fs:
            return {path: fs.read(path) for path in self.fs.MANAGED}

    def test_success_is_ghostty_simulation_only_and_never_deploys_hook(self):
        before_source = (self.root / self.fs.SOURCE).read_bytes()
        result = self.switch()
        self.assertTrue(result.success, result.warnings)
        self.assertEqual(result.active, "gothic")
        self.assertIn("unverified", " ".join(result.warnings))
        self.assertEqual((self.root / self.fs.SOURCE).read_bytes(), before_source)
        self.assertEqual((self.root / self.fs.HOOK).read_bytes(), before_source)
        self.assertFalse((self.root / "config/panda/theme-state.toml").exists())
        data = json.loads((self.root / self.fs.SELECTION).read_bytes())
        self.assertEqual(data["scope"], "ghostty-simulation-only")
        self.assertEqual(data["selection"]["active"], "gothic")
        self.assertEqual(json.loads((self.root / self.fs.JOURNAL).read_bytes())["payload"]["phase"], "committed")

    def test_preview_is_write_free_and_supplied_plans_never_execute(self):
        before = tree(self.root)
        plan = self.api.prepare_simulated(self.candidate, self.root)
        self.assertEqual(tree(self.root), before)
        self.assertEqual(len(plan.entries), 4)
        self.assertIn(b"config-file = ?../panda/generated/ghostty.conf", plan.hook_proposal)
        for supplied in (plan, {}, object()):
            result = self.switch(plan=supplied)
            self.assertFalse(result.success)
            self.assertEqual(result.rollback_status, "not-started")
            self.assertEqual(tree(self.root), before)

    def test_missing_or_invalid_enrollment_and_inputs_create_nothing(self):
        marker = self.root / self.fs.MARKER
        original = marker.read_bytes()
        for content in (None, b"{}", b"invalid"):
            if content is None: marker.unlink()
            else: marker.write_bytes(content)
            before = tree(self.root)
            self.assertFalse(self.switch().success)
            self.assertEqual(tree(self.root), before)
        marker.write_bytes(original)
        before = tree(self.root)
        self.assertFalse(self.switch(candidate="gothic").success)
        self.assertEqual(tree(self.root), before)
        self.assertFalse(self.api.switch_simulated(self.candidate, Path.home()).success)
        self.assertEqual(tree(self.root), before)

    def test_source_and_deployed_hook_drift_each_refuse_before_lock_creation(self):
        for relative in (self.fs.SOURCE, self.fs.HOOK):
            path = self.root / relative
            original = path.read_bytes()
            info = path.stat()
            path.write_bytes(original + b"# later edit\n")
            before = tree(self.root)
            self.assertFalse(self.switch().success)
            self.assertEqual(tree(self.root), before)
            path.write_bytes(original)
            os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns))

    def test_repeat_preserves_bytes_modes_mtimes_and_skips_refresh(self):
        self.assertTrue(self.switch().success)
        before = tree(self.root)
        from adapters.live_ghostty import GhosttyModel
        with patch.object(GhosttyModel, "refresh", side_effect=AssertionError("repeat refresh")):
            self.assertTrue(self.switch().success)
        self.assertEqual(tree(self.root), before)

    def test_failure_at_each_write_boundary_restores_recognized_old_images(self):
        self.assertTrue(self.switch(self.old).success)
        before = self.managed()
        original = self.fs.SimulatedLiveFS.replace
        for target in (*self.fs.MANAGED, self.fs.JOURNAL):
            for after_write in (False, True):
                calls = 0
                def fail(fs, relative, image, *, expected):
                    nonlocal calls
                    if relative == target:
                        calls += 1
                        # Final commit journal, rather than preparation.
                        fail_now = calls == (2 if target == self.fs.JOURNAL else 1)
                        if fail_now and not after_write: raise OSError("injected")
                        result = original(fs, relative, image, expected=expected)
                        if fail_now and after_write: raise OSError("injected")
                        return result
                    return original(fs, relative, image, expected=expected)
                with self.subTest(target=target, after_write=after_write), patch.object(
                        self.fs.SimulatedLiveFS, "replace", fail):
                    result = self.switch()
                self.assertFalse(result.success)
                self.assertEqual(result.rollback_status, "restored", result.warnings)
                self.assertEqual(self.managed(), before)

    def test_render_verify_and_refresh_failures_cannot_commit_selection(self):
        from adapters.live_ghostty import GhosttyModel
        from adapters.base import Outcome
        for method in ("prepare", "verify", "refresh"):
            before = self.managed()
            with self.subTest(method=method), patch.object(
                    GhosttyModel, method, side_effect=ValueError("injected")):
                result = self.switch()
            self.assertFalse(result.success)
            self.assertEqual(self.managed(), before)

    def test_under_lock_drift_is_refused_and_late_edits_are_preserved(self):
        from adapters.live_ghostty import GhosttyModel
        original = GhosttyModel.verify
        def edit(adapter, fs, prepared):
            outcome = original(adapter, fs, prepared)
            (self.root / self.fs.TARGET).write_bytes(b"external change\n")
            return outcome
        with patch.object(GhosttyModel, "verify", edit):
            result = self.switch()
        self.assertFalse(result.success)
        self.assertEqual(result.rollback_status, "incomplete")
        self.assertEqual((self.root / self.fs.TARGET).read_bytes(), b"external change\n")
        before = tree(self.root)
        recovery = self.api.recover_simulated(self.root)
        self.assertFalse(recovery.success)
        self.assertEqual(tree(self.root), before)

    def test_process_lock_contention_creates_no_target_writes(self):
        script = "import sys,time; sys.path.insert(0,sys.argv[1]); from live_fs import SimulatedLiveFS; from live_transaction import simulation_lock; from pathlib import Path; fs=SimulatedLiveFS(Path(sys.argv[2])); cm=simulation_lock(fs); cm.__enter__(); print('locked',flush=True); sys.stdin.readline()"
        process = subprocess.Popen([sys.executable, "-B", "-c", script, str(COMMON), str(self.root)],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(process.stdout.readline().strip(), "locked")
            before = tree(self.root)
            self.assertFalse(self.switch().success)
            self.assertEqual(tree(self.root), before)
        finally:
            process.communicate("done\n", timeout=10)

    def test_abrupt_exit_is_recovered_by_fresh_process_and_repeated_recovery_is_safe(self):
        script = "import sys,os; sys.path.insert(0,sys.argv[1]); from pathlib import Path; from live_fs import SimulatedLiveFS,TARGET; from live_transaction import switch_simulated; from state import ThemeState; original=SimulatedLiveFS.replace\ndef crash(fs,path,image,*,expected):\n original(fs,path,image,expected=expected)\n if path==TARGET: os._exit(23)\nSimulatedLiveFS.replace=crash\nswitch_simulated(ThemeState('manual','gothic','gothic',''),Path(sys.argv[2]))"
        process = subprocess.run([sys.executable, "-B", "-c", script, str(COMMON), str(self.root)],
                                 timeout=10, capture_output=True)
        self.assertEqual(process.returncode, 23, process.stderr)
        self.assertFalse(self.switch().success)
        script = "import sys; sys.path.insert(0,sys.argv[1]); from pathlib import Path; from live_transaction import recover_simulated; r=recover_simulated(Path(sys.argv[2])); print(r.rollback_status); sys.exit(0 if r.success else 1)"
        process = subprocess.run([sys.executable, "-B", "-c", script, str(COMMON), str(self.root)],
                                 timeout=10, capture_output=True, text=True)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(process.stdout.strip(), "restored")
        self.assertFalse((self.root / self.fs.TARGET).exists())
        before = tree(self.root)
        self.assertTrue(self.api.recover_simulated(self.root).success)
        self.assertEqual(tree(self.root), before)

    def test_corrupt_or_incomplete_journal_never_authorizes_restore(self):
        self.assertTrue(self.switch().success)
        journal = self.root / self.fs.JOURNAL
        data = json.loads(journal.read_bytes())
        for content in (b"invalid", json.dumps({"payload": data["payload"], "sha256": "0"*64}).encode()):
            journal.write_bytes(content)
            before = tree(self.root)
            self.assertFalse(self.api.recover_simulated(self.root).success)
            self.assertEqual(tree(self.root), before)

    def test_semantically_forged_journals_are_refused_even_with_valid_checksum(self):
        from enrollment import encode_record, digest
        self.assertTrue(self.switch().success)
        journal = self.root / self.fs.JOURNAL
        original = json.loads(journal.read_bytes())["payload"]
        changes = []
        omitted = copy.deepcopy(original)
        omitted["entries"].pop(0)
        changes.append(omitted)
        unsafe = copy.deepcopy(original)
        unsafe["entries"][0]["path"] = "config/ghostty/config.ghostty"
        changes.append(unsafe)
        for field, value in (("mode", 0o666), ("mode", -128), ("mtime_ns", 2**63),
                             ("atime_ns", True), ("content", "bad!")):
            changed = copy.deepcopy(original)
            changed["entries"][0]["after"][field] = value
            changes.append(changed)
        changed = copy.deepcopy(original)
        changed["created_dirs"] = ["source"]
        changes.append(changed)
        for payload in changes:
            journal.write_bytes(encode_record({"payload": payload, "sha256": digest(encode_record(payload))}))
            before = tree(self.root)
            self.assertFalse(self.api.recover_simulated(self.root).success)
            self.assertEqual(tree(self.root), before)

    def test_actual_under_lock_input_drift_prevents_journal_and_target_writes(self):
        from contextlib import contextmanager
        original_lock = self.api.simulation_lock
        @contextmanager
        def drift(fs):
            with original_lock(fs):
                (self.root / self.fs.HOOK).write_bytes(b"external under-lock edit\n")
                yield
        with patch.object(self.api, "simulation_lock", drift):
            result = self.switch()
        self.assertFalse(result.success)
        self.assertEqual(result.rollback_status, "not-started")
        self.assertFalse((self.root / self.fs.JOURNAL).exists())
        self.assertFalse((self.root / self.fs.TARGET).exists())

    def test_unowned_fragment_and_oversized_reason_are_refused_before_locks(self):
        from selection import Decision
        target = self.root / self.fs.TARGET
        target.parent.mkdir(mode=0o700, parents=True)
        target.write_bytes(b"user content\n")
        before = tree(self.root)
        self.assertFalse(self.switch().success)
        self.assertEqual(tree(self.root), before)
        target.unlink()
        before = tree(self.root)
        self.assertFalse(self.switch(decision=Decision("gothic", "x"*65536, "manual")).success)
        self.assertEqual(tree(self.root), before)

    def test_restore_failure_retains_record_and_later_recovery_restores_old_slice(self):
        self.assertTrue(self.switch(self.old).success)
        before = self.managed()
        from adapters.live_ghostty import GhosttyModel
        original = self.fs.SimulatedLiveFS.replace
        def refuse_restore(fs, path, image, *, expected):
            if path == self.fs.TARGET and image == before[path]:
                raise OSError("injected restore failure")
            return original(fs, path, image, expected=expected)
        with patch.object(GhosttyModel, "refresh", side_effect=OSError("refresh failed")), patch.object(
                self.fs.SimulatedLiveFS, "replace", refuse_restore):
            result = self.switch()
        self.assertFalse(result.success)
        self.assertEqual(result.rollback_status, "incomplete")
        self.assertEqual(result.active, "hybrid")  # Last good simulated selection, not current appearance.
        result = self.api.recover_simulated(self.root)
        self.assertTrue(result.success, result.warnings)
        self.assertEqual(self.managed(), before)

    def test_keyboard_interrupt_restores_before_propagation(self):
        from adapters.live_ghostty import GhosttyModel
        self.assertTrue(self.switch(self.old).success)
        before = self.managed()
        with patch.object(GhosttyModel, "refresh", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): self.switch()
        self.assertEqual(self.managed(), before)

    def test_all_palettes_and_explicit_auto_preserve_scoped_manual_history(self):
        from selection import Decision
        for slug in ("minimal", "cyber", "gothic", "hybrid", "pandawave"):
            candidate = ThemeState("manual", slug, slug, "")
            self.assertTrue(self.switch(candidate).success)
        candidate = ThemeState("auto", "hybrid", "pandawave", "")
        before = tree(self.root)
        self.assertFalse(self.switch(candidate).success)
        self.assertEqual(tree(self.root), before)
        self.assertTrue(self.switch(candidate, decision=Decision("hybrid", "daytime", "schedule")).success)
        self.assertEqual(json.loads((self.root / self.fs.SELECTION).read_bytes())["selection"]["last_manual"],
                         "pandawave")

    def test_new_file_rollback_removes_only_created_empty_directories(self):
        from adapters.live_ghostty import GhosttyModel
        panda = self.root / "config/panda"
        panda.mkdir(mode=0o700)
        unrelated = panda / "notes.txt"
        unrelated.write_bytes(b"keep me")
        with patch.object(GhosttyModel, "refresh", side_effect=ValueError("failed")):
            result = self.switch()
        self.assertEqual(result.rollback_status, "restored", result.warnings)
        self.assertEqual(unrelated.read_bytes(), b"keep me")
        self.assertFalse((panda / "generated").exists())

    def test_oversized_config_and_malformed_marker_are_zero_write_preflights(self):
        path = self.root / self.fs.HOOK
        path.write_bytes(b"#"*65537)
        before = tree(self.root)
        self.assertFalse(self.switch().success)
        self.assertEqual(tree(self.root), before)

    def test_prepared_journal_without_any_target_write_can_be_recovered(self):
        original = self.fs.SimulatedLiveFS.replace
        def fail_after_preparation(fs, path, image, *, expected):
            original(fs, path, image, expected=expected)
            if path == self.fs.JOURNAL:
                raise OSError("prepared journal persisted before interruption")
        with patch.object(self.fs.SimulatedLiveFS, "replace", fail_after_preparation):
            self.assertFalse(self.switch().success)
        self.assertFalse((self.root / self.fs.TARGET).exists())
        result = self.api.recover_simulated(self.root)
        self.assertTrue(result.success, result.warnings)
        self.assertEqual(result.rollback_status, "restored")

    def test_existing_cli_flags_cannot_apply_or_enroll_a_b1_root(self):
        for args in (("init-fixture", "--allow-fixture-writes"),
                     ("gothic", "--allow-fixture-writes"),
                     ("doctor", "--recover", "--allow-fixture-writes")):
            before = tree(self.root)
            process = subprocess.run([sys.executable, "-B", str(COMMON / "cli.py"), *args,
                                      "--fixture-root", str(self.root)], timeout=10, capture_output=True)
            self.assertNotEqual(process.returncode, 0)
            self.assertEqual(tree(self.root), before)

    def test_recovery_rejects_negative_mode_before_even_creating_a_lock(self):
        from enrollment import digest, encode_record
        planned = self.api.prepare_simulated(self.candidate, self.root)
        with self.fs.SimulatedLiveFS(self.root) as fs:
            self.api._journal(fs, planned.entries, fs.records_for(planned.created_dirs), "prepared")
        journal = self.root / self.fs.JOURNAL
        payload = json.loads(journal.read_bytes())["payload"]
        payload["entries"][0]["after"]["mode"] = -128
        journal.write_bytes(encode_record({"payload": payload, "sha256": digest(encode_record(payload))}))
        before = tree(self.root)
        result = self.api.recover_simulated(self.root)
        self.assertFalse(result.success)
        self.assertEqual(tree(self.root), before)
        self.assertFalse((self.root / self.fs.LOCK).exists())

    def test_rollback_preserves_preexisting_empty_panda_directory(self):
        from adapters.live_ghostty import GhosttyModel
        panda = self.root / "config/panda"
        panda.mkdir(mode=0o700)
        identity = panda.stat().st_ino
        with patch.object(GhosttyModel, "refresh", side_effect=ValueError("failed")):
            result = self.switch()
        self.assertEqual(result.rollback_status, "restored", result.warnings)
        self.assertTrue(panda.is_dir())
        self.assertEqual(panda.stat().st_ino, identity)
        self.assertEqual(list(panda.iterdir()), [])

    def test_rollback_removes_new_panda_directory_with_preexisting_state_directory(self):
        from adapters.live_ghostty import GhosttyModel
        (self.root / "state/panda-ghostty-simulation").mkdir(mode=0o700)
        with patch.object(GhosttyModel, "refresh", side_effect=ValueError("failed")):
            result = self.switch()
        self.assertEqual(result.rollback_status, "restored", result.warnings)
        self.assertFalse((self.root / "config/panda").exists())

    def test_directory_creation_between_preview_and_lock_is_stale_without_application(self):
        from contextlib import contextmanager
        original = self.api.simulation_lock
        external = [self.root / "config/panda", self.root / "config/panda/generated"]
        identities = []
        @contextmanager
        def intervening(fs):
            for path in external:
                path.mkdir(mode=0o700)
                identities.append(path.stat().st_ino)
            with original(fs):
                yield
        with patch.object(self.api, "simulation_lock", intervening):
            result = self.switch()
        self.assertFalse(result.success)
        self.assertEqual(result.rollback_status, "not-started")
        self.assertEqual([p.stat().st_ino for p in external], identities)
        self.assertEqual(list(external[-1].iterdir()), [])
        self.assertFalse((self.root / self.fs.TARGET).exists())
        self.assertFalse((self.root / self.fs.JOURNAL).exists())
        self.assertTrue(all(image is None for image in self.managed().values()))

    def test_external_directories_after_prepared_interruption_are_preserved(self):
        original = self.fs.SimulatedLiveFS.replace
        def interrupt(fs, path, image, *, expected):
            original(fs, path, image, expected=expected)
            if path == self.fs.JOURNAL:
                raise OSError("prepared record persisted")
        with patch.object(self.fs.SimulatedLiveFS, "replace", interrupt):
            self.assertFalse(self.switch().success)
        external = [self.root / "config/panda", self.root / "config/panda/generated"]
        for path in external:
            path.mkdir(mode=0o700)
        before = tree(self.root)
        result = self.api.recover_simulated(self.root)
        self.assertFalse(result.success)
        self.assertEqual(result.rollback_status, "incomplete")
        self.assertEqual(tree(self.root), before)
        self.assertTrue(all(p.is_dir() for p in external))
        self.assertFalse((self.root / self.fs.TARGET).exists())

    def cleanup_failure(self):
        from adapters.live_ghostty import GhosttyModel
        original = os.rmdir
        def fail(path, *, dir_fd=None):
            if path == "generated":
                raise OSError(errno.EIO, "directory cleanup failure")
            return original(path, dir_fd=dir_fd)
        with patch.object(GhosttyModel, "refresh", side_effect=OSError("refresh failed")), patch(
                "live_fs.os.rmdir", side_effect=fail):
            result = self.switch()
        return result, fail

    def test_cleanup_eio_remains_incomplete_and_can_be_retried(self):
        result, fail = self.cleanup_failure()
        self.assertFalse(result.success)
        self.assertEqual(result.rollback_status, "incomplete")
        self.assertEqual(json.loads((self.root / self.fs.JOURNAL).read_bytes())["payload"]["phase"],
                         "incomplete")
        self.assertTrue((self.root / "config/panda/generated").is_dir())
        self.assertFalse((self.root / self.fs.TARGET).exists())
        with patch("live_fs.os.rmdir", side_effect=fail):
            repeated = self.api.recover_simulated(self.root)
        self.assertFalse(repeated.success)
        self.assertEqual(repeated.rollback_status, "incomplete")
        recovery = self.api.recover_simulated(self.root)
        self.assertTrue(recovery.success, recovery.warnings)
        self.assertEqual(recovery.rollback_status, "restored")
        self.assertFalse((self.root / "config/panda").exists())
        before = tree(self.root)
        self.assertTrue(self.api.recover_simulated(self.root).success)
        self.assertEqual(tree(self.root), before)

    def test_cleanup_fsync_failure_retains_pending_record_after_removal(self):
        from adapters.live_ghostty import GhosttyModel
        import stat
        original = os.fsync
        original_rmdir = os.rmdir
        removed = False
        failed = False
        def remove(path, *, dir_fd=None):
            nonlocal removed
            original_rmdir(path, dir_fd=dir_fd)
            if path == "generated":
                removed = True
        def fail(fd):
            nonlocal failed
            panda = self.root / "config/panda"
            info = os.fstat(fd)
            if (removed and not failed and panda.exists() and stat.S_ISDIR(info.st_mode) and
                    info.st_ino == panda.stat().st_ino and not (panda / "generated").exists()):
                failed = True
                raise OSError(errno.EIO, "cleanup durability failure")
            return original(fd)
        with patch.object(GhosttyModel, "refresh", side_effect=OSError("refresh failed")), patch(
                "live_fs.os.fsync", side_effect=fail), patch("live_fs.os.rmdir", side_effect=remove):
            result = self.switch()
        self.assertTrue(failed)
        self.assertFalse(result.success)
        self.assertEqual(result.rollback_status, "incomplete")
        self.assertEqual(json.loads((self.root / self.fs.JOURNAL).read_bytes())["payload"]["phase"],
                         "incomplete")
        recovery = self.api.recover_simulated(self.root)
        self.assertTrue(recovery.success, recovery.warnings)
        self.assertFalse((self.root / "config/panda").exists())

    def test_restored_phase_cannot_hide_pending_directory_cleanup(self):
        from enrollment import digest, encode_record
        self.cleanup_failure()
        journal = self.root / self.fs.JOURNAL
        payload = json.loads(journal.read_bytes())["payload"]
        payload["phase"] = "restored"
        journal.write_bytes(encode_record({"payload": payload, "sha256": digest(encode_record(payload))}))
        before = tree(self.root)
        result = self.api.recover_simulated(self.root)
        self.assertFalse(result.success)
        self.assertEqual(result.rollback_status, "incomplete")
        self.assertFalse(self.switch().success)
        self.assertEqual(tree(self.root), before)

    def journal_durability_failure(self, *, refuse_pending=False):
        original_replace = self.fs.SimulatedLiveFS.replace
        original_fsync = os.fsync
        armed = False
        def replace(fs, path, image, *, expected):
            nonlocal armed
            if path == self.fs.JOURNAL and image is not None:
                phase = json.loads(image.content)["payload"]["phase"]
                if phase == "restored":
                    armed = True
                if armed and refuse_pending and phase == "incomplete":
                    raise OSError(errno.EIO, "pending record cannot be written")
            return original_replace(fs, path, image, expected=expected)
        def fsync(fd):
            parent = self.root / "state/panda-ghostty-simulation"
            if armed and parent.exists() and os.fstat(fd).st_ino == parent.stat().st_ino:
                raise OSError(errno.EIO, "journal directory durability failed")
            return original_fsync(fd)
        return replace, fsync

    def test_final_journal_fsync_failure_remains_pending_until_retry(self):
        from adapters.live_ghostty import GhosttyModel
        replace, fsync = self.journal_durability_failure()
        with patch.object(GhosttyModel, "refresh", side_effect=OSError("refresh failed")), patch.object(
                self.fs.SimulatedLiveFS, "replace", replace), patch("live_fs.os.fsync", side_effect=fsync):
            result = self.switch()
            self.assertEqual(result.rollback_status, "incomplete")
            self.assertEqual(json.loads((self.root / self.fs.JOURNAL).read_bytes())["payload"]["phase"],
                             "incomplete")
            self.assertFalse(self.api.recover_simulated(self.root).success)
        recovery = self.api.recover_simulated(self.root)
        self.assertTrue(recovery.success, recovery.warnings)
        self.assertEqual(recovery.rollback_status, "restored")
        before = tree(self.root)
        self.assertTrue(self.api.recover_simulated(self.root).success)
        self.assertEqual(tree(self.root), before)

    def test_renamed_restored_journal_retries_durability_when_pending_write_fails(self):
        from adapters.live_ghostty import GhosttyModel
        replace, fsync = self.journal_durability_failure(refuse_pending=True)
        with patch.object(GhosttyModel, "refresh", side_effect=OSError("refresh failed")), patch.object(
                self.fs.SimulatedLiveFS, "replace", replace), patch("live_fs.os.fsync", side_effect=fsync):
            self.assertEqual(self.switch().rollback_status, "incomplete")
            self.assertEqual(json.loads((self.root / self.fs.JOURNAL).read_bytes())["payload"]["phase"],
                             "restored")
            before = tree(self.root)
            recovery = self.api.recover_simulated(self.root)
            self.assertFalse(recovery.success)
            self.assertEqual(recovery.rollback_status, "incomplete")
            self.assertFalse(self.switch().success)
            self.assertEqual(tree(self.root), before)
        self.assertTrue(self.api.recover_simulated(self.root).success)

    def test_restored_journal_without_directory_records_retries_durability(self):
        from adapters.live_ghostty import GhosttyModel
        (self.root / "config/panda").mkdir(mode=0o700)
        (self.root / "config/panda/generated").mkdir(mode=0o700)
        replace, fsync = self.journal_durability_failure(refuse_pending=True)
        with patch.object(GhosttyModel, "refresh", side_effect=OSError("refresh failed")), patch.object(
                self.fs.SimulatedLiveFS, "replace", replace), patch("live_fs.os.fsync", side_effect=fsync):
            self.assertEqual(self.switch().rollback_status, "incomplete")
            payload = json.loads((self.root / self.fs.JOURNAL).read_bytes())["payload"]
            self.assertEqual(payload["created_dirs"], [])
            before = tree(self.root)
            self.assertFalse(self.api.recover_simulated(self.root).success)
            self.assertEqual(tree(self.root), before)
        self.assertTrue(self.api.recover_simulated(self.root).success)

    def test_recovery_preserves_replaced_directory_identity_and_content(self):
        self.cleanup_failure()
        generated = self.root / "config/panda/generated"
        generated.rename(generated.with_name("retained"))
        generated.mkdir(mode=0o700)
        note = generated / "unrelated.txt"
        note.write_bytes(b"external content")
        before = tree(self.root)
        result = self.api.recover_simulated(self.root)
        self.assertFalse(result.success)
        self.assertEqual(result.rollback_status, "incomplete")
        self.assertEqual(tree(self.root), before)
        self.assertEqual(note.read_bytes(), b"external content")

    def test_recovery_preserves_directory_modified_even_when_empty(self):
        self.cleanup_failure()
        generated = self.root / "config/panda/generated"
        note = generated / "later.txt"
        note.write_bytes(b"external")
        note.unlink()
        before = tree(self.root)
        result = self.api.recover_simulated(self.root)
        self.assertFalse(result.success)
        self.assertEqual(tree(self.root), before)
        self.assertEqual(list(generated.iterdir()), [])

    def test_crash_between_mkdir_and_provenance_record_preserves_unknown_directory(self):
        script = "import sys,os; sys.path.insert(0,sys.argv[1]); from pathlib import Path; import live_fs; from live_transaction import switch_simulated; from state import ThemeState; original=os.mkdir\ndef crash(path,mode=0o777,*,dir_fd=None):\n original(path,mode,dir_fd=dir_fd)\n if path=='panda': os._exit(29)\nlive_fs.os.mkdir=crash\nswitch_simulated(ThemeState('manual','gothic','gothic',''),Path(sys.argv[2]))"
        process = subprocess.run([sys.executable, "-B", "-c", script, str(COMMON), str(self.root)],
                                 timeout=10, capture_output=True)
        self.assertEqual(process.returncode, 29, process.stderr)
        panda = self.root / "config/panda"
        self.assertTrue(panda.is_dir())
        before = tree(self.root)
        result = self.api.recover_simulated(self.root)
        self.assertFalse(result.success)
        self.assertEqual(result.rollback_status, "incomplete")
        self.assertEqual(tree(self.root), before)

    def test_legacy_directory_journal_is_retained_without_automatic_replay(self):
        from enrollment import digest, encode_record
        self.assertTrue(self.switch().success)
        journal = self.root / self.fs.JOURNAL
        payload = json.loads(journal.read_bytes())["payload"]
        payload["schema_version"] = 1
        payload["created_dirs"] = ["config/panda", "config/panda/generated"]
        journal.write_bytes(encode_record({"payload": payload, "sha256": digest(encode_record(payload))}))
        before = tree(self.root)
        self.assertFalse(self.api.recover_simulated(self.root).success)
        self.assertEqual(tree(self.root), before)

    def test_failed_replace_does_not_adopt_external_directory_timestamps(self):
        self.cleanup_failure()
        generated = self.root / "config/panda/generated"
        with self.fs.SimulatedLiveFS(self.root) as fs:
            records = self.api._load_journal(fs)[1]
            fs.track_directories(records)
            original = copy.deepcopy(fs.created)
            note = generated / "external.txt"
            note.write_bytes(b"later edit")
            note.unlink()
            before = tree(self.root)
            with self.assertRaises(ValueError):
                fs.replace(self.fs.TARGET, None, expected=None)
            self.assertEqual(fs.created, original)
            with self.assertRaises(ValueError):
                fs.remove_empty_dirs(records)
            self.assertEqual(tree(self.root), before)

    def test_populated_directory_cleanup_is_incomplete_and_preserves_content(self):
        from adapters.live_ghostty import GhosttyModel
        note = self.root / "config/panda/generated/external.txt"
        def external():
            note.write_bytes(b"unrelated content")
            raise OSError("refresh failed")
        with patch.object(GhosttyModel, "refresh", side_effect=external):
            result = self.switch()
        self.assertFalse(result.success)
        self.assertEqual(result.rollback_status, "incomplete")
        self.assertEqual(note.read_bytes(), b"unrelated content")
        before = tree(self.root)
        self.assertFalse(self.api.recover_simulated(self.root).success)
        self.assertEqual(tree(self.root), before)

    def test_malformed_directory_provenance_is_refused_without_writes(self):
        from enrollment import digest, encode_record
        self.cleanup_failure()
        journal = self.root / self.fs.JOURNAL
        original = json.loads(journal.read_bytes())["payload"]
        invalid = [["config/panda"], original["created_dirs"] * 2,
                   list(reversed(original["created_dirs"])),
                   [{"path": "state/panda-ghostty-simulation", "identity": None}]]
        for key, value in (("inode", -1), ("device", True), ("uid", os.getuid()+1),
                           ("mode", 0o755), ("ctime_ns", 2**63)):
            records = copy.deepcopy(original["created_dirs"])
            records[0]["identity"][key] = value
            invalid.append(records)
        for records in invalid:
            with self.subTest(records=records):
                payload = copy.deepcopy(original)
                payload["created_dirs"] = records
                journal.write_bytes(encode_record({"payload": payload, "sha256": digest(encode_record(payload))}))
                before = tree(self.root)
                self.assertFalse(self.api.recover_simulated(self.root).success)
                self.assertEqual(tree(self.root), before)
