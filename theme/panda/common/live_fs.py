"""Independent B1 simulation capability; all writes require a private /tmp root."""

import errno
import os
from pathlib import Path
import stat
import uuid

from fixture_fs import FileImage
from enrollment import PATHS, Enrollment, decode_record, digest, encode_record

MARKER = ".panda-theme-b1.json"
SOURCE, HOOK, TARGET = (PATHS[k] for k in ("source", "hook", "target"))
PREFIX = "state/panda-ghostty-simulation/"
INDEX, DECISION, SELECTION, JOURNAL, LOCK = (
    PREFIX + name for name in ("managed-files.json", "decision.json", "selection.json", "journal.json", "lock"))
MANAGED = (TARGET, INDEX, DECISION, SELECTION)
WRITABLE = frozenset(MANAGED) | {JOURNAL, LOCK}
READABLE = WRITABLE | {SOURCE, HOOK, MARKER}
CREATABLE_DIRS = frozenset({"config/panda", "config/panda/generated", "state/panda-ghostty-simulation"})
CLEANUP_DIRS = ("config/panda", "config/panda/generated")
DIRECTORY_FIELDS = {"device", "inode", "uid", "gid", "mode", "mtime_ns", "ctime_ns"}


def directory_records(records):
    """Validate bounded schema-2 provenance, never a caller-supplied path list."""
    if not isinstance(records, (list, tuple)) or len(records) > len(CLEANUP_DIRS):
        raise ValueError("invalid directory provenance")
    paths = []
    for record in records:
        if (not isinstance(record, dict) or set(record) != {"path", "identity"} or
                record["path"] not in CLEANUP_DIRS):
            raise ValueError("unsupported cleanup scope")
        paths.append(record["path"])
        identity = record["identity"]
        if identity is not None and (not isinstance(identity, dict) or set(identity) != DIRECTORY_FIELDS or
                any(type(v) is not int or not 0 <= v <= 2**63-1 for v in identity.values()) or
                identity["uid"] != os.getuid() or identity["mode"] != 0o700):
            raise ValueError("unsupported directory identity")
    if paths != [path for path in CLEANUP_DIRS if path in paths]:
        raise ValueError("duplicate or reordered directory provenance")
    return tuple({"path": r["path"], "identity": dict(r["identity"]) if r["identity"] else None}
                 for r in records)


def _root(root):
    root = Path(root)
    if (not root.is_absolute() or ".." in root.parts or root.parent != Path("/tmp") or
            not root.name.startswith("panda-theme-b1-")):
        raise ValueError("B1 requires an explicit private /tmp/panda-theme-b1-* simulation")
    return root


def _directory(info, *, root=False):
    mode = stat.S_IMODE(info.st_mode)
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or
            mode & 0o022 or mode & 0o700 != 0o700 or (root and mode != 0o700)):
        raise ValueError("unsafe simulation directory ownership or mode")


def validate_image(image):
    if image is None:
        return
    if (not isinstance(image, FileImage) or not isinstance(image.content, bytes) or
            len(image.content) > 65536 or type(image.mode) is not int or
            not 0 <= image.mode <= 0o777 or image.mode & 0o600 != 0o600 or image.mode & 0o022 or
            any(type(v) is not int or not 0 <= v <= 2**63-1
                for v in (image.mtime_ns, image.atime_ns))):
        raise ValueError("unsupported simulation image metadata")


class _TreeIO:
    """Private reader used to validate enrollment before its exclusive creation."""

    def __init__(self, root):
        self.root = _root(root)
        self.fd = None
        self.pins = {}
        self.created = {}
        self.on_directory_change = None
        self.enrollment = None
        try:
            self.fd = self._open_root()
            _directory(os.fstat(self.fd), root=True)
            for name in ("home", "config", "data", "state", "cache", "source"):
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=self.fd)
                try:
                    _directory(os.fstat(child), root=True)
                    self.pins[name] = self._identity(child)
                finally:
                    os.close(child)
        except (OSError, ValueError):
            if self.fd is not None:
                os.close(self.fd)
            raise ValueError("B1 simulation root must contain private disposable HOME/XDG/source directories") from None

    def _open_root(self):
        tmp = os.open("/tmp", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            return os.open(self.root.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=tmp)
        finally:
            os.close(tmp)

    @staticmethod
    def _identity(fd):
        info = os.fstat(fd)
        return info.st_dev, info.st_ino

    @staticmethod
    def _directory_image(fd):
        info = os.fstat(fd)
        _directory(info)
        if os.listxattr(fd):
            raise ValueError("unsupported directory extended metadata")
        return {"device": info.st_dev, "inode": info.st_ino, "uid": info.st_uid,
                "gid": info.st_gid, "mode": stat.S_IMODE(info.st_mode),
                "mtime_ns": info.st_mtime_ns, "ctime_ns": info.st_ctime_ns}

    def _check_created(self, relative, fd):
        if relative in CLEANUP_DIRS and relative in self.created and self._directory_image(fd) != self.created[relative]:
            raise ValueError("transaction-created directory changed")

    def _refresh_created(self, relative, fd, *, notify=True):
        if relative not in self.created:
            return
        fresh = self._directory_image(fd)
        old = self.created[relative]
        if any(fresh[key] != old[key] for key in DIRECTORY_FIELDS - {"mtime_ns", "ctime_ns"}):
            raise ValueError("created directory identity or mode changed")
        self.created[relative] = fresh
        if fresh != old and notify and relative in CLEANUP_DIRS and self.on_directory_change:
            self.on_directory_change()

    def root_identity(self):
        info = os.fstat(self.fd)
        return {"device": info.st_dev, "inode": info.st_ino, "uid": info.st_uid,
                "gid": info.st_gid, "mode": stat.S_IMODE(info.st_mode)}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        os.close(self.fd)

    def check_pins(self):
        fresh = self._open_root()
        try:
            _directory(os.fstat(fresh), root=True)
            if self._identity(fresh) != self._identity(self.fd):
                raise ValueError("simulation root replaced")
            for path, identity in self.pins.items():
                current = os.dup(fresh)
                try:
                    for part in path.split("/"):
                        child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current)
                        os.close(current)
                        current = child
                        _directory(os.fstat(current))
                    if self._identity(current) != identity:
                        raise ValueError("simulation parent directory replaced")
                finally:
                    os.close(current)
        finally:
            os.close(fresh)

    def parent(self, relative, *, create=False):
        if not isinstance(relative, str) or relative not in READABLE or (create and relative not in WRITABLE):
            raise ValueError("path outside exact Ghostty simulation allowlist")
        self.check_pins()
        current = os.dup(self.fd)
        parts = relative.split("/")
        try:
            for index, part in enumerate(parts[:-1]):
                prefix = "/".join(parts[:index+1])
                created = False
                try:
                    child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current)
                except FileNotFoundError:
                    if not create or prefix not in CREATABLE_DIRS:
                        raise
                    self._check_created("/".join(parts[:index]), current)
                    os.mkdir(part, 0o700, dir_fd=current)
                    created = True
                    child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current)
                try:
                    _directory(os.fstat(child))
                    identity = self._identity(child)
                    if prefix in self.pins and self.pins[prefix] != identity:
                        raise ValueError("simulation parent replaced")
                    self.pins[prefix] = identity
                    if created:
                        self.created[prefix] = self._directory_image(child)
                        self._refresh_created("/".join(parts[:index]), current, notify=False)
                        os.fsync(child)
                        os.fsync(current)
                        if prefix in CLEANUP_DIRS and self.on_directory_change:
                            self.on_directory_change()
                except BaseException:
                    os.close(child)
                    raise
                os.close(current)
                current = child
            return current, parts[-1]
        except BaseException:
            os.close(current)
            raise

    @staticmethod
    def safe_file(fd, *, limit=65536):
        info = os.fstat(fd)
        mode = stat.S_IMODE(info.st_mode)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid() or
                mode > 0o777 or mode & 0o600 != 0o600 or mode & 0o022 or info.st_size > limit or
                os.listxattr(fd)):
            raise ValueError("unsupported simulation file type, owner, links, mode or extended metadata")
        return info

    def read(self, relative):
        parent = None
        try:
            parent, name = self.parent(relative)
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_NOATIME, dir_fd=parent)
            with os.fdopen(fd, "rb") as handle:
                limit = 1024*1024 if relative == JOURNAL else 65536
                info = self.safe_file(handle.fileno(), limit=limit)
                content = handle.read(limit+1)
                if len(content) > limit:
                    raise ValueError("simulation read limit exceeded")
                return FileImage(content, stat.S_IMODE(info.st_mode), info.st_mtime_ns, info.st_atime_ns)
        except FileNotFoundError:
            return None
        except OSError:
            raise ValueError("unsafe or unreadable simulation path") from None
        finally:
            if parent is not None:
                os.close(parent)

    def fingerprint(self, relative):
        image = self.read(relative)
        if image is None:
            raise ValueError("required source or hook baseline missing")
        validate_image(image)
        parent, name = self.parent(relative)
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_NOATIME, dir_fd=parent)
            try:
                info = self.safe_file(fd)
                if os.read(fd, 65537) != image.content or info.st_mtime_ns != image.mtime_ns:
                    raise ValueError("input changed during fingerprinting")
                return {"device": info.st_dev, "inode": info.st_ino, "uid": info.st_uid, "gid": info.st_gid,
                        "mode": image.mode, "nlink": info.st_nlink, "size": len(image.content),
                        "mtime_ns": image.mtime_ns, "sha256": digest(image.content)}
            finally:
                os.close(fd)
        finally:
            os.close(parent)

    def write_enrollment(self, record):
        # Exclusive creation only after complete read-only validation, never repairs a marker.
        self.check_pins()
        for key in ("source", "hook"):
            if self.fingerprint(PATHS[key]) != record.fingerprints[key]:
                raise ValueError("enrollment inputs changed")
        fd = os.open(MARKER, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
        with os.fdopen(fd, "wb") as handle:
            handle.write(encode_record(record.to_dict()))
            handle.flush()
            os.fsync(handle.fileno())
        os.fsync(self.fd)


class SimulatedLiveFS(_TreeIO):
    """An enrolled B1 capability; no dispatch, fallback or conversion to real paths."""

    def __init__(self, root):
        super().__init__(root)
        try:
            image = self.read(MARKER)
            if image is None or image.mode != 0o600:
                raise ValueError("explicit B1 enrollment missing")
            self.enrollment = Enrollment.from_dict(decode_record(image.content))
            self.marker_image = image
            if self.root_identity() != self.enrollment.root_identity:
                raise ValueError("enrollment belongs to another root")
        except (OSError, ValueError):
            os.close(self.fd)
            raise ValueError("invalid explicit Ghostty simulation enrollment") from None

    def check_enrollment(self):
        if self.read(MARKER) != self.marker_image:
            raise ValueError("simulation enrollment changed")
        for key in ("source", "hook"):
            if self.fingerprint(PATHS[key]) != self.enrollment.fingerprints[key]:
                raise ValueError("chezmoi source or deployed hook drift; refusing simulation")

    def missing_output_dirs(self):
        """Inspect each actual prospective output directory without creating probes."""
        missing = []
        for relative in ("config/panda", "config/panda/generated", "state/panda-ghostty-simulation"):
            self.check_pins()
            current = os.dup(self.fd)
            try:
                parts = relative.split("/")
                for index, part in enumerate(parts):
                    child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current)
                    os.close(current)
                    current = child
                    _directory(os.fstat(current))
                    prefix = "/".join(parts[:index+1])
                    identity = self._identity(current)
                    if prefix in self.pins and self.pins[prefix] != identity:
                        raise ValueError("prospective output parent replaced")
                    self.pins[prefix] = identity
            except FileNotFoundError:
                missing.append(relative)
            except OSError:
                raise ValueError("unsafe prospective output directory") from None
            finally:
                os.close(current)
        return tuple(missing)

    def directory_image(self, relative):
        if relative not in CLEANUP_DIRS:
            raise ValueError("directory outside cleanup capability")
        self.check_pins()
        current = os.dup(self.fd)
        try:
            for part in relative.split("/"):
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current)
                os.close(current)
                current = child
                _directory(os.fstat(current))
            return self._directory_image(current)
        except FileNotFoundError:
            return None
        finally:
            os.close(current)

    def records_for(self, planned):
        return directory_records([{"path": path, "identity": self.created.get(path)}
                                  for path in CLEANUP_DIRS if path in planned])

    def updated_records(self, records):
        return directory_records([{"path": r["path"],
                                   "identity": self.created.get(r["path"], r["identity"])}
                                  for r in directory_records(records)])

    def check_directories(self, records, *, completed=False):
        for record in directory_records(records):
            current = self.directory_image(record["path"])
            if current is not None and (completed or record["identity"] is None or
                                        current != record["identity"]):
                raise ValueError("directory provenance changed or unknown; manual review required")

    def track_directories(self, records):
        self.check_directories(records)
        for record in directory_records(records):
            if record["identity"] is not None:
                self.created[record["path"]] = dict(record["identity"])

    def sync_restoration(self, records):
        """Retry completed cleanup/journal durability without changing the tree."""
        parents = [r["path"].rsplit("/", 1)[0] for r in reversed(directory_records(records))]
        parents.extend(("config", JOURNAL.rsplit("/", 1)[0]))
        for relative in dict.fromkeys(parents):
            self.check_pins()
            current = os.dup(self.fd)
            try:
                for part in relative.split("/"):
                    try:
                        child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current)
                    except FileNotFoundError:
                        break  # Sync the nearest existing ancestor of the removed parent.
                    os.close(current)
                    current = child
                    _directory(os.fstat(current))
                os.fsync(current)
                self.check_pins()
            finally:
                os.close(current)

    def replace(self, relative, image, *, expected):
        if relative not in WRITABLE:
            raise ValueError("destination outside simulation write capability")
        if relative == JOURNAL and image is not None:
            # Journals contain several bounded images; each is independently validated by the consumer.
            if len(image.content) > 1024*1024:
                raise ValueError("journal too large")
            validate_image(FileImage(b"", image.mode, image.mtime_ns, image.atime_ns))
        else:
            validate_image(image)
        self.check_pins()
        if self.read(MARKER) != self.marker_image:
            raise ValueError("enrollment changed during transaction")
        if self.read(relative) != expected:
            raise ValueError("stale expected image; external edit preserved")
        parent, name = self.parent(relative, create=image is not None)
        parent_path = relative.rsplit("/", 1)[0]
        temporary = ".panda-b1-" + uuid.uuid4().hex
        mutated = False
        try:
            self._check_created(parent_path, parent)
            if image is not None:
                fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
                mutated = True
                with os.fdopen(fd, "wb") as handle:
                    handle.write(image.content)
                    handle.flush()
                    os.fchmod(handle.fileno(), image.mode)
                    os.utime(handle.fileno(), ns=(image.atime_ns, image.mtime_ns))
                    os.fsync(handle.fileno())
            self.check_pins()
            if self.read(relative) != expected:
                raise ValueError("destination changed during staging")
            if image is None:
                os.unlink(name, dir_fd=parent)
                mutated = True
            else:
                os.replace(temporary, name, src_dir_fd=parent, dst_dir_fd=parent)
            os.fsync(parent)
        finally:
            try:
                try:
                    os.unlink(temporary, dir_fd=parent)
                except FileNotFoundError:
                    pass
                if mutated:
                    self._refresh_created(parent_path, parent)
            finally:
                os.close(parent)

    def remove_empty_dirs(self, directories):
        for record in reversed(directory_records(directories)):
            relative = record["path"]
            expected = self.created.get(relative, record["identity"])
            current = self.directory_image(relative)
            if current is not None and (expected is None or current != expected):
                raise ValueError("unverified or modified directory preserved")
            if expected is None:
                continue  # No directory was created or proven; absence requires no cleanup.
            parent_path, name = relative.rsplit("/", 1)
            parent = os.dup(self.fd)
            try:
                self.check_pins()
                for part in parent_path.split("/"):
                    child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                    os.close(parent)
                    parent = child
                self._check_created(parent_path, parent)
                try:
                    os.rmdir(name, dir_fd=parent)
                    self.pins.pop(relative, None)
                except FileNotFoundError:
                    self.pins.pop(relative, None)
                except OSError as error:
                    if error.errno in (errno.ENOTEMPTY, errno.EEXIST):
                        raise ValueError("populated directory preserved; cleanup incomplete") from None
                    raise
                finally:
                    self._refresh_created(parent_path, parent, notify=False)
                os.fsync(parent)  # Also retries durability after an earlier removal/fsync failure.
            except FileNotFoundError:
                pass  # The directory and its parent are already absent.
            finally:
                os.close(parent)
