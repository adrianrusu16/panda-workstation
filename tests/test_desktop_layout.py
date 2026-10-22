"""Geometry and preservation contracts; no native desktop interaction."""
import copy
import tempfile
from unittest.mock import patch
import importlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "theme/panda/common"))
CONFIG = ROOT / "theme/panda/common/desktop/layout.toml"
FIXTURE = ROOT / "tests/fixtures/desktop/fhd.json"


class DesktopLayoutTests(unittest.TestCase):
    def setUp(self):
        self.layout = importlib.import_module("desktop_layout")
        self.config = self.layout.load_config(CONFIG)
        self.fixture = json.loads(FIXTURE.read_text())

    def plan(self, **options):
        return self.layout.build_plan(self.config, self.fixture, **options)

    def test_geometry_matrix_has_five_cards_and_fixed_panel_heights(self):
        for resolution in ("fhd", "qhd"):
            for scale in (1, 1.25, 1.5):
                for presentation in ("compact", "expanded"):
                    with self.subTest(resolution=resolution, scale=scale, presentation=presentation):
                        if (resolution, scale, presentation) == ("fhd", 1.5, "expanded"):
                            with self.assertRaisesRegex(ValueError, "does not fit"):
                                self.plan(resolution=resolution, scale=scale, presentation=presentation)
                            continue
                        plan = self.plan(resolution=resolution, scale=scale, presentation=presentation)
                        self.assertEqual([x["role"] for x in plan["widgets"]], ["clock", "media", "weather", "cpu", "ram"])
                        self.assertEqual(plan["top_bar"]["rect"][3], 48)
                        self.assertEqual(plan["dock"]["rect"][3], 56)
                        width, height = plan["output"]["logical_size"]
                        self.assertAlmostEqual(plan["dock"]["rect"][0] * 2 + plan["dock"]["rect"][2], width)
                        self.assertEqual(plan["dock"]["native_properties"]["lengthMode"], "fit")
                        previous_bottom = 48
                        for card in plan["widgets"]:
                            x, y, w, h = card["rect"]
                            self.assertGreaterEqual(y, previous_bottom)
                            self.assertAlmostEqual(x + w + 24, width)
                            self.assertLessEqual(y + h, height - 56 - 8 - 24)
                            previous_bottom = y + h
                        self.assertEqual(plan["native_verified"], False)

    def test_dock_content_size_tracks_distinct_application_slots(self):
        small = self.plan()["dock"]["rect"][2]
        self.fixture["applications"].append("org.kde.kate.desktop")
        large = self.plan()["dock"]["rect"][2]
        self.assertEqual(large - small, 48)
        self.fixture["applications"] *= 200
        with self.assertRaises(ValueError):
            self.plan()

    def test_flavors_change_only_palette(self):
        plans = [self.plan(flavor=f) for f in ("minimal", "cyber", "gothic", "hybrid", "wave")]
        self.assertEqual(len({p["structural_sha256"] for p in plans}), 1)
        self.assertEqual(len({p["palette"]["primary"] for p in plans}), 5)

    def test_planning_is_deterministic_and_preserves_fixture(self):
        before = copy.deepcopy(self.fixture)
        first = self.plan()
        self.assertEqual(first, self.plan())
        self.assertEqual(self.fixture, before)
        self.assertEqual(first["preserved_fixture"], before)
        self.assertEqual(first["preserved_fixture"]["desktop_count"], 1)

    def test_explicit_binding_reuses_instance_and_reaches_no_change_plan(self):
        first = self.plan()
        for number, card in enumerate(first["widgets"], 200):
            self.fixture["applets"].append(dict(id=number, containment_id=149, plugin=card["plugin"], geometry=card["rect"], config={"keep": "opaque"}))
            self.fixture["bindings"][card["role"]] = number
        plan = self.plan()
        self.assertTrue(all(x["action"] == "keep" for x in plan["widgets"]))
        self.assertEqual([x["instance_id"] for x in plan["widgets"]], list(range(200, 205)))
        self.fixture["applets"][-1]["geometry"][1] += 1
        self.assertEqual(self.plan()["widgets"][-1]["action"], "move_requested")

    def test_unbound_existing_desktop_widget_is_not_duplicated(self):
        self.fixture["applets"].append(dict(id=200, containment_id=149, plugin=self.config["widgets"]["clock"]["plugin"], geometry=None, config={}))
        with self.assertRaisesRegex(ValueError, "binding"):
            self.plan()

    def test_invalid_schema_identity_and_binding_are_rejected(self):
        mutations = [
            lambda f: f.update(schema_version=True),
            lambda f: f.update(extra="unknown"),
            lambda f: f["output"].update(scale=float("nan")),
            lambda f: f["output"].update(scale=True),
            lambda f: f["output"].update(width=0),
            lambda f: f["applets"].append(copy.deepcopy(f["applets"][0])),
            lambda f: f["bindings"].update(clock=151),
            lambda f: f["bindings"].update(clock=999),
            lambda f: f["panels"][0]["applet_ids"].append(999),
            lambda f: f["applets"][0].update(containment_id=999),
            lambda f: f.update(desktop_count=0),
            lambda f: f["applets"][0].update(geometry=[False, 0, 10, 10]),
            lambda f: f["applets"][0]["config"].update(nonfinite=float("nan")),
            lambda f: f["applications"].append(f["applications"][0]),
        ]
        for mutate in mutations:
            self.fixture = json.loads(FIXTURE.read_text())
            mutate(self.fixture)
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):
                self.plan()


    def test_palette_final_symlink_is_refused(self):
        with tempfile.TemporaryDirectory(prefix="panda-desktop-palettes-") as temporary:
            root = Path(temporary)
            for slug in ("minimal", "cyber", "gothic", "hybrid", "pandawave"):
                target = root / "theme/panda" / slug / "theme.toml"
                target.parent.mkdir(parents=True)
                target.write_bytes((ROOT / "theme/panda" / slug / "theme.toml").read_bytes())
            target = root / "theme/panda/hybrid/theme.toml"
            target.unlink()
            target.symlink_to(ROOT / "theme/panda/hybrid/theme.toml")
            with patch.object(self.layout, "ROOT", root):
                with self.assertRaises((ValueError, OSError)):
                    self.plan()

    def test_configuration_rejects_unknown_fields_plugins_and_unsafe_geometry(self):
        for mutate in (
            lambda c: c.update(unknown=1),
            lambda c: c.update(schema_version=True),
            lambda c: c["top_bar"].update(height=47),
            lambda c: c["top_bar"].update(height=48.0),
            lambda c: c["dock"].update(height=55),
            lambda c: c["dock"].update(icon_size=100),
            lambda c: c["profiles"]["compact"].update(heights=[1, 2]),
            lambda c: c["widgets"]["cpu"].update(plugin="third.party.cpu"),
            lambda c: c.update(gap=-1),
        ):
            value = copy.deepcopy(self.config)
            mutate(value)
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):
                self.layout.validate_config(value)


    def test_reviewed_sensor_face_overrides_preserve_fixed_plugin_and_package(self):
        for role, face in (("cpu", "org.kde.ksysguard.horizontalbars"),
                           ("ram", "org.kde.ksysguard.linechart")):
            config = copy.deepcopy(self.config)
            config["widgets"][role]["face"] = face
            plan = self.layout.build_plan(config, self.fixture)
            widget = next(w for w in plan["widgets"] if w["role"] == role)
            self.assertEqual(widget["preferred_face"], face)
            self.assertFalse(widget["native_presentation_verified"])
        for role in ("cpu", "ram"):
            for key, value in (("face", "unknown.face"), ("face", "third.party.sensor"),
                               ("plugin", "third.party.plugin"), ("package", "unknown-package"),
                               ("face", [])):
                config = copy.deepcopy(self.config)
                config["widgets"][role][key] = value
                with self.subTest(role=role, key=key), self.assertRaises(ValueError):
                    self.layout.validate_config(config)

    def test_floating_dock_clearance_and_top_clock_are_explicit_intent(self):
        plan = self.plan()
        dock = plan["dock"]
        self.assertTrue(dock["floating"])
        self.assertEqual(dock["bottom_clearance"], 8)
        self.assertEqual(dock["rect"][1] + dock["rect"][3] + 8, plan["output"]["logical_size"][1])
        self.assertEqual(dock["native_properties"]["alignment"], "center")
        self.assertEqual(dock["native_properties"]["location"], "bottom")
        self.assertIn("clock", plan["top_bar"]["roles"])
        self.assertIn("system_tray", plan["top_bar"]["roles"])
        self.assertEqual(len([w for w in plan["widgets"] if w["role"] == "clock"]), 1)
        self.assertEqual(plan["preserved_fixture"], self.fixture)

if __name__ == "__main__":
    unittest.main()
