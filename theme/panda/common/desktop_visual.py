"""Five independent offline cards over unchanged D4A plans; never native widgets."""
import base64
from html import escape
import json

from desktop_layout import ROLES, SENSOR_FACES, digest
from desktop_visual_fixture import validate_scene
from palette import IDENTITIES
from visual_assets import verified_assets
from visual_style import load_spec, contrast_report
from visual_svg import Canvas, contains, n

LABEL = "SYNTHETIC OFFLINE DESIGN — NATIVE UNVERIFIED"


def clock(canvas, box, scene, expanded):
    x, y, w, h = box
    canvas.text([x, y, w, 48 if expanded else 42], scene["time"],
                44 if expanded else 38, "accent_text", align="center", tag="clock-time")
    canvas.text([x, y+h-16, w, 16], scene["date"], 13, "muted", align="center", tag="clock-date")


def media(canvas, box, scene, expanded):
    x, y, w, h = box
    art = 80 if expanded else 56
    canvas.rect([x, y, art, art], "surface2", radius=8, border="border", tag="media-art-tile")
    canvas.icon([x+8, y+8, art-16, art-16], "music" if scene["artwork"] == "sample" else "missing-art", tag="media-art")
    tx, tw = x+art+12, w-art-12
    active = scene["state"] in ("playing", "paused")
    title = scene["title"] if active else "No player" if scene["state"] == "no-player" else "Media unavailable"
    artist = scene["artist"] if active else "Offline media sample"
    canvas.text([tx, y, tw, 22], title, 16, tag="media-title")
    canvas.text([tx, y+24, tw, 18], artist, 13, "muted", tag="media-artist")
    state = scene["state"].title() + (f' · {scene["players"]} players' if scene["players"] > 1 else "")
    canvas.text([tx, y+44, tw, 16], state, 13, "accent_text" if active else "muted", tag="media-state")
    button = 32 if expanded else 28
    controls = 3*button+16
    cx, cy = x+w-controls, y+h-button
    canvas.control([cx, cy, button, button], "previous", tag="media-previous")
    canvas.control([cx+button+8, cy, button, button], "pause" if scene["state"] == "playing" else "play", active=active, tag="media-play")
    canvas.control([cx+2*(button+8), cy, button, button], "next", tag="media-next")
    pw = w-controls-12
    if scene["duration"] is not None:
        percent = scene["elapsed"]/scene["duration"]*100
        canvas.bar([x, cy+2, pw, 6], percent, tag="media-progress")
        def stamp(seconds):
            return f"{int(seconds)//60}:{int(seconds)%60:02}"
        canvas.text([x, y+h-16, pw, 16], stamp(scene["elapsed"])+" / "+stamp(scene["duration"]), 13, "muted", tag="media-elapsed")
    else:
        canvas.text([x, cy, pw, button], "No timeline", 13, "muted", tag="media-no-timeline")


def weather(canvas, box, scene, expanded):
    x, y, w, h = box
    available = scene["state"] == "available"
    canvas.text([x, y, w, 18], scene["location"], 13, "muted", tag="weather-location")
    size = 40 if expanded else 32
    canvas.icon([x, y+28, size, size], "weather" if available else "weather-missing", tag="weather-icon")
    tx, tw = x+size+12, w-size-12
    value = f'{scene["temperature"]:g}°C' if scene["temperature"] is not None else "—"
    canvas.text([tx, y+22, tw, 36], value, 28 if expanded else 24, tag="weather-temperature")
    condition = scene["condition"] if available else {
        "offline": "Offline · weather unavailable", "unconfigured": "Provider unconfigured",
        "stale": "Stale sample · not current"}[scene["state"]]
    canvas.text([x if not expanded else tx, y+64, w if not expanded else tw, 18],
                condition, 13, "muted", tag="weather-condition")
    if expanded:
        detail = f'H {scene["high"]:g}° / L {scene["low"]:g}° · synthetic' if available else "No current provider data"
        canvas.text([x, y+h-18, w, 18], detail, 13, "muted", tag="weather-detail")


def sensor(canvas, box, scene, expanded, role, face):
    x, y, w, h = box
    canvas.icon([x, y+2, 16, 16], role, tag=role+"-icon")
    canvas.text([x+24, y, w-116, 22], role.upper(), 14, tag=role+"-heading")
    available = scene["state"] == "available"
    ratio = scene["percent"] if role == "cpu" else (
        scene["used_gib"]/scene["total_gib"]*100 if available else None)
    value = f"{ratio:.0f}%" if ratio is not None else "—"
    canvas.text([x+w-92, y, 92, 32 if expanded else 28], value,
                28 if expanded else 24, "accent_text", align="right", tag=role+"-value")
    if scene["state"] == "missing":
        canvas.text([x, y+36, w, 24], "Sensor unavailable", 14, "muted", tag=role+"-missing")
        return
    body = [x, y+36 if expanded else y+32, w, 32 if expanded else 24]
    if role == "cpu":
        if face.endswith("linechart"):
            canvas.rect(body, "surface2", radius=4, tag="cpu-chart-track")
            canvas.line(body, scene["history"], tag="cpu-series")
        else:
            canvas.bar([x, body[1]+6, w, 10], ratio, tag="cpu-current")
        detail = f'{scene["window_seconds"]:g} s · synthetic' if face.endswith("linechart") else "Current sample · synthetic"
    else:
        if ratio is None:
            canvas.text(body, "Total unknown · no utilization", 13, "muted", tag="ram-unknown-total")
        elif face.endswith("horizontalbars"):
            canvas.bar([x, body[1]+6, w, 10], ratio, tag="ram")
        else:
            canvas.text(body, "History not supplied", 13, "muted", tag="ram-no-history")
        total = f'{scene["total_gib"]:g}' if scene["total_gib"] is not None else "?"
        detail = f'{scene["used_gib"]:g} / {total} GiB · synthetic'
    canvas.text([x, y+h-16, w, 16], detail, 13, "muted", tag=role+"-detail")


def toolbar(canvas, plan, scene):
    width = plan["output"]["logical_size"][0]
    canvas.owner = "toolbar"
    canvas.rect(plan["top_bar"]["rect"], "surface", border="border", tag="toolbar")
    canvas.icon([24, 14, 20, 20], "launcher", token="accent_text", tag="toolbar-launcher")
    canvas.text([56, 12, 76, 24], "Panda", 16, tag="toolbar-panda")
    count = plan["preserved_fixture"]["desktop_count"]
    canvas.rect([144, 10, 156, 28], "surface2", radius=8, border="border", tag="workspaces")
    canvas.text([156, 14, 132, 20], f'{count} workspace' + ("s" if count != 1 else ""),
                13, "muted", tag="toolbar-workspaces")
    if width < 700:
        raise ValueError("toolbar content cannot fit")
    canvas.icon([width-300, 16, 16, 16], "offline", tag="toolbar-network-offline")
    canvas.icon([width-272, 16, 16, 16], "muted", tag="toolbar-audio-muted")
    canvas.text([width-234, 14, 128, 20], scene["clock"]["short_date"], 13, "muted", align="right", tag="toolbar-date")
    canvas.text([width-94, 12, 70, 24], scene["clock"]["time"], 16, align="right", tag="toolbar-time")


def dock(canvas, plan, scene):
    canvas.owner = "dock"
    box = plan["dock"]["rect"]
    canvas.rect(box, "surface", radius=12, border="border", tag="dock")
    x, y, w, h = box
    # Slot geometry comes from the D4A rectangle and application count.
    count = len(scene["dock"])
    if not count:
        return
    # D4A permits custom icon/padding values; infer only reviewed default slot geometry.
    if abs(w-(16+count*40+max(0,count-1)*8)) > 0.01:
        raise ValueError("visual dock requires reviewed 40/8/8 sizing")
    for index, app in enumerate(scene["dock"]):
        ix = x+8+index*48
        if app["selected"]:
            canvas.rect([ix-2, y+4, 44, 48], "selection", radius=8, border="focus", tag="dock-selected")
        canvas.icon([ix, y+8, 40, 40], app["icon"], tag="dock-"+app["icon"])
        if app["running"]:
            indicator = [ix+14, y+51, 12, 2] if app["selected"] else [ix+18, y+50, 4, 4]
            canvas.rect(indicator, "focus", radius=2, tag="dock-running-"+app["icon"])
        for item in canvas.elements[-3:]:
            if item["owner"] == "dock" and not contains(box, item["paint"]):
                raise ValueError("dock icon/control overflow")


def render_visual(plan, scene, *, composition=False):
    validate_scene(scene)
    spec = load_spec()
    receipt, assets, icons = verified_assets()
    if plan.get("scope") != "offline-only" or plan.get("native_verified") is not False:
        raise ValueError("only an offline D4A plan can be visualized")
    if [w["role"] for w in plan["widgets"]] != list(ROLES):
        raise ValueError("exactly five independent cards required")
    if [app["application"] for app in scene["dock"]] != plan["dock"]["applications"]:
        raise ValueError("visual dock does not match plan application identities/order")
    if composition and plan["flavor"] != "cyber":
        raise ValueError("reviewed composition wallpaper is Cyber only")
    colors = plan["palette"]
    contrast = contrast_report(colors)
    if any(not item["pass"] for item in contrast["used"]):
        raise ValueError("used semantic contrast pair failed")
    canvas = Canvas(colors, icons)
    width, height = plan["output"]["logical_size"]
    physical = plan["output"]["physical_size"]
    canvas.rect([0, 0, width, height], "background", tag="background")
    if composition:
        data = base64.b64encode(assets["cyber-overlook.png"]).decode()
        canvas.parts.append(f'<image x="0" y="0" width="{n(width)}" height="{n(height)}" preserveAspectRatio="xMidYMid slice" href="data:image/png;base64,{data}"/>')
    toolbar(canvas, plan, scene)
    faces = {}
    expanded = plan["presentation"] == "expanded"
    for widget in plan["widgets"]:
        role = widget["role"]
        canvas.owner = role
        box = widget["rect"]
        canvas.rect(box, "surface", radius=spec["radius"], border="border", tag=role+"-card")
        pad = spec["padding"][plan["presentation"]]
        x, y, w, h = box
        inner = [x+pad, y+pad, w-2*pad, h-2*pad]
        start = len(canvas.elements)
        if role in ("cpu", "ram"):
            face = widget["preferred_face"]
            if face not in SENSOR_FACES:
                raise ValueError("unreviewed sensor face")
            faces[role] = face
            sensor(canvas, inner, scene[role], expanded, role, face)
        else:
            {"clock": clock, "media": media, "weather": weather}[role](canvas, inner, scene[role], expanded)
        for item in canvas.elements[start:]:
            if not contains(inner, item["paint"]):
                raise ValueError("card padding exceeded: " + item["tag"])
    dock(canvas, plan, scene)
    canvas.owner = "annotation"
    label_width = min(680, plan["widgets"][0]["rect"][0]-64)
    canvas.rect([24, 76, label_width, 84], "surface", radius=8, border="border", tag="synthetic-caption")
    canvas.text([40, 88, label_width-32, 20], LABEL, 14, "accent_text", tag="synthetic-label")
    caption = f'{IDENTITIES[plan["flavor"]]} · {plan["presentation"]} · {plan["output"]["scale"]:g}×'
    canvas.text([40, 120, label_width-32, 22], caption, 16, tag="design-caption")
    metadata = dict(scope="synthetic-offline-design", native_verified=False,
                    fixture_sha256=plan["fixture_sha256"], structural_sha256=plan["structural_sha256"],
                    visual_fixture_sha256=digest(scene), visual_spec_sha256=digest(spec),
                    font=canvas.metrics.provenance, asset_hashes=receipt["files"],
                    icon_notice="Breeze icons: KDE contributors, LGPL-3.0-or-later; see source assets/COPYING-Breeze.txt",
                    composition=composition)
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{physical[0]}" height="{physical[1]}" viewBox="0 0 {n(width)} {n(height)}" role="img" aria-labelledby="title desc">\n'
           '<title id="title">Panda D4B synthetic offline design</title>\n'
           f'<desc id="desc">{escape(LABEL)}. All data is synthetic. Native card sizes, rendering and services are unverified.</desc>\n'
           '<metadata>'+escape(json.dumps(metadata,sort_keys=True,separators=(",",":")))+'</metadata>\n'
           +"\n".join(canvas.parts)+"\n</svg>\n")
    audit = dict(font_metrics=canvas.metrics.provenance, elements=canvas.elements,
                 bounds_failures=canvas.bounds_failures, contrast=contrast, faces=faces,
                 structural_sha256=plan["structural_sha256"], native_verified=False)
    return svg, audit
