"""Reusable opaque semantic style rules; no desktop or theme-manager effects."""
from pathlib import Path
import tomllib

from desktop_io import read_regular
from desktop_layout import fields
from palette import contrast_ratio

SPEC = Path(__file__).parent / "desktop/visual.toml"
TYPE = dict(label=13, body=14, title=16, clock_compact=38, clock_expanded=44,
            value_compact=24, value_expanded=28)
TOKENS = dict(panel="surface", track="surface2", content="text", label="muted",
              graph="accent_text", boundary="border", focus="focus")


def validate_spec(spec):
    fields(spec, ("schema_version", "radius", "font", "padding", "type", "tokens"), "visual specification")
    if type(spec["schema_version"]) is not int or spec["schema_version"] != 1:
        raise ValueError("visual schema_version must be integer 1")
    if type(spec["radius"]) is not int or spec["radius"] != 12 or spec["font"] != "Noto Sans":
        raise ValueError("reviewed radius/font required")
    for key, expected in (("padding", dict(compact=12, expanded=16)),
                          ("type", TYPE), ("tokens", TOKENS)):
        fields(spec[key], expected, key)
        if spec[key] != expected or any(type(spec[key][k]) is not type(v) for k, v in expected.items()):
            raise ValueError("only reviewed semantic styling values are supported")
    return spec


def load_spec():
    return validate_spec(tomllib.loads(read_regular(SPEC).decode()))


def contrast_report(palette):
    def check(fg, bg, minimum):
        ratio = contrast_ratio(palette[fg], palette[bg])
        return dict(foreground=fg, background=bg, ratio=ratio, minimum=minimum, **{"pass": ratio >= minimum})
    used = [check(fg, bg, 4.5) for fg in ("text", "muted", "accent_text")
            for bg in ("surface", "surface2")]
    used += [check(fg, bg, 3) for fg in ("border", "focus", "accent_text")
             for bg in ("surface", "surface2")]
    used += [check("on_selection", "selection", 4.5)]
    # These unchosen pairings document why brand fill is not a universal graph/text color.
    candidates = [check("primary", "surface", 3), check("secondary", "surface", 3)]
    return dict(used=used, candidates=candidates)
