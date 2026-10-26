"""Standalone SVG schematic. No QML loading, network or native rendering."""
from html import escape


def render_svg(plan):
    colors = plan["palette"]
    width, height = plan["output"]["logical_size"]
    physical = plan["output"]["physical_size"]

    def n(value):
        return f"{value:g}"

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{physical[0]}" height="{physical[1]}" '
             f'viewBox="0 0 {n(width)} {n(height)}" role="img" aria-labelledby="title desc">',
             '<title id="title">Panda Desktop D4A offline schematic</title>',
             '<desc id="desc">Synthetic fixture preview. Native widget rendering and sizing remain unverified.</desc>']

    def rect(box, fill, stroke=None):
        x, y, w, h = box
        border = f' stroke="{stroke}"' if stroke else ""
        parts.append(f'<rect x="{n(x)}" y="{n(y)}" width="{n(w)}" height="{n(h)}" fill="{fill}"{border}/>')

    def text(x, y, content, fill=None, size=15):
        parts.append(f'<text x="{n(x)}" y="{n(y)}" fill="{fill or colors["text"]}" '
                     f'font-family="sans-serif" font-size="{size}">{escape(content)}</text>')

    rect([0, 0, width, height], colors["background"])
    rect(plan["top_bar"]["rect"], colors["surface"], colors["border"])
    desktops = plan["preserved_fixture"]["desktop_count"]
    text(24, 30, f'Panda  |  {desktops} existing workspace(s)  |  System tray  |  {plan["preserved_fixture"]["providers"]["clock"]}')
    text(24, 92, "OFFLINE SCHEMATIC", colors["accent_text"], 20)
    text(24, 122, "Native rendering and card sizes unverified", colors["muted"])
    text(24, 150, "Right column: calculated placement preference", colors["muted"])
    text(24, 178, f'{plan["flavor"]} / {plan["presentation"]} / {plan["output"]["scale"]:g} scale', colors["muted"])
    for widget in plan["widgets"]:
        x, y, w, h = widget["rect"]
        rect(widget["rect"], colors["surface"], colors["border"])
        text(x + 16, y + 27, widget["role"].upper(), colors["accent_text"])
        label = plan["preserved_fixture"]["providers"][widget["role"]]
        # Approximate schematic label fit; this does not measure native font metrics.
        limit = max(8, int((w - 32) / 8))
        label = label if len(label) <= limit else label[:limit - 1] + "…"
        text(x + 16, y + 53, label)
    rect(plan["dock"]["rect"], colors["surface"], colors["border"])
    x, y, w, h = plan["dock"]["rect"]
    slots = len(plan["dock"]["applications"])
    if slots:
        step = w / slots
        for index in range(slots):
            text(x + index * step + 10, y + 34, str(index + 1), colors["accent_text"])
    parts.append("</svg>")
    return "\n".join(parts) + "\n"
