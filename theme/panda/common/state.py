"""Validated reads of the four-field state contract. Phase 2 never writes state."""

from dataclasses import dataclass
import os
from pathlib import Path
import stat
import tomllib

from palette import PaletteError, resolve_slug


class StateError(ValueError):
    """Invalid or unsafe existing state; leave it intact for user review."""


def _canonical(value: object, field: str, *, allow_empty: bool = False) -> None:
    if allow_empty and value == "":
        return
    try:
        if resolve_slug(value) == value:
            return
    except PaletteError:
        pass
    raise StateError(f"{field} must be a canonical theme slug" +
                     (" or an empty string" if allow_empty else ""))


@dataclass(frozen=True)
class ThemeState:
    mode: str
    active: str
    last_manual: str
    context: str

    def __post_init__(self):
        if self.mode not in ("auto", "manual"):
            raise StateError("mode must be auto or manual")
        _canonical(self.active, "active")
        _canonical(self.last_manual, "last_manual", allow_empty=True)
        if not isinstance(self.context, str) or any(
                ord(c) < 32 or ord(c) == 127 for c in self.context):
            raise StateError("context must be plain text without control characters")


def read_state(path: Path) -> ThemeState | None:
    """Read a regular file, refusing symlinks in every path component.

    Directory-relative no-follow opens prevent symlink races. A missing file or
    parent returns None; conflicting paths, malformed/unsupported state and read
    errors are diagnostics. No directories, locks, caches or files are created.
    """
    path = Path(path)
    if ".." in path.parts or not path.name:
        raise StateError("state path must name a file without parent (..) traversal")
    path = Path(os.path.abspath(path))
    directory_fd = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in path.parts[1:-1]:
            child_fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                               dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = child_fd
        file_fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                          dir_fd=directory_fd)
        with os.fdopen(file_fd, "rb") as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise StateError("state must be a regular file; review the conflicting path")
            content = handle.read(65537)
            if len(content) > 65536:
                raise StateError("state exceeds the 64 KiB read limit; review it manually")
        try:
            data = tomllib.loads(content.decode("utf-8"))
        except (ValueError, RecursionError) as error:
            raise StateError("cannot parse state TOML; review malformed or excessively nested "
                             "values without overwriting the file") from error
        if set(data) != {"mode", "active", "last_manual", "context"}:
            raise StateError("state requires exactly mode, active, last_manual and context; "
                             "review unsupported fields without overwriting the file")
        return ThemeState(**data)
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
        raise StateError("cannot read state safely; check TOML, permissions and path conflicts "
                         "(symlinks are unsupported); existing state was left unchanged") from error
    finally:
        os.close(directory_fd)
