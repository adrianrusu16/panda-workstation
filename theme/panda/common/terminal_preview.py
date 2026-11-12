"""Generate the five V2 terminal and shell samples in a private /tmp preview."""

import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--palette-version", choices=("v2",), required=True)
    parser.add_argument("--validate", action="store_true", help="run installed Ghostty's native parser")
    args = parser.parse_args(argv)

    from ghostty_preview import V2_GHOSTTY_CONFIG, preview_files, validate_profiles
    from palette import load_family

    directory = None
    try:
        family = load_family(Path(__file__).resolve().parent.parent, palette_version=args.palette_version)
        files = preview_files(family, palette_version=args.palette_version)
        if args.validate and shutil.which("ghostty") is None:
            raise ValueError("Ghostty is unavailable for native parser validation")
        directory = Path(tempfile.mkdtemp(prefix="panda-terminal-v2-preview-", dir="/tmp"))
        for relative, data in files.items():
            path = directory / relative
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(data)
        if args.validate:
            validate_profiles(directory, family, config_name=V2_GHOSTTY_CONFIG)
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        print(f"V2 terminal preview failed: {error}", file=sys.stderr)
        if directory is not None:
            shutil.rmtree(directory)
        return 1
    print(directory)
    return 0


if __name__ == "__main__":
    # Keep direct CLI invocations from creating bytecode in the checkout.
    sys.dont_write_bytecode = True
    raise SystemExit(main())
