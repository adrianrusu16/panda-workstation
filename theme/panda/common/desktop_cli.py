"""Panda Desktop D4A: explicit fixture reads and stdout-only planning."""
import argparse
import json
from pathlib import Path
import sys

from desktop_io import read_regular
from desktop_layout import ROOT, build_plan, load_config, validate_fixture
from desktop_packages import package_plan
from desktop_preview import render_svg


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError("non-finite JSON number")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", default="dry-run", choices=("dry-run", "validate", "preview", "packages", "clock-candidate"))
    parser.add_argument("--fixture", required=True, type=Path, help="explicit synthetic JSON fixture; no live discovery")
    parser.add_argument("--config", type=Path, default=ROOT / "theme/panda/common/desktop/layout.toml")
    parser.add_argument("--resolution", choices=("fhd", "qhd"))
    parser.add_argument("--scale", type=float, choices=(1, 1.25, 1.5))
    parser.add_argument("--presentation", choices=("compact", "expanded"))
    parser.add_argument("--flavor", choices=("minimal", "cyber", "gothic", "hybrid", "pandawave", "wave"), default="hybrid")
    parser.add_argument("--visual-fixture", type=Path, help="explicit synthetic presentation fixture for detailed offline SVG")
    parser.add_argument("--composition", action="store_true", help="Cyber-only offline wallpaper composition; no desktop application")
    parser.add_argument("--plasma-version", help="explicit upstream version claim for clock-candidate; not runtime discovery")
    parser.add_argument("--clock-schema", type=Path, help="explicit pinned clock XML source; never loaded as native code")
    args = parser.parse_args(argv)
    if (args.visual_fixture is not None and args.command != "preview") or (args.composition and args.visual_fixture is None):
        parser.error("visual inputs/composition require preview and an explicit --visual-fixture")
    if args.command == "clock-candidate":
        if (args.plasma_version is None or args.clock_schema is None or args.resolution is not None
                or args.scale is not None or args.presentation is not None):
            parser.error("clock-candidate requires --plasma-version and --clock-schema; layout overrides are unsupported")
    elif args.plasma_version is not None or args.clock_schema is not None:
        parser.error("clock source inputs require clock-candidate")
    try:
        fixture = json.loads(read_regular(args.fixture).decode("utf-8"), object_pairs_hook=unique_object, parse_constant=reject_constant)
        validate_fixture(fixture)
        config = load_config(args.config)
        if args.command == "clock-candidate":
            from desktop_clock_candidate import build_clock_candidate
            result = build_clock_candidate(config, fixture, plasma_version=args.plasma_version,
                        schema_xml=read_regular(args.clock_schema, limit=8192), flavor=args.flavor)
        elif args.command == "packages":
            result = package_plan(ROOT / "packages", fixture["installed_packages"])
        else:
            result = build_plan(config, fixture, resolution=args.resolution, scale=args.scale,
                                presentation=args.presentation or "compact", flavor=args.flavor)
            # A successful dry-run must also validate the full package manifest set.
            result["packages"] = package_plan(ROOT / "packages", fixture["installed_packages"])
        if args.command == "preview" and args.visual_fixture is not None:
            from desktop_visual_fixture import load_scene
            from desktop_visual import render_visual
            output, _ = render_visual(result, load_scene(args.visual_fixture), composition=args.composition)
        else:
            output = render_svg(result) if args.command == "preview" else json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n"
        print(output, end="")
        return 0
    except (OSError, ValueError, TypeError, RecursionError) as error:
        print(f"desktop: refused: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
