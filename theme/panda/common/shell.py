"""Read-only shell artwork and bounded health diagnostics; no automatic context."""

import argparse
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys

from palette import load_theme, resolve_slug, terminal_heading_roles
from state import StateError, read_state

SMALL = "  ʕ ●ᴥ● ʔ"
BIG = """  ▄██▄   ▄██▄
 █    █▄█    █
 █  ●     ●  █
  █    ▼    █
   ▀██▄▄▄██▀"""
TERMINAL_SEQUENCE = re.compile(
    r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|(?:\x1b\[|\x9b)[0-?]*[ -/]*[@-~]"
)
CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


def _output(command):
    if shutil.which(command[0]) is None:
        return "unavailable"
    try:
        result = subprocess.run(command, capture_output=True, text=True, errors="replace", timeout=3)
        # Render external diagnostics as plain text, even if a tool emits escapes.
        if result.returncode == 0:
            return CONTROL.sub("", TERMINAL_SEQUENCE.sub("", result.stdout)).strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return "unavailable"


def _palette(slug):
    if slug is None:
        from cli import state_path
        try:
            state = read_state(state_path())
        except StateError:
            state = None
        slug = state.active if state is not None else "minimal"
    return load_theme(Path(__file__).resolve().parent.parent / slug / "theme.toml")


def _supports_color():
    term = os.environ.get("TERM", "")
    return (sys.stdout.isatty() and "NO_COLOR" not in os.environ and
            term not in ("", "dumb") and
            (os.environ.get("COLORTERM", "").lower() in ("truecolor", "24bit") or
             term.endswith("-direct") or term in ("xterm-ghostty", "xterm-kitty")))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("panda", "panda-big", "panda-status"))
    parser.add_argument("--no-health", action="store_true", help="artwork/state only; no health commands")
    parser.add_argument("--theme", type=resolve_slug, help="style this output with a canonical flavor")
    parser.add_argument("--no-color", action="store_true", help="use plain text even in a color terminal")
    args = parser.parse_args(argv)

    theme = _palette(args.theme)
    colors = theme.palette
    use_color = not args.no_color and _supports_color()
    prominent, section = terminal_heading_roles(theme)

    def paint(text, role, *, bold=False):
        if not use_color:
            return text
        color = colors[role]
        rgb = ";".join(str(int(color[index:index + 2], 16)) for index in (1, 3, 5))
        weight = "1;" if bold else ""
        return f"\x1b[{weight}38;2;{rgb}m{text}\x1b[0m"

    def field(label, value, role="text"):
        print(paint(label, section, bold=True) + ": " + paint(value, role))

    if args.command != "panda-status":
        print(paint("Panda", prominent, bold=True))
        print(paint(BIG if args.command == "panda-big" else SMALL, "text"))
        print()
        field("Palette", theme.name + " · shell preview", "muted")
        if args.command == "panda" and not args.no_health:
            if shutil.which("fastfetch"):
                print()
                print(paint("System", section, bold=True))
                # Explicit preset-free output: do not load user executable custom modules.
                print(_output(["fastfetch", "--config", "none", "--logo", "none",
                               "--structure", "OS:Kernel:Memory", "--pipe", "true"]))
            else:
                field("Fastfetch", "unavailable", "muted")
        return 0
    print(paint("Panda status", prominent, bold=True) + " " + paint("· read-only", "muted"))
    print()
    print(paint("Theme state", section, bold=True))
    from cli import main as theme_main
    code = theme_main(["status"])
    print()
    print(paint("System", section, bold=True))
    field("Kernel", platform.release())
    field("GPU profile", "unverified; no safety policy inferred from theme state", "muted")
    if not args.no_health:
        modules = _output(["lsmod"])
        loaded = any(line.startswith("nvidia") for line in modules.splitlines())
        field("NVIDIA modules", "unavailable" if modules == "unavailable" else
              "loaded" if loaded else "not observed; blacklist policy unverified",
              "warning" if loaded else "muted")
        gpu = _output(["lspci", "-mm"])
        field("GPU", " | ".join(line for line in gpu.splitlines() if any(
              kind in line for kind in ("VGA compatible", "3D controller", "Display controller"))) or "unavailable")
        failed = _output(["systemctl", "--failed", "--no-legend", "--plain", "--no-pager"])
        field("Failed system units", "unavailable" if failed == "unavailable" else str(len(failed.splitlines())),
              "muted" if failed == "unavailable" else "warning" if failed else "success")
        try:
            usage = shutil.disk_usage(Path.home())
            field("Disk/home usage", f"{usage.used * 100 // usage.total}% · physical disk health unverified")
        except OSError:
            field("Disk", "unavailable", "muted")
        repo = Path(__file__).resolve().parents[3]
        git = _output(["git", "--no-optional-locks", "-C", str(repo), "status", "--porcelain"])
        field("Workstation Git", "unavailable" if git == "unavailable" else "modified" if git else "clean",
              "muted" if git == "unavailable" else "warning" if git else "success")
        field("Machine health", "no hardware self-test performed", "muted")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
