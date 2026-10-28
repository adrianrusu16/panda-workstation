"""Nine-slice offline model; not a KSvg/Plasma runtime test."""
import importlib
from io import BytesIO
from pathlib import Path
import sys
import unittest
import math
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"theme/panda/common"))

class PlasmaStylePreviewTests(unittest.TestCase):
    def setUp(self):
        try:
            self.preview=importlib.import_module("plasma_style_preview")
            self.style=importlib.import_module("plasma_style")
        except ModuleNotFoundError:
            self.fail("offline native-style preview model is not implemented")
        from palette import load_family
        self.family=load_family(ROOT/"theme/panda")

    def test_no_holes_or_translucency_at_slice_seams_for_all_flavors_and_scales(self):
        for theme in self.family.values():
            for kind in self.style.ASSETS:
                raw=self.style.frame_svg(theme.palette,kind)
                for w,h in ((24,24),(288,88),(352,168),(1024,48),(352,56),(303,119)):
                    for scale in (1,1.25,1.5,2):
                        image=self.preview.compose_frame(raw,theme.palette,kind,w,h,scale)
                        width,height=image.get_width(),image.get_height()
                        cap=round(12*scale)
                        for x,y in ((width//2,height//2),(cap,height//2),(width-cap-1,height//2),(width//2,cap),(width//2,height-cap-1)):
                            if 0<=x<width and 0<=y<height:
                                self.assertEqual(self.preview.rgba(image,x,y)[3],255,(theme.slug,kind,w,h,scale,x,y))
                        self.assertLess(self.preview.rgba(image,0,0)[3],255)

    def test_center_color_is_exact_and_masks_match_visible_silhouette(self):
        theme=self.family["cyber"];kind="widgets/background.svg"
        data=self.style.frame_svg(theme.palette,kind)
        image=self.preview.compose_frame(data,theme.palette,kind,288,88,1)
        expected=tuple(int(theme.palette["surface"][i:i+2],16) for i in (1,3,5))
        self.assertEqual(self.preview.rgba(image,144,44),(*expected,255))
        mask=self.preview.compose_frame(data,theme.palette,kind,288,88,1,prefix="mask-")
        for x in range(288):
            for y in (0,1,11,44,76,86,87):
                self.assertEqual(self.preview.rgba(image,x,y)[3],self.preview.rgba(mask,x,y)[3])

    def test_bad_sizes_and_prefixes_fail_before_rendering(self):
        theme=self.family["cyber"];kind="widgets/background.svg";raw=self.style.frame_svg(theme.palette,kind)
        for w,h,scale in ((23,88,1),(288,0,1),(True,88,1),(288,88,float("nan")),(100000,88,1),(288,88,0)):
            with self.subTest(size=(w,h,scale)),self.assertRaises(ValueError):
                self.preview.compose_frame(raw,theme.palette,kind,w,h,scale)
        with self.assertRaises(ValueError):
            self.preview.compose_frame(raw,theme.palette,kind,288,88,1,prefix="blurred-")

    def test_previews_repeat_and_are_labelled_as_models(self):
        files,report=self.preview.make_previews()
        again,second=self.preview.make_previews()
        self.assertEqual(files,again);self.assertEqual(report,second)
        self.assertFalse(report["native_verified"])
        self.assertEqual(report["label"],"OFFLINE SVG NINE-SLICE MODEL — NATIVE UNVERIFIED")
        self.assertEqual(len(report["flavors"]),5)
        self.assertIn("five-flavor-gallery.png",files)
        self.assertIn("cyber-d4b-comparison.png",files)
        self.assertTrue(all(data.startswith(b"\x89PNG") for name,data in files.items() if name.endswith(".png")))

    def test_fixed_writer_refuses_conflicts_and_never_exposes_install_destination(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            target=Path(td)/"panda"/"example"
            with self.assertRaises(ValueError):
                self.style.write_reviewed({"../escape":b"bad"},root=Path(td))
        self.assertNotIn("--install",self.style.cli_help())
