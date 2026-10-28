"""Offline Plasma Style package sources. Never installs or activates a theme."""
import argparse
import configparser
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import sys
import xml.etree.ElementTree as ET

from desktop_io import read_regular
from palette import load_family, ROLES, HEX
from visual_style import load_spec

ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = "theme/panda/plasma-styles/"
PREVIEW_ROOT = "docs/panda-theme/previews/d4c3-s1/"
PARTS = ("topleft","top","topright","left","center","right","bottomleft","bottom","bottomright")
ASSETS = {"widgets/background.svg":12, "widgets/translucentbackground.svg":12,
          "widgets/panel-background.svg":8, "solid/widgets/panel-background.svg":8,
          "dialogs/background.svg":16}
PACKAGE_FILES = ("metadata.json","plasmarc","colors","LICENSE",*ASSETS)
NS = "http://www.w3.org/2000/svg"
SPEC = Path(__file__).parent/"plasma_style/spec.json"


def _palette(palette):
    if (not isinstance(palette,dict) and not hasattr(palette,"items")) or set(palette)!=ROLES:
        raise ValueError("complete canonical semantic palette required")
    if any(not isinstance(v,str) or not HEX.fullmatch(v) for v in palette.values()):
        raise ValueError("opaque canonical sRGB paint required")


def contract():
    spec=json.loads(read_regular(SPEC))
    expected=dict(schema_version=1,radius=12,slice_size=12,border_width=1,assets=ASSETS,
                  background="surface",border="border",fallback="breeze-dark")
    if spec!=expected or any(type(spec[k]) is not int for k in ("schema_version","radius","slice_size","border_width")):
        raise ValueError("unreviewed Plasma Style contract")
    visual=load_spec()
    if visual["radius"]!=spec["radius"] or visual["padding"]!={"compact":12,"expanded":16}:
        raise ValueError("D4B style contract drift")
    return spec


def _piece(part,palette,mask=False):
    fill=palette["surface"];border=fill if mask else palette["border"]
    role="surface" if mask else "border"
    corner='<path data-panda-token="surface" fill="'+fill+'" d="M12 0 A12 12 0 0 0 0 12 L12 12 Z"/>'
    ring='<path data-panda-token="'+role+'" fill="'+border+'" d="M12 0 A12 12 0 0 0 0 12 L1 12 A11 11 0 0 1 12 1 Z"/>'
    transforms={"topleft":"","topright":"translate(36 0) scale(-1 1)",
                "bottomleft":"translate(0 36) scale(1 -1)","bottomright":"translate(36 36) scale(-1 -1)"}
    if part in transforms:
        transform=transforms[part]
        return ('<g transform="'+transform+'">' if transform else '<g>')+corner+ring+'</g>'
    boxes={"top":(12,0,12,12),"left":(0,12,12,12),"center":(12,12,12,12),
           "right":(24,12,12,12),"bottom":(12,24,12,12)}
    x,y,w,h=boxes[part]
    def rect(x,y,w,h,color,token):
        return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{color}" data-panda-token="{token}"/>'
    body=rect(x,y,w,h,fill,"surface")
    if part!="center":
        edges={"top":(12,0,12,1),"left":(0,12,1,12),"right":(35,12,1,12),"bottom":(12,35,12,1)}
        body+=rect(*edges[part],border,role)
    return body


def frame_svg(palette,kind):
    _palette(palette);contract()
    if kind not in ASSETS:raise ValueError("unreviewed native asset path")
    parts=[f'<svg xmlns="{NS}" width="112" height="64" viewBox="0 0 112 64">',
           '<!-- SPDX-License-Identifier: GPL-3.0-or-later; generated from canonical Panda tokens -->']
    for prefix in ("","mask-"):
        for part in PARTS:
            transform=' transform="translate(48 0)"' if prefix else ""
            parts.append(f'<g id="{prefix+part}"{transform}>'+_piece(part,palette,bool(prefix))+'</g>')
    margin=ASSETS[kind]
    for i,edge in enumerate(("top","right","bottom","left")):
        w,h=(margin,1) if edge in ("left","right") else (1,margin)
        parts.append(f'<rect id="hint-{edge}-margin" x="90" y="{i*16}" width="{w}" height="{h}" opacity="0" fill="{palette["surface"]}" data-panda-token="surface"/>')
    parts.append(f'<rect id="hint-stretch-borders" x="89" y="63" width="1" height="1" opacity="0" fill="{palette["surface"]}" data-panda-token="surface"/>')
    return ("\n".join(parts)+"\n</svg>\n").encode()


def validate_frame(raw,palette,kind):
    """Validate only this reviewed profile, not arbitrary third-party themes."""
    if not isinstance(raw,bytes) or len(raw)>65536:raise ValueError("bounded SVG bytes required")
    upper=raw.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper or b"<?" in raw:raise ValueError("entities/DTD/processing instructions refused")
    try:tree=ET.fromstring(raw)
    except ET.ParseError as e:raise ValueError("malformed SVG") from e
    allowed={"svg","g","path","rect"}
    attrs={"width","height","viewBox","id","transform","fill","d","data-panda-token","x","y","opacity"}
    ids=[]
    for node in tree.iter():
        if node.tag not in {"{"+NS+"}"+x for x in allowed}:raise ValueError("unsafe SVG element")
        if set(node.attrib)-attrs:raise ValueError("unsafe SVG attribute or resource")
        if node.text and node.text.strip():raise ValueError("unexpected SVG text")
        if node.get("id"):ids.append(node.get("id"))
        if any(v in value.lower() for value in node.attrib.values() for v in ("url(","javascript:","data:","http:","https:","@import")):
            raise ValueError("SVG resource references refused")
    if len(ids)!=len(set(ids)):raise ValueError("duplicate SVG identity")
    expected=ET.fromstring(frame_svg(palette,kind))
    # Exact geometry/role/opacity contract catches off-palette paints and hidden overlays.
    if ET.tostring(tree)!=ET.tostring(expected):raise ValueError("SVG differs from reviewed semantic/frame profile")
    return tree


def colors_file(theme):
    p=theme.palette
    groups={"Window":"surface","View":"background","Button":"surface2","Selection":"selection",
            "Tooltip":"surface","Complementary":"surface","Header":"surface"}
    cp=configparser.ConfigParser(interpolation=None);cp.optionxform=str
    cp["General"]={"Name":theme.name+" S1"}
    for group,bg in groups.items():
        fg="on_selection" if group=="Selection" else "text"
        roles=dict(BackgroundNormal=bg,BackgroundAlternate="surface2",ForegroundNormal=fg,
                   ForegroundInactive=fg if group=="Selection" else "muted",
                   ForegroundLink="accent_text",ForegroundVisited="accent_text",
                   ForegroundPositive="success",ForegroundNeutral="warning",ForegroundNegative="error",
                   DecorationFocus="focus",DecorationHover="focus")
        if group=="Selection":
            roles.update({key:"on_selection" for key in roles if key.startswith("Foreground")})
        cp["Colors:"+group]={key:",".join(str(int(p[role][i:i+2],16)) for i in (1,3,5)) for key,role in roles.items()}
    stream=io.StringIO();cp.write(stream,space_around_delimiters=False)
    return (stream.getvalue().rstrip("\n")+"\n").encode()


def parse_colors(raw):
    cp=configparser.ConfigParser(interpolation=None);cp.read_string(raw.decode())
    values=[]
    for group in cp.sections():
        if group=="General":continue
        for value in cp[group].values():
            if not re.fullmatch(r"\d{1,3},\d{1,3},\d{1,3}",value):raise ValueError("invalid style color")
            rgb=tuple(map(int,value.split(",")))
            if max(rgb)>255:raise ValueError("unbounded style color")
            values.append(rgb)
    return values


def build_packages():
    from visual_assets import verified_assets
    contract();_,assets,_=verified_assets()
    outputs={}
    for slug,theme in load_family(ROOT/"theme/panda").items():
        ident="panda-"+slug+"-s1"
        meta={"KPlugin":{"Id":ident,"Name":theme.name+" S1","Description":"Opaque Panda frame candidate; native verification pending",
                         "Version":"0.1.0","License":"GPL-3.0-or-later"},"X-Plasma-API":"5.0"}
        files={"metadata.json":(json.dumps(meta,sort_keys=True,indent=2)+"\n").encode(),
               "plasmarc":b"[Settings]\nFallbackTheme=breeze-dark\n\n[BlurBehindEffect]\nenabled=false\n\n[ContrastEffect]\nenabled=false\n\n[AdaptiveTransparency]\nenabled=false\n",
               "colors":colors_file(theme),"LICENSE":assets["GPL-3.0.txt"]}
        files.update({kind:frame_svg(theme.palette,kind) for kind in ASSETS})
        outputs.update({ident+"/"+name:data for name,data in files.items()})
    return outputs


def structure_digest(files,palette):
    shape={}
    for name,data in files.items():
        if name.endswith(".svg"):
            tree=ET.fromstring(data)
            for node in tree.iter():
                if "fill" in node.attrib:node.set("fill","[semantic-paint]")
            shape[name]=ET.tostring(tree).decode()
        elif name=="colors":
            cp=configparser.ConfigParser(interpolation=None);cp.read_string(data.decode())
            shape[name]={g:sorted(cp[g]) for g in cp.sections()}
        elif name=="metadata.json":
            meta=json.loads(data);meta["KPlugin"]["Id"]="[flavor]";meta["KPlugin"]["Name"]="[name]"
            shape[name]=meta
        else:shape[name]=hashlib.sha256(data).hexdigest()
    return hashlib.sha256(json.dumps(shape,sort_keys=True).encode()).hexdigest()


def check_packages():
    expected=build_packages();directory=ROOT/PACKAGE_ROOT
    actual={str(p.relative_to(directory)) for p in directory.rglob("*") if p.is_file() or p.is_symlink()}
    if actual!=set(expected):raise ValueError("native package inventory mismatch")
    for name,data in expected.items():
        if read_regular(directory/name)!=data:raise ValueError("stale/conflicting generated package: "+name)
    return len(expected)


def _allowed(relative):
    parts=Path(relative).parts
    if Path(relative).is_absolute() or ".." in parts:return False
    if relative.startswith(PACKAGE_ROOT):
        tail=relative[len(PACKAGE_ROOT):].split("/",1)
        return len(tail)==2 and tail[0] in {"panda-"+s+"-s1" for s in load_family(ROOT/"theme/panda")} and tail[1] in PACKAGE_FILES
    if relative.startswith(PREVIEW_ROOT):
        name=relative[len(PREVIEW_ROOT):]
        return name in {"five-flavor-gallery.png","cyber-d4b-comparison.png","verification.json","manifest.json"}|{s+".png" for s in load_family(ROOT/"theme/panda")}
    return False


def write_reviewed(outputs,*,root=ROOT):
    """Fixed repo artifact tree only. Preserve identical files; refuse every conflict."""
    root=Path(root).absolute()
    if any(not isinstance(k,str) or not _allowed(k) or not isinstance(v,bytes) for k,v in outputs.items()):
        raise ValueError("only reviewed repository artifact paths/bytes accepted")
    for relative,data in outputs.items():
        target=root/relative
        for ancestor in (target,*target.parents):
            if ancestor.is_symlink():raise ValueError("artifact symlink refused")
            if ancestor.exists():
                st=ancestor.stat()
                if ancestor!=target and not stat.S_ISDIR(st.st_mode):raise ValueError("artifact parent conflict")
                if st.st_uid not in (0,os.getuid()):raise ValueError("unexpected artifact path owner")
                sticky=ancestor!=target and st.st_uid==0 and bool(st.st_mode & stat.S_ISVTX)
                if st.st_mode & 0o022 and not sticky:raise ValueError("unsafe writable artifact path")
                if ancestor==target and st.st_uid!=os.getuid():raise ValueError("artifact not owned by current user")
        if target.exists() and read_regular(target,limit=16*1024*1024)!=data:
            raise ValueError("different existing artifact preserved: "+relative)
    for relative,data in outputs.items():
        target=root/relative
        # Re-open every parent at write time with directory descriptors. A late
        # symlink replacement must never redirect an artifact outside this tree.
        fds=[];bindings=[]
        def identity(info):return info.st_dev,info.st_ino,info.st_mode,info.st_uid,info.st_gid
        def verify():
            for parent,name,child,expected in bindings:
                if identity(os.fstat(child))!=expected or identity(os.stat(name,dir_fd=parent,follow_symlinks=False))!=expected:
                    raise ValueError("artifact parent identity changed")
        try:
            current=os.open("/",os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW);fds.append(current)
            for component in target.parent.parts[1:]:
                verify()
                try:child=os.open(component,os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=current)
                except FileNotFoundError:
                    os.mkdir(component,0o755,dir_fd=current)
                    child=os.open(component,os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=current)
                fds.append(child);info=os.fstat(child)
                sticky=info.st_uid==0 and bool(info.st_mode&stat.S_ISVTX)
                if info.st_uid not in (0,os.getuid()) or (info.st_mode&0o022 and not sticky):
                    raise ValueError("unsafe artifact parent")
                bindings.append((current,component,child,identity(info)));current=child
            verify()
            try:existing=os.stat(target.name,dir_fd=current,follow_symlinks=False)
            except FileNotFoundError:existing=None
            if existing is not None:
                if not stat.S_ISREG(existing.st_mode) or existing.st_uid!=os.getuid():
                    raise ValueError("unsafe existing artifact")
                if read_regular(target,limit=16*1024*1024)!=data:
                    raise ValueError("artifact changed since preflight")
            else:
                fd=os.open(target.name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o644,dir_fd=current)
                with os.fdopen(fd,"wb") as f:f.write(data)
            verify()
        finally:
            for fd in reversed(fds):os.close(fd)


def cli_help():
    return "Offline repository-only generator: --check (default), --generate. No installation or activation."


def main(argv=None):
    parser=argparse.ArgumentParser(description=cli_help())
    parser.add_argument("--generate",action="store_true",help="create fixed repo assets/previews; conflicts refused")
    parser.add_argument("--check",action="store_true",help="verify fixed repo assets/previews (default)")
    args=parser.parse_args(argv)
    try:
        from plasma_style_preview import make_previews
        packages=build_packages();previews,_=make_previews()
        outputs={PACKAGE_ROOT+k:v for k,v in packages.items()}
        outputs.update({PREVIEW_ROOT+k:v for k,v in previews.items()})
        if args.generate:write_reviewed(outputs)
        for name,data in outputs.items():
            if read_regular(ROOT/name,limit=16*1024*1024)!=data:raise ValueError("generated artifact mismatch: "+name)
        check_packages()
        print(f"Verified {len(packages)} offline native package files and {len(previews)} model artifacts; native unverified.")
        return 0
    except (ValueError,OSError,TypeError) as error:
        print("Plasma Style artifact refusal: "+str(error),file=sys.stderr);return 1

if __name__=="__main__":sys.exit(main())
