"""Hash-locked local visual inputs. No discovery, downloads or remote resources."""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from desktop_io import read_regular

ASSETS = Path(__file__).parent / "desktop/assets"
FILES = frozenset(("COPYING-Breeze.txt", "GPL-3.0.txt", "OFL-NotoSans.txt",
                   "NotoSans-Regular.ttf", "breeze-icons.json", "cyber-overlook.png"))
SVG = "http://www.w3.org/2000/svg"
ALLOWED = frozenset(("svg", "defs", "g", "path", "rect", "circle", "ellipse",
                     "linearGradient", "stop", "title", "style"))
ATTRS = frozenset(("id", "viewBox", "width", "height", "version", "x", "y", "d",
                   "cx", "cy", "rx", "ry", "r", "fill", "fill-rule", "stroke",
                   "stroke-width", "stroke-opacity", "transform", "gradientTransform", "gradientUnits",
                   "x1", "x2", "y1", "y2", "offset", "stop-color", "stop-opacity",
                   "opacity", "class", "style", "type", "href"))


def verified_assets():
    receipt = json.loads(read_regular(ASSETS / "provenance.json").decode())
    if not isinstance(receipt, dict) or set(receipt) != {"schema_version", "font", "icons", "wallpaper", "files"}:
        raise ValueError("malformed visual asset provenance")
    if type(receipt["schema_version"]) is not int or receipt["schema_version"] != 1 or not isinstance(receipt["files"], dict):
        raise ValueError("malformed visual asset inventory")
    if set(receipt["files"]) != FILES:
        raise ValueError("unexpected asset inventory")
    data = {}
    for name, expected in receipt["files"].items():
        raw = read_regular(ASSETS / name, limit=8 * 1024 * 1024)
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError("visual asset hash mismatch: " + name)
        data[name] = raw
    catalog = json.loads(data["breeze-icons.json"])
    for record in catalog["icons"].values():
        if hashlib.sha256(record["svg"].encode()).hexdigest() != record["sha256"]:
            raise ValueError("icon source hash mismatch")
    return receipt, data, catalog["icons"]


def icon_tree(source, prefix, color):
    import re
    if "<!DOCTYPE" in source.upper() or "<!ENTITY" in source.upper():
        raise ValueError("SVG entities are forbidden")
    root = ET.fromstring(source)
    css_colors = {}
    for node in root.iter():
        if node.tag == "{" + SVG + "}style":
            css = node.text or ""
            pattern = r"\.ColorScheme-(Text|Accent|NegativeText|Background|ButtonText)\s*\{\s*color:\s*(#[0-9a-fA-F]{6});?\s*\}"
            if re.sub(pattern, "", css).strip():
                raise ValueError("unreviewed icon CSS")
            for name, value in re.findall(pattern, css):
                css_colors["ColorScheme-" + name] = value if name == "Accent" else color

    def clean(parent):
        for child in list(parent):
            local = child.tag.rsplit("}", 1)[-1]
            if local in ("metadata", "namedview", "style"):
                parent.remove(child)
            elif child.tag.startswith("{" + SVG + "}") and local in ALLOWED:
                clean(child)
            else:
                raise ValueError("unsafe icon element")
        for key in list(parent.attrib):
            if key == "{http://www.w3.org/1999/xlink}href":
                value = parent.attrib.pop(key)
                if not value.startswith("#"):
                    raise ValueError("external icon reference")
                parent.set("href", "#" + prefix + value[1:])
            elif key.startswith("{"):
                del parent.attrib[key]
            elif key not in ATTRS:
                raise ValueError("unsafe icon attribute")
        for key, value in list(parent.attrib.items()):
            if "url(" in value and not re.fullmatch(r"(?:[^;]*;)*[^;]*url\(#[A-Za-z0-9_.-]+\)[^;]*(?:;[^;]*)*", value):
                raise ValueError("external SVG resource refused")
            if any(s in value.lower() for s in ("javascript:", "http:", "https:", "@import", "data:")):
                raise ValueError("remote SVG resource refused")
            parent.attrib[key] = value.replace("url(#", "url(#" + prefix)
        if "id" in parent.attrib:
            parent.attrib["id"] = prefix + parent.attrib["id"]
        classes = parent.attrib.pop("class", "").split()
        for name in classes:
            if name not in css_colors:
                raise ValueError("unreviewed icon class")
            parent.set("color", css_colors[name])
    clean(root)
    root.set("color", color)
    if "viewBox" not in root.attrib:
        root.set("viewBox", "0 0 " + root.attrib["width"] + " " + root.attrib["height"])
    return root


def icon_ink(source, color, width, height):
    """Measure actual librsvg paint operations, including transforms and opacity."""
    try:
        import gi
        gi.require_version("Rsvg", "2.0")
        from gi.repository import Rsvg
        import cairo
    except (ImportError, ValueError) as error:
        raise ValueError("accurate icon bounds require existing librsvg and pycairo") from error
    root = icon_tree(source, "metric-", color)
    root.set("width", str(width)); root.set("height", str(height))
    root.set("overflow", "visible")
    handle = Rsvg.Handle.new_from_data(ET.tostring(root))
    viewport = Rsvg.Rectangle()
    viewport.x, viewport.y, viewport.width, viewport.height = 0, 0, width, height
    surface = cairo.RecordingSurface(cairo.CONTENT_COLOR_ALPHA, None)
    cr = cairo.Context(surface)
    # Recording extents include painted operations, unlike librsvg geometry
    # estimates which can include fully transparent/offscreen construction paths.
    cr.scale(8, 8)
    if not handle.render_document(cr, viewport):
        raise ValueError("icon paint could not be measured")
    return [v / 8 for v in surface.ink_extents()]
