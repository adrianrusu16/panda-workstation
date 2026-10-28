"""Offline job and pixel-analysis behavior; never invokes a Qt/KSvg binary."""
import copy
import importlib
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"theme/panda/common"))


class NativeFramePlanTests(unittest.TestCase):
    def setUp(self):
        try:
            self.plan=importlib.import_module("native_frame_plan")
        except ModuleNotFoundError:
            self.fail("S2 native frame job/pixel validator is not implemented")

    def pixels(self,w=64,h=48,scale=1):
        from palette import load_family
        from plasma_style import frame_svg
        from plasma_style_preview import compose_frame,rgba
        palette=load_family(ROOT/"theme/panda")["cyber"].palette
        raw=frame_svg(palette,"widgets/background.svg")
        image=compose_frame(raw,palette,"widgets/background.svg",w,h,scale)
        mask=compose_frame(raw,palette,"widgets/background.svg",w,h,scale,prefix="mask-")
        def data(surface):
            return bytes(c for y in range(surface.get_height()) for x in range(surface.get_width()) for c in rgba(surface,x,y))
        return palette,data(image),data(mask),image.get_width(),image.get_height()

    def test_jobs_cover_700_unique_direct_frames_and_20_missing_probes(self):
        jobs=self.plan.build_jobs()
        self.assertEqual(len(jobs),20)
        self.assertEqual(sum(len(job["cases"]) for job in jobs),700)
        ids=set()
        for job in jobs:
            self.plan.validate_job(self.plan.encode(job))
            self.assertEqual(len(job["cases"]),35)
            self.assertEqual(job["missing_asset"],"widgets/panda-s2-absent.svg")
            self.assertEqual({c["asset"] for c in job["cases"]},{
                "widgets/background.svg","widgets/translucentbackground.svg",
                "widgets/panel-background.svg","solid/widgets/panel-background.svg","dialogs/background.svg"})
            self.assertEqual({tuple(c["size"]) for c in job["cases"]},{
                (24,24),(288,88),(288,120),(352,168),(1024,48),(352,56),(303,119)})
            ids.add((job["flavor"],job["scale"]))
        self.assertEqual(len(ids),20)
        self.assertEqual(self.plan.build_jobs(),jobs)

    def test_mutated_jobs_cannot_change_paths_bounds_hashes_or_identity(self):
        base=self.plan.build_jobs()[0]
        variants=[]
        for field,value in (("package_id","org.example.arbitrary"),("scale",True),("scale",float("nan"))):
            item=copy.deepcopy(base);item[field]=value;variants.append(item)
        for field,value in (("asset","../../escape.svg"),("size",[True,24]),("size",[0,24]),("id","../output")):
            item=copy.deepcopy(base);item["cases"][0][field]=value;variants.append(item)
        item=copy.deepcopy(base);item["cases"].append(item["cases"][0]);variants.append(item)
        item=copy.deepcopy(base);item["asset_sha256"]["widgets/background.svg"]="0"*64;variants.append(item)
        item=copy.deepcopy(base);item["execute"]=True;variants.append(item)
        for item in variants:
            with self.subTest(keys=list(item)),self.assertRaises(ValueError):
                self.plan.validate_job(json.dumps(item).encode())

    def test_duplicate_json_keys_are_refused(self):
        raw=self.plan.encode(self.plan.build_jobs()[0])
        raw=raw.replace(b'"schema_version":1',b'"schema_version":1,"schema_version":1')
        with self.assertRaisesRegex(ValueError,"duplicate"):
            self.plan.validate_job(raw)

    def test_asset_classification_does_not_equate_missing_and_unsupported(self):
        path="solid/widgets/panel-background.svg"
        self.assertEqual(self.plan.classify_asset(path,{}),"missing")
        self.assertEqual(self.plan.classify_asset(path,{path:b"fixture"}),"supported")
        for path in ("../escape.svg","widgets/unknown.svg","/live/settings"):
            self.assertEqual(self.plan.classify_asset(path,{}),"unsupported")

    def test_synthetic_pixels_can_pass_without_claiming_native_execution(self):
        p,rgba,mask,pw,ph=self.pixels()
        report=self.plan.analyze_pixels(rgba,mask,pw,ph,logical_size=(64,48),scale=1,surface=p["surface"])
        self.assertEqual(report["interior_holes"],0)
        self.assertFalse(report["native_runtime_verified"])
        self.assertEqual(report["fallback_status"],"unverified")

    def test_interior_holes_are_not_hidden_by_a_matching_mask(self):
        p,rgba,mask,pw,ph=self.pixels()
        rgba=bytearray(rgba);mask=bytearray(mask);i=((ph//2)*pw+pw//2)*4+3
        rgba[i]=mask[i]=0
        with self.assertRaisesRegex(ValueError,"interior"):
            self.plan.analyze_pixels(bytes(rgba),bytes(mask),pw,ph,logical_size=(64,48),scale=1,surface=p["surface"])

    def test_wrong_masks_exterior_paint_and_center_colors_are_refused(self):
        p,rgba,mask,pw,ph=self.pixels()
        variants=[]
        bad=bytearray(mask);bad[(ph//2*pw+pw//2)*4+3]=0;variants.append((rgba,bytes(bad),"mask"))
        bad=bytearray(rgba);bad[0:4]=bytes((255,0,0,255))
        bm=bytearray(mask);bm[3]=255;variants.append((bytes(bad),bytes(bm),"exterior"))
        bad=bytearray(rgba);i=(ph//2*pw+pw//2)*4;bad[i:i+3]=bytes((1,2,3));variants.append((bytes(bad),mask,"surface"))
        for image,alpha,reason in variants:
            with self.subTest(reason=reason),self.assertRaisesRegex(ValueError,reason):
                self.plan.analyze_pixels(image,alpha,pw,ph,logical_size=(64,48),scale=1,surface=p["surface"])

    def test_fractional_pixel_bounds_and_invalid_inputs(self):
        self.assertEqual(self.plan.pixel_size((303,119),1.25),(379,149))
        p,rgba,mask,pw,ph=self.pixels(303,119,1.25)
        self.plan.analyze_pixels(rgba,mask,pw,ph,logical_size=(303,119),scale=1.25,surface=p["surface"])
        with self.assertRaisesRegex(ValueError,"bounds"):
            self.plan.analyze_pixels(rgba,mask,pw-1,ph,logical_size=(303,119),scale=1.25,surface=p["surface"])
        for size,scale in (((True,24),1),((0,24),1),((24,24),float("nan")),((24,24),3)):
            with self.subTest(size=size,scale=scale),self.assertRaises(ValueError):
                self.plan.pixel_size(size,scale)

    def test_fixture_contract_and_data_only_cli(self):
        self.assertEqual(self.plan.check_fixture(),700)
        p=subprocess.run([sys.executable,"-B",str(ROOT/"theme/panda/common/native_frame_plan.py"),"--check"],capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertIn("700",p.stdout);self.assertIn("not executed",p.stdout)
        refused=subprocess.run([sys.executable,"-B",str(ROOT/"theme/panda/common/native_frame_plan.py"),"--execute"],capture_output=True,text=True)
        self.assertEqual(refused.returncode,2)
