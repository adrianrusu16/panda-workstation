"""Single-use B3-B0 private canary API. No CLI dispatch or live deployment ability."""

from collections import deque
from dataclasses import dataclass
from functools import lru_cache
import os
from pathlib import Path
import tempfile
import time

from adapters.live_ghostty import GhosttyModel, HOOK_LINE, model_hook
from palette import load_family
from canary_fs import (CanaryFS, SOURCE, DEPLOYED, TARGET, MANAGED, SUPPORT, JOURNAL, LOCK,
                       MARKER, FIXED_DIRS, OUTPUT_DIRS, STAGES, SCOPE, directory_identity,
                       image_data, image_from, pack, unpack, digest, validate_identity, write_all)

BASELINE_SHA = "87d967432b7086b7c746929ce712a2dc5b2fc40899c2faf4456d16e6d234c359"
MINIMAL_SHA = "5241a5b1d58bb15fa5d72e48bd8b9a1b89f12b4cddabb9474fcbc59e376ab03d"
HOOKED_SHA = "408e26c4b9e6a89728276051670a37ca2bd8ba11c8ea675ff7631bbfec2977b6"
WARNING = "B3-B0 simulation / fixture-only; live deployment and GUI activation disabled"


@dataclass(frozen=True)
class Result:
    success: bool
    status: str
    message: str = WARNING


def _result(success, status):
    return Result(success, status)


def _minimal():
    content = GhosttyModel().prepare(load_family(Path(__file__).parent.parent)["minimal"])
    if len(content) != 516 or digest(content) != MINIMAL_SHA:
        raise ValueError("B3A Minimal evidence no longer matches renderer")
    return content


def _entries(data):
    if not isinstance(data, list) or len(data) != 3:
        raise ValueError("exact three-file journal required")
    entries = []
    for path, value in zip(MANAGED, data):
        if not isinstance(value, dict) or set(value) != {"path", "before", "after"} or value["path"] != path:
            raise ValueError("untrusted or reordered recovery paths")
        before, after = image_from(value["before"]), image_from(value["after"])
        if after is None:
            raise ValueError("missing after image")
        if path == TARGET:
            if before is not None or after["mode"] != 0o600 or after["content"] != _minimal():
                raise ValueError("foreign generated output")
        elif (before is None or before["mode"] != 0o644 or after["mode"] != 0o644 or
              len(before["content"]) != 1376 or digest(before["content"]) != BASELINE_SHA or
              after["content"] != model_hook(before["content"]) or digest(after["content"]) != HOOKED_SHA or
              any(before[k] != after[k] for k in ("uid", "gid", "atime_ns", "mtime_ns"))):
            raise ValueError("recovery hook or baseline differs from approved canary")
        entries.append((path, before, after))
    if entries[1][1]["content"] != entries[2][1]["content"]:
        raise ValueError("source/deployed baseline mismatch")
    return entries


def create_fixture(baseline):
    """Create a NEW direct /tmp fixture; accepts bytes, never a HOME/path override.

    Fixture construction precedes the canary transaction. Interrupted construction
    is not an enrolled canary and requires disposal/inspection by its creator.
    """
    if not isinstance(baseline, bytes) or len(baseline) != 1376 or digest(baseline) != BASELINE_SHA:
        raise ValueError("fixture requires approved B3A baseline bytes")
    fragment = _minimal()
    root = Path(tempfile.mkdtemp(prefix="panda-theme-b3b-", dir="/tmp"))
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NOATIME)
    def parent(relative):
        current = os.dup(fd)
        try:
            for part in relative.split("/") if relative else ():
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NOATIME,
                                dir_fd=current)
                os.close(current)
                current = child
                directory_identity(current)
            return current
        except BaseException:
            os.close(current)
            raise
    try:
        identity = directory_identity(fd)
        for directory in FIXED_DIRS:
            parent_path, _, name = directory.rpartition("/")
            pfd = parent(parent_path)
            try:
                os.mkdir(name, 0o700, dir_fd=pfd)
                os.fsync(pfd)
            finally:
                os.close(pfd)
        images = {}
        lock_identity = None
        for path, content, mode in ((SOURCE, baseline, 0o644), (DEPLOYED, baseline, 0o644), (LOCK, b"", 0o600)):
            parent_path, name = path.rsplit("/", 1)
            pfd = parent(parent_path)
            try:
                file_fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode, dir_fd=pfd)
                try:
                    write_all(file_fd, content)
                    os.fchmod(file_fd, mode)
                    os.fsync(file_fd)
                    info = os.fstat(file_fd)
                    if path == LOCK:
                        lock_identity = dict(device=info.st_dev, inode=info.st_ino, ctime_ns=info.st_ctime_ns)
                    images[path] = dict(content=content, mode=mode, uid=info.st_uid, gid=info.st_gid,
                                        mtime_ns=info.st_mtime_ns, atime_ns=info.st_atime_ns)
                finally:
                    os.close(file_fd)
                os.fsync(pfd)
            finally:
                os.close(pfd)
        now = time.time_ns()
        target = dict(content=fragment, mode=0o600, uid=os.getuid(), gid=os.getgid(),
                      mtime_ns=now, atime_ns=now)
        entries = [{"path": TARGET, "before": None, "after": image_data(target)}]
        for path in (SOURCE, DEPLOYED):
            before = images[path]
            after = {**before, "content": model_hook(before["content"])}
            entries.append(dict(path=path, before=image_data(before), after=image_data(after)))
        pins = {}
        for directory in FIXED_DIRS:
            pfd = parent(directory)
            try:
                pins[directory] = directory_identity(pfd)
                os.fsync(pfd)
            finally:
                os.close(pfd)
        manifest = dict(schema=1, scope=SCOPE, root=identity, parents=pins, entries=entries, lock_identity=lock_identity,
                        bootstrap_intent="initialize-private-journal")
        marker_fd = os.open(MARKER, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        try:
            write_all(marker_fd, pack(manifest))
            os.fsync(marker_fd)
        finally:
            os.close(marker_fd)
        os.fsync(fd)
    except BaseException:
        # Preserve the exact incomplete construction for its creator; never glob
        # cleanup, follow substituted paths or pretend enrollment succeeded.
        raise RuntimeError(f"fixture-only construction incomplete; inspect {root}") from None
    finally:
        os.close(fd)
    return root


def _baseline(fs):
    fs.guard()
    entries = _entries(fs.manifest["entries"])
    fs.stages_absent()
    if fs.read(JOURNAL) is not None:
        raise ValueError("canary is single-use; inspect/recover retained record")
    for path in OUTPUT_DIRS:
        if fs.directory_stamp(path) is not None:
            raise ValueError("unexpected preexisting output ancestor")
    for path, before, _ in entries:
        if fs.read(path) != before:
            raise ValueError("fixture baseline changed")
    lock = fs.read(LOCK)
    if lock is None or lock["content"]:
        raise ValueError("fixture lock missing or foreign")
    return entries


def dry_run(root):
    """Read-only fixture planning. The result is never an execution capability."""
    try:
        with CanaryFS(root) as fs:
            _baseline(fs)
        return _result(True, "preview: Minimal -> source hook -> deployed hook")
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        return _result(False, "refused: fixture baseline/ancestors require inspection")


def _load(fs):
    image = fs.read(JOURNAL)
    if image is None:
        return None
    data = unpack(image["content"])
    if (not isinstance(data, dict) or set(data) != {
            "schema", "scope", "manifest_sha256", "phase", "entries", "directories", "intent", "sequence", "completed"} or
            type(data["schema"]) is not int or data["schema"] != 1 or data["scope"] != SCOPE or
            data["manifest_sha256"] != digest(fs.marker["content"]) or
            data["phase"] not in ("prepared", "applying", "applied", "recovering", "restored", "incomplete") or
            data["entries"] != fs.manifest["entries"] or
            any(type(data[k]) is not int or not 0 <= data[k] <= 128 for k in ("sequence", "completed")) or
            data["completed"] > data["sequence"]):
        raise ValueError("untrusted, legacy or inconsistent journal")
    _entries(data["entries"])
    records = data["directories"]
    if not isinstance(records, list) or len(records) != 2:
        raise ValueError("exact output provenance required")
    for path, record in zip(OUTPUT_DIRS, records):
        if (not isinstance(record, dict) or set(record) != {"path", "state", "identity"} or record["path"] != path or
                record["state"] not in ("pending", "created", "removed")):
            raise ValueError("invalid directory provenance")
        if record["state"] == "created":
            validate_identity(record["identity"], stamp=True)
            if record["identity"]["mount"] != fs.identity["mount"]:
                raise ValueError("directory mount provenance changed")
        elif record["identity"] is not None:
            raise ValueError("unproven directory has identity")
    intent = data["intent"]
    if intent is not None:
        if (not isinstance(intent, dict) or set(intent) != {"kind", "path"} or
                intent["kind"] not in ("mkdir", "stage", "replace", "unlink", "rmdir") or
                intent["path"] not in (OUTPUT_DIRS if intent["kind"] in ("mkdir", "rmdir") else MANAGED) or
                data["completed"] >= data["sequence"]):
            raise ValueError("invalid mutation intent")
    elif data["completed"] != data["sequence"]:
        raise ValueError("missing outstanding mutation intent")
    if data["phase"] in ("applied", "restored") and intent is not None:
        raise ValueError("completed-looking journal has outstanding intent")
    if data["phase"] == "applied" and (data["sequence"] != 8 or data["completed"] != 8 or
                                       any(r["state"] != "created" for r in records)):
        raise ValueError("applied journal lacks its eight durable operation checkpoints")
    if data["phase"] == "prepared" and (data["sequence"] != 0 or intent is not None or
                                        any(r["state"] != "pending" for r in records)):
        raise ValueError("prepared journal contradicts mutation checkpoints")
    _check_prefix(fs, data)
    return data


def _ledger_effect(state, operation, *, forward=False, checkpoint=False):
    directories, images, stages = map(list, state)
    kind, path = operation
    if kind in ("mkdir", "rmdir"):
        if checkpoint:
            directories[OUTPUT_DIRS.index(path)] = "created" if kind == "mkdir" else "removed"
    else:
        index = MANAGED.index(path)
        if kind == "stage":
            stages[index] = "after" if forward else "before"
        else:
            images[index] = forward
            stages[index] = None
    return tuple(directories), tuple(images), tuple(stages)


def _forward_records():
    state = (("pending", "pending"), (False, False, False), (None, None, None))
    yield 0, 0, None, state
    operations = (("mkdir", OUTPUT_DIRS[0]), ("mkdir", OUTPUT_DIRS[1]),
                  *((kind, path) for path in MANAGED for kind in ("stage", "replace")))
    for number, operation in enumerate(operations, 1):
        yield number, number - 1, operation, state
        mutated = _ledger_effect(state, operation, forward=True)
        yield number, number - 1, operation, mutated
        state = _ledger_effect(mutated, operation, forward=True, checkpoint=True)
        yield number, number, None, state


def _next_restore(state):
    directories, images, stages = state
    for index in range(2, -1, -1):
        if images[index]:
            return ("unlink" if index == 0 else "replace" if stages[index] == "before" else "stage",
                    MANAGED[index])
    for index in (1, 0):
        if directories[index] == "created":
            return "rmdir", OUTPUT_DIRS[index]
    return None


@lru_cache(maxsize=256)
def _reachable_recovery(sequence, completed, operation, state, *, final=False):
    """Bounded ledger search; retries add intents without completing mutations.

    A visible rename may be skipped on a subsequent recovery. An existing stage
    can continue to rename only in-process; restarting with it requires manual
    inspection. Directory stamps/bindings are verified separately by CanaryFS.
    """
    queue = deque()
    for seq, done, intent, current in _forward_records():
        if not any(current[2]):  # Only stage-free states can enter recovery.
            queue.append((seq, done, intent, current, "inherited"))
    seen = set()
    while queue:
        node = queue.popleft()
        seq, done, intent, current, progress = node
        if seq > sequence or done > completed or node in seen:
            continue
        if any(want and not have for have, want in zip(current[1], state[1])):
            continue  # Reverse restoration cannot reinstall an after-image.
        if any((have == "pending" and want != "pending") or
               (have == "removed" and want != "removed") or (have == "created" and want == "pending")
               for have, want in zip(current[0], state[0])):
            continue
        if any(stage == "before" and state[2][i] is None and state[1][i]
               for i, stage in enumerate(current[2])):
            continue  # Dropping a completed stage requires its baseline rename.
        seen.add(node)
        if (seq, done, intent, current) == (sequence, completed, operation, state):
            return True
        if final and _next_restore(current) is None and not any(current[2]):
            # Final restoration resolves an intent that failed before mutation,
            # even when no file/directory needed restoring (e.g. first mkdir EIO).
            queue.append((seq, seq, None, current, "inherited"))
        # A new recovery call may abandon an outstanding intent only when no
        # stage remains. Within a running call a completed stage proceeds to rename.
        if intent is None or not any(current[2]):
            next_operation = _next_restore(current)
            if next_operation is not None:
                queue.append((seq + 1, done, next_operation, current, "pending"))
        if progress == "pending":
            mutated = _ledger_effect(current, intent)
            queue.append((seq, done, intent, mutated, "mutated"))
        elif progress == "mutated":
            checkpoint = _ledger_effect(current, intent, checkpoint=True)
            queue.append((seq, seq, None, checkpoint, "inherited"))
    return False


def _check_prefix(fs, data):
    """Require a reachable forward/recovery ledger before locking or replay."""
    images, stages = [], []
    for path, before, after in _entries(data["entries"]):
        current = fs.read(path)
        if current not in (before, after):
            raise ValueError("journal image is neither approved before nor after")
        images.append(current == after)
        stage = fs.read(STAGES[path])
        if stage is None:
            stages.append(None)
        elif stage == after:
            stages.append("after")
        elif before is not None and stage == before:
            stages.append("before")
        else:
            raise ValueError("partial or foreign stage retained for manual inspection")
    state = (tuple(r["state"] for r in data["directories"]), tuple(images), tuple(stages))
    operation = None if data["intent"] is None else (data["intent"]["kind"], data["intent"]["path"])
    record = data["sequence"], data["completed"], operation, state
    phase = data["phase"]
    if phase in ("prepared", "applying", "applied"):
        if record not in _forward_records():
            raise ValueError("journal contradicts forward transaction order")
    elif not _reachable_recovery(*record, final=phase == "restored"):
        raise ValueError("journal contradicts reachable restoration checkpoints")
    if phase == "restored" and (any(images) or any(stages) or "created" in state[0]):
        raise ValueError("restored journal contradicts current images/provenance")


class _Journal:
    def __init__(self, fs, data):
        self.fs, self.data = fs, data
        fs.directories = data["directories"]
        self.expected = fs.read(JOURNAL)

    def save(self):
        if self.data["sequence"] > 128:
            raise ValueError("bounded mutation ledger exhausted; manual inspection")
        self.fs.write_journal(pack(self.data), expected=self.expected)
        self.expected = self.fs.read(JOURNAL)

    def intent(self, kind, path):
        self.data["sequence"] += 1
        self.data["intent"] = dict(kind=kind, path=path)
        self.save()

    def done(self):
        self.data["completed"] = self.data["sequence"]
        self.data["intent"] = None
        self.save()

    def bind(self):
        self.fs.on_intent, self.fs.on_done = self.intent, self.done


def _verify(fs, data, *, final=None):
    fs.guard()
    fs.directories = data["directories"]
    fs.check_directories()
    fs.stages_absent()
    for path, before, after in _entries(data["entries"]):
        current = fs.read(path)
        allowed = (before,) if final == "restored" else (after,) if final == "applied" else (before, after)
        if current not in allowed:
            raise ValueError("later edit preserved; full recovery refused")
    if final == "restored" and any(r["state"] == "created" for r in fs.directories):
        raise ValueError("restoration cleanup incomplete")
    if final == "applied" and any(r["state"] != "created" for r in fs.directories):
        raise ValueError("applied journal lacks proven output ancestors")


def _sync_verified(fs, data, *, final=None):
    expected = fs.read(JOURNAL)
    if _load(fs) != data:
        raise ValueError("journal changed before durability verification")
    fs.sync_parents()
    _verify(fs, data, final=final)
    if _load(fs) != data or fs.read(JOURNAL) != expected:
        raise ValueError("journal changed during final durability pass")


def apply(root, *, plan=None):
    """Fresh preparation under advisory lock. Supplied plans never authorize writes."""
    if plan is not None:
        return _result(False, "refused: supplied plans are preview-only")
    started = False
    try:
        with CanaryFS(root) as fs:
            entries = _baseline(fs)
            with fs.locked():
                if _baseline(fs) != entries:
                    raise ValueError("baseline changed under lock")
                data = dict(schema=1, scope=SCOPE, manifest_sha256=digest(fs.marker["content"]),
                            phase="prepared", entries=fs.manifest["entries"],
                            directories=[dict(path=p, state="pending", identity=None) for p in OUTPUT_DIRS],
                            intent=None, sequence=0, completed=0)
                journal = _Journal(fs, data)
                started = True  # Metadata rename may succeed before fsync raises.
                journal.save()
                journal.bind()
                data["phase"] = "applying"
                journal.save()
                for path in OUTPUT_DIRS:
                    fs.mkdir(path)
                for path, before, after in entries:
                    fs.replace(path, after, expected=before)
                _verify(fs, data, final="applied")
                _sync_verified(fs, data, final="applied")
                data["phase"] = "applied"
                journal.save()
                _verify(fs, data, final="applied")
                _sync_verified(fs, data, final="applied")
        return _result(True, "applied: fixture Minimal canary; explicit recovery restores baseline")
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        # Preserve all stages and the last durable record. No speculative cleanup
        # or best-effort rewrite that could disguise uncertain provenance.
        return _result(False, "incomplete: explicit recovery/manual inspection required" if started else
                       "refused: no canary mutation started")


def inspect(root):
    """Write-free status, except replaying fsync obligations on owned fixture dirs."""
    try:
        with CanaryFS(root) as fs:
            data = _load(fs)
            if data is None:
                _baseline(fs)
                return _result(True, "unused: approved fixture baseline")
            with fs.locked():
                if _load(fs) != data:
                    raise ValueError("journal changed under inspection lock")
                final = data["phase"] if data["phase"] in ("applied", "restored") else None
                _verify(fs, data, final=final)
                _sync_verified(fs, data, final=final)
                return _result(final is not None, data["phase"])
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        return _result(False, "incomplete: evidence retained; manual inspection/durability retry")


def recover(root):
    """Guarded reverse restoration; ambiguous images/provenance/stages are preserved."""
    try:
        with CanaryFS(root) as fs:
            data = _load(fs)
            if data is None:
                with fs.locked():
                    _baseline(fs)
                    fs.sync_parents()
                    _baseline(fs)
                return _result(True, "unused: no recovery needed")
            final = data["phase"] if data["phase"] in ("applied", "restored") else None
            _verify(fs, data, final=final)
            with fs.locked():
                if _load(fs) != data:
                    raise ValueError("journal changed under recovery lock")
                _verify(fs, data, final=final)
                if data["phase"] == "restored":
                    _sync_verified(fs, data, final="restored")
                    return _result(True, "restored: verified again; no file writes")
                journal = _Journal(fs, data)
                journal.bind()
                data["phase"] = "recovering"
                journal.save()
                for path, before, after in reversed(_entries(data["entries"])):
                    _verify(fs, data)
                    current = fs.read(path)
                    if current == before:
                        continue
                    if current != after:
                        raise ValueError("external edit preserved")
                    fs.replace(path, before, expected=current)
                for path in reversed(OUTPUT_DIRS):
                    fs.remove_dir(path)
                _verify(fs, data, final="restored")
                _sync_verified(fs, data, final="restored")
                data["phase"] = "restored"
                data["intent"] = None
                data["completed"] = data["sequence"]
                journal.save()
                _verify(fs, data, final="restored")
                _sync_verified(fs, data, final="restored")
        return _result(True, "restored: baseline images and output absence verified")
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        return _result(False, "incomplete: evidence retained; manual inspection/durability retry")
