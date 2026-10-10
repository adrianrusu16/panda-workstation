"""Disposable B1 homes; never loads installed applications or shell startup."""

import os
from pathlib import Path
import tempfile
from unittest.mock import patch

COMMON = Path(__file__).resolve().parents[1] / "theme/panda/common"
BASE = b"font-size = 11.5\nbackground = #010203\ncursor-style = bar\n"


def fixture(test):
    temporary = tempfile.TemporaryDirectory(prefix="panda-theme-b1-", dir="/tmp")
    test.addCleanup(temporary.cleanup)
    root = Path(temporary.name)
    for directory in ("home", "config", "data", "state", "cache", "source"):
        (root / directory).mkdir(mode=0o700)
    environment = {"HOME": str(root / "home"), "PYTHONDONTWRITEBYTECODE": "1"}
    environment.update({"XDG_" + name.upper() + "_HOME": str(root / name)
                        for name in ("config", "data", "state", "cache")})
    test.enterContext(patch.dict(os.environ, environment))
    for name in ("config/ghostty/config.ghostty", "source/home/dot_config/ghostty/config.ghostty"):
        path = root / name
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        path.write_bytes(BASE)
    return root


def tree(root):
    result = {}
    for path in root.rglob("*"):
        info = path.lstat()
        result[str(path.relative_to(root))] = (
            info.st_mode, info.st_ino, info.st_mtime_ns,
            path.read_bytes() if path.is_file() and not path.is_symlink() else None,
        )
    return result
