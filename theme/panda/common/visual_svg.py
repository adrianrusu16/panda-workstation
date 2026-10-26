"""Reusable bounded SVG primitives, actual glyph paths and semantic controls."""
from html import escape
import math
import xml.etree.ElementTree as ET

from visual_assets import icon_tree, icon_ink
from visual_text import get_metrics

NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", NS)


def n(value):
    return f"{value:.5f}".rstrip("0").rstrip(".") if value else "0"


def contains(box, paint, epsilon=0.015):
    x, y, w, h = box
    a, b, c, d = paint
    return a >= x - epsilon and b >= y - epsilon and a + c <= x + w + epsilon and b + d <= y + h + epsilon


class Canvas:
    def __init__(self, palette, icons):
        self.colors, self.icons = palette, icons
        self.metrics = get_metrics()
        self.parts, self.elements, self.bounds_failures = [], [], []
        self.owner = "canvas"

    def record(self, kind, tag, bounds, paint, **extra):
        if any(not math.isfinite(v) for v in (*bounds, *paint)) or min(bounds[2:]) < 0 or min(paint[2:]) < 0:
            raise ValueError("invalid painted geometry")
        item = dict(kind=kind, tag=tag, owner=self.owner, bounds=list(bounds), paint=list(paint), **extra)
        self.elements.append(item)
        if not contains(bounds, paint):
            self.bounds_failures.append(item)
            raise ValueError("paint exceeds bounds: " + tag)

    def rect(self, box, fill, *, radius=0, border=None, tag="surface"):
        x, y, w, h = box
        inset = 0.5 if border else 0
        stroke = f' stroke="{self.colors[border]}" stroke-width="1"' if border else ""
        self.parts.append(f'<rect data-tag="{escape(tag)}" x="{n(x+inset)}" y="{n(y+inset)}" width="{n(w-2*inset)}" height="{n(h-2*inset)}" rx="{n(radius)}" fill="{self.colors[fill]}"{stroke}/>')
        self.record("rect", tag, box, box)

    def text(self, box, text, size=14, token="text", *, align="left", tag="label"):
        x, y, w, h = box
        shaped = self.metrics.shape(text, size, w)
        a, b, iw, ih = shaped["ink"]
        if ih > h + 0.015:
            raise ValueError("text ink exceeds line height: " + tag)
        dx = x - a + (w-iw if align == "right" else (w-iw)/2 if align == "center" else 0)
        dy = y + (h-ih)/2 - b
        self.parts.append(f'<g data-tag="{escape(tag)}" role="img" aria-label="{escape(text, quote=True)}"><title>{escape(text)}</title><path fill="{self.colors[token]}" transform="translate({n(dx)} {n(dy)})" d="{shaped["path"]}"/></g>')
        self.record("text", tag, box, [a+dx, b+dy, iw, ih], text=text, ellipsized=shaped["ellipsized"], token=token)

    def icon(self, box, key, *, token="text", tag="icon"):
        x, y, w, h = box
        source = self.icons[key]["svg"]
        root = icon_tree(source, "icon" + str(len(self.elements)) + "-", self.colors[token])
        root.set("x", n(x)); root.set("y", n(y))
        root.set("width", n(w)); root.set("height", n(h))
        root.set("overflow", "visible")
        root.set("aria-label", key)
        self.parts.append(ET.tostring(root, encoding="unicode"))
        a, b, iw, ih = icon_ink(source, self.colors[token], w, h)
        self.record("icon", tag, box, [x+a, y+b, iw, ih], icon=key)

    def line(self, box, values, *, token="accent_text", tag="series"):
        x, y, w, h = box
        # Every disconnected run is a separate subpath; gaps are never interpolated.
        commands, started = [], False
        for i, value in enumerate(values):
            if value is None:
                started = False
                continue
            px, py = x+1+(w-2)*i/max(1, len(values)-1), y+1+(h-2)*(1-value/100)
            commands.append(("L" if started else "M") + n(px) + " " + n(py))
            started = True
        self.parts.append(f'<path data-tag="{escape(tag)}" d="{" ".join(commands)}" fill="none" stroke="{self.colors[token]}" stroke-width="2" stroke-linejoin="round"/>')
        self.record("linechart", tag, box, box, samples=list(values))

    def bar(self, box, percent, *, tag="bar"):
        self.rect(box, "surface2", radius=box[3]/2, border="border", tag=tag+"-track")
        if percent > 0:
            x, y, w, h = box
            # Stay inside the track boundary, including tiny positive readings.
            self.rect([x+1, y+1, (w-2)*percent/100, h-2], "accent_text", radius=(h-2)/2, tag=tag+"-fill")

    def control(self, box, icon, *, active=False, tag="control"):
        self.rect(box, "selection" if active else "surface2", radius=box[3]/2, border="focus" if active else "border", tag=tag)
        x, y, w, h = box
        self.icon([x+(w-20)/2, y+(h-20)/2, 20, 20], icon, token="on_selection" if active else "text", tag=tag+"-icon")
