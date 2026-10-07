"""Strict Phase 1 manifest schema and opaque-sRGB contrast validation.

Python 3.11+ standard library only. Reads manifests; never applies a theme,
generates application configuration, or writes runtime state.
"""

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
import sys
import tomllib
from types import MappingProxyType
from typing import Mapping


IDENTITIES = {
    "minimal": "Panda Minimal",
    "cyber": "Panda Cyber",
    "gothic": "Panda Gothic",
    "hybrid": "Panda Hybrid",
    "pandawave": "PandaWave Pulse",
}
ROLES = frozenset(
    "background surface surface2 text muted primary secondary success warning "
    "error border focus selection accent_text on_primary on_secondary on_selection".split()
)
FIELDS = frozenset(("schema_version", "name", "slug", "aliases", "palette"))
BASES = ("background", "surface", "surface2")
HEX = re.compile(r"#[0-9a-fA-F]{6}")


class PaletteError(ValueError):
    """A malformed manifest, family, or color."""


@dataclass(frozen=True)
class Theme:
    name: str
    slug: str
    aliases: tuple[str, ...]
    palette: Mapping[str, str]


@dataclass(frozen=True)
class ContrastCheck:
    foreground: str
    background: str
    ratio: float
    minimum: float
    criterion: str
    required: bool = True

    @property
    def passes(self) -> bool:
        # Only display rounds. WCAG thresholds use the full computed value.
        return self.ratio >= self.minimum


def resolve_slug(value: str) -> str:
    if value == "wave":
        return "pandawave"
    if not isinstance(value, str) or value not in IDENTITIES:
        raise PaletteError("unknown theme slug")
    return value


def validate_manifest(data: object, directory: str) -> Theme:
    if not isinstance(data, dict) or set(data) != FIELDS:
        raise PaletteError("expected exactly schema_version, name, slug, aliases, palette")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise PaletteError("schema_version must be integer 1")
    if directory not in IDENTITIES or data["slug"] != directory:
        raise PaletteError("canonical slug must match a known theme directory")
    if data["name"] != IDENTITIES[directory]:
        raise PaletteError("name must match the approved flavor name")
    aliases = ["wave"] if directory == "pandawave" else []
    if data["aliases"] != aliases:
        raise PaletteError("only pandawave has an alias: [\"wave\"]")
    palette = data["palette"]
    if not isinstance(palette, dict) or set(palette) != ROLES:
        raise PaletteError("palette must contain exactly the documented semantic roles")
    for role, color in palette.items():
        if not isinstance(color, str) or HEX.fullmatch(color) is None:
            raise PaletteError(f"palette.{role} must be opaque sRGB #RRGGBB")
    return Theme(data["name"], directory, tuple(aliases), MappingProxyType(dict(palette)))


def load_theme(path: Path) -> Theme:
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
        return validate_manifest(data, path.parent.name)
    except (OSError, ValueError) as error:
        raise PaletteError(f"{path}: {error}") from error


def load_family(root: Path) -> dict[str, Theme]:
    expected = {root / slug / "theme.toml" for slug in IDENTITIES}
    actual = set(root.glob("*/theme.toml"))
    if actual != expected:
        missing = sorted(str(p.relative_to(root)) for p in expected - actual)
        extra = sorted(str(p.relative_to(root)) for p in actual - expected)
        raise PaletteError(f"theme family mismatch; missing={missing}, extra={extra}")
    return {slug: load_theme(root / slug / "theme.toml") for slug in IDENTITIES}


def luminance(color: str) -> float:
    if not isinstance(color, str) or HEX.fullmatch(color) is None:
        raise PaletteError("contrast input must be opaque sRGB #RRGGBB")
    channels = (int(color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
              for c in channels]
    return sum(c * weight for c, weight in zip(linear, (0.2126, 0.7152, 0.0722)))


def contrast_ratio(foreground: str, background: str) -> float:
    lower, higher = sorted((luminance(foreground), luminance(background)))
    return (higher + 0.05) / (lower + 0.05)


def contrast_checks(theme: Theme) -> list[ContrastCheck]:
    pairs = []
    for background in BASES:
        for foreground in ("text", "muted", "accent_text", "success", "warning", "error"):
            pairs.append((foreground, background, 4.5, "1.4.3", True))
        for foreground in ("border", "focus"):
            pairs.append((foreground, background, 3.0, "1.4.11", True))
        # Brand fills are not text or standalone boundaries. Gothic deliberately
        # needs its separate border and accent_text roles; keep this visible.
        for foreground in ("primary", "secondary"):
            pairs.append((foreground, background, 3.0, "fill visibility advisory", False))
    for foreground, background in (("on_primary", "primary"), ("on_secondary", "secondary"),
                                   ("on_selection", "selection")):
        pairs.append((foreground, background, 4.5, "1.4.3", True))
    pairs.append(("focus", "selection", 3.0, "1.4.11", True))
    return [ContrastCheck(fg, bg, contrast_ratio(theme.palette[fg], theme.palette[bg]),
                          minimum, criterion, required)
            for fg, bg, minimum, criterion, required in pairs]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, nargs="?", default=Path(__file__).resolve().parents[1])
    parser.add_argument("--json", action="store_true", help="print every measured pair")
    args = parser.parse_args()
    try:
        family = load_family(args.root)
    except PaletteError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    report = {slug: contrast_checks(theme) for slug, theme in family.items()}
    failed = any(c.required and not c.passes for checks in report.values() for c in checks)
    if args.json:
        print(json.dumps({slug: [{**asdict(c), "passes": c.passes} for c in checks]
                          for slug, checks in report.items()}, indent=2))
    else:
        print("Opaque sRGB / WCAG 2.2: text >= 4.5:1; controls >= 3:1")
        for slug, checks in report.items():
            required = [c for c in checks if c.required]
            passed = sum(c.passes for c in required)
            print(f"{slug}: {passed}/{len(required)} required pairs pass")
            for c in checks:
                if not c.passes:
                    label = "FAIL" if c.required else "ADVISORY"
                    print(f"  {label} {c.foreground}/{c.background}: {c.ratio:.6f}:1 "
                          f"(minimum {c.minimum}:1; {c.criterion})")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
