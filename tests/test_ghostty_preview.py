"""Offline contracts for the standalone Panda Ghostty trial."""

from contextlib import redirect_stderr
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
COMMON = ROOT / "theme/panda/common"
sys.path.insert(0, str(COMMON))

import ghostty_preview
import terminal_preview
from ghostty_preview import preview_files
from palette import contrast_ratio, load_family, terminal_heading_roles
from render import ansi_roles, render_bytes, render_fish, render_ghostty_profile


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


class TerminalV2PreviewTests(unittest.TestCase):
    version_args = ["--palette-version", "v2"]
    names = ("config-v2.ghostty", "panda-v2.fish", "starship-v2.toml", "fastfetch-v2.json")

    def test_v2_renders_only_the_four_reviewed_consumers_and_labels_them(self):
        family = load_family(COMMON.parent, palette_version="v2")
        files = preview_files(family, palette_version="v2")
        self.assertEqual(files, preview_files(family, palette_version="v2"))
        self.assertEqual(set(files), {"index.html"} | {
            f"{slug}/{name}" for slug in family for name in self.names
        })
        html = files["index.html"].decode()
        self.assertIn("<h1>Panda Terminal and Shell V2</h1>", html)
        self.assertIn("2.481803:1", html)
        self.assertNotIn("Ghostty V1", html)
        self.assertNotIn('<span class="dots"', html)
        legacy = load_family(COMMON.parent)
        for slug, theme in family.items():
            with self.subTest(slug=slug):
                for name in self.names:
                    self.assertIn(f'href="{slug}/{name}"', html)
                ghostty, fish, starship, fastfetch = (files[f"{slug}/{name}"] for name in self.names)
                self.assertEqual(ghostty, render_ghostty_profile(theme))
                self.assertEqual(fish, render_fish(theme, trial=True).encode())
                self.assertEqual(starship, render_bytes("starship", theme))
                self.assertEqual(fastfetch, render_bytes("fastfetch", theme))

                colors = theme.palette
                config = ghostty.decode().splitlines()
                self.assertEqual([line for line in config if line.startswith("palette = ")],
                                 [f"palette = {index}={colors[role]}" for index, role in ansi_roles().items()])
                for setting, value in {
                    "background": colors["background"], "foreground": colors["text"],
                    "background-opacity": "1", "cursor-color": colors["focus"],
                    "selection-background": colors["selection"], "selection-foreground": colors["on_selection"],
                    "window-titlebar-background": colors["surface"], "window-titlebar-foreground": colors["text"],
                }.items():
                    self.assertEqual([line for line in config if line.startswith(f"{setting} = ")],
                                     [f"{setting} = {value}"])
                self.assertEqual(ghostty.split(b"# Panda Theme fixture fragment:", 1)[0],
                                 render_ghostty_profile(legacy[slug]).split(b"# Panda Theme fixture fragment:", 1)[0])

                prompt = tomllib.loads(starship.decode())
                self.assertEqual(set(prompt), {"palette", "palettes"})
                self.assertEqual(prompt["palette"], "panda")
                self.assertEqual(prompt["palettes"]["panda"]["accent"], colors["accent_text"])
                self.assertEqual(json.loads(fastfetch), {
                    "display": {"color": {"keys": colors["accent_text"], "title": colors["text"]}}
                })

    def test_cli_creates_private_v2_outputs_and_validates_the_v2_paths(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as tmp:
            root = Path(tmp)
            source_files = [
                *(COMMON / name for name in ("terminal_preview.py", "ghostty_preview.py",
                                             "render.py", "palette.py", "fixture_fs.py")),
                ROOT / "home/dot_config/ghostty/config.ghostty",
            ]
            for source in source_files:
                target = root / source.relative_to(ROOT)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
            common = root / COMMON.relative_to(ROOT)
            shutil.copytree(COMMON / "templates", common / "templates")
            shutil.copytree(COMMON.parent / "palettes", common.parent / "palettes")
            script = str(common / "terminal_preview.py")
            env = os.environ.copy()
            env.pop("PYTHONDONTWRITEBYTECODE", None)
            env.pop("PYTHONPYCACHEPREFIX", None)

            def run(*options):
                return subprocess.run([sys.executable, script, *options], env=env,
                                      capture_output=True, text=True, timeout=15)

            for options in ((), ("--palette-version", "v3")):
                rejected = run(*options)
                self.assertEqual(rejected.returncode, 2, rejected.stderr)
                self.assertEqual(rejected.stdout, "")
                self.assertFalse(list(root.rglob("__pycache__")))

            result = run(*self.version_args)
            self.assertEqual((result.returncode, result.stderr), (0, ""))
            directory = Path(result.stdout.strip())
            self.assertEqual(directory.parent, Path("/tmp"))
            self.assertTrue(directory.name.startswith("panda-terminal-v2-preview-"))
            self.addCleanup(shutil.rmtree, directory)
            self.assertFalse(list(root.rglob("__pycache__")))
        self.assertEqual(directory.stat().st_mode & 0o777, 0o700)
        expected = preview_files(load_family(COMMON.parent, palette_version="v2"), palette_version="v2")
        self.assertEqual({str(path.relative_to(directory)): path.read_bytes()
                          for path in directory.rglob("*") if path.is_file()}, expected)
        with patch.object(ghostty_preview.shutil, "which", return_value="/fake/ghostty"), \
                patch.object(ghostty_preview.subprocess, "run") as native, redirect_stderr(io.StringIO()):
            native.return_value = subprocess.CompletedProcess([], 0, "", "")
            ghostty_preview.validate_profiles(directory, ("hybrid", "gothic"), config_name=self.names[0])
        self.assertEqual([call.args[0][2] for call in native.call_args_list],
                         [f"--config-file={directory / slug / self.names[0]}" for slug in ("hybrid", "gothic")])

    def test_invalid_v2_fails_without_allocating_output_despite_valid_v1(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for slug in load_family(COMMON.parent):
                (root / slug).mkdir()
                shutil.copyfile(COMMON.parent / slug / "theme.toml", root / slug / "theme.toml")
            self.assertEqual(len(load_family(root)), 5)
            with patch.object(terminal_preview, "__file__", str(root / "common/terminal_preview.py")), \
                    patch.object(terminal_preview.tempfile, "mkdtemp") as create, redirect_stderr(io.StringIO()):
                self.assertEqual(terminal_preview.main(self.version_args), 1)
                shutil.copytree(COMMON.parent / "palettes/v2", root / "palettes/v2")
                target = root / "palettes/v2/hybrid/theme.toml"
                original = target.read_text()
                for invalid in ("[palette", original.replace('text = "#E0E9DD"', 'text = "#101D19"', 1)):
                    target.write_text(invalid)
                    self.assertEqual(terminal_preview.main(self.version_args), 1)
                target.unlink()
                self.assertEqual(terminal_preview.main(self.version_args), 1)
                with self.assertRaises(SystemExit) as failure:
                    terminal_preview.main(["--palette-version", "v3"])
                self.assertEqual(failure.exception.code, 2)
                create.assert_not_called()

    def test_v2_validation_failure_leaves_no_preview(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as tmp:
            target = Path(tmp) / "preview"

            mkdtemp = tempfile.mkdtemp

            def allocate(suffix=None, prefix=None, dir=None):
                if prefix == "panda-terminal-v2-preview-":
                    target.mkdir()
                    return str(target)
                return mkdtemp(suffix=suffix, prefix=prefix, dir=dir)

            with patch.object(terminal_preview.tempfile, "mkdtemp", side_effect=allocate) as create, \
                    patch.object(ghostty_preview.shutil, "which", return_value=None), redirect_stderr(io.StringIO()):
                self.assertEqual(terminal_preview.main([*self.version_args, "--validate"]), 1)
                create.assert_not_called()

            with patch.object(terminal_preview.tempfile, "mkdtemp", side_effect=allocate), \
                    patch.object(ghostty_preview.shutil, "which", return_value="/fake/ghostty"), \
                    patch.object(ghostty_preview.subprocess, "run") as native, redirect_stderr(io.StringIO()):
                native.return_value = subprocess.CompletedProcess([], 1, "", "invalid native config")
                self.assertEqual(terminal_preview.main([*self.version_args, "--validate"]), 1)
                native.assert_called_once()
                self.assertFalse(target.exists())
