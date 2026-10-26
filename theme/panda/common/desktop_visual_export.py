"""Explicit offline artifact exporter. Never writes native desktop configuration."""
import argparse
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import re
import platform
import stat
import sys

from desktop_io import read_regular
from desktop_layout import ROOT, build_plan, load_config
from desktop_visual import render_visual
from desktop_visual_fixture import load_scene
from palette import IDENTITIES
from visual_assets import verified_assets
from visual_style import contrast_report
from visual_svg import Canvas

FIXTURES = ROOT / "tests/fixtures/desktop/visual"
FLAVORS = ("minimal", "cyber", "gothic", "hybrid", "wave")


def raster(svg):
    try:
        import cairo
        import gi
        gi.require_version("Rsvg", "2.0")
        from gi.repository import Rsvg
    except (ImportError, ValueError) as error:
        raise ValueError("PNG export requires existing pycairo and librsvg; no fallback") from error
    import xml.etree.ElementTree as ET
    root = ET.fromstring(svg)
    width, height = int(root.attrib["width"]), int(root.attrib["height"])
    handle = Rsvg.Handle.new_from_data(svg.encode() if isinstance(svg, str) else svg)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    viewport = Rsvg.Rectangle()
    viewport.x, viewport.y, viewport.width, viewport.height = 0, 0, width, height
    if not handle.render_document(cairo.Context(surface), viewport):
        raise ValueError("SVG rasterization failed")
    output = BytesIO()
    surface.write_to_png(output)
    return output.getvalue()


def comparison(previews, plans):
    import cairo
    _, _, icons = verified_assets()
    palette = plans["hybrid"]["palette"]
    canvas = Canvas(palette, icons)
    canvas.rect([0, 0, 2000, 1000], "background")
    canvas.text([32, 20, 1936, 40], "Panda Desktop · five flavors", 24, tag="comparison-title")
    canvas.text([32, 70, 1936, 24], "SYNTHETIC OFFLINE DESIGN — NATIVE UNVERIFIED · same geometry, font and data", 14, "muted", tag="comparison-caption")
    for i, flavor in enumerate(FLAVORS):
        canvas.text([i*400+24, 118, 352, 24], IDENTITIES[plans[flavor]["flavor"]], 16, tag="comparison-flavor")
    svg = '<svg xmlns="http://www.w3.org/2000/svg" width="2000" height="1000">'+"".join(canvas.parts)+"</svg>"
    surface = cairo.ImageSurface.create_from_png(BytesIO(raster(svg)))
    cr = cairo.Context(surface)

    def crop(data, source, target):
        image = cairo.ImageSurface.create_from_png(BytesIO(data))
        sx, sy, sw, sh = source
        tx, ty, tw, th = target
        cr.save()
        cr.rectangle(tx, ty, tw, th); cr.clip()
        cr.translate(tx, ty); cr.scale(tw/sw, th/sh)
        cr.set_source_surface(image, -sx, -sy); cr.paint()
        cr.restore()

    for i, flavor in enumerate(FLAVORS):
        plan = plans[flavor]; scale = plan["output"]["scale"]
        x, y, w, _ = plan["widgets"][0]["rect"]
        last = plan["widgets"][-1]["rect"]
        stack = last[1]+last[3]-y
        crop(previews[flavor], [x*scale,y*scale,w*scale,stack*scale], [i*400+24,160,352,704])
        x, y, w, h = plan["dock"]["rect"]
        crop(previews[flavor], [x*scale,y*scale,w*scale,h*scale], [i*400+(400-w)/2,904,w,h])
    output = BytesIO();surface.write_to_png(output)
    return output.getvalue()


def make_exports():
    config = load_config(ROOT / "theme/panda/common/desktop/layout.toml")
    fixture = json.loads(read_regular(FIXTURES / "dock-seven.json").decode())
    playing = load_scene(FIXTURES / "playing.json")
    receipt = json.loads(read_regular(FIXTURES / "d4a-baseline.json").decode())
    for path, digest in receipt["files"].items():
        if hashlib.sha256(read_regular(ROOT / path)).hexdigest() != digest:
            raise ValueError("D4A baseline file changed: " + path)
    base = json.loads(read_regular(ROOT / "tests/fixtures/desktop/fhd.json").decode())
    accepts, refuses = 0, 0
    report = dict(geometry_accepts=0, expected_refusals=0, bounds_failures=[],
                  contrast={}, font_metrics=None, native_verified=False)
    inputs = [ROOT / "theme/panda/common/desktop/visual.toml", *sorted(FIXTURES.glob("*.json"))]
    try:
        import gi
        gi.require_version("Rsvg", "2.0")
        from gi.repository import Rsvg
    except (ImportError, ValueError) as error:
        raise ValueError("accurate export requires existing PyGObject/librsvg; no fallback") from error
    report["raster_environment"] = dict(python=platform.python_version(),
        librsvg=f"{Rsvg.MAJOR_VERSION}.{Rsvg.MINOR_VERSION}.{Rsvg.MICRO_VERSION}")
    sources = [ROOT / "theme/panda/common/desktop_cli.py", ROOT / "theme/panda/common/desktop_visual_fixture.py",
               ROOT / "theme/panda/common/desktop_visual.py", ROOT / "theme/panda/common/desktop_visual_export.py",
               *sorted((ROOT / "theme/panda/common").glob("visual_*.py"))]
    report["renderer_sha256"] = {str(p.relative_to(ROOT)): hashlib.sha256(read_regular(p)).hexdigest() for p in sources}
    report["input_sha256"] = {str(p.relative_to(ROOT)): hashlib.sha256(read_regular(p)).hexdigest() for p in inputs}
    for res in ("fhd", "qhd"):
        for scale in (1, 1.25, 1.5):
            for presentation in ("compact", "expanded"):
                key = f"{res}/{scale:g}/{presentation}"
                for flavor in FLAVORS:
                    if key not in receipt["structures"]:
                        try:
                            build_plan(config, fixture, resolution=res, scale=scale, presentation=presentation, flavor=flavor)
                        except ValueError as error:
                            if "does not fit" not in str(error):
                                raise
                            refuses += 1
                            continue
                        raise ValueError("expected overflow refusal was lost")
                    baseline = build_plan(config, base, resolution=res, scale=scale, presentation=presentation, flavor=flavor)
                    if baseline["structural_sha256"] != receipt["structures"][key]:
                        raise ValueError("D4A structural decision changed")
                    plan = build_plan(config, fixture, resolution=res, scale=scale, presentation=presentation, flavor=flavor)
                    _, audit = render_visual(plan, playing)
                    report["bounds_failures"].extend(audit["bounds_failures"])
                    report["font_metrics"] = audit["font_metrics"]
                    accepts += 1
    report.update(geometry_accepts=accepts, expected_refusals=refuses)
    outputs, qhd, qhd_plans = {}, {}, {}

    def export(name, plan, scene, composition=False):
        svg, audit = render_visual(plan, scene, composition=composition)
        outputs[name+".svg"] = svg.encode()
        outputs[name+".png"] = raster(svg)
        return audit

    for flavor in FLAVORS:
        for res, scale, presentation in (("fhd",1,"compact"),("qhd",1.25,"expanded")):
            plan = build_plan(config, fixture, resolution=res, scale=scale, presentation=presentation, flavor=flavor)
            name = f"{res}-{presentation}-{flavor}"
            export(name,plan,playing)
            if res == "qhd":
                qhd[flavor], qhd_plans[flavor] = outputs[name+".png"], plan
                report["contrast"][flavor] = contrast_report(plan["palette"])
    export("cyber-composition",qhd_plans["cyber"],playing,composition=True)
    for state in ("unavailable","paused"):
        plan = build_plan(config, fixture, flavor="cyber")
        export("state-"+state,plan,load_scene(FIXTURES/(state+".json")))
    for scale, presentation, name in ((1.25,"expanded","tight-fhd125-expanded"),(1.5,"compact","tight-fhd150-compact")):
        plan = build_plan(config,fixture,resolution="fhd",scale=scale,presentation=presentation,flavor="hybrid")
        export(name,plan,load_scene(FIXTURES/"long-text.json"))
    outputs["five-flavor-comparison.png"] = comparison(qhd,qhd_plans)
    outputs["verification.json"] = (json.dumps(report,sort_keys=True,indent=2)+"\n").encode()
    hashes = {name:hashlib.sha256(data).hexdigest() for name,data in sorted(outputs.items())}
    outputs["manifest.json"] = (json.dumps(dict(base_commit=receipt["base_commit"],sha256=hashes),
                                          sort_keys=True,indent=2)+"\n").encode()
    return outputs, report


def write_exports(directory, outputs):
    directory = Path(directory).absolute()
    if any(p.is_symlink() for p in (directory,*directory.parents)):
        raise ValueError("export directory symlink refused")
    if any(not re.fullmatch(r"[a-z0-9-]+\.(svg|png|json)", name) for name in outputs):
        raise ValueError("invalid artifact name")
    directory.mkdir(parents=True,exist_ok=True)
    st = directory.stat()
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o022:
        raise ValueError("unsafe export directory ownership/mode")
    missing = []
    # Refuse every conflict before creating the first artifact.
    for name,data in outputs.items():
        path = directory/name
        if path.exists() or path.is_symlink():
            if read_regular(path,limit=16*1024*1024) != data:
                raise ValueError("different existing export preserved: "+name)
        else:
            missing.append(name)
    fd = os.open(directory,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        for name in missing:
            binding = os.stat(directory,follow_symlinks=False)
            if (binding.st_dev,binding.st_ino) != (st.st_dev,st.st_ino):
                raise ValueError("export directory identity changed")
            out = os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o644,dir_fd=fd)
            with os.fdopen(out,"wb") as stream:
                stream.write(outputs[name])
    finally:
        os.close(fd)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir",required=True,type=Path,help="explicit artifact directory; identical files are preserved, conflicts refused")
    args = parser.parse_args(argv)
    try:
        outputs,report = make_exports()
        write_exports(args.output_dir,outputs)
        print(f'Exported/verified {len(outputs)} offline artifacts; {report["geometry_accepts"]} model cases, {report["expected_refusals"]} expected refusals.')
        return 0
    except (ValueError,OSError,TypeError) as error:
        print("visual export refused: "+str(error),file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
