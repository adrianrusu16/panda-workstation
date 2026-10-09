"""Native fixture outputs: pin semantic mappings, opacity and safe boundaries."""

import importlib
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import tomllib
import unittest

COMMON = Path(__file__).resolve().parents[1] / "theme/panda/common"
sys.path.insert(0, str(COMMON))
from palette import load_family, contrast_ratio


class RenderingContracts(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec("render"), "Phase 3A renderer missing")
        self.api = importlib.import_module("render")
        self.family = load_family(COMMON.parent)

    def test_native_formats_and_paired_semantics_for_every_flavor(self):
        import configparser
        for theme in self.family.values():
            with self.subTest(theme=theme.slug):
                ghostty = self.api.render_bytes("ghostty", theme).decode()
                kitty = self.api.render_bytes("kitty", theme).decode()
                self.assertIn("background = " + theme.palette["background"], ghostty)
                self.assertIn("background-opacity = 1", ghostty)
                self.assertIn("selection-foreground = " + theme.palette["on_selection"], ghostty)
                self.assertIn("background_opacity 1", kitty)
                self.assertIn("cursor " + theme.palette["focus"], kitty)
                self.assertNotIn("font", ghostty + kitty)
                ini = configparser.ConfigParser()
                ini.read_string(self.api.render_bytes("konsole", theme).decode())
                self.assertEqual(ini["General"]["Opacity"], "1")
                starship = tomllib.loads(self.api.render_bytes("starship", theme).decode())
                self.assertEqual(starship["palettes"]["panda"]["accent"], theme.palette["accent_text"])
                ff = json.loads(self.api.render_bytes("fastfetch", theme))
                self.assertEqual(ff["display"]["color"]["keys"], theme.palette["accent_text"])
                fish = self.api.render_bytes("fish", theme).decode()
                self.assertIn("set -g fish_color_error '" + theme.palette["error"] + "'", fish)
                for fg, bg in (("text", "background"), ("accent_text", "background"),
                               ("on_selection", "selection")):
                    self.assertGreaterEqual(contrast_ratio(theme.palette[fg], theme.palette[bg]), 4.5)

    def test_shared_ansi_mapping_is_readable_and_repeatable(self):
        for theme in self.family.values():
            for component in self.api.COMPONENTS:
                rendered = self.api.render_bytes(component, theme)
                self.assertEqual(rendered, self.api.render_bytes(component, theme))
                self.api.validate_rendered(component, rendered, theme)
            for index, role in self.api.ansi_roles().items():
                if index != 0:
                    self.assertGreaterEqual(contrast_ratio(theme.palette[role], theme.palette["background"]), 4.5)

    def test_unknown_components_and_corrupt_native_content_are_rejected(self):
        theme = self.family["hybrid"]
        with self.assertRaises(ValueError):
            self.api.render_bytes("plasma", theme)
        for component in self.api.COMPONENTS:
            with self.subTest(component=component), self.assertRaises(ValueError):
                self.api.validate_rendered(component, b"invalid\x00", theme)

    def test_public_renderer_requires_enrolled_temporary_destination(self):
        from fixture_fs import initialize_fixture
        with tempfile.TemporaryDirectory(prefix="panda-theme-fixture-") as directory:
            root = Path(directory)
            initialize_fixture(root)
            outputs = self.api.render_component("ghostty", self.family["gothic"], root / "state/render")
            self.assertEqual(outputs, [root / "state/render/ghostty.conf"])
            self.assertIn(b"background = #090708", outputs[0].read_bytes())
            before = outputs[0].read_bytes()
            with self.assertRaises(ValueError):
                self.api.render_component("ghostty", self.family["cyber"], root / "config")
            self.assertEqual(outputs[0].read_bytes(), before)

    def test_standalone_staging_refuses_unknown_existing_content(self):
        from fixture_fs import initialize_fixture
        with tempfile.TemporaryDirectory(prefix="panda-theme-fixture-") as directory:
            root = Path(directory)
            initialize_fixture(root)
            path = root / "state/render/ghostty.conf"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"user-owned staging data")
            with self.assertRaises(ValueError):
                self.api.render_component("ghostty", self.family["hybrid"], path.parent)
            self.assertEqual(path.read_bytes(), b"user-owned staging data")

    def test_sourced_fish_fragment_sets_colors_instead_of_comments(self):
        from fixture_fs import initialize_fixture
        with tempfile.TemporaryDirectory(prefix="panda-theme-fixture-") as directory:
            root = Path(directory)
            initialize_fixture(root)
            rendered = self.api.render_component("fish", self.family["gothic"], root / "state/render")[0]
            env = {**os.environ, "HOME": directory, "XDG_CONFIG_HOME": directory + "/config",
                   "XDG_DATA_HOME": directory + "/data", "XDG_CACHE_HOME": directory + "/cache",
                   "XDG_STATE_HOME": directory + "/state"}
            script = 'source $argv[1]; printf "%s\\n" $fish_color_normal $fish_color_error $fish_color_selection'
            result = subprocess.run(["fish", "--no-config", "-c", script, "--", str(rendered)],
                                    env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.splitlines(), ["#F0EAEC", "#E99B91", "--background=#741D32", "#F0EAEC"])


if __name__ == "__main__":
    unittest.main()
