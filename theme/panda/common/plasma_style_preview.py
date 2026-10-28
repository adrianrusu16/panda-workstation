"""CPU-only nine-slice model of S1 SVG sources; never loads KSvg or Plasma."""
import base64
import copy
from functools import lru_cache
import hashlib
from io import BytesIO
import json
import math
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

from desktop_io import read_regular
from desktop_visual_export import raster
from palette import load_family, contrast_ratio
from plasma_style import ROOT, ASSETS, PARTS, build_packages, frame_svg, validate_frame, structure_digest
from visual_assets import verified_assets
from visual_svg import Canvas
from visual_text import get_metrics

LABEL="OFFLINE SVG NINE-SLICE MODEL — NATIVE UNVERIFIED"
BOXES={"topleft":(0,0),"top":(12,0),"topright":(24,0),"left":(0,12),"center":(12,12),
       "right":(24,12),"bottomleft":(0,24),"bottom":(12,24),"bottomright":(24,24)}


def _cairo():
    try:import cairo
    except ImportError as e:raise ValueError("existing CPU Cairo/librsvg required; no fallback") from e
    return cairo


def rgba(surface,x,y):
    surface.flush();i=y*surface.get_stride()+x*4;v=bytes(surface.get_data()[i:i+4])
    b,g,r,a=v if sys.byteorder=="little" else (v[3],v[2],v[1],v[0])
    if a not in (0,255):r,g,b=(min(255,round(c*255/a)) for c in (r,g,b))
    return r,g,b,a


@lru_cache(maxsize=512)
def _slice(raw,part,width,height):
    tree=ET.fromstring(raw)
    node=next(x for x in tree if x.get("id")==part)
    sx,sy=BOXES[part.removeprefix("mask-")]
    if part.startswith("mask-"):sx+=48
    root=ET.Element("{http://www.w3.org/2000/svg}svg",
                    width=str(width),height=str(height),viewBox=f"{sx} {sy} 12 12",preserveAspectRatio="none")
    root.append(copy.deepcopy(node))
    return raster(ET.tostring(root,encoding="unicode"))


def compose_frame(raw,palette,kind,width,height,scale=1,*,prefix=""):
    if (any(type(v) not in (int,float) or not math.isfinite(v) for v in (width,height,scale))
            or min(width,height)<24 or max(width,height)>8192 or not .5<=scale<=4
            or width*height*scale*scale>16*1024*1024 or prefix not in ("","mask-")):
        raise ValueError("bounded frame >=24 logical pixels and reviewed prefix required")
    validate_frame(raw,palette,kind)
    cairo=_cairo()
    w,h=(int(v*scale+.5) for v in (width,height));cap=int(12*scale+.5)
    if min(w,h)<2*cap:raise ValueError("pixel-rounded frame too small")
    surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,w,h);cr=cairo.Context(surface)
    xs,ys=(0,cap,w-cap),(0,cap,h-cap);ws,hs=(cap,w-2*cap,cap),(cap,h-2*cap,cap)
    for i,part in enumerate(PARTS):
        row,col=divmod(i,3);pw,ph=ws[col],hs[row]
        if pw==0 or ph==0:continue
        piece=cairo.ImageSurface.create_from_png(BytesIO(_slice(raw,prefix+part,pw,ph)))
        cr.save();cr.rectangle(xs[col],ys[row],pw,ph);cr.clip()
        cr.set_source_surface(piece,xs[col],ys[row]);cr.get_source().set_filter(cairo.FILTER_NEAREST);cr.paint();cr.restore()
    return surface


def _png(surface):
    output=BytesIO();surface.write_to_png(output);return output.getvalue()


def _image(data,x,y,w,h):
    return f'<image x="{x}" y="{y}" width="{w}" height="{h}" href="data:image/png;base64,{base64.b64encode(data).decode()}" preserveAspectRatio="none"/>'


def _wallpaper(data):
    cairo=_cairo();source=cairo.ImageSurface.create_from_png(BytesIO(data))
    tile=cairo.ImageSurface(cairo.FORMAT_ARGB32,400,432);cr=cairo.Context(tile)
    scale=max(400/source.get_width(),432/source.get_height())
    cr.translate((400-source.get_width()*scale)/2,(432-source.get_height()*scale)/2)
    cr.scale(scale,scale);cr.set_source_surface(source,0,0);cr.paint()
    return tile


def _rgb_hex(pixel):return "#"+"".join(f"{x:02X}" for x in pixel[:3])


def make_previews():
    cairo=_cairo();family=load_family(ROOT/"theme/panda")
    provenance,assets,icons=verified_assets();packages=build_packages();outputs={}
    # Explicit fixture backgrounds; never alter native palette values.
    light=family["minimal"].palette["text"];dark=family["cyber"].palette["background"]
    wallpaper=_wallpaper(assets["cyber-overlook.png"]);wallpaper_png=_png(wallpaper)
    report=dict(label=LABEL,native_verified=False,raster_model="librsvg pieces, integer device-pixel seams; not KSvg",
                frame_radius=12,border_width=1,font=get_metrics().provenance,flavors={},
                background_fixtures=dict(light=light,dark=dark,wallpaper_sha256=hashlib.sha256(assets["cyber-overlook.png"]).hexdigest()),
                package_sha256={name:hashlib.sha256(data).hexdigest() for name,data in packages.items()})
    individual=[]
    for slug,theme in family.items():
        palette=dict(theme.palette);canvas=Canvas(palette,icons)
        canvas.rect([0,0,400,1424],"background")
        canvas.text([16,14,368,28],theme.name,20,tag="flavor")
        canvas.text([16,48,368,20],"OFFLINE MODEL · NATIVE UNVERIFIED",12,"muted",tag="synthetic")
        canvas.text([16,72,368,18],"No running widgets; stock controls unmeasured",11,"muted",tag="unverified")
        own={k.split("/",1)[1]:v for k,v in packages.items() if k.startswith("panda-"+slug+"-s1/")}
        audit=dict(border_surface_ratio=contrast_ratio(palette["border"],palette["surface"]),
                   structure_sha256=structure_digest(own,palette),external_border_contrast={},colors={})
        # Report all proposed native foreground pairings; never silently change a canonical token.
        import configparser
        cp=configparser.ConfigParser(interpolation=None);cp.optionxform=str;cp.read_string(own["colors"].decode())
        for group in cp.sections():
            if not group.startswith("Colors:"):continue
            bg=_rgb_hex(tuple(map(int,cp[group]["BackgroundNormal"].split(","))))
            audit["colors"][group]={key:dict(ratio=contrast_ratio(_rgb_hex(tuple(map(int,value.split(",")))),bg),
                minimum=3 if key.startswith("Decoration") else 4.5)
                for key,value in cp[group].items() if key.startswith(("Foreground","Decoration"))}
        for row,background in enumerate(("light","dark","wallpaper")):
            y=112+row*432
            if background=="wallpaper":canvas.parts.append(_image(wallpaper_png,0,y,400,432))
            else:
                palette["fixture"]=light if background=="light" else dark
                canvas.rect([0,y,400,432],"fixture")
            canvas.rect([8,y+6,384,30],"background",radius=4)
            canvas.text([16,y+10,368,20],background.title()+" backdrop · SVG frame model",12,tag="backdrop")
            def frame(kind,box):
                x,fy,w,h=box;canvas.parts.append(_image(_png(compose_frame(own[kind],theme.palette,kind,w,h)),x,fy,w,h))
            frame("widgets/panel-background.svg",[16,y+52,368,48])
            canvas.text([32,y+64,336,24],"Panda · toolbar frame · 48 logical",14,tag="toolbar")
            frame("widgets/background.svg",[56,y+116,288,88])
            canvas.text([68,y+128,264,42],"22:37",38,"accent_text",align="center",tag="clock")
            canvas.text([68,y+176,264,16],"Synthetic clock label",13,"muted",align="center",tag="clock-sample")
            frame("widgets/background.svg",[56,y+216,288,120])
            canvas.text([68,y+232,264,24],"Media frame",16,tag="media")
            canvas.text([68,y+264,264,20],"Stock representation not measured",12,"muted",tag="media-limit")
            canvas.text([68,y+300,264,18],"Full minimum: 14 × 10 native grid units",11,"muted",tag="media-min")
            frame("widgets/panel-background.svg",[24,y+352,352,56])
            canvas.text([36,y+368,328,24],"Floating dock frame · 56 logical",14,align="center",tag="dock")
            samples=[]
            for x,py in [(x,116) for x in range(68,332)]+[(x,203) for x in range(68,332)]+[(56,py) for py in range(128,192)]+[(343,py) for py in range(128,192)]:
                bg=_rgb_hex(rgba(wallpaper,x,py)) if background=="wallpaper" else light if background=="light" else dark
                samples.append(contrast_ratio(palette["border"],bg))
            audit["external_border_contrast"][background]=dict(minimum_ratio=min(samples),threshold=3,
                    fails=sum(v<3 for v in samples),samples=len(samples),classification="wallpaper/fixture advisory; no palette mutation")
        svg='<svg xmlns="http://www.w3.org/2000/svg" width="400" height="1424">'+"".join(canvas.parts)+'</svg>'
        data=raster(svg);outputs[slug+".png"]=data;individual.append(data);report["flavors"][slug]=audit
    gallery=cairo.ImageSurface(cairo.FORMAT_ARGB32,2000,1424);cr=cairo.Context(gallery)
    for index,data in enumerate(individual):
        cr.set_source_surface(cairo.ImageSurface.create_from_png(BytesIO(data)),index*400,0);cr.paint()
    outputs["five-flavor-gallery.png"]=_png(gallery)
    # Direct comparison with the approved D4B source export, never a native screenshot.
    preview_root=ROOT/"docs/panda-theme/previews/d4b";manifest=json.loads(read_regular(preview_root/"manifest.json"))
    reference={}
    for name in ("fhd-compact-cyber.png","five-flavor-comparison.png","cyber-composition.png"):
        data=read_regular(preview_root/name,limit=16*1024*1024)
        if hashlib.sha256(data).hexdigest()!=manifest["sha256"][name]:raise ValueError("D4B approved preview hash drift")
        reference[name]=hashlib.sha256(data).hexdigest()
    report["d4b_references_sha256"]=reference
    c=Canvas(dict(family["cyber"].palette),icons);c.rect([0,0,800,520],"background")
    c.text([16,12,768,28],"Cyber: D4B design / S1 native frame source model",20,tag="comparison")
    c.text([16,50,768,20],LABEL,13,"muted",tag="label")
    c.text([16,90,368,24],"D4B synthetic cards",16,tag="d4b")
    c.text([416,90,368,24],"S1 nine-slice model · frame only",16,tag="s1")
    surface=cairo.ImageSurface.create_from_png(BytesIO(raster('<svg xmlns="http://www.w3.org/2000/svg" width="800" height="520">'+"".join(c.parts)+'</svg>')))
    ctx=cairo.Context(surface);approved=cairo.ImageSurface.create_from_png(BytesIO(read_regular(preview_root/"fhd-compact-cyber.png",limit=16*1024*1024)))
    for sy,dy,h in ((72,132,88),(172,236,120)):
        ctx.save();ctx.rectangle(56,dy,288,h);ctx.clip();ctx.set_source_surface(approved,56-1608,dy-sy);ctx.paint();ctx.restore()
        raw=frame_svg(family["cyber"].palette,"widgets/background.svg")
        ctx.set_source_surface(compose_frame(raw,family["cyber"].palette,"widgets/background.svg",288,h),456,dy);ctx.paint()
    # Include dialog and alias source samples, with source-derived 16px / 12px margins.
    for kind,x in (("dialogs/background.svg",56),("widgets/translucentbackground.svg",456)):
        raw=frame_svg(family["cyber"].palette,kind)
        ctx.set_source_surface(compose_frame(raw,family["cyber"].palette,kind,288,96),x,392);ctx.paint()
    outputs["cyber-d4b-comparison.png"]=_png(surface)
    report["contrast_failures"]=[dict(flavor=slug,group=g,key=k,**v) for slug,a in report["flavors"].items()
        for g,colors in a["colors"].items() for k,v in colors.items() if v["ratio"]<v["minimum"]]
    report["selection_candidate_advisories"]=[
        dict(flavor=slug,foreground=role,background="selection",ratio=contrast_ratio(theme.palette[role],theme.palette["selection"]),minimum=4.5)
        for slug,theme in family.items() for role in ("accent_text","accent_text","success","warning","error")
        if contrast_ratio(theme.palette[role],theme.palette["selection"])<4.5]
    report["selection_mapping"]="all selected foreground states use canonical on_selection; no palette values changed"
    report["raster_environment"]=dict(cairo=cairo.cairo_version_string())
    outputs["verification.json"]=(json.dumps(report,sort_keys=True,indent=2)+"\n").encode()
    outputs["manifest.json"]=(json.dumps(dict(native_verified=False,sha256={name:hashlib.sha256(data).hexdigest() for name,data in sorted(outputs.items())}),sort_keys=True,indent=2)+"\n").encode()
    return outputs,report
