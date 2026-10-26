"""Pure offline desktop intent. No Plasma APIs, subprocesses or config writes."""
import copy
import hashlib
import json
from pathlib import Path
import tomllib

from palette import IDENTITIES, resolve_slug, validate_manifest
from desktop_io import read_regular

ROOT = Path(__file__).resolve().parents[3]
ROLES = ("clock", "media", "weather", "cpu", "ram")
CATALOG = {
    "clock": ("org.kde.plasma.digitalclock", "plasma-workspace"),
    "media": ("org.kde.plasma.mediacontroller", "plasma-workspace"),
    "weather": ("org.kde.plasma.weather", "kdeplasma-addons"),
    "cpu": ("org.kde.plasma.systemmonitor.cpu", "plasma-workspace"),
    "ram": ("org.kde.plasma.systemmonitor.memory", "plasma-workspace"),
}
# Both reviewed faces are supplied by the already-required libksysguard package.
SENSOR_FACES = frozenset(("org.kde.ksysguard.linechart", "org.kde.ksysguard.horizontalbars"))
RESOLUTIONS = {"fhd": (1920, 1080), "qhd": (2560, 1440)}
SCALES = (1, 1.25, 1.5)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def fields(value, expected, label):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError(f"{label}: expected exactly {', '.join(expected)}")


def integer(value, label, minimum=1, maximum=16384):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{label}: integer {minimum}..{maximum} required")


def string(value, label, limit=240):
    if not isinstance(value, str) or not value or len(value) > limit or any(not (0x20 <= ord(c) <= 0xD7FF or 0xE000 <= ord(c) <= 0xFFFD or 0x10000 <= ord(c) <= 0x10FFFF) for c in value):
        raise ValueError(f"{label}: nonempty printable string required")


def unique_strings(value, label):
    if not isinstance(value, list):
        raise ValueError(f"{label}: list required")
    for text in value:
        string(text, label)
    if len(value) != len(set(value)):
        raise ValueError(f"{label}: duplicate entries")


def validate_config(config):
    fields(config, ("schema_version", "margin", "gap", "top_bar", "dock", "profiles", "widgets"), "layout")
    if type(config["schema_version"]) is not int or config["schema_version"] != 1:
        raise ValueError("layout schema_version must be integer 1")
    integer(config["margin"], "margin", 0, 128)
    integer(config["gap"], "gap", 0, 128)
    top, dock = config["top_bar"], config["dock"]
    fields(top, ("height", "length_mode", "alignment", "opacity", "roles"), "top_bar")
    integer(top["height"], "top_bar.height", 48, 48)
    if top != dict(height=48, length_mode="fill", alignment="center", opacity="opaque",
                   roles=["launcher", "workspaces", "system_tray", "clock"]):
        raise ValueError("top_bar must retain approved 48 logical-pixel opaque structure")
    fields(dock, ("height", "length_mode", "alignment", "floating", "bottom_clearance", "icon_size", "spacing", "padding", "plugin"), "dock")
    if (type(dock["height"]) is not int or dock["height"] != 56 or
            dock["length_mode"] != "fit" or dock["alignment"] != "center" or
            dock["plugin"] != "org.kde.plasma.icontasks"):
        raise ValueError("dock must retain centered 56 logical-pixel fit-content structure")
    if dock["floating"] is not True:
        raise ValueError("dock floating intent must be true")
    integer(dock["bottom_clearance"], "dock.bottom_clearance", 1, 32)
    integer(dock["icon_size"], "dock.icon_size", 16, 56)
    integer(dock["spacing"], "dock.spacing", 0, 32)
    integer(dock["padding"], "dock.padding", 0, 32)
    if dock["icon_size"] + 2 * dock["padding"] > dock["height"]:
        raise ValueError("dock icon and padding exceed height")
    fields(config["profiles"], ("compact", "expanded"), "profiles")
    for name, profile in config["profiles"].items():
        fields(profile, ("width", "heights"), f"profiles.{name}")
        integer(profile["width"], "card width", 160, 640)
        if not isinstance(profile["heights"], list) or len(profile["heights"]) != len(ROLES):
            raise ValueError("profile must have exactly five card heights")
        for height in profile["heights"]:
            integer(height, "card height", 48, 480)
    fields(config["widgets"], ROLES, "widgets")
    for role in ROLES:
        widget = config["widgets"][role]
        fields(widget, ("plugin", "package", "face"), f"widgets.{role}")
        if (widget["plugin"], widget["package"]) != CATALOG[role]:
            raise ValueError("only the reviewed official KDE widget catalog is supported")
        face = widget["face"]
        allowed = SENSOR_FACES if role in ("cpu", "ram") else ("",)
        if not isinstance(face, str) or face not in allowed:
            raise ValueError("unknown or unreviewed widget face")
    return config


def load_config(path):
    return validate_config(tomllib.loads(read_regular(Path(path)).decode("utf-8")))


def validate_fixture(fixture):
    fields(fixture, ("schema_version", "scope", "output", "desktop_id", "desktop_count",
                     "panels", "applets", "bindings", "applications", "installed_packages", "providers"), "fixture")
    if type(fixture["schema_version"]) is not int or fixture["schema_version"] != 1:
        raise ValueError("fixture schema_version must be integer 1")
    if fixture["scope"] != "panda-desktop-offline-fixture":
        raise ValueError("explicit synthetic fixture scope required")
    integer(fixture["desktop_id"], "desktop_id")
    integer(fixture["desktop_count"], "desktop_count", 1, 64)
    output = fixture["output"]
    fields(output, ("name", "width", "height", "scale"), "output")
    string(output["name"], "output name")
    integer(output["width"], "output width")
    integer(output["height"], "output height")
    if (output["width"], output["height"]) not in RESOLUTIONS.values():
        raise ValueError("only FHD/QHD fixture outputs supported")
    scale = output["scale"]
    if type(scale) not in (int, float) or scale not in SCALES:
        raise ValueError("scale must be 1, 1.25 or 1.5")
    if not isinstance(fixture["panels"], list) or not isinstance(fixture["applets"], list):
        raise ValueError("panels and applets must be lists")
    containments = {fixture["desktop_id"]}
    declared = {}
    for panel in fixture["panels"]:
        fields(panel, ("id", "applet_ids"), "panel")
        integer(panel["id"], "panel id")
        if panel["id"] in containments:
            raise ValueError("duplicate containment id")
        containments.add(panel["id"])
        if not isinstance(panel["applet_ids"], list):
            raise ValueError("panel applet_ids must be a list")
        for ident in panel["applet_ids"]:
            integer(ident, "panel applet id")
            if ident in declared:
                raise ValueError("duplicate panel applet reference")
            declared[ident] = panel["id"]
    applets = {}
    for applet in fixture["applets"]:
        fields(applet, ("id", "containment_id", "plugin", "geometry", "config"), "applet")
        integer(applet["id"], "applet id")
        integer(applet["containment_id"], "containment id")
        if applet["id"] in applets or applet["id"] in containments:
            raise ValueError("duplicate or colliding applet identity")
        if applet["containment_id"] not in containments:
            raise ValueError("unknown containment")
        string(applet["plugin"], "plugin")
        if not isinstance(applet["config"], dict):
            raise ValueError("opaque applet config must be an object")
        rect = applet["geometry"]
        if rect is not None:
            if not isinstance(rect, list) or len(rect) != 4 or any(
                    type(n) not in (int, float) or not 0 <= n <= 16384 for n in rect) or min(rect[:2]) < 0 or min(rect[2:]) <= 0:
                raise ValueError("invalid applet geometry")
        applets[applet["id"]] = applet
        if applet["containment_id"] != fixture["desktop_id"] and declared.get(applet["id"]) != applet["containment_id"]:
            raise ValueError("panel applet membership mismatch")
    for ident, parent in declared.items():
        if ident not in applets or applets[ident]["containment_id"] != parent:
            raise ValueError("dangling panel applet reference")
    fields(fixture["bindings"], ROLES, "bindings")
    bound = set()
    for role, ident in fixture["bindings"].items():
        if ident is None:
            if any(a["containment_id"] == fixture["desktop_id"] and a["plugin"] == CATALOG[role][0] for a in applets.values()):
                raise ValueError(f"explicit binding required for existing {role} instance")
            continue
        integer(ident, "binding id")
        if ident in bound or ident not in applets:
            raise ValueError("duplicate or missing binding")
        applet = applets[ident]
        if applet["containment_id"] != fixture["desktop_id"] or applet["plugin"] != CATALOG[role][0]:
            raise ValueError("binding has wrong plugin or containment")
        bound.add(ident)
    unique_strings(fixture["applications"], "applications")
    unique_strings(fixture["installed_packages"], "installed_packages")
    fields(fixture["providers"], ROLES, "providers")
    for value in fixture["providers"].values():
        string(value, "provider fixture label")
    # Reject non-JSON values even inside opaque preserved configuration.
    try:
        json.dumps(fixture, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ValueError("fixture must contain finite JSON values") from error
    return fixture


def load_desktop_family(root):
    expected = {root / slug / "theme.toml" for slug in IDENTITIES}
    if set(root.glob("*/theme.toml")) != expected:
        raise ValueError("canonical theme family is incomplete or contains unknown manifests")
    return {slug: validate_manifest(tomllib.loads(read_regular(root / slug / "theme.toml").decode("utf-8")), slug)
            for slug in IDENTITIES}


def build_plan(config, fixture, *, resolution=None, scale=None, presentation="compact", flavor="hybrid"):
    validate_config(config)
    validate_fixture(fixture)
    if presentation not in config["profiles"]:
        raise ValueError("unknown layout presentation preference")
    if resolution is not None and resolution not in RESOLUTIONS:
        raise ValueError("unknown resolution")
    actual_scale = fixture["output"]["scale"] if scale is None else scale
    if type(actual_scale) not in (int, float) or actual_scale not in SCALES:
        raise ValueError("scale must be 1, 1.25 or 1.5")
    physical = RESOLUTIONS[resolution] if resolution else (fixture["output"]["width"], fixture["output"]["height"])
    width, height = [n / actual_scale for n in physical]
    margin, gap = config["margin"], config["gap"]
    profile, dock = config["profiles"][presentation], config["dock"]
    dock_width = 2 * dock["padding"] + len(fixture["applications"]) * dock["icon_size"] + max(0, len(fixture["applications"]) - 1) * dock["spacing"]
    dock_top = height - dock["height"] - dock["bottom_clearance"]
    stack_height = sum(profile["heights"]) + gap * (len(ROLES) - 1)
    if profile["width"] + 2 * margin > width or 48 + margin + stack_height > dock_top - margin or dock_width > width - 2 * margin:
        raise ValueError(f"{presentation} layout does not fit; select another explicit presentation/scale")
    widgets = []
    y = 48 + margin
    for role, card_height in zip(ROLES, profile["heights"]):
        instance = fixture["bindings"][role]
        rect = [width - margin - profile["width"], y, profile["width"], card_height]
        current = next((a for a in fixture["applets"] if a["id"] == instance), None)
        action = "create_requested" if current is None else "keep" if current["geometry"] == rect else "move_requested"
        widgets.append(dict(role=role, plugin=config["widgets"][role]["plugin"], instance_id=instance,
                            action=action, rect=rect, preferred_face=config["widgets"][role]["face"],
                            native_size_verified=False, native_presentation_verified=False))
        y += card_height + gap
    structure = dict(output=dict(physical_size=list(physical), logical_size=[width, height], scale=actual_scale),
                     presentation=presentation,
                     top_bar=dict(rect=[0, 0, width, 48], opacity="opaque", roles=config["top_bar"]["roles"],
                                  native_properties=dict(height=48, alignment="center", lengthMode="fill", location="top")),
                     dock=dict(rect=[(width - dock_width) / 2, dock_top, dock_width, 56],
                               floating=dock["floating"], bottom_clearance=dock["bottom_clearance"],
                               applications=copy.deepcopy(fixture["applications"]), plugin=dock["plugin"],
                               native_properties=dict(height=56, alignment="center", lengthMode="fit", location="bottom")),
                     widgets=widgets)
    theme = load_desktop_family(ROOT / "theme/panda")[resolve_slug(flavor)]
    return dict(schema_version=1, scope="offline-only", native_verified=False,
                fixture_sha256=digest(fixture), layout_sha256=digest(config), structural_sha256=digest(structure),
                flavor=theme.slug, palette=dict(theme.palette), **copy.deepcopy(structure),
                preserved_fixture=copy.deepcopy(fixture),
                warnings=["Card rectangles are model preferences, not verified Plasma minima.",
                          "Right-column positions are calculated once; native automatic anchoring is unverified.",
                          "Compact/expanded are layout preferences, not universal stock-widget modes.",
                          "CPU/RAM backends remain unobserved; no sensor service is contacted.",
                          "Panel intent is not applied or reconciled to existing panel IDs.",
                          "Floating dock clearance is an offline target; the native floating margin remains unverified.",
                          "R3 enumeration issue remains unresolved; no recovery success is claimed."])
