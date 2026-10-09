"""Deterministic native fragments for Phase 3A; no application enrollment."""

import configparser
import io
import json
from pathlib import Path
from string import Template
import tomllib

from fixture_fs import FILENAMES, FixtureError, FixtureFS, new_image
from palette import Theme, ROLES, HEX, contrast_checks, load_family

COMPONENTS = tuple(FILENAMES)
TEMPLATES = Path(__file__).parent / "templates"


def ansi_roles():
    data = tomllib.loads((TEMPLATES / "terminal/roles.toml").read_text())["ansi"]
    roles = {int(key): value for key, value in data.items()}
    if set(roles) != set(range(16)) or any(role not in ROLES for role in roles.values()):
        raise ValueError("invalid shared ANSI-role mapping")
    return roles


def render_bytes(component: str, theme: Theme) -> bytes:
    if component not in COMPONENTS:
        raise ValueError("unsupported Phase 3A component")
    if (not isinstance(theme, Theme) or set(theme.palette) != ROLES or
            any(not isinstance(color, str) or not HEX.fullmatch(color) for color in theme.palette.values()) or
            any(check.required and not check.passes for check in contrast_checks(theme))):
        raise ValueError("invalid canonical opaque palette")
    colors = theme.palette
    if component in ("ghostty", "kitty", "fish"):
        content = Template((TEMPLATES / component / "theme.tmpl").read_text()).substitute(colors)
        if component in ("ghostty", "kitty"):
            content += "".join((f"palette = {index}={colors[role]}\n" if component == "ghostty" else
                                f"color{index} {colors[role]}\n") for index, role in ansi_roles().items())
    elif component == "konsole":
        parser = configparser.ConfigParser()
        parser.optionxform = str
        parser["General"] = {"Description": theme.name, "Opacity": "1"}
        rgb = lambda color: ",".join(str(int(color[index:index + 2], 16)) for index in (1, 3, 5))
        parser["Background"] = {"Color": rgb(colors["background"])}
        parser["Foreground"] = {"Color": rgb(colors["text"])}
        for index, role in ansi_roles().items():
            group = f"Color{index % 8}" + ("Intense" if index >= 8 else "")
            parser[group] = {"Color": rgb(colors[role])}
        output = io.StringIO()
        parser.write(output)
        content = output.getvalue()
    elif component == "starship":
        # Palette fragment only: no prompt structure, modules or timings replaced.
        content = 'palette = "panda"\n\n[palettes.panda]\n' + "".join(
            f'{name} = "{colors[role]}"\n' for name, role in {
                "text": "text", "muted": "muted", "accent": "accent_text", "success": "success",
                "warning": "warning", "error": "error", "selection": "selection",
                "on_selection": "on_selection", "primary": "primary", "on_primary": "on_primary",
            }.items())
    else:
        content = json.dumps({"display": {"color": {"keys": colors["accent_text"],
                                                     "title": colors["text"]}}}, indent=2) + "\n"
    return content.encode("utf-8")


def validate_rendered(component, content, theme):
    """Check native structure and exact deterministic fragment, not app runtime."""
    text = content.decode("utf-8")
    if component == "starship":
        tomllib.loads(text)
    elif component == "fastfetch":
        json.loads(text)
    elif component == "konsole":
        parser = configparser.ConfigParser()
        try:
            parser.read_string(text)
        except configparser.Error as error:
            raise ValueError("invalid Konsole native structure") from error
    if content != render_bytes(component, theme):
        raise ValueError("rendered fragment failed canonical native-structure validation")


def render_component(component: str, theme: Theme, destination: Path) -> list[Path]:
    """Explicit standalone staging entry, restricted to fixture/state/render."""
    destination = Path(destination)
    if destination.name != "render" or destination.parent.name != "state":
        raise FixtureError("renderer destination must be fixture/state/render")
    content = render_bytes(component, theme)
    validate_rendered(component, content, theme)
    relative = "state/render/" + FILENAMES[component]
    with FixtureFS(destination.parent.parent) as fs:
        before = fs.read(relative)
        if before is not None and before.content not in {
                render_bytes(component, existing) for existing in load_family(Path(__file__).parent.parent).values()}:
            raise FixtureError("unowned staging content; refusing replacement")
        if before is None or before.content != content:
            fs.replace(relative, new_image(content, before.mode if before else 0o600), expected=before)
    return [destination / FILENAMES[component]]
