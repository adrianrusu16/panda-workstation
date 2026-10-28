"""Offline native style contracts; fixtures and CPU rasterization only."""
import copy
import importlib
from io import BytesIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "theme/panda/common"))


class PlasmaStyleTests(unittest.TestCase):
    def setUp(self):
        try:
            self.style = importlib.import_module("plasma_style")
        except ModuleNotFoundError:
            self.fail("native Plasma Style generator is not implemented")
        from palette import load_family
        self.family = load_family(ROOT / "theme/panda")

    def test_all_five_packages_are_deterministic_and_structurally_identical(self):
        first = self.style.build_packages()
        self.assertEqual(first, self.style.build_packages())
        self.assertEqual(len(first), 40)
        shapes = []
        for slug, theme in self.family.items():
            prefix = "panda-" + slug + "-s1/"
            own = {k[len(prefix):]: v for k,v in first.items() if k.startswith(prefix)}
            self.assertEqual(set(own), set(self.style.PACKAGE_FILES))
            metadata = json.loads(own["metadata.json"])
            self.assertEqual(metadata["KPlugin"]["Id"], "panda-" + slug + "-s1")
            self.assertEqual(metadata["X-Plasma-API"], "5.0")
            self.assertIn(b"FallbackTheme=breeze-dark", own["plasmarc"])
            self.assertNotIn(b"enabled=true", own["plasmarc"])
            for kind in self.style.ASSETS:
                self.style.validate_frame(own[kind], theme.palette, kind)
            shapes.append(self.style.structure_digest(own,theme.palette))
        self.assertEqual(len(set(shapes)),1)

    def test_frame_contains_exact_parts_and_margin_hints(self):
        theme=self.family["cyber"]
        for kind,margin in self.style.ASSETS.items():
            raw=self.style.frame_svg(theme.palette,kind)
            tree=self.style.validate_frame(raw,theme.palette,kind)
            ids={node.get("id"):node for node in tree.iter() if node.get("id")}
            self.assertTrue(set(self.style.PARTS)<=set(ids))
            self.assertTrue({"mask-"+x for x in self.style.PARTS}<=set(ids))
            self.assertEqual(float(ids["hint-top-margin"].get("height")),margin)
            self.assertEqual(float(ids["hint-left-margin"].get("width")),margin)
            self.assertIn("hint-stretch-borders",ids)
            self.assertNotIn("blurred-center",ids)
            self.assertNotIn("shadow-center",ids)

    def test_scripts_resources_entities_and_off_palette_paint_are_refused(self):
        theme=self.family["cyber"];kind="widgets/background.svg"
        raw=self.style.frame_svg(theme.palette,kind)
        mutations=[
            raw.replace(b"</svg>",b"<script>alert(1)</script></svg>"),
            b'<?xml-stylesheet href="https://example.invalid/style.css"?>'+raw,
            raw.replace(b"</svg>",b'<image href="https://example.invalid/x"/></svg>'),
            raw.replace(b"</svg>",b'<use href="#center"/></svg>'),
            raw.replace(b"<svg ",b'<svg onload="x()" ',1),
            raw.replace(b"<svg ",b'<!DOCTYPE svg [<!ENTITY x "bad">]><svg ',1),
            raw.replace(theme.palette["surface"].encode(),b"#123456"),
            raw.replace(b'id="center"',b'id="unexpected-center"'),
            raw.replace(b'opacity="0"',b'opacity="0.5"',1),
        ]
        for data in mutations:
            with self.subTest(data=data[-80:]),self.assertRaises(ValueError):
                self.style.validate_frame(data,theme.palette,kind)

    def test_selected_text_maps_to_reviewed_on_selection_role(self):
        import configparser
        for theme in self.family.values():
            parser=configparser.ConfigParser(interpolation=None);parser.optionxform=str
            parser.read_string(self.style.colors_file(theme).decode())
            expected=",".join(str(int(theme.palette["on_selection"][i:i+2],16)) for i in (1,3,5))
            for key,value in parser["Colors:Selection"].items():
                if key.startswith("Foreground"):self.assertEqual(value,expected,(theme.slug,key))

    def test_rejected_palette_and_unknown_assets(self):
        theme=self.family["cyber"];bad=dict(theme.palette);bad["surface"]="url(https://example.invalid)"
        for palette,kind in ((bad,"widgets/background.svg"),(theme.palette,"widgets/tasks.svg")):
            with self.assertRaises(ValueError):self.style.frame_svg(palette,kind)

    def test_writer_preserves_identity_and_refuses_conflicts_before_any_write(self):
        import os
        with tempfile.TemporaryDirectory(prefix="panda-style-write-") as td:
            root=Path(td)
            packages=self.style.build_packages()
            names=list(packages)[:2]
            outputs={self.style.PACKAGE_ROOT+n:packages[n] for n in names}
            self.style.write_reviewed(outputs,root=root)
            target=root/next(iter(outputs));before=target.stat()
            self.style.write_reviewed(outputs,root=root)
            self.assertEqual((before.st_ino,before.st_mtime_ns),(target.stat().st_ino,target.stat().st_mtime_ns))
            target.write_bytes(b"operator owned conflict")
            extra=self.style.PACKAGE_ROOT+list(packages)[2]
            with self.assertRaises(ValueError):
                self.style.write_reviewed({extra:packages[list(packages)[2]],**outputs},root=root)
            self.assertEqual(target.read_bytes(),b"operator owned conflict")
            self.assertFalse((root/extra).exists())
            sentinel=root/"external";sentinel.mkdir()
            link=root/"alias";link.symlink_to(sentinel,target_is_directory=True)
            with self.assertRaises(ValueError):self.style.write_reviewed(outputs,root=link)

    def test_writer_parent_replacement_cannot_redirect_a_new_file(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory(prefix="panda-style-race-") as td:
            root=Path(td)/"repo";root.mkdir()
            packages=self.style.build_packages();first="panda-cyber-s1/metadata.json";second="panda-cyber-s1/colors"
            existing=root/self.style.PACKAGE_ROOT/first;existing.parent.mkdir(parents=True);existing.write_bytes(packages[first])
            outside=Path(td)/"outside";outside.mkdir()
            read=self.style.read_regular
            moved=False
            def replace_parent(path,*args,**kwargs):
                nonlocal moved
                data=read(path,*args,**kwargs)
                if Path(path)==existing and not moved:
                    moved=True
                    existing.parent.rename(existing.parent.with_name("retained"))
                    existing.parent.symlink_to(outside,target_is_directory=True)
                return data
            with patch("plasma_style.read_regular",side_effect=replace_parent):
                with self.assertRaises((ValueError,OSError)):
                    self.style.write_reviewed({self.style.PACKAGE_ROOT+second:packages[second],
                                               self.style.PACKAGE_ROOT+first:packages[first]},root=root)
            self.assertFalse((outside/"colors").exists())

    def test_generated_repository_files_match_generator(self):
        expected=self.style.build_packages()
        self.assertEqual(self.style.check_packages(),len(expected))

    def test_colors_use_only_canonical_role_values_and_sufficient_border_contrast(self):
        from palette import contrast_ratio
        packages=self.style.build_packages()
        for slug,theme in self.family.items():
            raw=packages["panda-"+slug+"-s1/colors"]
            self.assertTrue(raw.endswith(b"\n") and not raw.endswith(b"\n\n"), "color file must have exactly one final newline")
            colors=self.style.parse_colors(raw)
            allowed={tuple(int(v[i:i+2],16) for i in (1,3,5)) for v in theme.palette.values()}
            self.assertTrue(set(colors)<=allowed)
            self.assertGreaterEqual(contrast_ratio(theme.palette["border"],theme.palette["surface"]),3)
