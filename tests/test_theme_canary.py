"""B3-B0 private canary contracts; no native program or installed HOME writes."""

import errno
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import unittest
from unittest.mock import patch

COMMON = Path(__file__).resolve().parents[1] / "theme/panda/common"
sys.path.insert(0, str(COMMON))


def snapshot(root):
    result = {}
    for path in root.rglob("*"):
        info = path.lstat()
        content = None
        if path.is_file() and not path.is_symlink():
            fd = os.open(path, os.O_RDONLY | os.O_NOATIME | os.O_NOFOLLOW)
            with os.fdopen(fd, "rb") as handle:
                content = handle.read()
        result[str(path.relative_to(root))] = (info.st_mode, info.st_ino,
                                               info.st_mtime_ns, info.st_ctime_ns, content)
    return result


class CanaryContracts(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec("canary"), "B3B fixture canary missing")
        self.api = importlib.import_module("canary")
        self.fs = importlib.import_module("canary_fs")
        source = COMMON.parents[2] / "home/dot_config/ghostty/config.ghostty"
        fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NOATIME)
        with os.fdopen(fd, "rb") as handle:
            self.baseline = handle.read()
        self.root = self.api.create_fixture(self.baseline)
        self.own_fixture(self.root)

    def own_fixture(self, root):
        initial = root.lstat()
        def cleanup():
            current = root.lstat()
            self.assertTrue(stat.S_ISDIR(current.st_mode))
            self.assertEqual((current.st_dev, current.st_ino, current.st_uid, stat.S_IMODE(current.st_mode)),
                             (initial.st_dev, initial.st_ino, os.getuid(), 0o700))
            shutil.rmtree(root)
        self.addCleanup(cleanup)

    def images(self):
        with self.fs.CanaryFS(self.root) as fs:
            return [fs.read(path) for path in self.fs.MANAGED]

    def fresh(self):
        self.root = self.api.create_fixture(self.baseline)
        self.own_fixture(self.root)

    def test_completed_applied_record_rejects_external_before_image(self):
        self.assertTrue(self.api.apply(self.root).success)
        marker = self.fs.unpack((self.root / self.fs.MARKER).read_bytes())
        baseline = self.fs.image_from(marker["entries"][1]["before"])
        path = self.root / self.fs.SOURCE
        path.write_bytes(baseline["content"])
        os.utime(path, ns=(baseline["atime_ns"], baseline["mtime_ns"]))
        before = snapshot(self.root)
        self.assertFalse(self.api.inspect(self.root).success)
        self.assertFalse(self.api.recover(self.root).success)
        self.assertEqual(snapshot(self.root), before)

    def test_replaced_empty_lock_is_refused_before_journal_creation(self):
        lock = self.root / self.fs.LOCK
        lock.unlink()
        lock.touch(mode=0o600)
        before = snapshot(self.root)
        self.assertFalse(self.api.apply(self.root).success)
        self.assertEqual(snapshot(self.root), before)

    def test_journal_staging_corruption_is_detected_before_target_writes(self):
        original = os.replace
        def replace(src, dst, **kwargs):
            if dst == "journal.json":
                fd = os.open(src, os.O_WRONLY | os.O_TRUNC, dir_fd=kwargs["src_dir_fd"])
                os.write(fd, b"corrupt journal\n")
                os.close(fd)
            return original(src, dst, **kwargs)
        with patch("canary_fs.os.replace", side_effect=replace):
            self.assertFalse(self.api.apply(self.root).success)
        self.assertEqual((self.root / self.fs.SOURCE).read_bytes(), self.baseline)
        self.assertEqual((self.root / self.fs.DEPLOYED).read_bytes(), self.baseline)
        self.assertFalse((self.root / "config/panda").exists())

    def test_foreign_staged_bytes_are_not_renamed_over_baseline(self):
        original = self.fs.CanaryFS._intent
        def intent(fs, kind, path):
            if kind == "replace" and path == self.fs.SOURCE:
                stage = self.root / self.fs.STAGES[path]
                stage.write_bytes(b"foreign staged data\n")
            return original(fs, kind, path)
        with patch.object(self.fs.CanaryFS, "_intent", intent):
            self.assertFalse(self.api.apply(self.root).success)
        self.assertEqual((self.root / self.fs.SOURCE).read_bytes(), self.baseline)
        self.assertEqual((self.root / self.fs.DEPLOYED).read_bytes(), self.baseline)

    def test_dry_run_is_write_free_and_preview_cannot_execute(self):
        before = snapshot(self.root)
        preview = self.api.dry_run(self.root)
        self.assertTrue(preview.success, preview)
        self.assertIn("fixture-only", preview.message)
        self.assertFalse(self.api.apply(self.root, plan=preview).success)
        self.assertEqual(snapshot(self.root), before)

    def test_minimal_first_deployed_last_and_reverse_restoration(self):
        before = self.images()
        order = []
        original = self.fs.CanaryFS.replace
        def replace(fs, path, image, *, expected):
            if path in self.fs.MANAGED:
                order.append(path)
            return original(fs, path, image, expected=expected)
        with patch.object(self.fs.CanaryFS, "replace", replace):
            result = self.api.apply(self.root)
            self.assertTrue(result.success, result)
            self.assertEqual(order, list(self.fs.MANAGED))
            target, source, deployed = self.images()
            self.assertEqual(hashlib.sha256(target["content"]).hexdigest(), self.api.MINIMAL_SHA)
            self.assertEqual(source["content"], self.baseline + self.api.HOOK_LINE)
            self.assertEqual(source["content"], deployed["content"])
            self.assertTrue(self.api.inspect(self.root).success)
            self.assertFalse(self.api.apply(self.root).success, "single-use")
            restored = self.api.recover(self.root)
            self.assertTrue(restored.success, restored)
            self.assertEqual(order[3:], list(reversed(self.fs.MANAGED)))
        self.assertEqual(self.images(), before)
        self.assertFalse((self.root / "config/panda").exists())
        state = snapshot(self.root)
        self.assertTrue(self.api.recover(self.root).success)
        self.assertEqual(snapshot(self.root), state)

    def test_real_and_legacy_roots_are_rejected(self):
        for root in (Path.home(), Path("/tmp/panda-theme-b1-fake"),
                     Path("/tmp/panda-theme-fixture-fake"), self.root / "home",
                     self.root / ".." / self.root.name):
            with self.subTest(root=root):
                self.assertFalse(self.api.apply(root).success)
                self.assertFalse(self.api.recover(root).success)

    def test_exact_allowlist(self):
        with self.fs.CanaryFS(self.root) as fs:
            for path in ("config/other", "../outside", "/home/adrian/.config/ghostty/config.ghostty"):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    fs.read(path)

    def test_unsafe_ancestors_are_zero_write_refusals(self):
        for mode in (0o770, 0o2700, 0o1700, 0o500):
            with self.subTest(mode=mode):
                parent = self.root / "source/home/dot_config"
                parent.chmod(mode)
                before = snapshot(self.root)
                self.assertFalse(self.api.apply(self.root).success)
                self.assertEqual(snapshot(self.root), before)
                parent.chmod(0o700)

    def test_opened_child_substitution_before_checkpoint_is_preserved(self):
        original = os.open
        replaced = []
        def opened(name, *args, **kwargs):
            fd = original(name, *args, **kwargs)
            if name == "generated" and args[0] & os.O_DIRECTORY and not replaced:
                child = self.root / "config/panda/generated"
                saved = self.root / "config/panda/generated.saved"
                child.rename(saved)
                child.mkdir(mode=0o700)
                (child / "external").write_bytes(b"external child bytes\n")
                replaced.append((child, child.lstat().st_ino, saved, os.fstat(fd).st_ino))
            return fd
        with patch("canary_fs.os.open", side_effect=opened):
            self.assertFalse(self.api.apply(self.root).success)
        self.assertTrue(replaced)
        before = snapshot(self.root)
        for _ in range(2):
            self.assertFalse(self.api.recover(self.root).success)
            self.assertEqual(snapshot(self.root), before)
        child, inode, saved, original_inode = replaced[0]
        self.assertEqual(child.lstat().st_ino, inode)
        self.assertEqual(saved.lstat().st_ino, original_inode)

    def test_mkdir_metadata_drift_keeps_child_unproven(self):
        original = os.open
        changed = []
        def opened(name, *args, **kwargs):
            fd = original(name, *args, **kwargs)
            if name == "generated" and args[0] & os.O_DIRECTORY and not changed:
                child = self.root / "config/panda/generated"
                changed.append((child, os.fstat(fd).st_ino))
                child.chmod(0o500)
            return fd
        try:
            with patch("canary_fs.os.open", side_effect=opened):
                self.assertFalse(self.api.apply(self.root).success)
            self.assertTrue(changed)
            child, inode = changed[0]
            self.assertEqual(child.lstat().st_ino, inode)
            before = snapshot(self.root)
            self.assertFalse(self.api.recover(self.root).success)
            self.assertEqual(snapshot(self.root), before)
        finally:
            for child, inode in changed:
                self.assertEqual(child.lstat().st_ino, inode)
                child.chmod(0o700)

    def test_valid_application_checkpoints_preserve_recovery_contract(self):
        for checkpoint in range(1, 9):
            with self.subTest(checkpoint=checkpoint):
                self.fresh()
                original = self.api._Journal.done
                fired = []
                def done(journal):
                    original(journal)
                    if journal.data["phase"] == "applying" and journal.data["completed"] == checkpoint:
                        fired.append(True)
                        raise OSError(errno.EIO, "exit after durable checkpoint")
                with patch.object(self.api._Journal, "done", done):
                    self.assertFalse(self.api.apply(self.root).success)
                self.assertTrue(fired)
                before = snapshot(self.root)
                result = self.api.recover(self.root)
                if checkpoint in (3, 5, 7):  # Completed stage persists: conservative manual review.
                    self.assertFalse(result.success)
                    self.assertEqual(snapshot(self.root), before)
                else:
                    self.assertTrue(result.success, result)
                    self.assertTrue(self.api.recover(self.root).success)
                    self.assertEqual((self.root / self.fs.SOURCE).read_bytes(), self.baseline)
                    self.assertEqual((self.root / self.fs.DEPLOYED).read_bytes(), self.baseline)
                    self.assertFalse((self.root / "config/panda").exists())

    def test_valid_recovery_checkpoints_preserve_retries(self):
        for checkpoint in range(1, 8):
            with self.subTest(checkpoint=checkpoint):
                self.fresh()
                self.assertTrue(self.api.apply(self.root).success)
                original = self.api._Journal.done
                fired = []
                def done(journal):
                    original(journal)
                    if journal.data["completed"] == 8 + checkpoint:
                        fired.append(True)
                        raise OSError(errno.EIO, "exit after durable restoration checkpoint")
                with patch.object(self.api._Journal, "done", done):
                    self.assertFalse(self.api.recover(self.root).success)
                self.assertTrue(fired)
                before = snapshot(self.root)
                result = self.api.recover(self.root)
                if checkpoint in (1, 3):
                    self.assertFalse(result.success)
                    self.assertEqual(snapshot(self.root), before)
                else:
                    self.assertTrue(result.success, result)
                    self.assertTrue(self.api.recover(self.root).success)
                    self.assertFalse((self.root / "config/panda").exists())

    def test_outstanding_cleanup_intent_retries_remain_recoverable(self):
        self.assertTrue(self.api.apply(self.root).success)
        original = os.unlink
        fired = []
        def unlink(name, *args, **kwargs):
            if name == "ghostty.conf":
                fired.append(True)
                raise OSError(errno.EIO, "persistent target unlink EIO")
            return original(name, *args, **kwargs)
        with patch("canary_fs.os.unlink", side_effect=unlink):
            for _ in range(3):
                self.assertFalse(self.api.recover(self.root).success)
        self.assertEqual(len(fired), 3)
        self.assertTrue(self.api.recover(self.root).success)
        before = snapshot(self.root)
        self.assertTrue(self.api.recover(self.root).success)
        self.assertEqual(snapshot(self.root), before)

    def test_foreign_output_directory_is_rejected_before_lock_or_journal(self):
        (self.root / "config/panda").mkdir(mode=0o700)
        before = snapshot(self.root)
        self.assertFalse(self.api.apply(self.root).success)
        self.assertEqual(snapshot(self.root), before)

    def test_later_edit_prevents_all_recovery_writes(self):
        self.assertTrue(self.api.apply(self.root).success)
        (self.root / self.fs.SOURCE).write_bytes(b"external edit\n")
        before = snapshot(self.root)
        self.assertFalse(self.api.recover(self.root).success)
        self.assertEqual(snapshot(self.root), before)

    def test_malformed_and_legacy_journals_are_zero_write_refusals(self):
        self.assertTrue(self.api.apply(self.root).success)
        journal = self.root / self.fs.JOURNAL
        original = journal.read_bytes()
        for raw in (b"{}", b'{"payload":{},"sha256":"invalid"}', b"{", original[:-1]):
            journal.write_bytes(raw)
            before = snapshot(self.root)
            self.assertFalse(self.api.recover(self.root).success)
            self.assertEqual(snapshot(self.root), before)

    def test_completed_state_still_requires_parent_durability(self):
        self.assertTrue(self.api.apply(self.root).success)
        parent = self.root / "config/ghostty"
        identity = (parent.stat().st_dev, parent.stat().st_ino)
        original = os.fsync
        def fail(fd):
            info = os.fstat(fd)
            if (info.st_dev, info.st_ino) == identity:
                raise OSError(errno.EIO, "injected parent EIO")
            return original(fd)
        before = snapshot(self.root)
        with patch("canary_fs.os.fsync", side_effect=fail):
            self.assertFalse(self.api.inspect(self.root).success)
        self.assertEqual(snapshot(self.root), before)
        self.assertTrue(self.api.inspect(self.root).success)

    def test_replaced_parent_refused_with_evidence_retained(self):
        self.assertTrue(self.api.apply(self.root).success)
        parent = self.root / "config/ghostty"
        parent.rename(self.root / "config/ghostty.saved")
        parent.mkdir(mode=0o700)
        shutil.copyfile(self.root / "config/ghostty.saved/config.ghostty", parent / "config.ghostty")
        before = snapshot(self.root)
        self.assertFalse(self.api.recover(self.root).success)
        self.assertEqual(snapshot(self.root), before)

    def test_all_fixed_ancestors_are_checked_before_first_transaction_write(self):
        for directory in self.fs.FIXED_DIRS:
            with self.subTest(directory=directory):
                path = self.root / directory
                path.chmod(0o2700)
                before = snapshot(self.root)
                self.assertFalse(self.api.apply(self.root).success)
                self.assertEqual(snapshot(self.root), before)
                path.chmod(0o700)

    def test_real_user_xattrs_on_ancestor_are_refused(self):
        path = self.root / "source/home"
        try:
            os.setxattr(path, "user.panda_b3b_test", b"present")
        except OSError as error:
            self.skipTest(f"fixture xattrs unavailable: errno {error.errno}")
        before = snapshot(self.root)
        self.assertFalse(self.api.apply(self.root).success)
        self.assertEqual(snapshot(self.root), before)

    def test_file_xattrs_hardlinks_symlinks_fifo_and_special_modes_are_refused(self):
        for kind in ("xattr", "hardlink", "symlink", "fifo", "special-mode"):
            with self.subTest(kind=kind):
                self.fresh()
                path = self.root / self.fs.SOURCE
                if kind == "xattr":
                    os.setxattr(path, "user.panda_b3b_test", b"present")
                elif kind == "hardlink":
                    os.link(path, self.root / "source/extra-link")
                elif kind == "special-mode":
                    path.chmod(0o4644)
                else:
                    path.unlink()
                    if kind == "symlink":
                        path.symlink_to(self.root / self.fs.DEPLOYED)
                    else:
                        os.mkfifo(path, mode=0o600)
                # snapshot cannot read a FIFO; record metadata without opening it.
                before = snapshot(self.root)
                self.assertFalse(self.api.apply(self.root).success)
                self.assertEqual(snapshot(self.root), before)

    def test_symlinked_root_and_ancestor_are_refused_without_following(self):
        parent = self.root / "config/ghostty"
        parent.rename(self.root / "config/saved")
        parent.symlink_to(self.root / "config/saved", target_is_directory=True)
        before = snapshot(self.root)
        self.assertFalse(self.api.apply(self.root).success)
        self.assertEqual(snapshot(self.root), before)

    def test_mount_alias_identity_is_not_treated_as_nofollow_protection(self):
        original = self.fs.mount_id
        def alias(fd):
            value = original(fd)
            if os.readlink(f"/proc/self/fd/{fd}").endswith("source/home/dot_config"):
                return value + 100000
            return value
        before = snapshot(self.root)
        with patch("canary_fs.mount_id", side_effect=alias):
            self.assertFalse(self.api.apply(self.root).success)
        self.assertEqual(snapshot(self.root), before)

    def test_existing_stages_and_recovery_files_are_not_overwritten(self):
        for path in (*self.fs.STAGES.values(), self.fs.JOURNAL):
            with self.subTest(path=path):
                self.fresh()
                target = self.root / path
                target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                target.write_bytes(b"foreign staging or recovery evidence")
                target.chmod(0o600)
                before = snapshot(self.root)
                self.assertFalse(self.api.apply(self.root).success)
                self.assertFalse(self.api.recover(self.root).success)
                self.assertEqual(snapshot(self.root), before)

    def test_schema_corruption_even_with_valid_checksum_is_rejected(self):
        self.assertTrue(self.api.apply(self.root).success)
        journal = self.root / self.fs.JOURNAL
        original = self.fs.unpack(journal.read_bytes())
        variants = []
        for key, value in (("schema", 0), ("scope", "live"), ("sequence", True),
                           ("entries", []), ("manifest_sha256", "0" * 64),
                           ("directories", []), ("completed", 129), ("intent", {"kind": "unlink", "path": "/home"})):
            data = {**original, key: value}
            variants.append(self.fs.pack(data))
        variants.extend((b"{\"payload\":{},\"payload\":{},\"sha256\":\"x\"}\n", b" " * (self.fs.LIMIT + 1)))
        for raw in variants:
            with self.subTest(length=len(raw)):
                journal.write_bytes(raw)
                before = snapshot(self.root)
                self.assertFalse(self.api.recover(self.root).success)
                self.assertEqual(snapshot(self.root), before)

    def test_unknown_directory_provenance_is_never_inferred_from_empty_directory(self):
        self.assertTrue(self.api.apply(self.root).success)
        journal = self.root / self.fs.JOURNAL
        data = self.fs.unpack(journal.read_bytes())
        data["phase"] = "incomplete"
        data["directories"][1].update(state="pending", identity=None)
        journal.write_bytes(self.fs.pack(data))
        before = snapshot(self.root)
        self.assertFalse(self.api.recover(self.root).success)
        self.assertEqual(snapshot(self.root), before)

    def test_external_directory_event_is_preserved_even_when_empty_again(self):
        self.assertTrue(self.api.apply(self.root).success)
        path = self.root / "config/panda/generated/later-file"
        path.write_bytes(b"external")
        path.unlink()
        before = snapshot(self.root)
        self.assertFalse(self.api.recover(self.root).success)
        self.assertEqual(snapshot(self.root), before)

    def test_late_destination_edit_during_staging_is_preserved(self):
        original = self.fs.CanaryFS._intent
        def intent(fs, kind, path):
            if kind == "replace" and path == self.fs.DEPLOYED:
                (self.root / path).write_bytes(b"late external edit\n")
            return original(fs, kind, path)
        with patch.object(self.fs.CanaryFS, "_intent", intent):
            self.assertFalse(self.api.apply(self.root).success)
        self.assertEqual((self.root / self.fs.DEPLOYED).read_bytes(), b"late external edit\n")
        before = snapshot(self.root)
        self.assertFalse(self.api.recover(self.root).success)
        self.assertEqual(snapshot(self.root), before)

    def test_write_eio_and_injected_enospc_preserve_stage_evidence(self):
        for path in (*self.fs.MANAGED, self.fs.JOURNAL):
            for code in (errno.EIO, errno.ENOSPC):
                with self.subTest(path=path, errno=code):
                    self.fresh()
                    original = os.write
                    fired = False
                    stage = str(self.root / self.fs.STAGES[path])
                    def fail(fd, content):
                        nonlocal fired
                        if os.readlink(f"/proc/self/fd/{fd}") == stage:
                            fired = True
                            original(fd, content[:7])
                            raise OSError(code, "injected write failure")
                        return original(fd, content)
                    with patch("canary_fs.os.write", side_effect=fail):
                        self.assertFalse(self.api.apply(self.root).success)
                    self.assertTrue(fired)
                    self.assertTrue(Path(stage).exists())
                    before = snapshot(self.root)
                    self.assertFalse(self.api.recover(self.root).success)
                    self.assertEqual(snapshot(self.root), before)

    def test_file_fsync_eio_and_injected_enospc_preserve_evidence(self):
        for path in (*self.fs.MANAGED, self.fs.JOURNAL):
            for code in (errno.EIO, errno.ENOSPC):
                with self.subTest(path=path, errno=code):
                    self.fresh()
                    original = os.fsync
                    fired = False
                    stage = str(self.root / self.fs.STAGES[path])
                    def fail(fd):
                        nonlocal fired
                        if os.readlink(f"/proc/self/fd/{fd}") == stage:
                            fired = True
                            raise OSError(code, "injected file fsync")
                        return original(fd)
                    with patch("canary_fs.os.fsync", side_effect=fail):
                        self.assertFalse(self.api.apply(self.root).success)
                    self.assertTrue(fired)
                    before = snapshot(self.root)
                    self.assertFalse(self.api.recover(self.root).success)
                    self.assertEqual(snapshot(self.root), before)

    def test_rename_eio_and_injected_enospc_do_not_overwrite_destination(self):
        for path in (*self.fs.MANAGED, self.fs.JOURNAL):
            for code in (errno.EIO, errno.ENOSPC):
                with self.subTest(path=path, errno=code):
                    self.fresh()
                    original = os.replace
                    fired = False
                    destination = path.rsplit("/", 1)[1]
                    def fail(src, dst, **kwargs):
                        nonlocal fired
                        if dst == destination:
                            fired = True
                            raise OSError(code, "injected rename")
                        return original(src, dst, **kwargs)
                    with patch("canary_fs.os.replace", side_effect=fail):
                        self.assertFalse(self.api.apply(self.root).success)
                    self.assertTrue(fired)
                    if path in (self.fs.SOURCE, self.fs.DEPLOYED):
                        self.assertEqual((self.root / path).read_bytes(), self.baseline)
                    before = snapshot(self.root)
                    self.assertFalse(self.api.recover(self.root).success)
                    self.assertEqual(snapshot(self.root), before)

    def test_mkdir_eio_and_enospc_before_mutation_can_be_recovered(self):
        for directory in self.fs.OUTPUT_DIRS:
            for code in (errno.EIO, errno.ENOSPC):
                with self.subTest(directory=directory, errno=code):
                    self.fresh()
                    original = os.mkdir
                    fired = False
                    def fail(path, *args, **kwargs):
                        nonlocal fired
                        if path == directory.rsplit("/", 1)[1]:
                            fired = True
                            raise OSError(code, "injected mkdir")
                        return original(path, *args, **kwargs)
                    with patch("canary_fs.os.mkdir", side_effect=fail):
                        self.assertFalse(self.api.apply(self.root).success)
                    self.assertTrue(fired)
                    self.assertTrue(self.api.recover(self.root).success)
                    self.assertFalse((self.root / "config/panda").exists())

    def test_completed_applied_and_restored_records_retry_all_parent_fsyncs(self):
        for phase in ("applied", "restored"):
            for directory in ("config/ghostty", "source/home/dot_config/ghostty", "state/canary",
                              "config", "config/panda/generated" if phase == "applied" else ""):
                with self.subTest(phase=phase, directory=directory):
                    self.fresh()
                    self.assertTrue(self.api.apply(self.root).success)
                    if phase == "restored":
                        self.assertTrue(self.api.recover(self.root).success)
                    original = os.fsync
                    parent = str(self.root / directory)
                    fired = False
                    def fail(fd):
                        nonlocal fired
                        if os.readlink(f"/proc/self/fd/{fd}") == parent:
                            fired = True
                            raise OSError(errno.EIO, "persistent parent EIO")
                        return original(fd)
                    before = snapshot(self.root)
                    with patch("canary_fs.os.fsync", side_effect=fail):
                        self.assertFalse(self.api.inspect(self.root).success)
                        self.assertFalse(self.api.inspect(self.root).success)
                    self.assertTrue(fired)
                    self.assertEqual(snapshot(self.root), before)
                    self.assertTrue(self.api.inspect(self.root).success)
                    self.assertTrue(self.api.recover(self.root).success)

    def test_rollback_unlink_and_rmdir_failures_retain_recoverable_journal(self):
        for operation in ("unlink", "rmdir"):
            with self.subTest(operation=operation):
                self.fresh()
                self.assertTrue(self.api.apply(self.root).success)
                original = getattr(os, operation)
                fired = False
                def fail(path, *args, **kwargs):
                    nonlocal fired
                    if path in ("ghostty.conf", "generated"):
                        fired = True
                        raise OSError(errno.EIO, "injected cleanup failure")
                    return original(path, *args, **kwargs)
                with patch("canary_fs.os." + operation, side_effect=fail):
                    self.assertFalse(self.api.recover(self.root).success)
                self.assertTrue(fired)
                self.assertTrue((self.root / self.fs.JOURNAL).exists())
                self.assertTrue(self.api.recover(self.root).success)
                self.assertFalse((self.root / "config/panda").exists())

    def child(self, script):
        env = {"HOME": str(self.root / "home"), "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8",
               "PYTHONDONTWRITEBYTECODE": "1", "TMPDIR": str(self.root / "cache"),
               "XDG_RUNTIME_DIR": str(self.root / "runtime")}
        env.update({"XDG_" + n.upper() + "_HOME": str(self.root / n)
                    for n in ("config", "data", "state", "cache")})
        return subprocess.run([sys.executable, "-B", "-I", "-S", "-c",
                               "import os,sys; from pathlib import Path; sys.path.insert(0,sys.argv[1]); "
                               "import canary,canary_fs; root=Path(sys.argv[2]);\n" + script,
                               str(COMMON), str(self.root)], env=env, cwd=self.root,
                              capture_output=True, text=True, timeout=10)

    def test_advisory_lock_contention_does_not_create_journal(self):
        with self.fs.CanaryFS(self.root) as fs, fs.locked():
            before = snapshot(self.root)
            process = self.child("r=canary.apply(root); print(r.message); sys.exit(0 if not r.success else 1)")
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertIn("fixture-only", process.stdout)
            self.assertEqual(snapshot(self.root), before)

    def test_fresh_process_abrupt_exit_after_durable_target_allows_recovery(self):
        process = self.child("original=canary_fs.CanaryFS.replace\n"
                             "def replace(fs,path,image,*,expected):\n"
                             " original(fs,path,image,expected=expected)\n"
                             " if path==canary_fs.TARGET: os._exit(86)\n"
                             "canary_fs.CanaryFS.replace=replace\ncanary.apply(root)")
        self.assertEqual(process.returncode, 86, process.stderr)
        process = self.child("r=canary.recover(root); print(r.message); sys.exit(0 if r.success else 1)")
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertFalse((self.root / "config/panda").exists())
        self.assertEqual((self.root / self.fs.SOURCE).read_bytes(), self.baseline)

    def test_sigkill_in_mkdir_provenance_gap_requires_manual_inspection(self):
        process = self.child("import signal\noriginal=os.mkdir\n"
                             "def mkdir(path,*args,**kwargs):\n"
                             " original(path,*args,**kwargs)\n"
                             " if path=='panda': os.kill(os.getpid(),signal.SIGKILL)\n"
                             "os.mkdir=mkdir\ncanary.apply(root)")
        self.assertEqual(process.returncode, -9, process.stderr)
        before = snapshot(self.root)
        process = self.child("r=canary.recover(root); print(r.message); sys.exit(0 if not r.success else 1)")
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(snapshot(self.root), before)
        self.assertTrue((self.root / "config/panda").exists())

    def test_journal_parent_fsync_failure_after_rename_replays_from_visible_record(self):
        for checkpoint in ("prepared", "target-done", "applied", "restored"):
            with self.subTest(checkpoint=checkpoint):
                self.fresh()
                if checkpoint == "restored":
                    self.assertTrue(self.api.apply(self.root).success)
                original = os.fsync
                fired = False
                parent = str(self.root / self.fs.SUPPORT)
                def fail(fd):
                    nonlocal fired
                    journal = self.root / self.fs.JOURNAL
                    if not fired and os.readlink(f"/proc/self/fd/{fd}") == parent and journal.exists():
                        data = self.fs.unpack(journal.read_bytes())
                        match = data["phase"] == checkpoint
                        if checkpoint == "target-done":
                            match = data["phase"] == "applying" and data["sequence"] == 4 and data["intent"] is None
                        if match:
                            fired = True
                            raise OSError(errno.EIO, "journal parent fsync after rename")
                    return original(fd)
                with patch("canary_fs.os.fsync", side_effect=fail):
                    result = self.api.recover(self.root) if checkpoint == "restored" else self.api.apply(self.root)
                    self.assertFalse(result.success)
                self.assertTrue(fired)
                self.assertTrue(self.api.recover(self.root).success)
                self.assertFalse((self.root / "config/panda").exists())
                self.assertEqual((self.root / self.fs.SOURCE).read_bytes(), self.baseline)

    def test_preexisting_parent_fsync_after_rename_remains_retryable(self):
        self.assertTrue(self.api.apply(self.root).success)
        original = os.fsync
        parent = str(self.root / "config/ghostty")
        data = self.fs.unpack((self.root / self.fs.MARKER).read_bytes())
        before_image = self.fs.image_from(data["entries"][2]["before"])
        def noatime_fail(fd):
            if os.readlink(f"/proc/self/fd/{fd}") == parent:
                file_fd = os.open(self.root / self.fs.DEPLOYED, os.O_RDONLY | os.O_NOATIME)
                try:
                    content = os.read(file_fd, 65536)
                finally:
                    os.close(file_fd)
                if content == before_image["content"]:
                    raise OSError(errno.EIO, "preexisting restoration parent EIO")
            return original(fd)
        with patch("canary_fs.os.fsync", side_effect=noatime_fail):
            self.assertFalse(self.api.recover(self.root).success)
            self.assertFalse(self.api.recover(self.root).success)
        self.assertTrue(self.api.recover(self.root).success)

    def test_created_parent_fsync_gap_keeps_ambiguous_provenance_for_manual_review(self):
        original = os.fsync
        parent = str(self.root / "config/panda/generated")
        fired = False
        def fail(fd):
            nonlocal fired
            if (os.readlink(f"/proc/self/fd/{fd}") == parent and
                    (self.root / self.fs.TARGET).exists()):
                fired = True
                raise OSError(errno.EIO, "generated parent EIO after rename")
            return original(fd)
        with patch("canary_fs.os.fsync", side_effect=fail):
            self.assertFalse(self.api.apply(self.root).success)
        self.assertTrue(fired)
        before = snapshot(self.root)
        self.assertFalse(self.api.recover(self.root).success)
        self.assertEqual(snapshot(self.root), before)

    def test_directory_fsync_failure_in_mkdir_gap_preserves_unknown_directory(self):
        original = os.fsync
        fired = False
        def fail(fd):
            nonlocal fired
            if os.readlink(f"/proc/self/fd/{fd}") == str(self.root / "config/panda"):
                fired = True
                raise OSError(errno.EIO, "new directory fsync EIO")
            return original(fd)
        with patch("canary_fs.os.fsync", side_effect=fail):
            self.assertFalse(self.api.apply(self.root).success)
        self.assertTrue(fired)
        before = snapshot(self.root)
        self.assertFalse(self.api.recover(self.root).success)
        self.assertEqual(snapshot(self.root), before)

    def test_completed_journal_requires_consistent_operation_checkpoints(self):
        self.assertTrue(self.api.apply(self.root).success)
        path = self.root / self.fs.JOURNAL
        data = self.fs.unpack(path.read_bytes())
        data.update(sequence=0, completed=0)
        path.write_bytes(self.fs.pack(data))
        before = snapshot(self.root)
        self.assertFalse(self.api.inspect(self.root).success)
        self.assertFalse(self.api.recover(self.root).success)
        self.assertEqual(snapshot(self.root), before)

    def test_unavailable_mount_identity_closes_root_descriptors(self):
        before = len(os.listdir("/proc/self/fd"))
        with patch("canary_fs.mount_id", side_effect=ValueError("unavailable mount identity")):
            for _ in range(5):
                self.assertFalse(self.api.apply(self.root).success)
        self.assertEqual(len(os.listdir("/proc/self/fd")), before)

    def test_parent_substitution_after_mkdir_is_preserved(self):
        original = os.mkdir
        replacements = {}
        def mkdir(name, *args, **kwargs):
            original(name, *args, **kwargs)
            if name == "generated":
                parent = self.root / "config/panda"
                parent.rename(self.root / "config/panda.saved")
                original(parent, 0o700)
                original(parent / "generated", 0o700)
                for path in (parent, parent / "generated"):
                    replacements[path] = path.lstat().st_ino
        with patch("canary_fs.os.mkdir", side_effect=mkdir):
            result = self.api.apply(self.root)
        self.assertTrue(replacements)
        self.assertFalse(result.success, result)
        self.assertIn("incomplete", result.status)
        before = snapshot(self.root)
        for _ in range(2):
            self.assertFalse(self.api.recover(self.root).success)
            self.assertEqual(snapshot(self.root), before)
        for path, inode in replacements.items():
            self.assertEqual(path.lstat().st_ino, inode)
        self.assertTrue((self.root / "config/panda.saved/generated").exists())

    def test_refresh_never_adopts_replaced_child(self):
        self.assertTrue(self.api.apply(self.root).success)
        with self.fs.CanaryFS(self.root) as fs:
            data = self.api._load(fs)
            fs.directories = data["directories"]
            recorded = dict(fs.directories[1]["identity"])
            child = self.root / "config/panda/generated"
            child.rename(self.root / "config/panda/generated.saved")
            child.mkdir(mode=0o700)
            (child / "external").write_bytes(b"external replacement bytes\n")
            before = snapshot(self.root)
            with self.assertRaises(ValueError):
                fs._refresh("config/panda/generated")
            self.assertEqual(fs.directories[1]["identity"], recorded)
            self.assertEqual(snapshot(self.root), before)

    def test_apply_final_sync_rejects_late_changes(self):
        self.final_sync_changes("apply", 2)

    def test_recovery_final_sync_rejects_late_changes(self):
        self.final_sync_changes("recover", 2)

    def test_inspect_final_sync_rejects_late_changes(self):
        self.final_sync_changes("inspect", 1)

    def final_sync_changes(self, action, final_call):
        for subject in (self.fs.SOURCE, self.fs.DEPLOYED, self.fs.JOURNAL, "ancestor", "provenance", self.fs.TARGET):
            with self.subTest(action=action, subject=subject):
                self.fresh()
                if action != "apply":
                    self.assertTrue(self.api.apply(self.root).success)
                original = self.fs.CanaryFS.sync_parents
                calls = 0
                def sync(fs):
                    nonlocal calls
                    original(fs)
                    calls += 1
                    if calls == final_call:
                        if subject == "ancestor":
                            parent = self.root / "config/ghostty"
                            parent.rename(self.root / "config/ghostty.saved")
                            parent.mkdir(mode=0o700)
                            (parent / "config.ghostty").write_bytes(b"external ancestor bytes\n")
                        elif subject == "provenance":
                            parent = self.root / "config/panda"
                            if parent.exists():
                                info = parent.lstat()
                                os.utime(parent, ns=(info.st_atime_ns, info.st_mtime_ns + 1))
                            else:
                                parent.mkdir(mode=0o700)
                        elif subject == self.fs.TARGET:
                            (self.root / subject).parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                            (self.root / subject).write_bytes(b"late generated bytes\n")
                        else:
                            (self.root / subject).write_bytes(b"late external bytes\n")
                with patch.object(self.fs.CanaryFS, "sync_parents", sync):
                    result = getattr(self.api, action)(self.root)
                self.assertEqual(calls, final_call)
                self.assertFalse(result.success, result)
                self.assertIn("incomplete", result.status)
                before = snapshot(self.root)
                for _ in range(2):
                    self.assertFalse(self.api.inspect(self.root).success)
                    self.assertFalse(self.api.recover(self.root).success)
                    self.assertEqual(snapshot(self.root), before)

    def test_restored_retry_final_sync_rejects_late_edit(self):
        self.assertTrue(self.api.apply(self.root).success)
        self.assertTrue(self.api.recover(self.root).success)
        original = self.fs.CanaryFS.sync_parents
        def sync(fs):
            original(fs)
            (self.root / self.fs.SOURCE).write_bytes(b"late baseline edit\n")
        with patch.object(self.fs.CanaryFS, "sync_parents", sync):
            self.assertFalse(self.api.recover(self.root).success)
        before = snapshot(self.root)
        self.assertFalse(self.api.recover(self.root).success)
        self.assertEqual(snapshot(self.root), before)

    def test_unused_recovery_final_sync_rejects_late_edit(self):
        original = self.fs.CanaryFS.sync_parents
        def sync(fs):
            original(fs)
            (self.root / self.fs.DEPLOYED).write_bytes(b"late unused edit\n")
        with patch.object(self.fs.CanaryFS, "sync_parents", sync):
            self.assertFalse(self.api.recover(self.root).success)
        before = snapshot(self.root)
        self.assertFalse(self.api.recover(self.root).success)
        self.assertEqual(snapshot(self.root), before)

    def test_interrupted_journal_rejects_impossible_prefixes_before_lock(self):
        variants = [
            dict(phase="applying", sequence=0, completed=0, intent=None),
            dict(phase="recovering", sequence=0, completed=0, intent=None),
            dict(phase="applying", sequence=8, completed=7,
                 intent=dict(kind="unlink", path=self.fs.TARGET)),
            dict(phase="applying", sequence=8, completed=6,
                 intent=dict(kind="replace", path=self.fs.DEPLOYED)),
        ]
        for update in variants:
            with self.subTest(update=update):
                self.fresh()
                self.assertTrue(self.api.apply(self.root).success)
                path = self.root / self.fs.JOURNAL
                original = self.fs.unpack(path.read_bytes())
                path.write_bytes(self.fs.pack({**original, **update}))
                before = snapshot(self.root)
                locked = self.fs.CanaryFS.locked
                locks = []
                def lock(fs):
                    locks.append(True)
                    return locked(fs)
                with patch.object(self.fs.CanaryFS, "locked", lock):
                    self.assertFalse(self.api.inspect(self.root).success)
                    self.assertFalse(self.api.recover(self.root).success)
                self.assertEqual(locks, [], "inconsistent record refused before lock")
                self.assertEqual(snapshot(self.root), before)

    def test_recovery_completion_without_required_stage_is_refused(self):
        self.assertTrue(self.api.apply(self.root).success)
        journal = self.root / self.fs.JOURNAL
        data = self.fs.unpack(journal.read_bytes())
        data.update(phase="recovering", sequence=9, completed=9, intent=None)
        journal.write_bytes(self.fs.pack(data))
        before = snapshot(self.root)
        locked = self.fs.CanaryFS.locked
        locks = []
        def lock(fs):
            locks.append(True)
            return locked(fs)
        with patch.object(self.fs.CanaryFS, "locked", lock):
            self.assertFalse(self.api.inspect(self.root).success)
            self.assertFalse(self.api.recover(self.root).success)
        self.assertEqual(locks, [])
        self.assertEqual(snapshot(self.root), before)

    def test_recovery_intent_requires_installation_completion_evidence(self):
        for checkpoint, kind, path, restore_source in (
                (6, "stage", self.fs.SOURCE, False),
                (6, "replace", self.fs.SOURCE, True),
                (4, "unlink", self.fs.TARGET, False)):
            with self.subTest(kind=kind, path=path):
                self.fresh()
                original = self.api._Journal.done
                def done(journal):
                    original(journal)
                    if journal.data["completed"] == checkpoint:
                        raise OSError(errno.EIO, "stop at installed image checkpoint")
                with patch.object(self.api._Journal, "done", done):
                    self.assertFalse(self.api.apply(self.root).success)
                journal = self.root / self.fs.JOURNAL
                data = self.fs.unpack(journal.read_bytes())
                if restore_source:
                    before = self.fs.image_from(data["entries"][1]["before"])
                    source = self.root / self.fs.SOURCE
                    source.write_bytes(before["content"])
                    os.utime(source, ns=(before["atime_ns"], before["mtime_ns"]))
                data.update(phase="recovering", sequence=checkpoint + (2 if kind == "replace" else 1),
                            completed=2, intent=dict(kind=kind, path=path))
                journal.write_bytes(self.fs.pack(data))
                before = snapshot(self.root)
                locked = self.fs.CanaryFS.locked
                locks = []
                def lock(fs):
                    locks.append(True)
                    return locked(fs)
                with patch.object(self.fs.CanaryFS, "locked", lock):
                    self.assertFalse(self.api.inspect(self.root).success)
                    self.assertFalse(self.api.recover(self.root).success)
                self.assertEqual(locks, [])
                self.assertEqual(snapshot(self.root), before)

    def test_stage_refresh_failure_closes_fd_and_retains_evidence(self):
        for fault in ("EIO", "mode"):
            with self.subTest(fault=fault):
                self.fresh()
                original = os.open
                descriptors = []
                changed = []
                def opened(name, *args, **kwargs):
                    fd = original(name, *args, **kwargs)
                    if name == ".ghostty.conf.b3b-stage" and kwargs.get("dir_fd") is not None:
                        descriptors.append(fd)
                        if fault == "mode":
                            parent = self.root / "config/panda/generated"
                            changed.append((parent, parent.lstat().st_ino))
                            parent.chmod(0o500)
                    return fd
                stamp = self.fs.CanaryFS.directory_stamp
                def read_stamp(fs, path):
                    if fault == "EIO" and path == "config/panda/generated" and descriptors:
                        raise OSError(errno.EIO, "ordinary provenance read failure")
                    return stamp(fs, path)
                before_fds = len(os.listdir("/proc/self/fd"))
                try:
                    with patch("canary_fs.os.open", side_effect=opened), \
                            patch.object(self.fs.CanaryFS, "directory_stamp", read_stamp):
                        result = self.api.apply(self.root)
                    after_fds = len(os.listdir("/proc/self/fd"))
                finally:
                    # Close only still-live descriptors opened by this test, even on RED.
                    for fd in descriptors:
                        try:
                            if os.readlink(f"/proc/self/fd/{fd}") == str(self.root / self.fs.STAGES[self.fs.TARGET]):
                                os.close(fd)
                        except FileNotFoundError:
                            pass
                    for parent, inode in changed:
                        self.assertEqual(parent.lstat().st_ino, inode)
                        parent.chmod(0o700)
                self.assertTrue(descriptors)
                self.assertFalse(result.success)
                self.assertIn("incomplete", result.status)
                self.assertTrue((self.root / self.fs.STAGES[self.fs.TARGET]).exists())
                self.assertEqual(after_fds, before_fds)
                before = snapshot(self.root)
                self.assertFalse(self.api.recover(self.root).success)
                self.assertEqual(snapshot(self.root), before)
