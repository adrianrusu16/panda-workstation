"""Phase 3A fixture transactions. No real application activation or home writes."""

from contextlib import contextmanager
from dataclasses import dataclass
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import tomllib

from adapters.terminals import TerminalAdapter
from adapters.shell import ShellAdapter
from fixture_fs import FileImage, FixtureError, FixtureFS, FILENAMES, MANAGED, new_image
from palette import load_family
from selection import Decision
from state import ThemeState, read_state

STATE = "config/panda/theme-state.toml"
REASON = "config/panda/theme-decision.toml"
INDEX = "config/panda/managed-files.json"
JOURNAL = "state/panda-transactions/journal.json"
LOCK = "state/panda-transactions/lock"


@dataclass(frozen=True)
class SwitchResult:
    success: bool
    active: str | None
    warnings: tuple[str, ...]
    rollback_status: str


@dataclass(frozen=True)
class Entry:
    relative: str
    before: FileImage | None
    after: FileImage


@dataclass(frozen=True)
class Plan:
    root: Path
    candidate: ThemeState
    entries: tuple[Entry, ...]
    prepared: tuple
    adapters: tuple
    warnings: tuple[str, ...]
    created_dirs: tuple[str, ...]


def fixture_root(config_root, state_root):
    config_root, state_root = Path(config_root), Path(state_root)
    if (config_root.name != "config" or state_root.name != "state" or
            config_root.parent != state_root.parent or ".." in config_root.parts or
            ".." in state_root.parts):
        raise FixtureError("config/state must be direct children of the same enrolled fixture")
    with FixtureFS(config_root.parent):
        return config_root.parent


def default_adapters():
    return tuple(TerminalAdapter(name) if name in ("ghostty", "kitty", "konsole") else ShellAdapter(name)
                 for name in FILENAMES)


def _digest(content):
    return hashlib.sha256(content).hexdigest()


def _unique(items):
    result = {}
    for key, value in items:
        if key in result:
            raise FixtureError("duplicate metadata key")
        result[key] = value
    return result


def _json(content):
    try:
        return json.loads(content, object_pairs_hook=_unique)
    except (ValueError, RecursionError) as error:
        raise FixtureError("invalid transaction metadata; manual review required") from error


def _encode(data):
    return (json.dumps(data, sort_keys=True, indent=2) + "\n").encode()


def _index(image):
    if image is None:
        return {}
    data = _json(image.content)
    generated = {"config/panda/generated/" + name for name in FILENAMES.values()}
    if (not isinstance(data, dict) or set(data) != {"schema_version", "files"} or
            type(data["schema_version"]) is not int or data["schema_version"] != 1 or
            not isinstance(data["files"], dict) or not set(data["files"]) <= generated or
            any(not isinstance(value, str) or len(value) != 64 or
                any(char not in "0123456789abcdef" for char in value)
                for value in data["files"].values())):
        raise FixtureError("invalid managed ownership index")
    return data["files"]


def _decision(image, state):
    if image is None:
        return None
    try:
        data = tomllib.loads(image.content.decode())
        if set(data) != {"active", "reason", "source"} or state is None or data["active"] != state.active:
            raise ValueError()
        return Decision(data["active"], data["reason"], data["source"])
    except (ValueError, TypeError, RecursionError) as error:
        raise FixtureError("inconsistent decision sidecar; review without overwriting") from error


def read_decision(config_root):
    """Fixture-only reason lookup; never retrofit a reason to legacy state."""
    with FixtureFS(Path(config_root).parent) as fs:
        return _decision(fs.read(REASON), read_state(Path(config_root) / "panda/theme-state.toml"))


def inspect_fixture(config_root, state_root):
    """Read-only consistency checks; no lock, staging, refresh or recovery."""
    root = fixture_root(config_root, state_root)
    with FixtureFS(root) as fs:
        current = read_state(Path(config_root) / "panda/theme-state.toml")
        _decision(fs.read(REASON), current)
        ownership = _index(fs.read(INDEX))
        for relative, digest in ownership.items():
            image = fs.read(relative)
            if image is None or _digest(image.content) != digest:
                raise FixtureError("fixture ownership/content inconsistent; manual review required")
        journal = _load_journal(fs)
        if journal is not None and journal[2] in ("prepared", "incomplete"):
            raise FixtureError("interrupted fixture requires explicit doctor --recover")
        if journal is not None and journal[2] == "committed":
            for entry in journal[0]:
                if fs.read(entry.relative) != entry.after:
                    raise FixtureError("committed fixture changed externally; review required")
        return (f"fixture fragments: {len(ownership)}/6 enrolled; native applications unverified",
                f"fixture journal: {journal[2] if journal else 'absent'}",
                "live configuration hooks: disabled until Phase 3B")


def prepare_switch(candidate: ThemeState, config_root: Path, state_root: Path, *,
                   decision: Decision | None = None, adapters=None) -> Plan:
    """Plan/validate everything in memory. Creates no directories, locks or temps."""
    if not isinstance(candidate, ThemeState):
        raise FixtureError("candidate must satisfy the four-field state contract")
    root = fixture_root(config_root, state_root)
    family = load_family(Path(__file__).parent.parent)
    theme = family[candidate.active]
    if decision is None:
        if candidate.mode != "manual":
            raise FixtureError("automatic transaction requires its explicit selection decision")
        decision = Decision(candidate.active, "explicit manual command", "manual")
    if decision.slug != candidate.active or (candidate.mode == "manual" and decision.source != "manual"):
        raise FixtureError("decision does not match proposed state")
    adapters = tuple(default_adapters() if adapters is None else adapters)
    if len(adapters) != len(FILENAMES) or {a.component for a in adapters} != set(FILENAMES):
        raise FixtureError("fixture registry must account for all six terminal/shell targets")
    with FixtureFS(root) as fs:
        previous = read_state(Path(config_root) / "panda/theme-state.toml")
        _decision(fs.read(REASON), previous)
        ownership = _index(fs.read(INDEX))
        # Validate every previously enrolled file, including an unavailable adapter.
        for relative, digest in ownership.items():
            image = fs.read(relative)
            if image is None or _digest(image.content) != digest:
                raise FixtureError("managed content changed externally; refusing overwrite")
        prepared, enrolled, warnings, entries = [], [], [], []
        for adapter in adapters:
            outcome = adapter.probe()
            if not outcome.success:
                if adapter.critical:
                    raise FixtureError(f"{adapter.component}: required fixture target unavailable")
                warnings.append(f"{adapter.component}: optional target unavailable; not verified")
                continue
            item = adapter.prepare(theme, root / "state/render")
            expected_path = "config/panda/generated/" + FILENAMES[adapter.component]
            if item.component != adapter.component or item.relative != expected_path:
                raise FixtureError("adapter proposed an unapproved destination")
            if len(item.content) > 65536:
                raise FixtureError("prepared fragment exceeds recoverable image limit")
            outcome = adapter.validate(item)
            if not outcome.success:
                raise FixtureError(f"{adapter.component}: prepared fragment validation failed")
            old = fs.read(item.relative)
            if old is not None and (item.relative not in ownership or not old.mode & 0o200):
                raise FixtureError("ownership conflict or read-only managed fragment")
            after = old if old is not None and old.content == item.content else new_image(
                item.content, old.mode if old else 0o600)
            entries.append(Entry(item.relative, old, after))
            ownership[item.relative] = _digest(item.content)
            prepared.append(item)
            enrolled.append(adapter)
        if not prepared:
            raise FixtureError("no available enrolled components; selection cannot be verified")
        # json.dumps produces TOML-compatible quoted plain strings, including escaping.
        state_bytes = "".join(f"{key} = {json.dumps(getattr(candidate, key), ensure_ascii=False)}\n"
                              for key in ("mode", "active", "last_manual", "context")).encode()
        reason_bytes = "".join(f"{key} = {json.dumps(value, ensure_ascii=False)}\n" for key, value in {
            "active": candidate.active, "reason": decision.reason, "source": decision.source,
        }.items()).encode()
        for relative, content in ((INDEX, _encode({"schema_version": 1, "files": ownership})),
                                  (REASON, reason_bytes), (STATE, state_bytes)):
            if len(content) > 65536:
                raise FixtureError("proposed state/decision exceeds recoverable image limit")
            old = fs.read(relative)
            if old is not None and not old.mode & 0o200:
                raise FixtureError("managed metadata is read-only")
            after = old if old is not None and old.content == content else new_image(content, old.mode if old else 0o600)
            entries.append(Entry(relative, old, after))
        directories = []
        for relative in ("config", "config/panda", "config/panda/generated"):
            try:
                directory_fd, _ = fs.parent(relative + "/probe")
                os.close(directory_fd)
            except FileNotFoundError:
                directories.append(relative)
        warnings.append("Phase 3A fixture verification only; all native applications and Wayland behavior unverified")
        # Use exactly the recovery consumer's image contract before writing its
        # producer record; unsupported original metadata is a preparation error.
        for entry in entries:
            _image_from(_image_data(entry.before))
            _image_from(_image_data(entry.after))
        return Plan(root, candidate, tuple(entries), tuple(prepared), tuple(enrolled),
                    tuple(warnings), tuple(directories))


@contextmanager
def _lock(fs):
    parent_fd, name = fs.parent(LOCK, create=True)
    file_fd = None
    try:
        file_fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                          0o600, dir_fd=parent_fd)
        info = os.fstat(file_fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600):
            raise FixtureError("unsafe transaction lock")
        try:
            fcntl.flock(file_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise FixtureError("fixture transaction is locked by another process") from error
        os.fsync(parent_fd)
        yield
    finally:
        if file_fd is not None:
            os.close(file_fd)
        os.close(parent_fd)


def _image_data(image):
    if image is None:
        return None
    return {"content": base64.b64encode(image.content).decode(), "mode": image.mode,
            "mtime_ns": image.mtime_ns, "atime_ns": image.atime_ns}


def _image_from(data):
    if data is None:
        return None
    if (not isinstance(data, dict) or set(data) != {"content", "mode", "mtime_ns", "atime_ns"} or
            any(type(data[key]) is not int or data[key] < 0 for key in ("mode", "mtime_ns", "atime_ns")) or
            data["mode"] > 0o777 or data["mode"] & 0o600 != 0o600 or
            any(data[key] > 2 ** 63 - 1 for key in ("mtime_ns", "atime_ns")) or
            not isinstance(data["content"], str)):
        raise FixtureError("corrupt backup metadata")
    try:
        content = base64.b64decode(data["content"], validate=True)
    except ValueError as error:
        raise FixtureError("corrupt backup encoding") from error
    if len(content) > 65536:
        raise FixtureError("backup exceeds managed fragment limit")
    return FileImage(content, data["mode"], data["mtime_ns"], data["atime_ns"])


def _journal(fs, entries, directories, phase):
    payload = {"schema_version": 1, "phase": phase, "created_dirs": list(directories),
               "entries": [{"path": entry.relative, "before": _image_data(entry.before),
                            "after": _image_data(entry.after)} for entry in entries]}
    envelope = {"payload": payload, "sha256": _digest(_encode(payload))}
    fs.replace(JOURNAL, new_image(_encode(envelope)), expected=fs.read(JOURNAL))


def _load_journal(fs):
    image = fs.read(JOURNAL)
    if image is None:
        return None
    envelope = _json(image.content)
    if (not isinstance(envelope, dict) or set(envelope) != {"payload", "sha256"} or
            _digest(_encode(envelope["payload"])) != envelope["sha256"]):
        raise FixtureError("corrupt recovery journal; manual review required")
    data = envelope["payload"]
    if (not isinstance(data, dict) or set(data) != {"schema_version", "phase", "created_dirs", "entries"}
            or type(data["schema_version"]) is not int or data["schema_version"] != 1
            or data["phase"] not in ("prepared", "committed", "restored", "incomplete")
            or not isinstance(data["entries"], list) or not 3 <= len(data["entries"]) <= 9
            or not isinstance(data["created_dirs"], list)
            or any(directory not in ("config", "config/panda", "config/panda/generated")
                   for directory in data["created_dirs"])):
        raise FixtureError("unsupported recovery journal")
    entries = []
    for item in data["entries"]:
        if (not isinstance(item, dict) or set(item) != {"path", "before", "after"} or
                not isinstance(item["path"], str) or item["path"] not in MANAGED):
            raise FixtureError("unapproved recovery path")
        before, after = _image_from(item["before"]), _image_from(item["after"])
        if after is None:
            raise FixtureError("missing prepared image")
        entries.append(Entry(item["path"], before, after))
    paths = [entry.relative for entry in entries]
    if len(set(paths)) != len(paths) or paths[-3:] != [INDEX, REASON, STATE]:
        raise FixtureError("colliding or incomplete recovery paths")
    # A checksum alone cannot prove the backup includes every changed target.
    # Cross-check both ownership snapshots against all generated images.
    by_path = {entry.relative: entry for entry in entries}
    before_index = _index(by_path[INDEX].before)
    after_index = _index(by_path[INDEX].after)
    generated_paths = set(paths) - {INDEX, REASON, STATE}
    if not generated_paths <= set(after_index) or not set(before_index) <= set(after_index):
        raise FixtureError("inconsistent recovery ownership snapshots")
    for relative, digest in after_index.items():
        if relative not in generated_paths:
            if before_index.get(relative) != digest:
                raise FixtureError("changed target missing from recovery snapshot")
            continue
        entry = by_path[relative]
        if _digest(entry.after.content) != digest or (
                entry.before is None and relative in before_index) or (
                entry.before is not None and before_index.get(relative) != _digest(entry.before.content)):
            raise FixtureError("recovery content/ownership mismatch")
    for image in (by_path[STATE].before, by_path[STATE].after):
        if image is not None:
            try:
                values = tomllib.loads(image.content.decode())
                if set(values) != {"mode", "active", "last_manual", "context"}:
                    raise ValueError()
                ThemeState(**values)
            except (ValueError, TypeError, RecursionError) as error:
                raise FixtureError("invalid backed-up state contract") from error
    return tuple(entries), tuple(data["created_dirs"]), data["phase"]


def _restore(fs, entries, directories, adapters=()):
    errors = []
    by_path = {"config/panda/generated/" + FILENAMES[adapter.component]: adapter for adapter in adapters}
    for entry in reversed(entries):
        try:
            current = fs.read(entry.relative)
            if current == entry.before:
                continue
            if current != entry.after:
                raise FixtureError("external modification; manual restore required")
            if entry.relative in by_path:
                outcome = by_path[entry.relative].restore(entry.before)
                if not outcome.success:
                    raise FixtureError("adapter restoration failed")
            else:
                fs.replace(entry.relative, entry.before, expected=current)
            if fs.read(entry.relative) != entry.before:
                raise FixtureError("restore verification failed")
        except (OSError, ValueError):
            errors.append(f"{entry.relative}: restoration incomplete; backup retained")
    fs.remove_empty_dirs(directories)
    try:
        _journal(fs, entries, directories, "incomplete" if errors else "restored")
    except (OSError, ValueError):
        errors.append("recovery journal update failed; original backup retained where available")
    return tuple(errors)


def _diagnostic(error):
    # Our path/ownership errors contain no user contents. Arbitrary adapter or
    # native parser errors may contain config values; keep those out of output.
    return str(error) if isinstance(error, FixtureError) else f"transaction failed ({type(error).__name__})"


def switch_theme(candidate: ThemeState, config_root: Path, state_root: Path, *,
                 decision=None, adapters=None, plan=None) -> SwitchResult:
    previous = None
    try:
        fixture_root(config_root, state_root)
        previous = read_state(Path(config_root) / "panda/theme-state.toml")
        planned = prepare_switch(candidate, config_root, state_root, decision=decision, adapters=adapters)
        if plan is not None:
            if (not isinstance(plan, Plan) or plan.root != planned.root or plan.candidate != candidate or
                    [(e.relative, e.before, e.after.content) for e in plan.entries] !=
                    [(e.relative, e.before, e.after.content) for e in planned.entries]):
                raise FixtureError("stale or inconsistent transaction plan")
            planned = plan
        with FixtureFS(planned.root) as fs, _lock(fs):
            previous = read_state(Path(config_root) / "panda/theme-state.toml")
            journal = _load_journal(fs)
            if journal is not None and journal[2] in ("prepared", "incomplete"):
                raise FixtureError("interrupted transaction requires doctor --recover before switching")
            for entry in planned.entries:
                if fs.read(entry.relative) != entry.before:
                    raise FixtureError("stale plan or external modification under lock")
            bound = {entry.relative: entry for entry in planned.entries}
            for adapter, item in zip(planned.adapters, planned.prepared):
                adapter.fs, adapter.entries = fs, bound
                if adapter.snapshot(fs.root / "state/panda-transactions") != bound[item.relative].before:
                    raise FixtureError("adapter snapshot changed during preparation")
            if all(entry.before == entry.after for entry in planned.entries):
                for adapter, item in zip(planned.adapters, planned.prepared):
                    if not adapter.verify(item).success:
                        raise FixtureError("unchanged fixture verification failed")
                return SwitchResult(True, candidate.active, planned.warnings, "not-needed")
            # The fsynced record contains all before/after images before any target
            # replacement, including intended timestamps for the crash window.
            _journal(fs, planned.entries, planned.created_dirs, "prepared")
            try:
                warnings = list(planned.warnings)
                for adapter, item in zip(planned.adapters, planned.prepared):
                    if not adapter.apply(item).success:
                        raise FixtureError(f"{adapter.component}: fixture application failed")
                for adapter, item in zip(planned.adapters, planned.prepared):
                    if not adapter.verify(item).success:
                        raise FixtureError(f"{adapter.component}: fixture verification failed")
                    refreshed = adapter.refresh()
                    if not refreshed.success:
                        raise FixtureError(f"{adapter.component}: required refresh failed")
                    warnings.append(refreshed.message)
                # Index and reason are committed before the four-field state.
                for entry in planned.entries[-3:]:
                    # Refresh or a later writer may invalidate an earlier verify.
                    # Recheck the entire slice immediately before persistence.
                    for item in planned.prepared:
                        if fs.read(item.relative) != bound[item.relative].after:
                            raise FixtureError("managed fragment changed after verification; refusing state commit")
                    if entry.before != entry.after:
                        fs.replace(entry.relative, entry.after, expected=entry.before)
                    if fs.read(entry.relative) != entry.after:
                        raise FixtureError("state/decision commit verification failed")
                if read_state(Path(config_root) / "panda/theme-state.toml") != candidate:
                    raise FixtureError("persisted state verification failed")
                _journal(fs, planned.entries, planned.created_dirs, "committed")
                return SwitchResult(True, candidate.active, tuple(warnings), "not-needed")
            except BaseException as error:
                restore_errors = _restore(fs, planned.entries, planned.created_dirs, planned.adapters)
                if not isinstance(error, Exception):
                    raise
                return SwitchResult(False, previous.active if previous else None,
                                    (_diagnostic(error), *restore_errors),
                                    "incomplete" if restore_errors else "restored")
    except (OSError, ValueError, TypeError, KeyError) as error:
        return SwitchResult(False, previous.active if previous else None, (_diagnostic(error),), "not-started")


def recover(config_root: Path, state_root: Path) -> SwitchResult:
    """Conservative explicit recovery; never infer snapshots from current files."""
    try:
        root = fixture_root(config_root, state_root)
        with FixtureFS(root) as fs, _lock(fs):
            journal = _load_journal(fs)
            if journal is None or journal[2] in ("committed", "restored"):
                current = read_state(Path(config_root) / "panda/theme-state.toml")
                return SwitchResult(True, current.active if current else None,
                                    ("no interrupted fixture transaction to recover",), "not-needed")
            entries, directories, _ = journal
            # Preflight every image before restoring any file, so an ambiguous
            # record produces a diagnostic without partial speculative recovery.
            for entry in entries:
                if fs.read(entry.relative) not in (entry.before, entry.after):
                    raise FixtureError("external modification; recovery refused; backup retained")
            errors = _restore(fs, entries, directories)
            current = read_state(Path(config_root) / "panda/theme-state.toml")
            return SwitchResult(not errors, current.active if current else None, errors,
                                "incomplete" if errors else "restored")
    except (OSError, ValueError, TypeError, KeyError) as error:
        return SwitchResult(False, None, (_diagnostic(error),), "incomplete")
