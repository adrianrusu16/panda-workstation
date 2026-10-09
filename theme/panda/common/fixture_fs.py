"""Linux fixture-only I/O. Directory-relative no-follow opens; no home fallback."""

from dataclasses import dataclass, field
import os
from pathlib import Path
import stat
import time
import uuid

MARKER = ".panda-theme-fixture.json"
ENROLLMENT = b'{"schema_version":1,"purpose":"panda-theme-phase3a"}\n'
FILENAMES = {
    "ghostty": "ghostty.conf", "kitty": "kitty.conf", "konsole": "konsole.colorscheme",
    "starship": "starship.toml", "fastfetch": "fastfetch.json", "fish": "fish.fish",
}
MANAGED = frozenset("config/panda/generated/" + name for name in FILENAMES.values()) | {
    "config/panda/theme-state.toml", "config/panda/theme-decision.toml",
    "config/panda/managed-files.json",
}
WRITABLE = MANAGED | {"state/panda-transactions/journal.json", "state/panda-transactions/lock"} | {
    "state/render/" + name for name in FILENAMES.values()
}
LIMIT = 1024 * 1024


class FixtureError(ValueError):
    """Unsafe fixture, ownership conflict, or stale filesystem state."""


@dataclass(frozen=True)
class FileImage:
    content: bytes
    mode: int
    mtime_ns: int
    atime_ns: int = field(compare=False)


def _directory(info, *, root=False):
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or info.st_mode & 0o022 or info.st_mode & 0o700 != 0o700
            or (root and stat.S_IMODE(info.st_mode) != 0o700)):
        raise FixtureError("fixture directories must be owned, writable and not group/world writable")


def _root_path(root):
    root = Path(root)
    if (not root.is_absolute() or ".." in root.parts or root.parent != Path("/tmp")
            or not root.name.startswith("panda-theme-fixture-")):
        raise FixtureError("Phase 3A requires an explicit /tmp/panda-theme-fixture-* directory")
    return root


def initialize_fixture(root: Path) -> None:
    """Enroll an existing private temporary directory; never create a live root."""
    root = _root_path(root)
    tmp_fd = os.open("/tmp", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        root_fd = os.open(root.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=tmp_fd)
        try:
            _directory(os.fstat(root_fd), root=True)
            try:
                marker_fd = os.open(MARKER, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                    0o600, dir_fd=root_fd)
            except FileExistsError:
                with FixtureFS(root):
                    return
            with os.fdopen(marker_fd, "wb") as handle:
                handle.write(ENROLLMENT)
                handle.flush()
                os.fsync(handle.fileno())
            os.fsync(root_fd)
        finally:
            os.close(root_fd)
    except OSError as error:
        raise FixtureError("cannot enroll fixture safely; existing paths were not replaced") from error
    finally:
        os.close(tmp_fd)


class FixtureFS:
    def __init__(self, root):
        self.root = _root_path(root)
        self.fd = None
        self.created = []
        try:
            self.fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            _directory(os.fstat(self.fd), root=True)
            marker_fd = os.open(MARKER, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.fd)
            with os.fdopen(marker_fd, "rb") as handle:
                info = os.fstat(handle.fileno())
                if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or
                        info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600 or
                        handle.read(256) != ENROLLMENT):
                    raise FixtureError("invalid fixture enrollment marker")
        except (OSError, ValueError) as error:
            if self.fd is not None:
                os.close(self.fd)
                self.fd = None
            raise FixtureError("Phase 3A requires an enrolled private temporary fixture") from error

    def __enter__(self):
        return self

    def __exit__(self, *_):
        os.close(self.fd)

    def _check_root(self):
        fresh = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            _directory(os.fstat(fresh), root=True)
            old, new = os.fstat(self.fd), os.fstat(fresh)
            if (old.st_dev, old.st_ino) != (new.st_dev, new.st_ino):
                raise FixtureError("fixture root was replaced")
        finally:
            os.close(fresh)

    @staticmethod
    def parts(relative):
        if (not isinstance(relative, str) or not relative or relative.startswith("/") or
                any(part in ("", ".", "..") for part in relative.split("/")) or
                relative.split("/")[0] not in ("config", "state")):
            raise FixtureError("fixture path must be relative without traversal")
        return relative.split("/")

    def parent(self, relative, *, create=False):
        parts = self.parts(relative)
        self._check_root()
        directory_fd = os.dup(self.fd)
        try:
            for index, component in enumerate(parts[:-1]):
                try:
                    child_fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                       dir_fd=directory_fd)
                except FileNotFoundError:
                    if not create:
                        raise
                    os.mkdir(component, 0o700, dir_fd=directory_fd)
                    self.created.append("/".join(parts[:index + 1]))
                    os.fsync(directory_fd)
                    child_fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                       dir_fd=directory_fd)
                try:
                    _directory(os.fstat(child_fd))
                except BaseException:
                    os.close(child_fd)
                    raise
                os.close(directory_fd)
                directory_fd = child_fd
            return directory_fd, parts[-1]
        except BaseException:
            os.close(directory_fd)
            raise

    def read(self, relative):
        directory_fd = None
        limit = LIMIT if relative == "state/panda-transactions/journal.json" else 65536
        try:
            directory_fd, name = self.parent(relative)
            file_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_NOATIME,
                              dir_fd=directory_fd)
            with os.fdopen(file_fd, "rb") as handle:
                info = os.fstat(handle.fileno())
                if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or
                        info.st_uid != os.getuid() or not info.st_mode & 0o400 or
                        info.st_size > limit):
                    raise FixtureError("managed file must be a readable, singly linked owned regular file")
                content = handle.read(limit + 1)
                if len(content) > limit:
                    raise FixtureError("managed file exceeds fixture read limit")
                return FileImage(content, stat.S_IMODE(info.st_mode), info.st_mtime_ns, info.st_atime_ns)
        except FileNotFoundError:
            return None
        except OSError as error:
            raise FixtureError("unsafe or unreadable fixture path (symlinks are rejected)") from error
        finally:
            if directory_fd is not None:
                os.close(directory_fd)

    def replace(self, relative, image, *, expected):
        """Compare before replace, fsync a same-directory temp and rename it."""
        if relative not in WRITABLE:
            raise FixtureError("destination is outside explicitly managed boundaries")
        if self.read(relative) != expected:
            raise FixtureError("stale plan or external modification; refusing replacement")
        if expected is not None and not expected.mode & 0o200:
            raise FixtureError("managed destination is read-only")
        directory_fd, name = self.parent(relative, create=image is not None)
        temporary = ".panda-" + uuid.uuid4().hex
        try:
            if image is None:
                os.unlink(name, dir_fd=directory_fd)
            else:
                file_fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                  0o600, dir_fd=directory_fd)
                with os.fdopen(file_fd, "wb") as handle:
                    handle.write(image.content)
                    handle.flush()
                    os.fchmod(handle.fileno(), image.mode)
                    os.utime(handle.fileno(), ns=(image.atime_ns, image.mtime_ns))
                    os.fsync(handle.fileno())
                # Repeat validation after staging. Held descriptors prevent following a
                # swapped symlink, but cooperative locking cannot exclude hostile peers.
                if self.read(relative) != expected:
                    raise FixtureError("destination changed during preparation")
                self._check_root()
                os.replace(temporary, name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
            os.fsync(directory_fd)
        finally:
            try:
                os.unlink(temporary, dir_fd=directory_fd)
            except FileNotFoundError:
                pass
            os.close(directory_fd)

    def remove_empty_dirs(self, directories):
        for relative in reversed(directories):
            directory_fd = None
            try:
                directory_fd, name = self.parent(relative)
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory_fd)
                os.close(child)
                os.rmdir(name, dir_fd=directory_fd)
                os.fsync(directory_fd)
            except FileNotFoundError:
                pass
            except OSError:
                # A directory with later/unrelated content belongs to its user.
                pass
            finally:
                if directory_fd is not None:
                    os.close(directory_fd)


def new_image(content, mode=0o600):
    stamp = time.time_ns()
    return FileImage(content, mode, stamp, stamp)
