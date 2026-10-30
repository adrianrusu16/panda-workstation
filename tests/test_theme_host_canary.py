"""B3B1 file-only fixture regressions; no native/GUI or live path destinations."""

import ast
import errno
import hashlib
import importlib
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import unittest
from unittest.mock import patch

from host_canary_operator import Operator

COMMON = Path(__file__).resolve().parents[1] / "theme/panda/common"
sys.path.insert(0, str(COMMON))


def snapshot(root):
    result = {}
    def paths(path):
        yield path
        if stat.S_ISDIR(path.lstat().st_mode):
            fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NOATIME)
            try:
                names = os.listdir(fd)
            finally:
                os.close(fd)
            for name in names:
                yield from paths(path / name)
    for path in paths(root):
        s = path.lstat()
        data = None
        if stat.S_ISREG(s.st_mode):
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NOATIME)
            with os.fdopen(fd, "rb") as f:
                data = f.read()
        result[str(path.relative_to(root))] = (
            s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid,
            s.st_atime_ns, s.st_mtime_ns, s.st_ctime_ns, data)
    return result


class HostCanaryContracts(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec("host_canary"),
                             "separate file-only host-canary implementation missing")
        self.api = importlib.import_module("host_canary")
        source = COMMON.parents[2] / "home/dot_config/ghostty/config.ghostty"
        fd = os.open(source, os.O_RDONLY | os.O_NOATIME | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as f:
            self.baseline = f.read()
        self.operator = self.fresh()
        self.root = self.operator.root

    def fresh(self, stop=None):
        operator = Operator(self.api, self.baseline, self.addCleanup)
        operator.provision(stop=stop)
        return operator

    def unprovisioned(self):
        return Operator(self.api, self.baseline, self.addCleanup)

    def program_bytes(self):
        fd = os.open(self.api.__file__, os.O_RDONLY | os.O_NOFOLLOW | os.O_NOATIME)
        with os.fdopen(fd, "rb") as f:
            return f.read()

    def reconciliation_tree(self, op):
        """Exact private-fixture metadata and byte digests, without huge failure dumps."""
        result = {}
        for path, entry in snapshot(op.root).items():
            s = (op.root / path).lstat()
            result[path] = (*entry[:-1], s.st_size, s.st_nlink,
                            tuple(os.listxattr(op.root / path, follow_symlinks=False)),
                            hashlib.sha256(entry[-1]).hexdigest() if entry[-1] is not None else None)
        return result

    def pending_reconciliation(self, kind):
        op = self.fresh()
        if kind == "unlink":
            self.assertEqual(self.api.install_minimal(op.root)["status"], "installed")
        point = ("published:" if kind == "publish" else "unlinked:") + self.api.TARGET
        def interrupt(name):
            if name == point:
                raise OSError(errno.EIO, "controlled post-operation interruption")
        with patch("host_canary._checkpoint", side_effect=interrupt):
            answer = (self.api.install_minimal if kind == "publish" else self.api.recover)(op.root)
        self.assertEqual(answer["status"], "incomplete")
        raw = snapshot(op.root)[self.api.JOURNAL][-1]
        pending = self.api.unpack(raw)
        self.assertEqual(pending["intent"], [kind, self.api.TARGET])
        self.assertEqual(pending["phase"], "applying" if kind == "publish" else "recovering")
        return op

    def reconciliation_edit(self, op, path, data=b"# fixture reconciliation foreign edit\n"):
        fd = os.open(op.root / path, os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW)
        try:
            position = 0
            while position < len(data):
                position += os.write(fd, data[position:])
            os.utime(fd, ns=(1, 2))
        finally:
            os.close(fd)

    def reconciliation_probe(self, op, mutate, sync_number=2, fault=None):
        before = self.reconciliation_tree(op)
        journal_bytes = snapshot(op.root)[self.api.JOURNAL][-1]
        expected = dict(before)
        events, attempts, replacements = [], [], []
        real_sync, real_record, real_replace = self.api.FS.sync, self.api.FS.record, os.replace
        real_reconcile = self.api.reconcile
        reconciling = False
        count = 0
        injections = 0
        def reconcile(fs, e, baseline, j, journal):
            nonlocal reconciling
            self.assertIn(j["intent"], (["publish", self.api.TARGET], ["unlink", self.api.TARGET]))
            reconciling = True
            try:
                return real_reconcile(fs, e, baseline, j, journal)
            finally:
                reconciling = False
        def sync(fs, *args, **kwargs):
            nonlocal count, expected, injections
            count += 1
            selected = count == 1 if sync_number == 1 else reconciling
            events.append(["sync-begin", count])
            if selected and fault is not None:
                injections += 1
                raise OSError(fault, "persistent reconciliation sync fault")
            real_sync(fs, *args, **kwargs)
            events.append(["sync-end", count])
            if selected and mutate is not None:
                mutate()
                injections += 1
                expected = self.reconciliation_tree(op)
                events.append(["external-edit", count])
        def record(fs, path, payload, current):
            if path == self.api.JOURNAL:
                attempts.append(path)
                events.append(["journal-attempt", len(attempts)])
            return real_record(fs, path, payload, current)
        def replace(source, target, **kwargs):
            answer = real_replace(source, target, **kwargs)
            if os.path.basename(os.fsdecode(target)) == "journal.json":
                replacements.append(os.fsdecode(target))
                events.append(["journal-replacement", len(replacements)])
            return answer
        descriptors = len(os.listdir("/proc/self/fd"))
        with patch("host_canary.reconcile", reconcile), \
                patch.object(self.api.FS, "sync", sync), patch.object(self.api.FS, "record", record), \
                patch("host_canary.os.replace", replace):
            answer = self.api.recover(op.root)
        after = self.reconciliation_tree(op)
        actual_bytes = snapshot(op.root)[self.api.JOURNAL][-1]
        evidence = dict(status=answer["status"], events=events, attempts=len(attempts),
                        replacements=len(replacements), root_identity=op.initial,
                        journal_before=before[self.api.JOURNAL], journal_after=after[self.api.JOURNAL],
                        journal_bytes_unchanged=actual_bytes == journal_bytes,
                        source_retained=after[self.api.SOURCE] == expected[self.api.SOURCE])
        print("RECONCILIATION_EVIDENCE " + json.dumps(evidence, sort_keys=True))
        self.assertEqual(injections, 1, "selected reconciliation injection did not occur exactly once")
        self.assertEqual(len(os.listdir("/proc/self/fd")), descriptors, "recovery leaked a descriptor")
        self.assertEqual(answer["status"], "incomplete" if fault is not None else "manual-inspection-required")
        self.assertEqual(after[self.api.SOURCE], expected[self.api.SOURCE], "injected source was changed")
        self.assertEqual(len(attempts), 0, "reconciliation tried to publish a journal after the fault")
        self.assertEqual(len(replacements), 0, "reconciliation replaced the journal after the fault")
        self.assertEqual(actual_bytes, journal_bytes, "pending journal bytes changed")
        self.assertEqual(after[self.api.JOURNAL], before[self.api.JOURNAL], "pending journal identity changed")
        self.assertEqual(after, expected, "recovery changed fixture images, metadata or stages")
        return evidence

    def test_reconciliation_publish_post_sync_source_edit_preserves_journal(self):
        op = self.pending_reconciliation("publish")
        self.reconciliation_probe(op, lambda: self.reconciliation_edit(op, self.api.SOURCE))

    def test_reconciliation_unlink_post_sync_source_edit_preserves_journal(self):
        op = self.pending_reconciliation("unlink")
        self.reconciliation_probe(op, lambda: self.reconciliation_edit(op, self.api.SOURCE))

    def test_reconciliation_initial_replay_source_edit_preserves_journal(self):
        for kind in ("publish", "unlink"):
            with self.subTest(kind=kind):
                op = self.pending_reconciliation(kind)
                self.reconciliation_probe(op, lambda: self.reconciliation_edit(op, self.api.SOURCE), 1)

    def test_reconciliation_clean_interrupted_histories_recover_idempotently(self):
        for kind in ("publish", "unlink"):
            with self.subTest(kind=kind):
                op = self.pending_reconciliation(kind)
                self.assertEqual(self.api.recover(op.root)["status"], self.api.RESTORED)
                before = self.reconciliation_tree(op)
                self.assertEqual(self.api.recover(op.root)["status"], self.api.RESTORED)
                self.assertEqual(self.reconciliation_tree(op), before)
                current = snapshot(op.root)
                self.assertEqual(current[self.api.SOURCE][-1], self.baseline)
                self.assertEqual(current[self.api.DEPLOYED][-1], self.baseline)
                self.assertNotIn(self.api.TARGET, current)

    def test_reconciliation_persistent_sync_errors_preserve_pending_journal(self):
        for kind in ("publish", "unlink"):
            for fault in (errno.EIO, errno.ENOSPC):
                with self.subTest(kind=kind, fault=fault):
                    op = self.pending_reconciliation(kind)
                    for _ in range(2):
                        self.reconciliation_probe(op, None, fault=fault)
                    self.assertEqual(self.api.recover(op.root)["status"], self.api.RESTORED)

    def test_reconciliation_post_sync_prerequisite_changes_preserve_journal(self):
        roles = (self.api.PROVISION, self.api.BASELINE, self.api.PROGRAM,
                 self.api.SOURCE_BEFORE, self.api.DEPLOYED_BEFORE, "config/ghostty")
        for kind in ("publish", "unlink"):
            for role in roles:
                with self.subTest(kind=kind, role=role):
                    op = self.pending_reconciliation(kind)
                    def mutate():
                        path = op.root / role
                        if role == "config/ghostty":
                            path.rename(path.with_name("original-ghostty"))
                            path.mkdir(mode=0o700)
                        elif role in (self.api.PROVISION, self.api.BASELINE):
                            held = os.open(path, os.O_RDONLY | os.O_NOATIME | os.O_NOFOLLOW)
                            try:
                                image = snapshot(op.root)[role][-1]
                                path.unlink()
                                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                                try:
                                    self.assertNotEqual(os.fstat(fd).st_ino, os.fstat(held).st_ino)
                                    position = 0
                                    while position < len(image):
                                        position += os.write(fd, image[position:])
                                    os.utime(fd, ns=(0, 0))
                                finally:
                                    os.close(fd)
                            finally:
                                os.close(held)
                        else:
                            self.reconciliation_edit(op, role)
                    self.reconciliation_probe(op, mutate)

    def test_schema2_baseline_is_independent_completed_receipt_authority(self):
        # Design-new shape assertions; receipt substitution is the behavioral RED.
        with self.api.FS(self.root) as fs:
            b = self.api.unpack(self.api.decode(fs.read(self.api.BASELINE)["image"]))
            r = self.api.unpack(self.api.decode(fs.read(self.api.PROVISION)["image"]))
        self.assertEqual(b["schema"], 2)
        self.assertEqual(r["schema"], 2)
        self.assertRegex(b["enrollment_id"], r"^[0-9a-f]{32}$")
        self.assertEqual(r["enrollment_id"], b["enrollment_id"])
        self.assertEqual(r["state"], "completed")
        self.assertNotIn("sealed", r)
        self.assertNotIn("seal_identity", r)
        self.assertEqual(r["preseal"], b["preseal"])
        self.assertEqual(b["completed_provisioning"]["image"],
                         self.api.image(self.api.pack(r)))
        self.assertIn("ctime_ns", b["completed_provisioning"])

    def test_receipt_ctime_only_change_refuses_before_lock_or_sync(self):
        path = self.root / self.api.PROVISION
        before = path.stat()
        path.chmod(0o600)  # Same inode/mode/atime/mtime; ctime alone changes.
        after = path.stat()
        self.assertEqual((before.st_ino, before.st_atime_ns, before.st_mtime_ns),
                         (after.st_ino, after.st_atime_ns, after.st_mtime_ns))
        self.assertNotEqual(before.st_ctime_ns, after.st_ctime_ns)
        self.assert_authority_refused()

    def test_receipt_recomputed_self_pin_refuses_before_lock_or_sync(self):
        path = self.root / self.api.PROVISION
        with self.api.FS(self.root) as fs:
            original = fs.read(self.api.PROVISION)
        value = self.api.unpack(self.api.decode(original["image"]))
        path.unlink()
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            with self.api.FS(self.root) as fs:
                value["seal_identity"] = fs.pin(fd, file=True)
            raw = self.api.pack(value)
            self.assertEqual(os.write(fd, raw), len(raw))
            os.utime(fd, ns=(original["image"]["atime"], original["image"]["mtime"]))
        finally:
            os.close(fd)
        self.assert_authority_refused()

    def assert_authority_refused(self, root=None):
        with patch("host_canary.fcntl.flock", side_effect=AssertionError("authority lock")), \
                patch("host_canary.os.fsync", side_effect=AssertionError("authority sync")), \
                patch("host_canary.os.write", side_effect=AssertionError("authority write")), \
                patch.object(self.api.FS, "create", side_effect=AssertionError("authority create")):
            self.assert_refused_without_changes(root)

    def cold(self, root, action, *, forbid_mutation=False):
        """Only root + frozen executable; no Provider, repo imports, or PATH help."""
        program = str(root / self.api.PROGRAM)
        script = ("import os,sys,runpy,json\nrepo=" + repr(str(COMMON.parents[2])) + "\n"
                  "def deny(event,args):\n"
                  " if event=='open' and isinstance(args[0],(str,bytes)) and os.fsdecode(args[0]).startswith(repo+'/'):raise FileNotFoundError('denied repository')\n"
                  " if event=='import' and args[0].split('.')[0] in ('host_canary','palette','render','adapters'):raise ImportError('denied project')\n"
                  "sys.addaudithook(deny)\n"
                  "ns=runpy.run_path(" + repr(program) + ")\n")
        if forbid_mutation:
            script += ("def deny_mutation(*a,**kw):raise AssertionError('cold mutation/lock/sync')\n"
                       "ns['fcntl'].flock=deny_mutation\nns['os'].fsync=deny_mutation\n"
                       "ns['os'].write=deny_mutation\nns['FS'].create=deny_mutation\n")
        script += "print(json.dumps(ns[" + repr(action) + "](" + repr(str(root)) + ")))\n"
        env = {"HOME": str(root / "home"), "PATH": "", "PYTHONDONTWRITEBYTECODE": "1",
               "TMPDIR": str(root / "runtime")}
        for role in ("config", "data", "state", "cache", "runtime"):
            env["XDG_" + ("RUNTIME_DIR" if role == "runtime" else role.upper() + "_HOME")] = str(root / role)
        result = subprocess.run(["/usr/bin/python3", "-B", "-I", "-S", "-c", script],
                                cwd=root / "home", env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def rewrite_record(self, root, role, change):
        with self.api.FS(root) as fs:
            obj = fs.read(role)
        value = self.api.unpack(self.api.decode(obj["image"]))
        change(value)
        path = root / role
        path.write_bytes(self.api.pack(value))
        os.utime(path, ns=(obj["image"]["atime"], obj["image"]["mtime"]))

    def replace_identical(self, root, role):
        path = root / role
        with self.api.FS(root) as fs:
            original = fs.read(role)
        held = os.open(path, os.O_RDONLY | os.O_NOATIME | os.O_NOFOLLOW)
        self.addCleanup(os.close, held)
        replacement = root / "controlled-replacement"
        fd = os.open(replacement, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     original["image"]["mode"])
        try:
            raw = self.api.decode(original["image"])
            with os.fdopen(fd, "wb", closefd=False) as f:
                f.write(raw)
            os.utime(fd, ns=(original["image"]["atime"], original["image"]["mtime"]))
            self.assertNotEqual(os.fstat(fd).st_ino, os.fstat(held).st_ino)
        finally:
            os.close(fd)
        replacement.replace(path)

    def test_schema2_fresh_process_install_recovery_and_cleanup(self):
        self.assertEqual(self.cold(self.root, "install_minimal")["status"], "installed")
        self.assertEqual(self.cold(self.root, "recover")["status"], self.api.RESTORED)
        self.assertEqual(self.cold(self.root, "recover")["status"], self.api.RESTORED)
        self.operator.cleanup_outputs()
        self.assertEqual(self.cold(self.root, "recover")["status"], self.api.CLOSED)
        with self.api.FS(self.root) as fs:
            records = {p: self.api.unpack(self.api.decode(fs.read(p)["image"]))
                       for p in (self.api.BASELINE, self.api.PROVISION, self.api.JOURNAL, self.api.CLEANUP)}
            b = fs.read(self.api.BASELINE)
        self.assertEqual({v["schema"] for v in records.values()}, {2})
        self.assertEqual(len({v["enrollment_id"] for v in records.values()}), 1)
        for p in (self.api.JOURNAL, self.api.CLEANUP):
            self.assertEqual(records[p]["enrollment"], b["image"]["sha256"])

    def test_schema2_equal_baseline_copy_accepts_but_receipt_copy_refuses(self):
        self.replace_identical(self.root, self.api.BASELINE)
        self.assertEqual(self.cold(self.root, "status", forbid_mutation=True)["status"], "not-started")
        self.assertEqual(self.cold(self.root, "install_minimal")["status"], "installed")
        self.assertEqual(self.cold(self.root, "recover")["status"], self.api.RESTORED)
        op = self.fresh()
        self.replace_identical(op.root, self.api.PROVISION)
        self.assert_authority_refused(op.root)
        self.assertEqual(self.cold(op.root, "install_minimal", forbid_mutation=True)["status"],
                         "manual-inspection-required")

    def test_schema2_receipt_mutations_refuse_in_fresh_process_before_lock(self):
        for kind in ("bytes", "atime", "mtime", "ctime", "symlink", "hardlink", "mode", "xattr"):
            with self.subTest(kind=kind):
                op = self.fresh()
                path = op.root / self.api.PROVISION
                if kind == "bytes":
                    path.write_bytes(b"broken\n")
                elif kind in ("atime", "mtime"):
                    os.utime(path, ns=(1, 0) if kind == "atime" else (0, 1))
                elif kind == "ctime":
                    path.chmod(0o600)
                elif kind == "symlink":
                    path.rename(path.with_name("held-receipt")); path.symlink_to("held-receipt")
                elif kind == "hardlink":
                    os.link(path, path.with_name("alias"))
                elif kind == "mode":
                    path.chmod(0o644)
                else:
                    os.setxattr(path, "user.unapproved", b"value")
                self.assert_authority_refused(op.root)
                self.assertEqual(self.cold(op.root, "install_minimal", forbid_mutation=True)["status"],
                                 "manual-inspection-required")

    def test_schema2_old_mixed_extra_and_cross_enrollment_records_refuse(self):
        for role in (self.api.BASELINE, self.api.PROVISION, self.api.JOURNAL, self.api.CLEANUP):
            for field, value in (("schema", 1), ("schema", True), ("enrollment_id", "a" * 32),
                                 ("enrollment_id", "A" * 32), ("enrollment_id", "0" * 31),
                                 ("extra", 1), ("enrollment", "0" * 64)):
                with self.subTest(role=role, field=field, value=value):
                    op = self.fresh()
                    if role in (self.api.JOURNAL, self.api.CLEANUP):
                        self.assertEqual(self.api.install_minimal(op.root)["status"], "installed")
                    if role == self.api.CLEANUP:
                        self.assertEqual(self.api.recover(op.root)["status"], self.api.RESTORED)
                        self.api.CleanupProvider(op.root).start()
                    self.rewrite_record(op.root, role, lambda r: r.update({field: value}))
                    before = snapshot(op.root)
                    with patch("host_canary.fcntl.flock", side_effect=AssertionError("invalid ledger lock")), \
                            patch("host_canary.os.fsync", side_effect=AssertionError("invalid ledger sync")), \
                            patch("host_canary.os.write", side_effect=AssertionError("invalid ledger write")):
                        self.assertEqual(self.api.recover(op.root)["status"], "manual-inspection-required")
                    self.assertEqual(snapshot(op.root), before)

    def test_schema2_baseline_invalid_content_metadata_or_absence_refuses(self):
        for kind in ("missing", "partial", "bytes", "atime", "mtime", "mode", "xattr"):
            with self.subTest(kind=kind):
                op = self.fresh()
                path = op.root / self.api.BASELINE
                if kind == "missing": path.unlink()
                elif kind in ("partial", "bytes"): path.write_bytes(b"{" if kind == "partial" else b"broken\n")
                elif kind in ("atime", "mtime"): os.utime(path, ns=(1, 0) if kind == "atime" else (0, 1))
                elif kind == "mode": path.chmod(0o644)
                else: os.setxattr(path, "user.unapproved", b"value")
                self.assert_authority_refused(op.root)

    def test_schema2_recovery_replays_before_any_journal_write(self):
        self.assertEqual(self.api.install_minimal(self.root)["status"], "installed")
        before = snapshot(self.root)
        for fault in (errno.EIO, errno.ENOSPC):
            for attempt in range(2):
                with self.subTest(fault=fault, attempt=attempt), \
                        patch.object(self.api.FS, "sync", side_effect=OSError(fault, "persistent replay fault")), \
                        patch.object(self.api.FS, "record", side_effect=AssertionError("write before replay")), \
                        patch.object(self.api.FS, "create", side_effect=AssertionError("create before replay")):
                    self.assertEqual(self.api.recover(self.root)["status"], "incomplete")
                self.assertEqual(snapshot(self.root), before)
        self.assertEqual(self.api.recover(self.root)["status"], self.api.RESTORED)

    def test_schema2_historical_preseal_is_not_the_current_receipt(self):
        with self.api.FS(self.root) as fs:
            e, b = self.api.load(fs)
            self.assertEqual(e["completed_provisioning"], fs.read(self.api.PROVISION, authority=True))
        self.assertNotEqual(e["preseal"]["pin"]["ino"], e["completed_provisioning"]["pin"]["ino"])
        preseal = self.api.unpack(self.api.decode(e["preseal"]["image"]))
        self.assertEqual((preseal["state"], preseal["preseal"]), ("provisioning", None))
        self.assertEqual(self.cold(self.root, "install_minimal")["status"], "installed")

    def test_schema2_readonly_observation_never_replays_or_writes(self):
        before = snapshot(self.root)
        with patch("host_canary.fcntl.flock", side_effect=AssertionError("readonly lock")), \
                patch("host_canary.os.fsync", side_effect=AssertionError("readonly sync")), \
                patch("host_canary.os.write", side_effect=AssertionError("readonly write")), \
                patch.object(self.api.FS, "create", side_effect=AssertionError("readonly create")):
            for method in (self.api.preview, self.api.status):
                answer = method(self.root)
                self.assertEqual(answer["status"], "not-started")
                self.assertIn("observed-checkpoint-only", answer["durability"])
        self.assertEqual(snapshot(self.root), before)

    def test_schema2_seal_io_and_publication_failure_matrix(self):
        """Design-new baseline-last boundaries; real validation remains enabled."""
        stage = self.api.STAGES[self.api.PROVISION]
        cases = ("stage-open", "stage-write", "stage-fsync", "stage-parent-fsync",
                 "rename", "receipt-fsync", "receipt-parent-fsync", "baseline-open",
                 "baseline-write", "baseline-fsync", "baseline-parent-fsync", "final-sync")
        for fault in (errno.EIO, errno.ENOSPC):
            for boundary in cases:
                with self.subTest(fault=fault, boundary=boundary):
                    op = self.fresh(stop=self.api.OUTPUT_DIRS[1] + ":attested")
                    originals = {n: getattr(os, n) for n in ("open", "write", "fsync", "replace")}
                    fired = False
                    partial = False
                    def fail():
                        nonlocal fired
                        fired = True
                        raise OSError(fault, "seal fault: " + boundary)
                    def opened(path, flags, *a, **kw):
                        name = os.fsdecode(path)
                        if flags & os.O_CREAT and ((boundary == "stage-open" and name == stage.rsplit("/", 1)[1]) or
                                                   (boundary == "baseline-open" and name == "baseline.json")):
                            fail()
                        return originals["open"](path, flags, *a, **kw)
                    def written(fd, data):
                        nonlocal partial
                        name = os.readlink("/proc/self/fd/" + str(fd))
                        selected = ((boundary == "stage-write" and name.endswith("/" + stage)) or
                                    (boundary == "baseline-write" and name.endswith("/" + self.api.BASELINE)))
                        if selected:
                            if partial: fail()
                            partial = True
                            return originals["write"](fd, data[:16])
                        return originals["write"](fd, data)
                    def synced(fd):
                        name = os.readlink("/proc/self/fd/" + str(fd))
                        parent = name == str(op.root / self.api.SUPPORT)
                        baseline = (op.root / self.api.BASELINE).exists()
                        staged = (op.root / stage).exists()
                        if ((boundary == "stage-fsync" and name.endswith("/" + stage)) or
                            (boundary == "receipt-fsync" and name.endswith("/" + self.api.PROVISION)) or
                            (boundary == "baseline-fsync" and name.endswith("/" + self.api.BASELINE)) or
                            (boundary == "stage-parent-fsync" and parent and staged) or
                            (boundary == "receipt-parent-fsync" and parent and not staged and not baseline) or
                            (boundary == "baseline-parent-fsync" and parent and baseline)):
                            fail()
                        return originals["fsync"](fd)
                    def renamed(src, dst, *a, **kw):
                        if boundary == "rename" and os.fsdecode(dst) == "provisioning.json": fail()
                        return originals["replace"](src, dst, *a, **kw)
                    original_sync = self.api.FS.sync
                    def replay(fs, *a, **kw):
                        if boundary == "final-sync": fail()
                        return original_sync(fs, *a, **kw)
                    with patch("host_canary.os.open", opened), patch("host_canary.os.write", written), \
                            patch("host_canary.os.fsync", synced), patch("host_canary.os.replace", renamed), \
                            patch.object(self.api.FS, "sync", replay):
                        with self.assertRaises(OSError): op.seal()
                    self.assertTrue(fired)
                    self.assertFalse(op.provider.enrolled)
                    retained = snapshot(op.root)
                    with self.assertRaises(ValueError): op.seal()
                    self.assertEqual(snapshot(op.root), retained)
                    if self.api.status(op.root)["status"] == "not-started":
                        for attempt in range(2):
                            with patch.object(self.api.FS, "sync", side_effect=OSError(fault, "replay still failed")), \
                                    patch.object(self.api.FS, "record", side_effect=AssertionError("transaction before replay")):
                                self.assertEqual(self.api.install_minimal(op.root)["status"], "incomplete")
                            self.assertEqual(snapshot(op.root), retained)
                        self.assertEqual(self.cold(op.root, "install_minimal")["status"], "installed")
                        self.assertEqual(self.cold(op.root, "recover")["status"], self.api.RESTORED)
                    else:
                        self.assert_authority_refused(op.root)

    def test_schema2_receipt_rebinding_between_check_and_baseline_is_not_anchored(self):
        op = self.fresh(stop=self.api.OUTPUT_DIRS[1] + ":attested")
        original = self.api.Provider.checkpoint_matches
        changed = False
        def checked(provider):
            nonlocal changed
            original(provider)
            if provider.p["state"] == "completed" and not changed:
                changed = True
                self.replace_identical(op.root, self.api.PROVISION)
        with patch.object(self.api.Provider, "checkpoint_matches", checked), self.assertRaises(ValueError):
            op.seal()
        self.assertTrue(changed)
        self.assertFalse(op.provider.enrolled)
        self.assert_authority_refused(op.root)
        self.assertEqual(self.cold(op.root, "install_minimal", forbid_mutation=True)["status"],
                         "manual-inspection-required")

    def test_schema2_unknown_output_and_support_stage_refuse_enrollment_and_install(self):
        roles = (self.api.OUTPUT_DIRS[0] + "/foreign", self.api.OUTPUT_DIRS[1] + "/foreign",
                 self.api.SUPPORT + "/.unknown.panda-b3b-stage")
        for window in ("before-seal", "after-sync", "after-enrollment"):
            for role in roles:
                with self.subTest(window=window, role=role):
                    op = self.fresh(stop=None if window == "after-enrollment" else
                                    self.api.OUTPUT_DIRS[1] + ":attested")
                    def mutate(): (op.root / role).write_bytes(b"controlled foreign artifact\n")
                    if window == "after-sync":
                        self.seal_with_late_fault(op, window, mutate)
                    else:
                        mutate()
                        if window == "before-seal":
                            with self.assertRaises(ValueError): op.seal()
                            self.assertFalse(op.provider.enrolled)
                        self.assert_authority_refused(op.root)
                    self.assertTrue((op.root / role).exists())

    def test_schema2_support_authority_capture_preserves_original_creation_pins(self):
        for role in (self.api.PROGRAM, self.api.SOURCE_BEFORE, self.api.DEPLOYED_BEFORE, self.api.LOCK):
            with self.subTest(role=role):
                op = self.unprovisioned()
                original = self.api.FS.read
                changed = False
                def read(fs, path, **kwargs):
                    nonlocal changed
                    if fs.root == str(op.root) and path == role and kwargs.get("authority") and not changed:
                        changed = True
                        self.replace_identical(op.root, role)
                    return original(fs, path, **kwargs)
                with patch.object(self.api.FS, "read", read), self.assertRaises(ValueError):
                    op.provision()
                self.assertTrue(changed)
                self.assertFalse(op.provider.enrolled)
                self.assert_authority_refused(op.root)

    def test_source_short_reads_freeze_complete_recoverable_program(self):
        expected = self.program_bytes()
        original = os.read
        for repeated in (False, True):
            with self.subTest(repeated=repeated):
                op = self.unprovisioned()
                first = True
                def short(fd, count):
                    nonlocal first
                    if os.readlink("/proc/self/fd/" + str(fd)) == self.api.__file__:
                        if repeated or first:
                            first = False
                            return original(fd, min(count, 32))
                    return original(fd, count)
                with patch.object(self.api.os, "read", short):
                    op.provision()
                frozen = op.root / self.api.PROGRAM
                fd = os.open(frozen, os.O_RDONLY | os.O_NOFOLLOW | os.O_NOATIME)
                with os.fdopen(fd, "rb") as f:
                    self.assertEqual(f.read(), expected)
                self.assertEqual(self.api.install_minimal(op.root)["status"], "installed")
                # Recovery needs neither executable PATH nor repository reads/imports.
                script = ("import os,sys,runpy\nrepo=" + repr(str(COMMON.parents[2])) + "\n"
                          "def deny(event,args):\n"
                          " if event=='open' and isinstance(args[0],(str,bytes)) and os.fsdecode(args[0]).startswith(repo+'/'):raise FileNotFoundError('denied checkout')\n"
                          " if event=='import' and args[0].split('.')[0] in ('host_canary','palette','render','adapters'):raise ImportError('denied project')\n"
                          "sys.addaudithook(deny)\n"
                          "sys.argv=['canary.py','recover'," + repr(str(op.root)) + "]\n"
                          "runpy.run_path(" + repr(str(frozen)) + ",run_name='__main__')\n")
                env = {"HOME": str(op.root / "home"), "PATH": "", "PYTHONDONTWRITEBYTECODE": "1"}
                for role in ("config", "data", "state", "cache", "runtime"):
                    env["XDG_" + ("RUNTIME_DIR" if role == "runtime" else role.upper() + "_HOME")] = str(op.root / role)
                env["TMPDIR"] = str(op.root / "runtime")
                result = subprocess.run(["/usr/bin/python3", "-B", "-I", "-S", "-c", script],
                                        cwd=op.root / "home", env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn(self.api.RESTORED, result.stdout)
                self.assertFalse((op.root / self.api.TARGET).exists())

    def test_source_premature_eof_refuses_before_support_publication(self):
        original = os.read
        for prefix in (0, 32):
            with self.subTest(prefix=prefix):
                op = self.unprovisioned()
                first = True
                descriptors = set(os.listdir("/proc/self/fd"))
                def premature(fd, count):
                    nonlocal first
                    if os.readlink("/proc/self/fd/" + str(fd)) == self.api.__file__:
                        if first:
                            first = False
                            return original(fd, min(count, prefix)) if prefix else b""
                        return b""
                    return original(fd, count)
                with patch.object(self.api.os, "read", premature), self.assertRaises(ValueError):
                    op.provision()
                self.assertEqual(set(os.listdir("/proc/self/fd")), descriptors)
                self.assertFalse((op.root / self.api.PROGRAM).exists())
                self.assert_refused_without_changes(op.root)

    def test_source_transient_eintr_retries_but_eio_never_enrolls(self):
        original = os.read
        for fault in (errno.EINTR, errno.EIO):
            for after_short in (False, True):
                with self.subTest(fault=fault, after_short=after_short):
                    op = self.unprovisioned()
                    calls = 0
                    def failed(fd, count):
                        nonlocal calls
                        if os.readlink("/proc/self/fd/" + str(fd)) == self.api.__file__:
                            calls += 1
                            if after_short and calls == 1:
                                return original(fd, min(count, 32))
                            if calls == (2 if after_short else 1):
                                raise OSError(fault, "injected program read fault")
                        return original(fd, count)
                    with patch.object(self.api.os, "read", failed):
                        if fault == errno.EIO:
                            with self.assertRaises(OSError):
                                op.provision()
                        else:
                            op.provision()
                    if fault == errno.EIO:
                        self.assertFalse((op.root / self.api.PROGRAM).exists())
                        self.assert_refused_without_changes(op.root)
                    else:
                        self.assertEqual(self.api.install_minimal(op.root)["status"], "installed")
                        self.assertEqual(self.api.recover(op.root)["status"], self.api.RESTORED)

    def test_source_unstable_identity_size_or_metadata_never_enrolls(self):
        expected = self.program_bytes()
        original_read, original_open = os.read, os.open
        for fault in ("truncate-open", "truncate-read", "metadata", "pathname-open", "pathname", "descriptor", "publication"):
            with self.subTest(fault=fault):
                op = self.unprovisioned()
                source = op.root / "program-source.py"
                source.write_bytes(expected)
                source.chmod(0o644)
                replacement = op.root / "program-replacement.py"
                replacement.write_bytes(expected)
                replacement.chmod(0o644)
                fired = False
                def opened(path, flags, *args, **kwargs):
                    fd = original_open(path, flags, *args, **kwargs)
                    if os.fspath(path) == str(source) and fault == "truncate-open":
                        source.write_bytes(b"")
                    if os.fspath(path) == str(source) and fault == "pathname-open":
                        replacement.replace(source)
                    return fd
                def changed(fd, count):
                    nonlocal fired
                    raw = original_read(fd, min(count, 32))
                    if not fired and os.readlink("/proc/self/fd/" + str(fd)) == str(source):
                        fired = True
                        if fault == "truncate-read":
                            source.write_bytes(b"")
                        elif fault == "metadata":
                            source.chmod(0o600)
                        elif fault == "pathname":
                            replacement.replace(source)
                        elif fault == "descriptor":
                            other = original_open(replacement, os.O_RDONLY | os.O_NOFOLLOW | os.O_NOATIME)
                            try:
                                os.dup2(other, fd)
                            finally:
                                os.close(other)
                    return raw
                checkpoint = self.api._checkpoint
                def publishing(name):
                    if fault == "publication" and name == "before-create:" + self.api.PROGRAM:
                        replacement.replace(source)
                    checkpoint(name)
                with patch.object(self.api, "__file__", str(source)), \
                        patch.object(self.api.os, "open", opened), patch.object(self.api.os, "read", changed), \
                        patch.object(self.api, "_checkpoint", publishing), self.assertRaises(ValueError):
                    op.provision()
                self.assertFalse((op.root / self.api.BASELINE).exists())
                self.assert_refused_without_changes(op.root)

    def test_source_unsafe_type_links_mode_or_size_refuses(self):
        expected = self.program_bytes()
        for fault in ("large", "empty", "truncated", "mode", "hardlink", "symlink", "fifo"):
            with self.subTest(fault=fault):
                op = self.unprovisioned()
                source = op.root / "program-source.py"
                if fault == "fifo":
                    os.mkfifo(source, 0o600)
                elif fault == "symlink":
                    source.symlink_to(self.api.__file__)
                else:
                    source.write_bytes(b"x" * (self.api.LIMIT + 1) if fault == "large" else
                                       b"" if fault == "empty" else expected[:32] if fault == "truncated" else expected)
                    source.chmod(0o666 if fault == "mode" else 0o644)
                    if fault == "hardlink":
                        os.link(source, op.root / "program-hardlink.py")
                with patch.object(self.api, "__file__", str(source)), self.assertRaises((ValueError, OSError, SyntaxError)):
                    op.provision()
                self.assertFalse((op.root / self.api.PROGRAM).exists())
                self.assert_refused_without_changes(op.root)

    def test_source_final_bootstrap_failure_cannot_continue_provisioning(self):
        expected = self.program_bytes()
        for window in ("before-create:", "created:"):
            with self.subTest(window=window):
                op = self.unprovisioned()
                source = op.root / "program-source.py"
                source.write_bytes(expected)
                source.chmod(0o644)
                replacement = op.root / "program-replacement.py"
                replacement.write_bytes(expected)
                replacement.chmod(0o644)
                def change(name):
                    if name == window + self.api.PROVISION:
                        replacement.replace(source)
                with patch.object(self.api, "__file__", str(source)), \
                        patch.object(self.api, "_checkpoint", change), self.assertRaises(ValueError):
                    op.provider.start()
                retained = snapshot(op.root)
                with self.assertRaises(ValueError):
                    op.provider.directory_intent(self.api.OUTPUT_DIRS[0])
                self.assertEqual(snapshot(op.root), retained)
                self.assert_refused_without_changes(op.root)

    def test_source_nanosecond_only_metadata_drift_refuses(self):
        original_read, original_stat = os.read, os.fstat
        for field in ("st_atime_ns", "st_mtime_ns", "st_ctime_ns"):
            with self.subTest(field=field):
                op = self.unprovisioned()
                changed = False
                def read(fd, count):
                    nonlocal changed
                    raw = original_read(fd, count)
                    if os.readlink("/proc/self/fd/" + str(fd)) == self.api.__file__:
                        changed = True
                    return raw
                def metadata(fd):
                    s = original_stat(fd)
                    if changed and os.readlink("/proc/self/fd/" + str(fd)) == self.api.__file__:
                        precise = {k: getattr(s, k) for k in ("st_atime_ns", "st_mtime_ns", "st_ctime_ns")}
                        precise[field] += 1
                        # stat_result tuple equality ignores these precise attributes.
                        return os.stat_result(tuple(s), precise)
                    return s
                with patch.object(self.api.os, "read", read), patch.object(self.api.os, "fstat", metadata), \
                        self.assertRaises(ValueError):
                    op.provision()
                self.assertFalse((op.root / self.api.PROGRAM).exists())
                self.assert_refused_without_changes(op.root)

    def test_source_same_size_subsecond_rewrite_refuses(self):
        op = self.unprovisioned()
        source = op.root / "program-source.py"
        expected = self.program_bytes()
        source.write_bytes(expected)
        source.chmod(0o644)
        initial = source.stat()
        original_read, original_fstat, original_stat = os.read, os.fstat, os.stat
        changed = False
        def precise(s):
            # Deterministically model a rewrite inside the same whole second,
            # retaining real inode, size and nanosecond metadata.
            fields = list(s)
            fields[7:10] = tuple(initial)[7:10]
            return os.stat_result(fields, {k: getattr(s, k) for k in
                                         ("st_atime_ns", "st_mtime_ns", "st_ctime_ns")})
        def fstat(fd):
            s = original_fstat(fd)
            return precise(s) if os.readlink("/proc/self/fd/" + str(fd)) == str(source) else s
        def stat_path(path, *args, **kwargs):
            s = original_stat(path, *args, **kwargs)
            return precise(s) if os.fspath(path) == str(source) else s
        def rewrite(fd, count):
            nonlocal changed
            raw = original_read(fd, min(count, 32))
            if not changed and os.readlink("/proc/self/fd/" + str(fd)) == str(source):
                changed = True
                source.write_bytes(expected.replace(b"B3B1", b"B3B2", 1))
                os.utime(source, ns=(initial.st_atime_ns, initial.st_mtime_ns + 1))
            return raw
        with patch.object(self.api, "__file__", str(source)), patch.object(self.api.os, "read", rewrite), \
                patch.object(self.api.os, "fstat", fstat), patch.object(self.api.os, "stat", stat_path), \
                self.assertRaises(ValueError):
            op.provision()
        self.assertTrue(changed)
        self.assertFalse((op.root / self.api.PROGRAM).exists())
        self.assert_refused_without_changes(op.root)

    def test_directory_substitution_before_later_witness_is_not_adopted(self):
        original = self.api.FS.directory_witnesses
        for equal_mtime in (False, True):
            with self.subTest(equal_mtime=equal_mtime):
                op = self.unprovisioned()
                replaced = False
                def swapped(fs, paths):
                    nonlocal replaced
                    if tuple(paths) == (self.api.OUTPUT_DIRS[1],) and not replaced:
                        replaced = True
                        child = op.root / self.api.OUTPUT_DIRS[1]
                        times = child.stat()
                        child.rename(child.with_name("original-created"))
                        child.mkdir(mode=0o700)
                        if equal_mtime:
                            os.utime(child, ns=(times.st_atime_ns, times.st_mtime_ns))
                    return original(fs, paths)
                with patch.object(self.api.FS, "directory_witnesses", swapped), self.assertRaises(ValueError):
                    op.provision()
                self.assertTrue(replaced)
                self.assertTrue((op.root / "config/panda/original-created").is_dir())
                self.assert_refused_without_changes(op.root)

    def test_creation_witness_missing_or_mismatched_refuses_sealing(self):
        for fault in ("missing", "mismatched"):
            with self.subTest(fault=fault):
                op = self.fresh(stop=self.api.OUTPUT_DIRS[1] + ":attested")
                evidence = getattr(op, "creation", {})
                if fault == "missing":
                    evidence.pop(self.api.OUTPUT_DIRS[1], None)
                elif self.api.OUTPUT_DIRS[1] in evidence:
                    evidence[self.api.OUTPUT_DIRS[1]] = {**evidence[self.api.OUTPUT_DIRS[1]], "ino": 0}
                with self.assertRaises(ValueError):
                    op.seal() if hasattr(op, "seal") else op.provider.seal()
                self.assert_refused_without_changes(op.root)

    def test_directory_replacements_after_descriptor_during_closure_and_after_enrollment_refuse(self):
        for window in ("descriptor", "closure", "enrolled", "parent", "ancestor"):
            with self.subTest(window=window):
                op = self.unprovisioned()
                swapped = False
                def replace(path):
                    child = op.root / path
                    child.rename(child.with_name(child.name + "-original"))
                    child.mkdir(mode=0o700)
                original = os.open
                def opened(path, flags, *args, **kwargs):
                    nonlocal swapped
                    fd = original(path, flags, *args, **kwargs)
                    if window == "descriptor" and path == "generated" and not swapped:
                        swapped = True
                        replace(self.api.OUTPUT_DIRS[1])
                    return fd
                if window == "descriptor":
                    with patch.object(self.api.os, "open", opened), self.assertRaises(ValueError):
                        op.provision()
                    self.assertTrue(swapped)
                else:
                    op.provision(stop=self.api.OUTPUT_DIRS[1] + ":attested" if window != "enrolled" else None)
                    replace("config" if window == "ancestor" else self.api.OUTPUT_DIRS[0] if window == "parent" else self.api.OUTPUT_DIRS[1])
                    if window != "enrolled":
                        with self.assertRaises((ValueError, OSError)):
                            op.seal() if hasattr(op, "seal") else op.provider.seal()
                self.assert_refused_without_changes(op.root)

    def assert_refused_without_changes(self, root=None):
        root = root or self.root
        before = snapshot(root)
        self.assertEqual(self.api.install_minimal(root)["status"],
                         "manual-inspection-required")
        self.assertEqual(snapshot(root), before)

    def test_inspection_is_read_only_and_preview_is_not_execution_authority(self):
        before = snapshot(self.root)
        with patch("host_canary.os.fsync", side_effect=AssertionError("read-only fsync")), \
                patch("host_canary.fcntl.flock", side_effect=AssertionError("read-only lock")), \
                patch("host_canary.os.replace", side_effect=AssertionError("read-only replace")):
            preview = self.api.preview(self.root)
            self.assertEqual(preview["status"], "not-started")
            self.assertIn(self.api.TARGET, preview["absent"])
            self.assertEqual(self.api.status(self.root)["status"], "not-started")
            self.assertEqual(preview["proposed"][self.api.SOURCE],
                             "408e26c4b9e6a89728276051670a37ca2bd8ba11c8ea675ff7631bbfec2977b6")
            self.assertEqual(preview["proposed"][self.api.TARGET],
                             "5241a5b1d58bb15fa5d72e48bd8b9a1b89f12b4cddabb9474fcbc59e376ab03d")
        self.assertEqual(snapshot(self.root), before)
        with self.assertRaises(TypeError):
            self.api.install_minimal(self.root, plan=preview)
        self.assertEqual(snapshot(self.root), before)

    def test_engine_cannot_create_or_remove_directories_or_locks(self):
        with patch("host_canary.os.mkdir", side_effect=AssertionError("engine mkdir")), \
                patch("host_canary.os.rmdir", side_effect=AssertionError("engine rmdir")):
            self.assertEqual(self.api.install_minimal(self.root)["status"], "installed")
            self.assertEqual(self.api.recover(self.root)["status"],
                             "files-restored / manual-directory-cleanup-pending")
        for path in (self.api.SOURCE, self.api.DEPLOYED):
            self.assertEqual((self.root / path).read_bytes(), self.baseline)
        self.assertFalse((self.root / self.api.TARGET).exists())
        self.assertTrue((self.root / self.api.LOCK).exists())
        self.assertTrue((self.root / self.api.OUTPUT_DIRS[1]).is_dir())

    def test_interrupted_provisioning_never_authorizes_installation(self):
        stops = ["support", *[p + ":" + s for p in self.api.OUTPUT_DIRS
                              for s in ("intent", "created", "attested")]]
        for stop in stops:
            with self.subTest(stop=stop):
                operator = self.fresh(stop=stop)
                self.assert_refused_without_changes(operator.root)

    def test_replaced_provisioned_child_refuses_without_cleanup(self):
        path = self.root / self.api.OUTPUT_DIRS[1]
        path.rename(path.with_name("held-generated"))
        path.mkdir(mode=0o700)
        self.assert_refused_without_changes()
        self.assertTrue(path.is_dir())

    def test_foreign_or_unsafe_managed_entries_are_preserved(self):
        for kind in ("symlink", "hardlink", "fifo", "mode", "xattr", "sticky", "setgid"):
            with self.subTest(kind=kind):
                op = self.fresh()
                path = op.root / self.api.SOURCE
                if kind == "symlink":
                    path.rename(path.with_name("original"))
                    path.symlink_to("original")
                elif kind == "hardlink":
                    os.link(path, path.with_name("alias"))
                elif kind == "fifo":
                    path.unlink()
                    os.mkfifo(path)
                elif kind == "mode":
                    path.chmod(0o666)
                elif kind == "xattr":
                    os.setxattr(path, "user.unapproved", b"value")
                elif kind == "sticky":
                    path.chmod(0o1644)
                else:
                    path.chmod(0o2644)
                self.assert_refused_without_changes(op.root)

    def test_arbitrary_and_cross_prefix_roots_are_refused_without_open(self):
        for root in ("/home/panda-fixture-user", str(COMMON.parents[2]), "/tmp/panda-theme-b3b-other",
                     str(self.root) + "/../" + self.root.name, "/tmp/random"):
            with self.subTest(root=root), patch("host_canary.os.open",
                                               side_effect=AssertionError("invalid root opened")):
                self.assertEqual(self.api.install_minimal(root)["status"],
                                 "manual-inspection-required")

    def test_replaced_lock_and_ancestor_refuse_before_any_journal(self):
        for role in (self.api.LOCK, self.api.SUPPORT, "source/home/dot_config"):
            with self.subTest(role=role):
                op = self.fresh()
                path = op.root / role
                path.rename(path.with_name("held-" + path.name))
                if role == self.api.LOCK:
                    path.touch(mode=0o600)
                else:
                    path.mkdir(mode=0o700)
                self.assert_refused_without_changes(op.root)

    def test_foreign_stage_refuses_before_writes(self):
        for path in self.api.STAGES.values():
            with self.subTest(path=path):
                op = self.fresh()
                (op.root / path).write_bytes(b"foreign\n")
                (op.root / path).chmod(0o600)
                self.assert_refused_without_changes(op.root)

    def test_file_restore_and_operator_cleanup_are_distinct(self):
        self.assertEqual(self.api.install_minimal(self.root)["status"], "installed")
        self.assertEqual(self.api.recover(self.root)["status"],
                         "files-restored / manual-directory-cleanup-pending")
        self.operator.cleanup_outputs()
        self.assertEqual(self.api.status(self.root)["status"],
                         "files-restored / manual-directory-cleanup-pending")
        self.assertEqual(self.api.recover(self.root)["status"],
                         "fully-restored after verified cleanup")
        before = snapshot(self.root)
        self.assertEqual(self.api.status(self.root)["status"],
                         "fully-restored after verified cleanup")
        self.assertEqual(snapshot(self.root), before)

    def test_frozen_recovery_without_repository_restores_independent_metadata(self):
        before = {p: (self.root / p).stat() for p in (self.api.SOURCE, self.api.DEPLOYED)}
        self.assertEqual(self.api.install_minimal(self.root)["status"], "installed")
        env = {"HOME": str(self.root / "home"), "PYTHONPATH": "/nonexistent/broken-project",
               "PATH": "/nonexistent", "PYTHONDONTWRITEBYTECODE": "1"}
        result = subprocess.run(["/usr/bin/python3", "-B", "-I", "-S",
                                 str(self.root / self.api.PROGRAM), "recover", str(self.root)],
                                cwd=self.root, env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("files-restored / manual-directory-cleanup-pending", result.stdout)
        for path in before:
            s = (self.root / path).stat()
            for field in ("st_mode", "st_uid", "st_gid", "st_atime_ns", "st_mtime_ns"):
                self.assertEqual(getattr(s, field), getattr(before[path], field))

    def test_no_project_imports_or_native_launch_in_standalone_artifact(self):
        tree = ast.parse((COMMON / "host_canary.py").read_text())
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name.split(".")[0] for a in node.names] if isinstance(node, ast.Import) else [node.module.split(".")[0]]
                self.assertTrue(set(names) <= sys.stdlib_module_names)
        with patch("subprocess.Popen", side_effect=AssertionError("native invocation")):
            self.assertEqual(self.api.install_minimal(self.root)["status"], "installed")
            self.assertIn("files-restored", self.api.recover(self.root)["status"])

    def test_rebound_tmp_parent_is_not_learned_from_the_current_namespace(self):
        original = self.api.tmp_identity
        def rebound(fd):
            value = original(fd)
            value[1] += 1
            return value
        with patch("host_canary.tmp_identity", side_effect=rebound):
            self.assert_refused_without_changes()

    def test_checksum_valid_stage_alias_and_recovery_prefix_are_impossible(self):
        self.assertEqual(self.api.install_minimal(self.root)["status"], "installed")
        with self.api.FS(self.root) as fs:
            e, baseline = self.api.load(fs)
        path = self.root / self.api.JOURNAL
        original = self.api.unpack(path.read_bytes())
        for kind in ("stage-alias", "odd-forward"):
            with self.subTest(kind=kind):
                j = json.loads(json.dumps(original))
                if kind == "stage-alias":
                    j["forward"][0]["stage"] = e["support"][self.api.LOCK]["pin"]
                    with self.assertRaises(ValueError):
                        self.api.model(j, e, baseline)
                else:
                    j["phase"] = "recovering"
                    j["forward"] = j["forward"][:1]
                    with self.assertRaises(ValueError):
                        self.api.model(j, e, baseline)

    def test_late_file_edits_at_final_boundaries_prevent_false_success(self):
        for point in ("after-final-sync", "before-unlock", "before-success-return"):
            with self.subTest(point=point):
                op = self.fresh()
                def edit(name):
                    if name == point:
                        (op.root / self.api.SOURCE).write_bytes(b"foreign late edit\n")
                with patch("host_canary._checkpoint", side_effect=edit):
                    self.assertEqual(self.api.install_minimal(op.root)["status"],
                                     "manual-inspection-required")
                self.assertEqual((op.root / self.api.SOURCE).read_bytes(), b"foreign late edit\n")
                before = snapshot(op.root)
                self.assertEqual(self.api.recover(op.root)["status"], "manual-inspection-required")
                self.assertEqual(snapshot(op.root), before)

    def test_every_parent_and_file_sync_failure_preserves_evidence_and_truthful_status(self):
        roles = ("", *self.api.FIXED_DIRS, *self.api.OUTPUT_DIRS,
                 self.api.PROGRAM, self.api.SOURCE_BEFORE, self.api.DEPLOYED_BEFORE,
                 self.api.PROVISION, self.api.BASELINE, self.api.LOCK,
                 self.api.JOURNAL, self.api.SOURCE, self.api.DEPLOYED, self.api.TARGET)
        original = os.fsync
        for role in roles:
            with self.subTest(role=role):
                op = self.fresh()
                if role != self.api.TARGET:
                    self.assertEqual(self.api.install_minimal(op.root)["status"], "installed")
                def fail(fd):
                    if os.readlink("/proc/self/fd/" + str(fd)) == str(op.root / role):
                        raise OSError(errno.EIO, "injected persistent sync failure")
                    return original(fd)
                with patch("host_canary.os.fsync", side_effect=fail):
                    answer = (self.api.install_minimal(op.root) if role == self.api.TARGET
                              else self.api.recover(op.root))
                    self.assertEqual(answer["status"], "incomplete", answer)
                answer = self.api.recover(op.root)
                self.assertIn(answer["status"], ("manual-inspection-required", self.api.RESTORED), answer)

    def test_enospc_before_journal_rename_preserves_unknown_stage(self):
        original = os.write
        def fail(fd, data):
            if os.readlink("/proc/self/fd/" + str(fd)).endswith(".journal.json.panda-b3b-stage"):
                raise OSError(errno.ENOSPC, "injected full staging volume")
            return original(fd, data)
        with patch("host_canary.os.write", side_effect=fail):
            self.assertEqual(self.api.install_minimal(self.root)["status"], "incomplete")
        before = snapshot(self.root)
        self.assertEqual(self.api.recover(self.root)["status"], "manual-inspection-required")
        self.assertEqual(snapshot(self.root), before)

    def test_read_failure_and_lock_contention_close_all_descriptors(self):
        import fcntl
        count = len(os.listdir("/proc/self/fd"))
        with patch("host_canary.os.read", side_effect=OSError(errno.EIO, "read error")):
            self.assertEqual(self.api.install_minimal(self.root)["status"], "incomplete")
        self.assertEqual(len(os.listdir("/proc/self/fd")), count)
        fd = os.open(self.root / self.api.LOCK, os.O_RDONLY | os.O_NOATIME)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertEqual(self.api.install_minimal(self.root)["status"], "incomplete")
        finally:
            os.close(fd)
        self.assertEqual(len(os.listdir("/proc/self/fd")), count)

    def test_corrupt_or_semantically_impossible_journal_refuses_without_locks(self):
        self.assertEqual(self.api.install_minimal(self.root)["status"], "installed")
        path = self.root / self.api.JOURNAL
        original = self.api.unpack(path.read_bytes())
        edits = (lambda j: j.update(schema=True), lambda j: j.update(phase="restored"),
                 lambda j: j.update(intent=["unlink", self.api.SOURCE]),
                 lambda j: j["forward"][2].update(path=self.api.DEPLOYED),
                 lambda j: j["proposed"][self.api.SOURCE].update(sha256="0" * 64),
                 lambda j: j.update(forward=j["forward"] * 2))
        for edit in edits:
            j = json.loads(json.dumps(original))
            edit(j)
            path.write_bytes(self.api.pack(j))
            before = snapshot(self.root)
            with patch("host_canary.fcntl.flock", side_effect=AssertionError("invalid ledger locked")):
                self.assertEqual(self.api.recover(self.root)["status"], "manual-inspection-required")
            self.assertEqual(snapshot(self.root), before)
        for raw in (b"not json", b'{"payload":{},"payload":{},"sha256":"0"}', b"x" * (self.api.LIMIT + 1)):
            path.write_bytes(raw)
            before = snapshot(self.root)
            self.assertEqual(self.api.recover(self.root)["status"], "manual-inspection-required")
            self.assertEqual(snapshot(self.root), before)

    def test_partial_cleanup_and_foreign_directory_never_claim_closure(self):
        for point in (p + ":" + suffix for p in reversed(self.api.OUTPUT_DIRS)
                      for suffix in ("intent", "removed", "attested")):
            with self.subTest(point=point):
                op = self.fresh()
                self.assertEqual(self.api.install_minimal(op.root)["status"], "installed")
                self.assertEqual(self.api.recover(op.root)["status"], self.api.RESTORED)
                op.cleanup_outputs(stop=point)
                answer = self.api.recover(op.root)
                self.assertEqual(answer["status"], self.api.CLOSED if point.endswith("panda:attested")
                                 else "manual-inspection-required" if point.endswith(":removed")
                                 else self.api.RESTORED, answer)
        self.assertEqual(self.api.install_minimal(self.root)["status"], "installed")
        self.assertEqual(self.api.recover(self.root)["status"], self.api.RESTORED)
        foreign = self.root / self.api.OUTPUT_DIRS[1] / "foreign"
        foreign.write_bytes(b"retain")
        with self.assertRaises(ValueError):
            self.operator.cleanup_outputs()
        self.assertEqual(foreign.read_bytes(), b"retain")

    def test_sigkill_at_publication_and_restore_checkpoints_preserves_or_replays(self):
        for action, point in (("install_minimal", "published:" + self.api.TARGET),
                              ("install_minimal", "done:publish:" + self.api.SOURCE),
                              ("recover", "published:" + self.api.DEPLOYED),
                              ("recover", "unlinked:" + self.api.TARGET)):
            with self.subTest(action=action, point=point):
                op = self.fresh()
                if action == "recover":
                    self.assertEqual(self.api.install_minimal(op.root)["status"], "installed")
                program = op.root / self.api.PROGRAM
                script = ("import importlib.util,os,signal;"
                          "s=importlib.util.spec_from_file_location('frozen'," + repr(str(program)) + ");"
                          "m=importlib.util.module_from_spec(s);s.loader.exec_module(m);"
                          "m._checkpoint=lambda n:os.kill(os.getpid(),signal.SIGKILL) if n==" + repr(point) + " else None;"
                          "getattr(m," + repr(action) + ")(" + repr(str(op.root)) + ")")
                env = {"HOME": str(op.root / "home"), "PYTHONDONTWRITEBYTECODE": "1"}
                completed = subprocess.run(["/usr/bin/python3", "-B", "-I", "-S", "-c", script],
                                           cwd=op.root, env=env, capture_output=True)
                self.assertEqual(completed.returncode, -signal.SIGKILL, completed.stderr)
                answer = self.api.recover(op.root)
                self.assertEqual(answer["status"], self.api.RESTORED, answer)

    def test_stage_and_held_parent_replacement_never_publish_foreign_objects(self):
        for kind in ("stage", "parent", "destination"):
            with self.subTest(kind=kind):
                op = self.fresh()
                def replace(name):
                    if name != "before-publish:" + self.api.SOURCE:
                        return
                    if kind == "parent":
                        parent = (op.root / self.api.SOURCE).parent
                        parent.rename(parent.with_name("held-original"))
                        parent.mkdir(mode=0o700)
                    else:
                        path = op.root / (self.api.STAGES[self.api.SOURCE] if kind == "stage" else self.api.SOURCE)
                        path.write_bytes(b"foreign race\n")
                with patch("host_canary._checkpoint", side_effect=replace):
                    answer = self.api.install_minimal(op.root)
                    self.assertEqual(answer["status"], "manual-inspection-required", answer)
                if kind == "parent":
                    self.assertFalse((op.root / self.api.SOURCE).exists())
                else:
                    path = op.root / (self.api.STAGES[self.api.SOURCE] if kind == "stage" else self.api.SOURCE)
                    self.assertEqual(path.read_bytes(), b"foreign race\n")

    def test_namespace_mount_owner_and_subvolume_drift_are_refused(self):
        from types import SimpleNamespace
        original_fstat = os.fstat
        original_mount = self.api.mount
        original_ns = self.api.namespace
        def owner(fd):
            s = original_fstat(fd)
            if s.st_ino != self.root.stat().st_ino:
                return s
            return SimpleNamespace(**{k: (s.st_uid + 1 if k == "st_uid" else getattr(s, k))
                                      for k in dir(s) if k.startswith("st_")})
        def subvolume(fd):
            s = original_fstat(fd)
            if s.st_ino != self.root.stat().st_ino:
                return s
            return SimpleNamespace(**{k: (256 if k == "st_ino" else getattr(s, k))
                                      for k in dir(s) if k.startswith("st_")})
        for name, value in (("namespace", lambda: {**original_ns(), "mnt": "mnt:[foreign]"}),
                            ("mount", lambda fd: original_mount(fd) + 1),
                            ("os.fstat", owner), ("os.fstat", subvolume)):
            with self.subTest(name=name), patch("host_canary." + name, side_effect=value):
                self.assert_refused_without_changes()

    def test_parent_modes_symlinks_and_acl_xattrs_are_not_accepted(self):
        for kind in ("symlink", "setuid", "setgid", "sticky", "xattr"):
            with self.subTest(kind=kind):
                op = self.fresh()
                path = op.root / "config/ghostty"
                if kind == "symlink":
                    path.rename(path.with_name("held-original"))
                    path.symlink_to("held-original", target_is_directory=True)
                elif kind == "xattr":
                    os.setxattr(path, "user.unapproved", b"preserve")
                else:
                    path.chmod({"setuid": 0o4700, "setgid": 0o2700, "sticky": 0o1700}[kind])
                self.assert_refused_without_changes(op.root)

    def test_explicit_acl_entries_are_refused(self):
        import struct
        path = self.root / self.api.SOURCE
        acl = struct.pack("<I", 2) + b"".join(struct.pack("<HHI", *entry) for entry in (
            (1, 6, 0xffffffff), (2, 4, os.getuid()), (4, 4, 0xffffffff),
            (16, 4, 0xffffffff), (32, 4, 0xffffffff)))
        try:
            os.setxattr(path, "system.posix_acl_access", acl)
        except OSError as error:
            if error.errno in (errno.EOPNOTSUPP, errno.ENOTSUP):
                self.skipTest("fixture filesystem does not support POSIX ACL xattrs")
            raise
        self.assert_refused_without_changes()

    def test_all_operation_intents_and_completions_survive_controlled_interruption(self):
        for action, ops in (("install_minimal", self.api.FORWARD), ("recover", self.api.REVERSE)):
            for kind, path in ops:
                for boundary in ("intent", "done"):
                    with self.subTest(action=action, operation=(kind, path), boundary=boundary):
                        op = self.fresh()
                        if action == "recover":
                            self.assertEqual(self.api.install_minimal(op.root)["status"], "installed")
                        point = boundary + ":" + kind + ":" + path
                        def interrupt(name):
                            if name == point:
                                raise OSError(errno.EIO, "controlled checkpoint interruption")
                        with patch("host_canary._checkpoint", side_effect=interrupt):
                            self.assertEqual(getattr(self.api, action)(op.root)["status"], "incomplete")
                        before = snapshot(op.root)
                        answer = self.api.recover(op.root)
                        if action == "install_minimal" and ((kind == "stage" and boundary == "done") or
                                                            (kind == "publish" and boundary == "intent")):
                            self.assertEqual(answer["status"], "manual-inspection-required", answer)
                            # An intent can be durably retired; the attested unpublished
                            # managed stage remains, and no destination is changed.
                            for p in self.api.MANAGED:
                                self.assertEqual(snapshot(op.root).get(p), before.get(p))
                        else:
                            self.assertEqual(answer["status"], self.api.RESTORED, answer)

    def test_provisioning_support_write_interruptions_do_not_enroll(self):
        for role in (self.api.PROGRAM, self.api.SOURCE_BEFORE, self.api.DEPLOYED_BEFORE,
                     self.api.LOCK, self.api.PROVISION):
            with self.subTest(role=role):
                op = Operator(self.api, self.baseline, self.addCleanup)
                def interrupt(name):
                    if name == "created:" + role:
                        raise OSError(errno.EIO, "support interrupted")
                with patch("host_canary._checkpoint", side_effect=interrupt), self.assertRaises(OSError):
                    op.provision()
                self.assert_refused_without_changes(op.root)

    def test_constructor_failure_has_creation_identity_and_teardown_registered(self):
        registered = []
        with patch("host_canary.Provider", side_effect=ValueError("provider constructor failed")):
            with self.assertRaises(ValueError):
                Operator(self.api, self.baseline, registered.append)
        self.assertEqual(len(registered), 1)
        operator = registered[0].__self__
        self.assertEqual(operator.root.stat().st_ino, operator.initial[1])
        registered[0]()
        self.assertFalse(operator.root.exists())

    def test_recovery_runs_when_repository_reads_and_project_imports_are_unavailable(self):
        self.assertEqual(self.api.install_minimal(self.root)["status"], "installed")
        replica = self.root / "repository"
        replica.mkdir(mode=0o700)
        (replica / "palette.py").write_text("raise RuntimeError('broken repository import')\n")
        replica.rename(self.root / "repository-unavailable")
        script = ("import os,sys,runpy\n"
                  "repo=" + repr(str(COMMON.parents[2])) + "\n"
                  "def unavailable(event,args):\n"
                  " if event=='open' and isinstance(args[0],(str,bytes)) and os.fsdecode(args[0]).startswith(repo+'/'):raise FileNotFoundError('repository unavailable')\n"
                  " if event=='import' and args[0].split('.')[0] in ('palette','render','canary_fs','adapters'):raise ImportError('broken project import')\n"
                  "sys.addaudithook(unavailable)\n"
                  "try:open(repo+'/theme/panda/common/palette.py')\n"
                  "except FileNotFoundError:pass\n"
                  "else:raise AssertionError('repository denial did not run')\n"
                  "sys.argv=['canary.py','recover'," + repr(str(self.root)) + "]\n"
                  "runpy.run_path(" + repr(str(self.root / self.api.PROGRAM)) + ",run_name='__main__')\n")
        env = {"HOME": str(self.root / "home"), "XDG_CONFIG_HOME": str(self.root / "config"),
               "XDG_DATA_HOME": str(self.root / "data"), "XDG_STATE_HOME": str(self.root / "state"),
               "XDG_CACHE_HOME": str(self.root / "cache"), "XDG_RUNTIME_DIR": str(self.root / "runtime"),
               "TMPDIR": str(self.root / "runtime"), "PYTHONDONTWRITEBYTECODE": "1"}
        completed = subprocess.run(["/usr/bin/python3", "-B", "-I", "-S", "-c", script],
                                   cwd=self.root, env=env, capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn(self.api.RESTORED, completed.stdout)
        self.assertFalse((self.root / self.api.TARGET).exists())

    def test_nested_record_and_changed_before_image_refuse_without_mutation(self):
        path = self.root / self.api.SOURCE_BEFORE
        path.write_bytes(b"altered independent backup")
        self.assert_refused_without_changes()
        op = self.fresh()
        journal = op.root / self.api.JOURNAL
        journal.write_bytes(b'{"payload":{"nested":' + b"[" * 1500 + b"0" +
                            b"]" * 1500 + b'},"sha256":"0"}')
        journal.chmod(0o600)
        before = snapshot(op.root)
        answer = self.api.recover(op.root)
        self.assertEqual(answer["status"], "manual-inspection-required")
        self.assertEqual(snapshot(op.root), before)

    def test_failed_provisioning_checkpoint_cannot_be_sealed_in_memory(self):
        op = self.fresh(stop=self.api.OUTPUT_DIRS[1] + ":created")
        with self.api.FS(op.root) as fs:
            witness = fs.directory_witnesses((self.api.OUTPUT_DIRS[1],))[self.api.OUTPUT_DIRS[1]]
        with patch.object(self.api.FS, "record", side_effect=OSError(errno.EIO, "checkpoint failed")):
            with self.assertRaises(OSError):
                op.provider.attest_directory(self.api.OUTPUT_DIRS[1], witness)
        before = snapshot(op.root)
        with self.assertRaises(ValueError):
            op.provider.seal()
        self.assertEqual(snapshot(op.root), before)

    def test_parser_recursion_limit_is_a_write_free_refusal(self):
        before = snapshot(self.root)
        with patch("host_canary.json.loads", side_effect=RecursionError("parser nesting limit")):
            self.assertEqual(self.api.recover(self.root)["status"], "manual-inspection-required")
        self.assertEqual(snapshot(self.root), before)

    def test_failed_cleanup_intent_cannot_authorize_removal_attestation(self):
        self.assertEqual(self.api.install_minimal(self.root)["status"], "installed")
        self.assertEqual(self.api.recover(self.root)["status"], self.api.RESTORED)
        receipt = self.api.CleanupProvider(self.root)
        receipt.start()
        path = self.api.OUTPUT_DIRS[1]
        with patch.object(self.api.FS, "record", side_effect=OSError(errno.EIO, "intent failed")):
            with self.assertRaises(OSError):
                receipt.directory_intent(path)
        # Separately modeled operator action: even continued misuse cannot certify it.
        (self.root / path).rmdir()
        before = snapshot(self.root)
        with self.assertRaises(ValueError):
            receipt.attest_absence(path)
        self.assertEqual(snapshot(self.root), before)

    def test_operator_refuses_ambient_runtime_before_fixture_creation(self):
        with patch.dict(os.environ, {"XDG_RUNTIME_DIR": "/run/user/1000"}), \
                patch("host_canary_operator.tempfile.mkdtemp",
                      side_effect=AssertionError("unsafe runner created fixture")):
            with self.assertRaises(ValueError):
                Operator(self.api, self.baseline, self.addCleanup)

    def test_failed_enrollment_seal_does_not_authorize_new_mutations(self):
        for boundary in ("sync", "baseline-published"):
            with self.subTest(boundary=boundary):
                op = self.fresh(stop=self.api.OUTPUT_DIRS[1] + ":attested")
                def interrupt(name):
                    if name == "created:" + self.api.BASELINE:
                        raise OSError(errno.EIO, "baseline publication durability interrupted")
                with patch.object(self.api.FS, "sync", side_effect=OSError(errno.EIO, "seal sync failed")) \
                        if boundary == "sync" else patch("host_canary._checkpoint", side_effect=interrupt):
                    with self.assertRaises(OSError):
                        op.provider.seal()
                self.assertFalse(op.provider.enrolled)
                before = snapshot(op.root)
                with patch.object(self.api.FS, "sync", side_effect=OSError(errno.EIO, "replay failed")):
                    self.assertEqual(self.api.install_minimal(op.root)["status"], "incomplete")
                self.assertEqual(snapshot(op.root), before)
                self.assertEqual(self.api.install_minimal(op.root)["status"], "installed")

    def test_private_record_modes_are_enforced_on_first_load(self):
        for role in (self.api.BASELINE, self.api.JOURNAL, self.api.CLEANUP):
            with self.subTest(role=role):
                op = self.fresh()
                if role != self.api.BASELINE:
                    self.assertEqual(self.api.install_minimal(op.root)["status"], "installed")
                    self.assertEqual(self.api.recover(op.root)["status"], self.api.RESTORED)
                if role == self.api.CLEANUP:
                    receipt = self.api.CleanupProvider(op.root)
                    receipt.start()
                (op.root / role).chmod(0o644)
                before = snapshot(op.root)
                self.assertEqual(self.api.recover(op.root)["status"], "manual-inspection-required")
                self.assertEqual(snapshot(op.root), before)

    def test_cleanup_attestation_rechecks_foreign_edits_before_receipt_write(self):
        self.assertEqual(self.api.install_minimal(self.root)["status"], "installed")
        self.assertEqual(self.api.recover(self.root)["status"], self.api.RESTORED)
        receipt = self.api.CleanupProvider(self.root)
        receipt.start()
        path = self.api.OUTPUT_DIRS[1]
        receipt.directory_intent(path)
        (self.root / path).rmdir()  # separately modeled operator action
        (self.root / self.api.SOURCE).write_bytes(b"foreign edit after cleanup intent\n")
        before = snapshot(self.root)
        with self.assertRaises(ValueError):
            receipt.attest_absence(path)
        self.assertEqual(snapshot(self.root), before)

    def test_seal_completion_sync_failure_is_retried_before_transaction_writes(self):
        op = self.fresh(stop=self.api.OUTPUT_DIRS[1] + ":attested")
        original = self.api.FS.publish
        def interrupted(fs, path, staged, expected):
            original(fs, path, staged, expected)
            if path == self.api.PROVISION:
                raise OSError(errno.EIO, "seal completion publication sync failed")
        with patch.object(self.api.FS, "publish", interrupted), self.assertRaises(OSError):
            op.provider.seal()
        self.assertFalse((op.root / self.api.BASELINE).exists())
        self.assert_authority_refused(op.root)

    def test_interpreter_read_atime_on_frozen_program_does_not_disable_recovery(self):
        self.assertEqual(self.api.install_minimal(self.root)["status"], "installed")
        program = self.root / self.api.PROGRAM
        # Simulate only the OS observation of a legitimate read-atime update on
        # noatime runners. Real reads/bytes/bindings/ctime validation still run;
        # utime would instead be a ctime-changing metadata edit and must refuse.
        before = program.stat()
        original_stat, original_fstat = os.stat, os.fstat
        class ReadAtime:
            def __init__(self, actual): self.actual = actual
            def __getattr__(self, name):
                if name == "st_atime_ns": return self.actual.st_atime_ns + 1
                return getattr(self.actual, name)
            def __eq__(self, other):
                return self.actual == (other.actual if isinstance(other, ReadAtime) else other)
        def fstat(fd):
            actual = original_fstat(fd)
            return ReadAtime(actual) if os.readlink("/proc/self/fd/" + str(fd)) == str(program) else actual
        def observed_stat(path, *a, **kw):
            actual = original_stat(path, *a, **kw)
            name = os.fspath(path)
            if not os.path.isabs(name) and kw.get("dir_fd") is not None:
                name = os.readlink("/proc/self/fd/" + str(kw["dir_fd"])) + "/" + name
            return ReadAtime(actual) if name == str(program) else actual
        with patch("host_canary.os.stat", observed_stat), patch("host_canary.os.fstat", fstat):
            with self.api.FS(self.root) as fs:
                observed = fs.read(self.api.PROGRAM, authority=True)
                self.assertEqual(observed["image"]["atime"], before.st_atime_ns + 1)
                self.assertEqual(observed["ctime_ns"], before.st_ctime_ns)
            self.assertEqual(self.api.recover(self.root)["status"], self.api.RESTORED)
        self.assertEqual(program.stat().st_ctime_ns, before.st_ctime_ns)
        program.chmod(0o644)
        before = snapshot(self.root)
        self.assertEqual(self.api.recover(self.root)["status"], "manual-inspection-required")
        self.assertEqual(snapshot(self.root), before)

    def seal_with_late_fault(self, op, window, mutate, *, install_refusal=True):
        """Keep real durability/publication; inject only at the selected boundary."""
        original_sync, original_checkpoint = self.api.FS.sync, self.api._checkpoint
        fired = False
        managed = None
        def inject():
            nonlocal fired, managed
            if not fired:
                fired = True
                mutate()
                current = snapshot(op.root)
                managed = {p: current.get(p) for p in self.api.MANAGED}
        def synced(fs, *args, **kwargs):
            original_sync(fs, *args, **kwargs)
            if window == "after-sync":
                inject()
        def checkpoint(name):
            original_checkpoint(name)
            if window == "after-publication" and name == "provision:sealed":
                inject()
        error = None
        returned = "not-returned"
        with patch.object(self.api.FS, "sync", synced), \
                patch.object(self.api, "_checkpoint", checkpoint):
            try:
                returned = op.seal()
            except (ValueError, OSError, TypeError, KeyError) as caught:
                error = caught
        self.assertTrue(fired)
        self.assertFalse(op.provider.enrolled, (window, returned, error))
        self.assertIsNotNone(error, "seal returned readiness instead of refusing")
        current = snapshot(op.root)
        self.assertEqual({p: current.get(p) for p in self.api.MANAGED}, managed)
        self.assertTrue((op.root / self.api.BASELINE).exists())
        self.assertTrue((op.root / self.api.PROVISION).exists())
        if install_refusal:
            self.assert_refused_without_changes(op.root)
        else:
            # A local-only memory fault does not invalidate an otherwise valid
            # durable receipt. Independent observation stays read-only; a fresh
            # installer still has to replay durability before transaction writes.
            retained = snapshot(op.root)
            self.assertEqual(self.api.status(op.root)["status"], "not-started")
            self.assertEqual(snapshot(op.root), retained)
        return error

    def test_seal_late_artifact_edits_refuse_readiness(self):
        # Removing the final capability verification must make these cases fail.
        roles = (self.api.PROGRAM, self.api.SOURCE_BEFORE, self.api.DEPLOYED_BEFORE,
                 self.api.LOCK, self.api.SOURCE, self.api.DEPLOYED)
        for window in ("after-sync", "after-publication"):
            for role in roles:
                with self.subTest(window=window, role=role):
                    op = self.fresh(stop=self.api.OUTPUT_DIRS[1] + ":attested")
                    self.seal_with_late_fault(op, window,
                                              lambda: (op.root / role).write_bytes(b"broken\n"))

    def test_seal_equal_image_rebindings_refuse_readiness(self):
        roles = (self.api.PROGRAM, self.api.SOURCE_BEFORE, self.api.DEPLOYED_BEFORE,
                 self.api.LOCK, self.api.BASELINE, self.api.PROVISION)
        for window in ("after-sync", "after-publication"):
            for role in roles:
                with self.subTest(window=window, role=role):
                    op = self.fresh(stop=self.api.OUTPUT_DIRS[1] + ":attested")
                    def replace():
                        path = op.root / role
                        original = snapshot(op.root)[role]
                        held = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NOATIME)
                        self.addCleanup(os.close, held)
                        replacement = op.root / "controlled-replacement"
                        fd = os.open(replacement, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                                     os.O_NOFOLLOW, stat.S_IMODE(original[2]))
                        try:
                            birth = os.fstat(fd)
                            self.assertNotEqual(birth.st_ino, original[1])
                            raw, position = original[-1], 0
                            while position < len(raw):
                                written = os.write(fd, raw[position:])
                                self.assertGreater(written, 0)
                                position += written
                            os.utime(fd, ns=(original[5], original[6]))
                            os.fsync(fd)
                        finally:
                            os.close(fd)
                        replacement.replace(path)
                        self.assertEqual(path.lstat().st_ino, birth.st_ino)
                    self.seal_with_late_fault(op, window, replace,
                                              install_refusal=role != self.api.BASELINE)

    def test_seal_receipt_timestamp_drift_refuses_readiness_and_install(self):
        for window in ("after-sync", "after-publication"):
            for field in ("atime", "mtime"):
                with self.subTest(window=window, field=field):
                    op = self.fresh(stop=self.api.OUTPUT_DIRS[1] + ":attested")
                    def change():
                        os.utime(op.root / self.api.PROVISION,
                                 ns=(1, 0) if field == "atime" else (0, 1))
                    self.seal_with_late_fault(op, window, change)

    def test_seal_late_records_and_absences_refuse_readiness(self):
        roles = (self.api.BASELINE, self.api.PROVISION, self.api.JOURNAL,
                 self.api.CLEANUP, self.api.TARGET, *self.api.STAGES.values())
        for window in ("after-sync", "after-publication"):
            for role in roles:
                with self.subTest(window=window, role=role):
                    op = self.fresh(stop=self.api.OUTPUT_DIRS[1] + ":attested")
                    def change():
                        path = op.root / role
                        path.write_bytes(b"foreign record or output\n")
                        path.chmod(0o600)
                    self.seal_with_late_fault(op, window, change)

    def test_seal_late_directory_and_namespace_drift_refuse_readiness(self):
        for window in ("after-sync", "after-publication"):
            for role in ("config", self.api.OUTPUT_DIRS[1], "namespace", "mount"):
                with self.subTest(window=window, role=role):
                    op = self.fresh(stop=self.api.OUTPUT_DIRS[1] + ":attested")
                    from contextlib import ExitStack
                    with ExitStack() as faults:
                        def change():
                            if role == "namespace":
                                original = self.api.namespace
                                faults.enter_context(patch.object(self.api, "namespace",
                                    lambda: {**original(), "mnt": "mnt:[changed-after-seal]"}))
                            elif role == "mount":
                                original = self.api.mount
                                faults.enter_context(patch.object(self.api, "mount",
                                                                  lambda fd: original(fd) + 1))
                            else:
                                path = op.root / role
                                path.rename(path.with_name(path.name + "-original"))
                                path.mkdir(mode=0o700)
                        self.seal_with_late_fault(op, window, change)
                    if role not in ("namespace", "mount"):
                        self.assert_refused_without_changes(op.root)

    def test_seal_late_memory_checkpoint_drift_refuses_readiness(self):
        for window in ("after-sync", "after-publication"):
            for fault in ("history", "pending", "directory-pin"):
                with self.subTest(window=window, fault=fault):
                    op = self.fresh(stop=self.api.OUTPUT_DIRS[1] + ":attested")
                    def change():
                        if fault == "history":
                            op.provider.p["done"] = []
                        elif fault == "pending":
                            op.provider.p["pending"] = self.api.OUTPUT_DIRS[1]
                        else:
                            path = self.api.OUTPUT_DIRS[1]
                            op.provider.p["dirs"][path] = {**op.provider.p["dirs"][path], "ino": 0}
                    self.seal_with_late_fault(op, window, change,
                                              install_refusal=False)

    def test_seal_final_verification_is_read_only_and_healthy_cycle_works(self):
        from contextlib import ExitStack
        op = self.fresh(stop=self.api.OUTPUT_DIRS[1] + ":attested")
        reached = False
        with ExitStack() as forbidden:
            def published(name):
                nonlocal reached
                if name == "provision:sealed":
                    reached = True
                    for method in ("create", "record", "publish", "sync"):
                        forbidden.enter_context(patch.object(self.api.FS, method,
                            side_effect=AssertionError("read-only seal verification wrote")))
                    forbidden.enter_context(patch.object(self.api.os, "fsync",
                        side_effect=AssertionError("read-only seal verification synced")))
            with patch.object(self.api, "_checkpoint", published):
                self.assertIsNone(op.seal())
            self.assertTrue(reached)
            self.assertTrue(op.provider.enrolled)
        sealed = snapshot(op.root)
        with self.assertRaises(ValueError):
            op.seal()
        self.assertEqual(snapshot(op.root), sealed)
        self.assertEqual(self.api.install_minimal(op.root)["status"], "installed")
        self.assertEqual(self.api.recover(op.root)["status"], self.api.RESTORED)
        op.cleanup_outputs()
        self.assertEqual(self.api.recover(op.root)["status"], self.api.CLOSED)

    def test_seal_interrupted_publication_never_sets_ready_or_reseals(self):
        for point in ("created:" + self.api.BASELINE, "published:" + self.api.PROVISION,
                      "provision:sealed"):
            with self.subTest(point=point):
                op = self.fresh(stop=self.api.OUTPUT_DIRS[1] + ":attested")
                def interrupt(name):
                    if name == point:
                        raise OSError(errno.EIO, "interrupted seal publication")
                with patch.object(self.api, "_checkpoint", interrupt), self.assertRaises(OSError):
                    op.seal()
                self.assertFalse(op.provider.enrolled)
                retained = snapshot(op.root)
                with self.assertRaises(ValueError):
                    op.seal()
                self.assertEqual(snapshot(op.root), retained)
                # Visible valid completion may replay durability through installation;
                # a baseline lacking completion authority must remain refused.
                answer = self.api.install_minimal(op.root)
                self.assertEqual(answer["status"], "manual-inspection-required"
                                 if point == "published:" + self.api.PROVISION else "installed", answer)

    def test_seal_final_observation_to_return_interval_remains_nonatomic(self):
        op = self.fresh(stop=self.api.OUTPUT_DIRS[1] + ":attested")
        original = self.api.verify
        changed = False
        def after_observation(fs, *args, **kwargs):
            nonlocal changed
            answer = original(fs, *args, **kwargs)
            changed = True
            (op.root / self.api.PROGRAM).write_bytes(b"edit after final observation\n")
            return answer
        with patch.object(self.api, "verify", after_observation):
            op.seal()
        self.assertTrue(changed, "seal did not perform the complete verifier")
        self.assertTrue(op.provider.enrolled)
        # This deliberately outside-contract writer acts after the last observation.
        # Subsequent installation still refuses without mutation; no atomic claim.
        self.assert_refused_without_changes(op.root)
