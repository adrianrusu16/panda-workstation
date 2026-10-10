"""Ghostty-only B1 simulation transactions; no installed CLI or live write backend."""

import base64
from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import os
from pathlib import Path

from adapters.live_ghostty import GhosttyModel, model_hook, effective_model
from enrollment import decode_record, digest, encode_record
from fixture_fs import FileImage, new_image
from live_fs import (SimulatedLiveFS, TARGET, HOOK, MARKER, INDEX, DECISION, SELECTION,
                     JOURNAL, LOCK, MANAGED, directory_records, validate_image)
from palette import load_family
from selection import Decision
from state import ThemeState
from transaction import SwitchResult

SCOPE = "ghostty-simulation-only"
WARNING = "B1 Ghostty simulation only; native parser/reload and Wayland appearance unverified"


class _RecoveryRequired(ValueError):
    """A retained record cannot yet be accepted as completed."""


@dataclass(frozen=True)
class Entry:
    relative: str
    before: FileImage | None
    after: FileImage


@dataclass(frozen=True)
class SimulationPlan:
    entries: tuple[Entry, ...]
    hook_proposal: bytes
    created_dirs: tuple[str, ...]


def _schema(data, fields, *, version=1):
    if (not isinstance(data, dict) or set(data) != {"schema_version", "scope", *fields} or
            type(data["schema_version"]) is not int or data["schema_version"] != version or data["scope"] != SCOPE):
        raise ValueError("invalid scoped simulation metadata")
    return data


def _metadata(**values):
    return encode_record({"schema_version": 1, "scope": SCOPE, **values})


def _selection(content):
    data = _schema(decode_record(content), {"selection"})
    value = data["selection"]
    if not isinstance(value, dict) or set(value) != {"mode", "active", "last_manual", "context"}:
        raise ValueError("invalid four-field simulated selection")
    return ThemeState(**value)


def _validate_slice(images):
    if all(image is None for image in images.values()):
        return None
    if set(images) != set(MANAGED) or any(image is None for image in images.values()):
        raise ValueError("incomplete or unowned Ghostty simulation slice")
    for image in images.values():
        validate_image(image)
    candidate = _selection(images[SELECTION].content)
    decision = _schema(decode_record(images[DECISION].content), {"active", "reason", "source"})
    selected = Decision(decision["active"], decision["reason"], decision["source"])
    if selected.slug != candidate.active or (candidate.mode == "manual" and selected.source != "manual"):
        raise ValueError("simulation decision and selection disagree")
    index = _schema(decode_record(images[INDEX].content), {"target", "sha256"})
    if index["target"] != TARGET or index["sha256"] != digest(images[TARGET].content):
        raise ValueError("simulation ownership mismatch")
    family = load_family(Path(__file__).parent.parent)
    if GhosttyModel().prepare(family[candidate.active]) != images[TARGET].content:
        raise ValueError("simulation fragment differs from canonical selected palette")
    return candidate


def _images(fs):
    return {path: fs.read(path) for path in MANAGED}


def _prepare(fs, candidate, decision):
    # A partial rollback need not form a valid complete slice; classify its record first.
    journal = _load_journal(fs)
    if journal is not None and journal[2] in ("prepared", "incomplete"):
        raise _RecoveryRequired("interrupted simulation requires explicit recovery")
    if journal is not None:
        _check_completed(fs, journal)
    if not isinstance(candidate, ThemeState):
        raise ValueError("simulation requires a four-field ThemeState candidate")
    if decision is None:
        if candidate.mode != "manual":
            raise ValueError("automatic simulation requires its explicit decision")
        decision = Decision(candidate.active, "explicit manual command", "manual")
    if not isinstance(decision, Decision) or decision.slug != candidate.active or (
            candidate.mode == "manual" and decision.source != "manual"):
        raise ValueError("explicit simulation decision does not match candidate")
    fs.check_enrollment()
    family = load_family(Path(__file__).parent.parent)
    content = GhosttyModel().prepare(family[candidate.active])
    hook = model_hook(fs.read(HOOK).content)
    effective = effective_model(hook, content)
    if effective.get("background-opacity") != "1":
        raise ValueError("Ghostty simulation must be opaque")
    old = _images(fs)
    _validate_slice(old)
    lock = fs.read(LOCK)
    if lock is not None and (lock.mode != 0o600 or lock.content):
        raise ValueError("invalid simulation lock")
    values = {TARGET: content, INDEX: _metadata(target=TARGET, sha256=digest(content)),
              DECISION: _metadata(active=decision.slug, reason=decision.reason, source=decision.source),
              SELECTION: _metadata(selection={key: getattr(candidate, key)
                                             for key in ("mode", "active", "last_manual", "context")})}
    entries = []
    for path in MANAGED:
        before = old[path]
        after = before if before is not None and before.content == values[path] else new_image(
            values[path], before.mode if before is not None else 0o600)
        validate_image(after)
        entries.append(Entry(path, before, after))
    _validate_slice({entry.relative: entry.after for entry in entries})
    return SimulationPlan(tuple(entries), hook, fs.missing_output_dirs())


def prepare_simulated(candidate, root, *, decision=None):
    """Write-free preview in explicitly enrolled B1 fixtures; never an execution token."""
    with SimulatedLiveFS(root) as fs:
        return _prepare(fs, candidate, decision)


@contextmanager
def simulation_lock(fs):
    fs.check_enrollment()
    parent, name = fs.parent(LOCK, create=True)
    fd = None
    try:
        fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=parent)
        info = fs.safe_file(fd)
        if info.st_size or info.st_mode & 0o777 != 0o600:
            raise ValueError("invalid simulation lock inode")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("simulation locked by another process") from None
        fs.check_pins()
        fresh = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if (info.st_dev, info.st_ino) != (fresh.st_dev, fresh.st_ino):
            raise ValueError("simulation lock inode replaced")
        os.fsync(parent)
        yield
    finally:
        if fd is not None:
            os.close(fd)
        os.close(parent)


def _image_data(image):
    if image is None:
        return None
    validate_image(image)
    return {"content": base64.b64encode(image.content).decode(), "mode": image.mode,
            "mtime_ns": image.mtime_ns, "atime_ns": image.atime_ns}


def _image_from(data):
    if data is None:
        return None
    if not isinstance(data, dict) or set(data) != {"content", "mode", "mtime_ns", "atime_ns"}:
        raise ValueError("incomplete simulation recovery image")
    if not isinstance(data["content"], str) or len(data["content"]) > 90000:
        raise ValueError("oversized simulation recovery image")
    image = FileImage(base64.b64decode(data["content"], validate=True), data["mode"],
                      data["mtime_ns"], data["atime_ns"])
    validate_image(image)
    return image


def _journal(fs, entries, directories, phase):
    payload = {"schema_version": 2, "scope": SCOPE, "phase": phase,
               "enrollment_sha256": digest(fs.marker_image.content),
               "created_dirs": list(directory_records(directories)),
               "entries": [{"path": e.relative, "before": _image_data(e.before),
                            "after": _image_data(e.after)} for e in entries]}
    fs.replace(JOURNAL, new_image(encode_record({"payload": payload, "sha256": digest(encode_record(payload))})),
               expected=fs.read(JOURNAL))


def _load_journal(fs):
    image = fs.read(JOURNAL)
    if image is None:
        return None
    if image.mode != 0o600:
        raise ValueError("unsafe simulation recovery journal mode")
    # Journal holds four pairs of bounded images; its envelope has a separate larger limit.
    if len(image.content) > 1024*1024:
        raise ValueError("oversized simulation journal")
    import json
    from enrollment import _unique
    envelope = json.loads(image.content, object_pairs_hook=_unique)
    if (not isinstance(envelope, dict) or set(envelope) != {"payload", "sha256"} or
            envelope["sha256"] != digest(encode_record(envelope["payload"]))):
        raise ValueError("corrupt simulation recovery journal")
    data = _schema(envelope["payload"], {"phase", "enrollment_sha256", "created_dirs", "entries"}, version=2)
    if (data["phase"] not in ("prepared", "committed", "restored", "incomplete") or
            data["enrollment_sha256"] != digest(fs.marker_image.content) or
            not isinstance(data["created_dirs"], list) or
            not isinstance(data["entries"], list) or len(data["entries"]) != len(MANAGED)):
        raise ValueError("unsupported simulation recovery scope")
    entries = []
    for path, item in zip(MANAGED, data["entries"]):
        if (not isinstance(item, dict) or set(item) != {"path", "before", "after"} or item["path"] != path):
            raise ValueError("incomplete or reordered simulation recovery paths")
        before, after = _image_from(item["before"]), _image_from(item["after"])
        if after is None:
            raise ValueError("missing intended simulation image")
        entries.append(Entry(path, before, after))
    for field in ("before", "after"):
        _validate_slice({e.relative: getattr(e, field) for e in entries})
    return tuple(entries), directory_records(data["created_dirs"]), data["phase"]


def _check_completed(fs, record):
    entries, directories, phase = record
    try:
        fs.check_directories(directories, completed=phase == "restored")
        for entry in entries:
            expected = entry.before if phase == "restored" else entry.after
            if fs.read(entry.relative) != expected:
                raise ValueError("completed record differs from current images")
        fs.sync_restoration(directories)
    except (OSError, ValueError) as error:
        raise _RecoveryRequired("completed simulation requires recovery or manual review") from error


def _restore(fs, entries, directories):
    errors = []
    fs.on_directory_change = None
    try:
        fs.track_directories(directories)
    except (OSError, ValueError):
        # Never restore files through directories whose recorded provenance has drifted.
        return ("simulation directory provenance unknown or changed; manual review required; record retained",)
    for entry in reversed(entries):
        try:
            current = fs.read(entry.relative)
            if current == entry.before:
                continue
            if current != entry.after:
                raise ValueError("later edit conflicts with simulation recovery")
            fs.replace(entry.relative, entry.before, expected=current)
            if fs.read(entry.relative) != entry.before:
                raise ValueError("simulation restoration verification failed")
        except (OSError, ValueError):
            errors.append(f"{entry.relative}: restoration incomplete; record retained")
    try:
        fs.remove_empty_dirs(directories)
    except (OSError, ValueError):
        errors.append("simulation directory cleanup incomplete")
    try:
        # Already-recognized before-images can still owe a sync from a failed rename/unlink.
        fs.sync_restoration(directories)
    except (OSError, ValueError):
        errors.append("simulation managed-parent durability incomplete")
    try:
        _journal(fs, entries, fs.updated_records(directories), "incomplete" if errors else "restored")
    except (OSError, ValueError):
        errors.append("simulation recovery journal update failed; record retained where available")
        # Rename may have succeeded before its parent fsync failed. Do not leave
        # an apparently completed record when a pending replacement can be saved.
        try:
            _journal(fs, entries, fs.updated_records(directories), "incomplete")
        except (OSError, ValueError):
            pass  # The original failure is reported; recovery retries restored-record durability too.
    return tuple(errors)


def _diagnostic(error):
    # Parser/adapter exceptions can contain arbitrary supplied values; never echo them.
    return f"Ghostty simulation refused or failed ({type(error).__name__}); live capability disabled"


def switch_simulated(candidate, root, *, decision=None, plan=None):
    """Fresh internal preparation under lock; supplied previews are always refused."""
    previous = None
    recovery_required = False
    try:
        if plan is not None:
            raise ValueError("supplied simulation plans are preview-only")
        with SimulatedLiveFS(root) as fs:
            preview = _prepare(fs, candidate, decision)  # Full preflight before any lock/directory write.
            previous = _validate_slice({e.relative: e.before for e in preview.entries})
            with simulation_lock(fs):
                prepared = _prepare(fs, candidate, decision)
                if (prepared.hook_proposal != preview.hook_proposal or
                        any(a.before != b.before for a, b in zip(prepared.entries, preview.entries)) or
                        prepared.created_dirs != tuple(p for p in preview.created_dirs if p not in fs.created) or
                        any(p not in preview.created_dirs for p in fs.created)):
                    raise ValueError("simulation changed while waiting for lock")
                adapter = GhosttyModel()
                if all(e.before == e.after for e in prepared.entries):
                    if not adapter.verify(fs, prepared.entries[0].after.content).success:
                        raise ValueError("unchanged simulation verification failed")
                    fs.sync_restoration(())
                    return SwitchResult(True, candidate.active, (WARNING,), "not-needed")
                recovery_required = True  # A journal rename may succeed before the writer raises.
                try:
                    _journal(fs, prepared.entries, fs.records_for(prepared.created_dirs), "prepared")
                    # Persist actual mkdir identities and owned directory mutations before
                    # returning from the operation. A crash before this callback remains ambiguous.
                    fs.on_directory_change = lambda: _journal(
                        fs, prepared.entries, fs.records_for(prepared.created_dirs), "prepared")
                    target = prepared.entries[0]
                    fs.replace(target.relative, target.after, expected=target.before)
                    if not adapter.verify(fs, target.after.content).success or fs.read(TARGET) != target.after:
                        raise ValueError("simulation verification failed")
                    refresh = adapter.refresh()
                    if not refresh.success:
                        raise ValueError("simulation refresh model failed")
                    for entry in prepared.entries[1:]:
                        fs.check_enrollment()
                        if fs.read(TARGET) != target.after:
                            raise ValueError("simulation changed after verification")
                        if entry.before != entry.after:
                            fs.replace(entry.relative, entry.after, expected=entry.before)
                        if fs.read(entry.relative) != entry.after:
                            raise ValueError("simulation metadata commit verification failed")
                    fs.check_enrollment()
                    if _images(fs) != {e.relative: e.after for e in prepared.entries}:
                        raise ValueError("simulation slice changed before commit")
                    fs.on_directory_change = None
                    fs.sync_restoration(fs.records_for(prepared.created_dirs))
                    _journal(fs, prepared.entries, fs.records_for(prepared.created_dirs), "committed")
                    return SwitchResult(True, candidate.active, (WARNING, refresh.message), "not-needed")
                except BaseException as error:
                    try:
                        errors = _restore(fs, prepared.entries, fs.records_for(prepared.created_dirs))
                    except Exception:
                        errors = ("simulation restoration setup failed; recovery required; record retained where available",)
                    if not isinstance(error, Exception):
                        raise
                    return SwitchResult(False, previous.active if previous else None,
                                        (_diagnostic(error), *errors), "incomplete" if errors else "restored")
    except (OSError, ValueError, TypeError, KeyError, RecursionError) as error:
        status = "incomplete" if recovery_required or isinstance(error, _RecoveryRequired) else "not-started"
        return SwitchResult(False, previous.active if previous else None, (_diagnostic(error),), status)


def recover_simulated(root):
    """Conservative explicit replay, scoped to matching B1 enrollment and exact images."""
    try:
        with SimulatedLiveFS(root) as fs:
            fs.check_enrollment()
            record = _load_journal(fs)
            if record is None or record[2] in ("committed", "restored"):
                if record is not None:
                    _check_completed(fs, record)
                current = _validate_slice(_images(fs))
                return SwitchResult(True, current.active if current else None, (WARNING,), "not-needed")
            entries, directories, _ = record
            fs.check_directories(directories)
            # Refuse the whole recovery before opening/creating a lock if any image is ambiguous.
            for entry in entries:
                if fs.read(entry.relative) not in (entry.before, entry.after):
                    raise ValueError("later external edit; recovery refused")
            with simulation_lock(fs):
                fs.check_enrollment()
                if _load_journal(fs) != record:
                    raise ValueError("recovery record changed under lock")
                fs.check_directories(directories)
                for entry in entries:
                    if fs.read(entry.relative) not in (entry.before, entry.after):
                        raise ValueError("later edit under recovery lock")
                errors = _restore(fs, entries, directories)
                current = _validate_slice(_images(fs)) if not errors else None
                return SwitchResult(not errors, current.active if current else None, (WARNING, *errors),
                                    "incomplete" if errors else "restored")
    except (OSError, ValueError, TypeError, KeyError, RecursionError) as error:
        return SwitchResult(False, None, (_diagnostic(error), WARNING), "incomplete")
