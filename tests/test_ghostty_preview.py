"""Offline contracts for the standalone Panda Ghostty trial."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
COMMON = ROOT / "theme/panda/common"
sys.path.insert(0, str(COMMON))

from ghostty_preview import preview_files
from palette import contrast_ratio, load_family, terminal_heading_roles
from render import render_bytes


class GhosttyPreviewTests(unittest.TestCase):
    def test_heading_roles_match_each_flavor_and_are_readable(self):
        expected = {
            "minimal": ("secondary", "primary"),
            "cyber": ("accent_text", "secondary"),
            "gothic": ("accent_text", "focus"),
            "hybrid": ("accent_text", "secondary"),
            "pandawave": ("accent_text", "focus"),
        }
        family = load_family(COMMON.parent)
        preview = preview_files(family)["index.html"].decode()
        self.assertEqual(set(family), set(expected))
        for slug, (prominent, secondary) in expected.items():
            with self.subTest(slug=slug):
                theme = family[slug]
                self.assertEqual(terminal_heading_roles(theme), (prominent, secondary))
                colors = theme.palette
                card = next(card for card in preview.split("<section ")
                            if f'href="{slug}/config.ghostty"' in card)
                self.assertIn(f"--accent:{colors[prominent]};", card)
                self.assertIn(f"--section:{colors[secondary]};", card)
                for role in (prominent, secondary):
                    self.assertGreaterEqual(contrast_ratio(colors[role], colors["background"]), 4.5)

    def test_profiles_keep_trial_behavior_and_use_canonical_colors(self):
        family = load_family(COMMON.parent)
        files = preview_files(family)
        self.assertEqual(files, preview_files(family))
        for slug, theme in family.items():
            with self.subTest(slug=slug):
                profile = files[f"{slug}/config.ghostty"].decode()
                self.assertIn(render_bytes("ghostty", theme).decode(), profile)
                for line in (
                    "font-family = JetBrainsMono Nerd Font Mono",
                    "window-padding-x = 10", "window-padding-y = 8",
                    "shell-integration = fish", "window-decoration = auto",
                    "keybind = ctrl+shift+enter=new_split:auto",
                    "keybind = ctrl+shift+right=goto_split:right",
                    "window-theme = ghostty",
                    "window-titlebar-background = " + theme.palette["surface"],
                    "window-titlebar-foreground = " + theme.palette["text"],
                ):
                    self.assertIn(line + "\n", profile)
                self.assertEqual(profile.count("\nbackground = "), 1)
                self.assertEqual(profile.count("\npalette = "), 16)
                self.assertNotIn("config-file", profile)
                fish = files[f"{slug}/panda.fish"].decode()
                command_color = theme.palette["secondary" if slug == "minimal" else "accent_text"]
                self.assertIn(f"set -g fish_color_command '{command_color}' --bold\n", fish)

    def test_cyber_dots_are_labeled_illustration_with_canonical_colors(self):
        files = preview_files(load_family(COMMON.parent))
        preview = files["index.html"].decode()
        for color in ("#20D7F2", "#52E397", "#E6F7FA"):
            self.assertIn(f'<i style="background:{color}"></i>', preview)
        self.assertIn("illustrative", preview)
        self.assertNotIn("<i", files["cyber/config.ghostty"].decode())
        for slug in ("minimal", "cyber", "gothic", "hybrid", "pandawave"):
            self.assertIn(f'href="{slug}/config.ghostty"', preview)
