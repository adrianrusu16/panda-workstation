"""Ghostty 1.3.1 include and refresh model; never launches or reloads Ghostty."""

import posixpath
import re

from adapters.base import Outcome
from enrollment import PATHS
from render import render_bytes, validate_rendered

HOOK_LINE = b"config-file = ?../panda/generated/ghostty.conf\n"


def _lines(content):
    if not isinstance(content, bytes) or len(content) > 65536:
        raise ValueError("bounded Ghostty configuration bytes required")
    try:
        text = content.decode("utf-8")
    except UnicodeError:
        raise ValueError("unsupported Ghostty configuration encoding") from None
    if any(ord(c) < 32 and c not in "\n\t" for c in text):
        raise ValueError("unsupported Ghostty configuration controls")
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = re.fullmatch(r"\s*([a-z][a-z0-9-]*)\s*=\s*(.*?)\s*", line)
        if match is None:
            raise ValueError("unsupported Ghostty configuration line")
        yield match.groups()


def resolve_hook(hook_path):
    if hook_path != PATHS["hook"]:
        raise ValueError("unexpected Ghostty include entry point")
    return posixpath.normpath(posixpath.join(posixpath.dirname(hook_path), "../panda/generated/ghostty.conf"))


def model_hook(baseline):
    """Propose an appended optional include without writing source or destination."""
    if not baseline or not baseline.endswith(b"\n"):
        raise ValueError("baseline must end in newline; no implicit rewriting")
    if any(key in ("config-file", "theme") for key, _ in _lines(baseline)):
        raise ValueError("existing include/theme requires separate precedence review")
    if len(baseline) + len(HOOK_LINE) > 65536:
        raise ValueError("modeled include exceeds configuration limit")
    return baseline + HOOK_LINE


def effective_model(config, fragment):
    """Subset model: included values load last; missing optional fragment is ignored.

    Native documentation: /usr/share/ghostty/doc/ghostty.5.md, config-file.
    This scalar/ANSI model is not Ghostty's complete parser or runtime.
    """
    pairs = list(_lines(config))
    includes = [value for key, value in pairs if key == "config-file"]
    if includes != ["?../panda/generated/ghostty.conf"]:
        raise ValueError("expected one exact optional Panda include")
    effective = {key if key != "palette" else "palette:" + value.split("=", 1)[0]: value
                 for key, value in pairs if key != "config-file"}
    if fragment is not None:
        for key, value in _lines(fragment):
            if key in ("config-file", "theme"):
                raise ValueError("generated fragment may not load external configuration")
            effective[key if key != "palette" else "palette:" + value.split("=", 1)[0]] = value
    return effective


class GhosttyModel:
    def prepare(self, theme):
        content = render_bytes("ghostty", theme)
        validate_rendered("ghostty", content, theme)
        return content

    def verify(self, fs, prepared):
        current = fs.read(PATHS["target"])
        return Outcome(current is not None and current.content == prepared, "Ghostty fixture bytes checked")

    def refresh(self):
        return Outcome(True, "Ghostty refresh modeled only; native parser/reload and Wayland appearance unverified")
