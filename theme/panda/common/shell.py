"""Read-only shell artwork and bounded health diagnostics; no automatic context."""

import argparse
from pathlib import Path
import platform
import shutil
import subprocess

SMALL = "Panda\n  ʕ ●ᴥ● ʔ\n"
BIG = "Panda\n  ▄██▄   ▄██▄\n █    █▄█    █\n █  ●     ●  █\n  █    ▼    █\n   ▀██▄▄▄██▀\n"


def _output(command):
    if shutil.which(command[0]) is None:
        return "unavailable"
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=3)
        # Avoid displaying arbitrary external errors/configuration values.
        return result.stdout.strip() if result.returncode == 0 else "unavailable"
    except (OSError, subprocess.TimeoutExpired):
        return "unavailable"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("panda", "panda-big", "panda-status"))
    parser.add_argument("--no-health", action="store_true", help="artwork/state only; no health commands")
    args = parser.parse_args(argv)
    if args.command != "panda-status":
        print(BIG if args.command == "panda-big" else SMALL, end="")
        print("palette: terminal inherited; live Panda integration unverified (Phase 3B)")
        if args.command == "panda" and not args.no_health:
            if shutil.which("fastfetch"):
                # Explicit preset-free output: do not load user executable custom modules.
                print(_output(["fastfetch", "--config", "none", "--logo", "none", "--structure", "OS:Kernel:Memory"]))
            else:
                print("Fastfetch: unavailable")
        return 0
    print("Panda status · read-only")
    from cli import main as theme_main
    code = theme_main(["status"])
    print(f"Kernel: {platform.release()}")
    print("GPU profile: unverified; no safety policy inferred from theme state")
    if not args.no_health:
        modules = _output(["lsmod"])
        print("NVIDIA modules: " + ("unavailable" if modules == "unavailable" else
                                    "loaded" if any(line.startswith("nvidia") for line in modules.splitlines())
                                    else "not observed; blacklist policy unverified"))
        gpu = _output(["lspci", "-mm"])
        print("GPU: " + ("unavailable" if gpu == "unavailable" else
                         " | ".join(line for line in gpu.splitlines() if any(
                             kind in line for kind in ("VGA compatible", "3D controller", "Display controller"))) or "unavailable"))
        failed = _output(["systemctl", "--failed", "--no-legend", "--plain", "--no-pager"])
        print("Failed system units: " + ("unavailable" if failed == "unavailable" else str(len(failed.splitlines()))))
        try:
            usage = shutil.disk_usage(Path.home())
            print(f"Disk/home usage: {usage.used * 100 // usage.total}% · physical disk health unverified")
        except OSError:
            print("Disk: unavailable")
        repo = Path(__file__).resolve().parents[3]
        git = _output(["git", "--no-optional-locks", "-C", str(repo), "status", "--porcelain"])
        print("Workstation Git: " + ("unavailable" if git == "unavailable" else "modified" if git else "clean"))
        print("Machine health: no hardware self-test performed")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
