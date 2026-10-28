"""S2 job/pixel contracts only. No Qt imports, process launch or desktop discovery."""
import argparse
import hashlib
import json
import math
import re
import sys

from desktop_io import read_regular
from palette import load_family
from plasma_style import ROOT, ASSETS, PACKAGE_ROOT, build_packages

SCALES=(1.0,1.25,1.5,2.0)
SIZES=((24,24),(288,88),(288,120),(352,168),(1024,48),(352,56),(303,119))
ASSET_IDS={"widgets/background.svg":"widget","widgets/translucentbackground.svg":"translucent",
           "widgets/panel-background.svg":"panel","solid/widgets/panel-background.svg":"solid-panel",
           "dialogs/background.svg":"dialog"}
FIXTURE=ROOT/"tests/fixtures/desktop/native-frame-contract.json"


def encode(value):
    return (json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n").encode()


def build_jobs():
    packages=build_packages()
    if set(ASSETS)!=set(ASSET_IDS):raise ValueError("native asset contract drift")
    jobs=[]
    for slug,theme in load_family(ROOT/"theme/panda").items():
        package="panda-"+slug+"-s1"
        hashes={asset:hashlib.sha256(packages[package+"/"+asset]).hexdigest() for asset in ASSET_IDS}
        for scale in SCALES:
            cases=[dict(id=ident+"-"+str(w)+"x"+str(h),asset=asset,size=[w,h],margin=ASSETS[asset])
                   for asset,ident in ASSET_IDS.items() for w,h in SIZES]
            jobs.append(dict(schema_version=1,flavor=slug,package_id=package,scale=scale,radius=12,
                             palette=dict(surface=theme.palette["surface"],border=theme.palette["border"]),
                             asset_sha256=hashes,cases=cases,missing_asset="widgets/panda-s2-absent.svg"))
    return jobs


def _pairs(items):
    result={}
    for key,value in items:
        if key in result:raise ValueError("duplicate JSON key")
        result[key]=value
    return result


def _number_refused(value):
    raise ValueError("non-finite JSON number")


def _same(actual,expected):
    if type(expected) is float:
        return type(actual) in (int,float) and math.isfinite(actual) and actual==expected
    if type(actual) is not type(expected):return False
    if isinstance(expected,dict):
        return actual.keys()==expected.keys() and all(_same(actual[k],v) for k,v in expected.items())
    if isinstance(expected,list):
        return len(actual)==len(expected) and all(_same(a,b) for a,b in zip(actual,expected))
    return actual==expected


def validate_job(raw):
    if not isinstance(raw,bytes) or len(raw)>32768:raise ValueError("bounded job bytes required")
    try:job=json.loads(raw,object_pairs_hook=_pairs,parse_constant=_number_refused)
    except (UnicodeError,json.JSONDecodeError) as error:raise ValueError("malformed job JSON") from error
    if not any(_same(job,expected) for expected in build_jobs()):
        raise ValueError("job differs from reviewed paths, identities, dimensions or hashes")
    return job


def classify_asset(relative,available):
    if not isinstance(relative,str) or relative not in ASSETS:return "unsupported"
    return "supported" if relative in available else "missing"


def pixel_size(logical_size,scale):
    if (not isinstance(logical_size,(list,tuple)) or len(logical_size)!=2
            or any(type(v) is not int or not 24<=v<=4096 for v in logical_size)
            or type(scale) not in (int,float) or not math.isfinite(scale) or scale not in SCALES):
        raise ValueError("reviewed bounded size/scale required")
    size=tuple(math.ceil(v*scale) for v in logical_size)
    if size[0]*size[1]>4*1024*1024:raise ValueError("pixel budget exceeded")
    return size


def analyze_pixels(rgba,mask,pixel_width,pixel_height,*,logical_size,scale,surface):
    """Assertions on explicit RGBA buffers; cannot certify native execution/isolation."""
    expected=pixel_size(logical_size,scale)
    if (type(pixel_width) is not int or type(pixel_height) is not int
            or (pixel_width,pixel_height)!=expected):
        raise ValueError("native pixel bounds mismatch")
    length=pixel_width*pixel_height*4
    if type(rgba) is not bytes or type(mask) is not bytes or len(rgba)!=length or len(mask)!=length:
        raise ValueError("bounded complete RGBA buffers required")
    if not isinstance(surface,str) or not re.fullmatch("#[0-9a-fA-F]{6}",surface):
        raise ValueError("canonical opaque surface required")
    w,h=logical_size;radius=12;band=1/scale;core=0;exterior=0
    for y in range(pixel_height):
        py=(y+.5)/scale
        for x in range(pixel_width):
            i=(y*pixel_width+x)*4
            if rgba[i+3]!=mask[i+3]:raise ValueError("mask silhouette mismatch")
            px=(x+.5)/scale
            qx=abs(px-w/2)-(w/2-radius);qy=abs(py-h/2)-(h/2-radius)
            distance=math.hypot(max(qx,0),max(qy,0))+min(max(qx,qy),0)-radius
            if distance < -band:
                core+=1
                if rgba[i+3]!=255:raise ValueError("opaque interior hole/seam")
            elif distance > band:
                exterior+=1
                if rgba[i+3]!=0:raise ValueError("paint outside rounded exterior")
    center=((pixel_height//2)*pixel_width+pixel_width//2)*4
    color=bytes(int(surface[i:i+2],16) for i in (1,3,5))
    if rgba[center:center+4]!=color+b"\xff":raise ValueError("canonical center surface mismatch")
    return dict(interior_holes=0,interior_pixels_checked=core,exterior_pixels_checked=exterior,
                mask_matches=True,native_runtime_verified=False,fallback_status="unverified")


def fixture_contract():
    jobs=build_jobs()
    return dict(schema_version=1,frame_cases=700,missing_probes=20,native_worker_executed=False,
                job_sha256={job["flavor"]+"-"+str(int(job["scale"]*100)):
                            hashlib.sha256(encode(job)).hexdigest() for job in jobs})


def check_fixture():
    raw=read_regular(FIXTURE)
    actual=json.loads(raw,object_pairs_hook=_pairs,parse_constant=_number_refused)
    if not _same(actual,fixture_contract()):raise ValueError("stale native job fixture contract")
    return actual["frame_cases"]


def main(argv=None):
    parser=argparse.ArgumentParser(description="Offline data contract only; no native worker execution")
    group=parser.add_mutually_exclusive_group()
    group.add_argument("--check",action="store_true")
    group.add_argument("--print-jobs",action="store_true",help="print canonical job data; does not launch anything")
    args=parser.parse_args(argv)
    try:
        if args.print_jobs:sys.stdout.buffer.write(encode(build_jobs()))
        else:print(str(check_fixture())+" direct frame cases,20 missing probes; native worker not executed.")
    except (OSError,ValueError,TypeError) as error:
        print("Native frame data refusal: "+str(error),file=sys.stderr);return 1
    return 0


if __name__=="__main__":sys.exit(main())
