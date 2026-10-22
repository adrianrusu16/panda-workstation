"""Bounded reads for explicit offline inputs; never follows the final symlink."""
import os
from pathlib import Path
import stat


def read_regular(path: Path, limit=1024 * 1024) -> bytes:
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_NOATIME
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            raise ValueError("input must be a regular file no larger than 1 MiB")
        chunks, total = [], 0
        while True:
            block = os.read(fd, min(65536, limit + 1 - total))
            if not block:
                break
            chunks.append(block)
            total += len(block)
            if total > limit:
                raise ValueError("input exceeds size limit")
        after = os.fstat(fd)
        binding = os.stat(path, follow_symlinks=False)
        fields = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink",
                  "st_size", "st_atime_ns", "st_mtime_ns", "st_ctime_ns")
        initial = tuple(getattr(before, key) for key in fields)
        if initial != tuple(getattr(after, key) for key in fields) or initial != tuple(
                getattr(binding, key) for key in fields) or total != before.st_size:
            raise ValueError("input changed while reading")
        return b"".join(chunks)
    finally:
        os.close(fd)
