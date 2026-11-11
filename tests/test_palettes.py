"""Behavioral contracts for the Phase 1 palette foundation (stdlib only)."""

from hashlib import sha256
import importlib
import json
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
THEMES = ROOT / "theme/panda"
MODULE = THEMES / "common/palette.py"
ROLES = (
    "background surface surface2 text muted primary secondary success warning "
    "error border focus selection accent_text on_primary on_secondary on_selection"
).split()


class PaletteContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(MODULE.parent))
        try:
            cls.api = importlib.import_module("palette")
        except ModuleNotFoundError:
            cls.api = None

    def setUp(self):
        self.assertIsNotNone(self.api, "Phase 1 palette validator is not implemented")

    def fixture(self):
        # Independently chosen black/white fixture; not copied from a manifest.
        colors = {role: "#FFFFFF" for role in ROLES}
        colors.update({role: "#000000" for role in (
            "background", "surface", "surface2", "on_primary", "on_secondary",
            "on_selection",
        )})
        return {"schema_version": 1, "name": "Panda Hybrid", "slug": "hybrid",
                "aliases": [], "palette": colors}

    def test_accepts_semantic_palette_and_preserves_identity(self):
        theme = self.api.validate_manifest(self.fixture(), "hybrid")
        self.assertEqual(theme.slug, "hybrid")
        self.assertEqual(theme.palette["background"], "#000000")

    def test_rejects_missing_or_misspelled_roles(self):
        for role in ROLES:
            data = self.fixture()
            del data["palette"][role]
            with self.subTest(role=role), self.assertRaises(self.api.PaletteError):
                self.api.validate_manifest(data, "hybrid")
        data = self.fixture()
        data["palette"]["backgound"] = "#000000"
        with self.assertRaises(self.api.PaletteError):
            self.api.validate_manifest(data, "hybrid")

    def test_rejects_alpha_and_non_srgb_hex_colors(self):
        for value in ("#FFF", "#12345678", "#GG0000", "transparent", "red",
                      "rgb(0,0,0)", "#123456\n", "123456", 123456, True, None):
            data = self.fixture()
            data["palette"]["text"] = value
            with self.subTest(value=value), self.assertRaises(self.api.PaletteError):
                self.api.validate_manifest(data, "hybrid")

    def test_rejects_malformed_structure_and_unknown_fields(self):
        invalid = [[], None, {}, {**self.fixture(), "palette": []},
                   {**self.fixture(), "schema_version": True},
                   {**self.fixture(), "schema_version": 2},
                   {**self.fixture(), "schema_version": 1.0},
                   {**self.fixture(), "scripts": {"apply": "anything"}}]
        for key in ("schema_version", "name", "slug", "aliases", "palette"):
            data = self.fixture()
            del data[key]
            invalid.append(data)
        for data in invalid:
            with self.subTest(data=data), self.assertRaises(self.api.PaletteError):
                self.api.validate_manifest(data, "hybrid")

    def test_rejects_wrong_name_directory_and_aliases(self):
        for field, value in (("slug", "wave"), ("slug", "../hybrid"),
                             ("name", "Hybrid"), ("aliases", ["wave"]),
                             ("aliases", ""), ("aliases", ["hybrid"])):
            data = self.fixture()
            data[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(self.api.PaletteError):
                self.api.validate_manifest(data, "hybrid")
        with self.assertRaises(self.api.PaletteError):
            self.api.validate_manifest(self.fixture(), "cyber")

    def test_wave_resolves_to_one_canonical_pandawave_manifest(self):
        family = self.api.load_family(THEMES)
        self.assertEqual(set(family), {"minimal", "cyber", "gothic", "hybrid", "pandawave"})
        self.assertEqual(self.api.resolve_slug("wave"), "pandawave")
        self.assertEqual(self.api.resolve_slug("pandawave"), "pandawave")
        self.assertEqual(family["pandawave"].aliases, ("wave",))
        for value in ("Wave", "", "../gothic", "unknown"):
            with self.subTest(value=value), self.assertRaises(self.api.PaletteError):
                self.api.resolve_slug(value)

    def test_load_errors_are_actionable_and_do_not_traceback(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "hybrid/theme.toml"
            path.parent.mkdir()
            for content in ('[palette\n', 'name = "one"\nname = "two"\n'):
                path.write_text(content)
                with self.assertRaisesRegex(self.api.PaletteError, "theme.toml"):
                    self.api.load_theme(path)
            path.write_bytes(b"\xff")
            with self.assertRaises(self.api.PaletteError):
                self.api.load_theme(path)
            with self.assertRaises(self.api.PaletteError):
                self.api.load_family(Path(directory))

    def test_family_rejects_missing_and_extra_manifests(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            for source in THEMES.glob("*/theme.toml"):
                path = target / source.relative_to(THEMES)
                path.parent.mkdir()
                path.write_bytes(source.read_bytes())
            (target / "hybrid/theme.toml").unlink()
            with self.assertRaises(self.api.PaletteError):
                self.api.load_family(target)
            (target / "hybrid/theme.toml").write_bytes((THEMES / "hybrid/theme.toml").read_bytes())
            (target / "wave").mkdir()
            (target / "wave/theme.toml").write_bytes((THEMES / "pandawave/theme.toml").read_bytes())
            with self.assertRaises(self.api.PaletteError):
                self.api.load_family(target)

    def test_contrast_uses_linearized_srgb_luminance(self):
        self.assertAlmostEqual(self.api.contrast_ratio("#000000", "#FFFFFF"), 21.0)
        self.assertAlmostEqual(self.api.contrast_ratio("#FFFFFF", "#FFFFFF"), 1.0)
        self.assertAlmostEqual(self.api.contrast_ratio("#777777", "#FFFFFF"), 4.478089, places=5)
        self.assertAlmostEqual(self.api.contrast_ratio("#0A0A0A", "#FFFFFF"), 19.798146, places=5)
        self.assertAlmostEqual(self.api.contrast_ratio("#FF0000", "#FFFFFF"), 3.998477, places=5)
        self.assertAlmostEqual(self.api.contrast_ratio("#FFFFFF", "#ff0000"), 3.998477, places=5)

    def test_threshold_is_not_rounded_up(self):
        data = self.fixture()
        data["palette"]["text"] = "#777777"
        data["palette"]["background"] = "#FFFFFF"
        checks = self.api.contrast_checks(self.api.validate_manifest(data, "hybrid"))
        pair = next(c for c in checks if (c.foreground, c.background) == ("text", "background"))
        self.assertFalse(pair.passes)
        self.assertEqual(pair.minimum, 4.5)

    def test_all_intended_text_control_and_selection_pairs_are_covered(self):
        theme = self.api.validate_manifest(self.fixture(), "hybrid")
        checks = self.api.contrast_checks(theme)
        required = {(c.foreground, c.background): c.minimum for c in checks if c.required}
        for bg in ("background", "surface", "surface2"):
            for fg in ("text", "muted", "accent_text", "success", "warning", "error"):
                self.assertEqual(required[fg, bg], 4.5)
            for fg in ("border", "focus"):
                self.assertEqual(required[fg, bg], 3.0)
        for fg, bg in (("on_primary", "primary"), ("on_secondary", "secondary"),
                       ("on_selection", "selection")):
            self.assertEqual(required[fg, bg], 4.5)
        self.assertEqual(required["focus", "selection"], 3.0)

    def test_five_palettes_pass_all_required_contrast_pairs(self):
        for theme in self.api.load_family(THEMES).values():
            for check in self.api.contrast_checks(theme):
                if check.required:
                    with self.subTest(slug=theme.slug, pair=(check.foreground, check.background)):
                        self.assertTrue(check.passes, f"{check.ratio:.6f} < {check.minimum}")

    def test_gothic_brand_is_not_misclassified_as_text(self):
        theme = self.api.load_family(THEMES)["gothic"]
        checks = self.api.contrast_checks(theme)
        fill = next(c for c in checks if (c.foreground, c.background) == ("primary", "surface2"))
        self.assertFalse(fill.required)
        self.assertLess(fill.ratio, 3.0)
        label = next(c for c in checks if (c.foreground, c.background) == ("on_primary", "primary"))
        self.assertTrue(label.passes)

    def test_validator_process_reports_real_contrast_and_rejects_bad_root(self):
        result = subprocess.run([sys.executable, "-B", str(MODULE), "--json"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(set(report), {"minimal", "cyber", "gothic", "hybrid", "pandawave"})
        self.assertTrue(all("ratio" in item for item in report["hybrid"]))
        with tempfile.TemporaryDirectory() as directory:
            failed = subprocess.run([sys.executable, "-B", str(MODULE), directory],
                                    capture_output=True, text=True)
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn("ERROR", failed.stderr)
            self.assertNotIn("Traceback", failed.stderr)

    def test_validator_process_fails_on_contrast_regression(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            for source in THEMES.glob("*/theme.toml"):
                path = target / source.relative_to(THEMES)
                path.parent.mkdir()
                content = source.read_text()
                if source.parent.name == "hybrid":
                    content = content.replace('text = "#E7EDF2"', 'text = "#1D2630"', 1)
                path.write_text(content)
            result = subprocess.run([sys.executable, "-B", str(MODULE), str(target)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn("FAIL", result.stdout)


    def test_explicit_editions_preserve_v1_and_load_approved_v2_tokens(self):
        v1 = self.api.load_family(THEMES)
        self.assertEqual(v1, self.api.load_family(THEMES, palette_version="v1"))
        v2 = self.api.load_family(THEMES, palette_version="v2")
        self.assertEqual(list(v2), ["minimal", "cyber", "gothic", "hybrid", "pandawave"])
        self.assertEqual(v2["minimal"], v1["minimal"])
        self.assertEqual(v2[self.api.resolve_slug("wave")].aliases, ("wave",))
        palettes = {slug: dict(theme.palette) for slug, theme in v2.items()}
        self.assertEqual(sum(len(palette) for palette in palettes.values()), 85)
        # Sorted object keys at both levels, compact separators, UTF-8, no newline.
        encoded = json.dumps(palettes, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.assertEqual(sha256(encoded).hexdigest(),
                         "bb261a76ed5854c371d84b9cff6f6c8abcd1e0384d21570695415e4f0c033bec")

    def test_validator_reports_deterministic_editions_and_advisories(self):
        def run(*options):
            return subprocess.run([sys.executable, "-B", str(MODULE), *options],
                                  capture_output=True)

        for output in ((), ("--json",)):
            with self.subTest(output=output):
                implicit, explicit = run(*output), run("--palette-version", "v1", *output)
                self.assertEqual(implicit.returncode, 0)
                self.assertEqual(implicit.stderr, b"")
                self.assertEqual(implicit.stdout, explicit.stdout)
                self.assertEqual((explicit.returncode, explicit.stderr), (0, b""))

        report = run("--palette-version", "v2", "--json")
        repeated = run("--palette-version", "v2", "--json")
        self.assertEqual((report.returncode, report.stderr), (0, b""))
        self.assertEqual((repeated.returncode, repeated.stderr), (0, b""))
        self.assertEqual(report.stdout, repeated.stdout)
        pairs = json.loads(report.stdout)
        advisory_failures = []
        for slug, checks in pairs.items():
            required = [check for check in checks if check["required"]]
            advisory = [check for check in checks if not check["required"]]
            self.assertEqual(len(required), 28)
            self.assertTrue(all(check["passes"] for check in required))
            self.assertEqual(len(advisory), 6)
            advisory_failures.extend((slug, check["foreground"], check["background"])
                                     for check in advisory if not check["passes"])
        self.assertEqual(list(pairs), ["minimal", "cyber", "gothic", "hybrid", "pandawave"])
        self.assertEqual(advisory_failures, [("gothic", "secondary", "surface2")])
        human = run("--palette-version", "v2")
        self.assertEqual((human.returncode, human.stderr), (0, b""))
        self.assertIn(b"ADVISORY secondary/surface2:", human.stdout)

    def test_unknown_editions_fail(self):
        for version in ("v3", "", "../v2", None, 2):
            with self.subTest(version=version), self.assertRaises(self.api.PaletteError):
                self.api.load_family(THEMES, palette_version=version)
        result = subprocess.run([sys.executable, "-B", str(MODULE), "--palette-version", "v3"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid choice", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_explicit_v2_never_falls_back_to_valid_v1(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for source in THEMES.glob("*/theme.toml"):
                path = root / source.relative_to(THEMES)
                path.parent.mkdir()
                path.write_bytes(source.read_bytes())
            v1 = self.api.load_family(root)
            with self.assertRaises(self.api.PaletteError):
                self.api.load_family(root, palette_version="v2")

            v2 = root / "palettes/v2"
            shutil.copytree(THEMES / "palettes/v2", v2)
            path = v2 / "hybrid/theme.toml"
            original = path.read_text()
            command = [sys.executable, "-B", str(MODULE), str(root), "--palette-version", "v2"]
            for data in ("[palette\n", original.replace('text = "#E0E9DD"', 'text = "#12345678"', 1)):
                path.write_text(data)
                with self.assertRaises(self.api.PaletteError):
                    self.api.load_family(root, palette_version="v2")
                invalid = subprocess.run(command, capture_output=True, text=True)
                self.assertEqual(invalid.returncode, 1)
                self.assertIn("ERROR", invalid.stderr)
                self.assertEqual(invalid.stdout, "")
                self.assertEqual(self.api.load_family(root), v1)

            path.write_text(original.replace('text = "#E0E9DD"', 'text = "#101D19"', 1))
            low_contrast = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(low_contrast.returncode, 1)
            self.assertIn("FAIL text/background", low_contrast.stdout)
            self.assertEqual(self.api.load_family(root), v1)

            path.unlink()
            with self.assertRaises(self.api.PaletteError):
                self.api.load_family(root, palette_version="v2")
            path.write_text(original)
            (v2 / "wave").mkdir()
            (v2 / "wave/theme.toml").write_text(original)
            with self.assertRaises(self.api.PaletteError):
                self.api.load_family(root, palette_version="v2")
            self.assertEqual(self.api.load_family(root), v1)


if __name__ == "__main__":
    unittest.main()
