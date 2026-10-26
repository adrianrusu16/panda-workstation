"""Offline visual contracts. No desktop, sensor, provider or package operations."""
import copy
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "theme/panda/common"))
VISUAL = ROOT / "tests/fixtures/desktop/visual"
FLAVORS = ("minimal", "cyber", "gothic", "hybrid", "wave")


class DesktopVisualTests(unittest.TestCase):
    def setUp(self):
        self.style = importlib.import_module("visual_style")
        self.scene_module = importlib.import_module("desktop_visual_fixture")
        self.renderer = importlib.import_module("desktop_visual")
        self.layout = importlib.import_module("desktop_layout")
        self.config = self.layout.load_config(ROOT / "theme/panda/common/desktop/layout.toml")
        self.fixture = json.loads((VISUAL / "dock-seven.json").read_text())
        self.scene = self.scene_module.load_scene(VISUAL / "playing.json")

    def plan(self, **kwargs):
        return self.layout.build_plan(self.config, self.fixture, **kwargs)

    def render(self, **kwargs):
        return self.renderer.render_visual(self.plan(**kwargs), self.scene)

    def test_spec_is_semantic_strict_and_radius_is_twelve(self):
        spec = self.style.load_spec()
        self.assertEqual(spec["radius"], 12)
        for mutate in (lambda s: s.update(radius=True),
                       lambda s: s.update(radius=500),
                       lambda s: s.update(extra="unknown"),
                       lambda s: s["tokens"].update(graph="#ff00ff"),
                       lambda s: s["padding"].update(compact=0)):
            value = copy.deepcopy(spec)
            mutate(value)
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.style.validate_spec(value)

    def test_scene_rejects_unknown_nonfinite_and_misleading_unavailable_data(self):
        mutations = (
            lambda s: s.update(extra=1),
            lambda s: s.update(schema_version=True),
            lambda s: s["cpu"].update(percent=float("nan")),
            lambda s: s["cpu"].update(percent=True),
            lambda s: s["cpu"].update(state="missing"),
            lambda s: s["ram"].update(total_gib=0),
            lambda s: s["weather"].update(state="offline"),
            lambda s: s["media"].update(elapsed=999999),
            lambda s: s["dock"][0].update(icon="../private"),
            lambda s: s["dock"][0].update(running="true"),
            lambda s: s["clock"].update(date="bad\u0000text"),
        )
        for mutate in mutations:
            scene = copy.deepcopy(self.scene)
            mutate(scene)
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):
                self.scene_module.validate_scene(scene)
        with tempfile.TemporaryDirectory(prefix="panda-visual-json-") as td:
            path = Path(td) / "scene.json"
            path.write_text('{"schema_version":1,"schema_version":1}')
            with self.assertRaises(ValueError):
                self.scene_module.load_scene(path)

    def test_actual_font_metrics_are_pinned_and_outline_text(self):
        text = importlib.import_module("visual_text").get_metrics()
        self.assertGreater(text.measure("WWWW", 14)["width"], text.measure("iiii", 14)["width"])
        self.assertEqual(text.provenance["family"], "Noto Sans")
        self.assertGreater(text.measure("Panda · Καλημέρα · Привет", 14)["width"], 0)
        self.assertEqual(len(text.provenance["sha256"]), 64)
        with self.assertRaisesRegex(ValueError, "glyph"):
            text.measure("\U0001f600", 14)
        svg, audit = self.render()
        self.assertNotIn("<text", svg)
        self.assertIn("font_metrics", audit)
        self.assertTrue(any(x.get("kind") == "text" for x in audit["elements"]))

    def test_tight_fit_actual_text_icons_and_controls_stay_within_bounds(self):
        for scale, presentation in ((1.25, "expanded"), (1.5, "compact")):
            for name in ("playing", "unavailable", "paused", "long-text"):
                self.scene = self.scene_module.load_scene(VISUAL / (name + ".json"))
                svg, audit = self.render(resolution="fhd", scale=scale, presentation=presentation)
                self.assertEqual(audit["bounds_failures"], [])
                for item in audit["elements"]:
                    x, y, w, h = item["bounds"]
                    a, b, c, d = item["paint"]
                    with self.subTest(case=(scale, presentation, name), item=item["tag"]):
                        self.assertGreaterEqual(a + 0.02, x)
                        self.assertGreaterEqual(b + 0.02, y)
                        self.assertLessEqual(a + c, x + w + 0.02)
                        self.assertLessEqual(b + d, y + h + 0.02)
                shapes = [x for x in audit["elements"] if x["kind"] in ("text", "icon") and x["owner"] in ("clock","media","weather","cpu","ram")]
                for i, left in enumerate(shapes):
                    for right in shapes[i+1:]:
                        if left["owner"] != right["owner"]:
                            continue
                        x,y,w,h = left["paint"];a,b,c,d = right["paint"]
                        overlap_w = min(x+w,a+c)-max(x,a)
                        overlap_h = min(y+h,b+d)-max(y,b)
                        self.assertFalse(overlap_w > 0.02 and overlap_h > 0.02,
                                         (left["tag"],right["tag"]))
                self.assertNotIn("clipPath", svg)  # clipping must not hide layout defects

    def test_matrix_preserves_d4a_decisions_and_flavor_structure(self):
        receipt = json.loads((VISUAL / "d4a-baseline.json").read_text())
        base = json.loads((ROOT / "tests/fixtures/desktop/fhd.json").read_text())
        accepts = refuses = 0
        for resolution in ("fhd", "qhd"):
            for scale in (1, 1.25, 1.5):
                for presentation in ("compact", "expanded"):
                    key = f"{resolution}/{scale:g}/{presentation}"
                    for flavor in FLAVORS:
                        if key not in receipt["structures"]:
                            with self.assertRaisesRegex(ValueError, "does not fit"):
                                self.layout.build_plan(self.config, base, resolution=resolution,
                                    scale=scale, presentation=presentation, flavor=flavor)
                            refuses += 1
                        else:
                            plan = self.layout.build_plan(self.config, base, resolution=resolution,
                                    scale=scale, presentation=presentation, flavor=flavor)
                            self.assertEqual(plan["structural_sha256"], receipt["structures"][key])
                            svg, audit = self.render(resolution=resolution, scale=scale,
                                                     presentation=presentation, flavor=flavor)
                            ET.fromstring(svg)
                            self.assertEqual(audit["bounds_failures"], [])
                            accepts += 1
        self.assertEqual((accepts, refuses), (55, 5))
        for path, expected in receipt["files"].items():
            self.assertEqual(hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), expected, path)

    def test_states_never_draw_healthy_values_for_missing_sensors(self):
        self.scene = self.scene_module.load_scene(VISUAL / "unavailable.json")
        svg, audit = self.render()
        labels = [x.get("text", "") for x in audit["elements"]]
        self.assertTrue(any("Sensor unavailable" in t for t in labels))
        self.assertTrue(any("Offline" in t for t in labels))
        self.assertFalse(any(x["tag"].endswith(("cpu-series", "ram-fill")) for x in audit["elements"]))
        self.assertNotIn("0%", " ".join(labels))
        self.assertIn("No player", " ".join(labels))

    def test_face_overrides_are_independent_and_do_not_change_plugin_ids(self):
        self.config["widgets"]["cpu"]["face"] = "org.kde.ksysguard.horizontalbars"
        self.config["widgets"]["ram"]["face"] = "org.kde.ksysguard.linechart"
        plan = self.plan()
        svg, audit = self.renderer.render_visual(plan, self.scene)
        self.assertEqual(audit["faces"], {"cpu": "org.kde.ksysguard.horizontalbars",
                                        "ram": "org.kde.ksysguard.linechart"})
        self.assertEqual(plan["widgets"][3]["plugin"], "org.kde.plasma.systemmonitor.cpu")

    def test_contrast_all_flavors_records_candidate_failures_without_palette_changes(self):
        for flavor in FLAVORS:
            plan = self.plan(flavor=flavor)
            report = self.style.contrast_report(plan["palette"])
            self.assertTrue(report["used"])
            self.assertTrue(all(x["pass"] for x in report["used"]), report)
            if flavor == "gothic":
                self.assertTrue(any(not x["pass"] for x in report["candidates"]))

    def test_svg_is_self_contained_safe_labelled_and_deterministic(self):
        before = copy.deepcopy((self.fixture, self.scene))
        self.scene["media"]["title"] = '<script> & "fixture"'
        first, audit = self.render()
        second, _ = self.render()
        self.assertEqual(first, second)
        root = ET.fromstring(first)
        self.assertIn("SYNTHETIC OFFLINE DESIGN", first)
        self.assertIn("NATIVE UNVERIFIED", first)
        self.assertNotIn("<script>", first)
        for item in root.iter():
            self.assertNotIn(item.tag.rsplit("}", 1)[-1], ("script", "foreignObject", "text"))
            for key, value in item.attrib.items():
                self.assertFalse(key.lower().startswith("on"))
                if key.endswith("href"):
                    self.assertTrue(value.startswith(("#", "data:image/png;base64,")), value)
        self.assertEqual(self.fixture, before[0])
        self.assertEqual(self.scene["cpu"], before[1]["cpu"])

    def test_dock_identity_mismatch_and_multiple_selection_are_refused(self):
        self.scene["dock"][0]["application"] = "unexpected.desktop"
        with self.assertRaises(ValueError):
            self.renderer.render_visual(self.plan(), self.scene)
        self.scene = self.scene_module.load_scene(VISUAL / "playing.json")
        for app in self.scene["dock"][:2]:
            app.update(selected=True, running=True)
        with self.assertRaises(ValueError):
            self.scene_module.validate_scene(self.scene)

    def test_extreme_numbers_are_cleanly_refused(self):
        scene = copy.deepcopy(self.scene)
        scene["cpu"]["percent"] = 10 ** 400
        with self.assertRaises(ValueError):
            self.scene_module.validate_scene(scene)

    def test_gap_partial_stale_and_no_host_writes(self):
        scene = copy.deepcopy(self.scene)
        scene["cpu"]["history"] = [10, 15, None, 20, 30]
        scene["ram"].update(state="partial", total_gib=None)
        scene["weather"]["state"] = "stale"
        svg, audit = self.renderer.render_visual(self.plan(), scene)
        labels = " ".join(x.get("text", "") for x in audit["elements"])
        self.assertIn("Total unknown", labels)
        self.assertIn("Stale sample", labels)
        series = next(x for x in audit["elements"] if x["tag"] == "cpu-series")
        self.assertEqual(series["samples"], scene["cpu"]["history"])
        path = next(e for e in ET.fromstring(svg).iter() if e.attrib.get("data-tag") == "cpu-series")
        self.assertEqual(path.attrib["d"].count("M"), 2)
        import os
        with tempfile.TemporaryDirectory(prefix="panda-visual-no-host-") as td:
            home = Path(td)
            env = {**os.environ, "HOME":td, "XDG_CONFIG_HOME":td+"/config",
                   "XDG_DATA_HOME":td+"/data", "XDG_CACHE_HOME":td+"/cache",
                   "XDG_STATE_HOME":td+"/state", "XDG_RUNTIME_DIR":td+"/runtime",
                   "DBUS_SESSION_BUS_ADDRESS":"disabled", "WAYLAND_DISPLAY":"disabled",
                   "DISPLAY":"", "PYTHONDONTWRITEBYTECODE":"1"}
            paths = [VISUAL/"playing.json", VISUAL/"dock-seven.json"]
            before = [(p.stat().st_ino,p.stat().st_mtime_ns,hashlib.sha256(p.read_bytes()).hexdigest()) for p in paths]
            result = subprocess.run([sys.executable,"-B",str(ROOT/"theme/panda/common/desktop_cli.py"),
                     "preview","--fixture",str(paths[1]),"--visual-fixture",str(paths[0])],
                     env=env,capture_output=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(list(home.iterdir()),[])
            after = [(p.stat().st_ino,p.stat().st_mtime_ns,hashlib.sha256(p.read_bytes()).hexdigest()) for p in paths]
            self.assertEqual(before,after)

    def test_malformed_asset_inventory_is_cleanly_refused(self):
        from unittest.mock import patch
        assets = importlib.import_module("visual_assets")
        with tempfile.TemporaryDirectory(prefix="panda-visual-assets-") as td:
            root = Path(td)
            (root / "provenance.json").write_text("{}")
            with patch.object(assets, "ASSETS", root):
                with self.assertRaises(ValueError):
                    assets.verified_assets()

    def test_icon_css_is_scoped_and_internal_gradient_bindings_survive(self):
        assets = importlib.import_module("visual_assets")
        _, _, icons = assets.verified_assets()
        root = assets.icon_tree(icons["offline"]["svg"], "review-", "#ffffff")
        self.assertFalse(any(e.tag.endswith("}style") for e in root.iter()))
        files = assets.icon_tree(icons["files"]["svg"], "review-", "#ffffff")
        ids = {e.attrib["id"] for e in files.iter() if "id" in e.attrib}
        for node in files.iter():
            if "href" in node.attrib:
                self.assertIn(node.attrib["href"][1:], ids)
        for source in ('<svg xmlns="http://www.w3.org/2000/svg"><script/></svg>',
                       '<svg xmlns="http://www.w3.org/2000/svg" onload="evil()"/>'):
            with self.assertRaises(ValueError):
                assets.icon_tree(source, "review-", "#ffffff")

    def test_visual_cli_is_explicit_read_only_and_rejects_apply(self):
        cli = ROOT / "theme/panda/common/desktop_cli.py"
        args = [sys.executable, "-B", str(cli), "preview", "--fixture",
                str(VISUAL / "dock-seven.json"), "--visual-fixture", str(VISUAL / "paused.json")]
        first = subprocess.run(args, capture_output=True, timeout=20)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertIn(b"SYNTHETIC OFFLINE DESIGN", first.stdout)
        second = subprocess.run(args, capture_output=True, timeout=20)
        self.assertEqual(first.stdout, second.stdout)
        for extra in (["--apply"], ["--composition", "--flavor", "hybrid"]):
            result = subprocess.run(args + extra, capture_output=True, timeout=20)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn(b"<svg", result.stdout)


if __name__ == "__main__":
    unittest.main()
