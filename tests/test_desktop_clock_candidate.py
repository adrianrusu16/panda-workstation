"""Clock-only planning is hermetic; no native widget or user config is loaded."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "theme/panda/common"))
SCHEMA = ROOT / "tests/fixtures/desktop/clock-6.8.2.xml"
FIXTURE = ROOT / "tests/fixtures/desktop/assessment/sanitized-shape.json"
SETTINGS = {
    "Appearance/showDate": True,
    "Appearance/dateFormat": "custom",
    "Appearance/customDateFormat": "dddd, d MMMM",
    "Appearance/use24hFormat": 2,
    "Appearance/dateDisplayFormat": 2,
    "Appearance/showSeconds": 0,
    "Appearance/autoFontAndSize": True,
}


class ClockCandidateTests(unittest.TestCase):
    def setUp(self):
        from desktop_layout import load_config
        self.config = load_config(ROOT / "theme/panda/common/desktop/layout.toml")
        self.fixture = json.loads(FIXTURE.read_text())

    def candidate(self, **kwargs):
        from desktop_clock_candidate import build_clock_candidate
        return build_clock_candidate(self.config, self.fixture, plasma_version="6.8.2",
                                     schema_xml=SCHEMA.read_bytes(), **kwargs)

    def test_absent_desktop_clock_is_only_an_additive_proposal(self):
        plan = self.candidate()
        self.assertEqual(plan["plugin"], "org.kde.plasma.digitalclock")
        self.assertEqual(plan["desktop_id"], 10)
        self.assertIsNone(plan["instance_id"])
        self.assertEqual(plan["intent"], "propose-one-additive-desktop-instance")
        self.assertEqual(plan["settings"], SETTINGS)
        self.assertEqual(plan["background_request"], "StandardBackground-current-style")
        self.assertFalse(plan["native_verified"])
        self.assertFalse(plan["ready_for_native_test"])
        self.assertEqual(plan["operations"], [])

    def test_rejects_unreviewed_version_or_changed_schema(self):
        from desktop_clock_candidate import build_clock_candidate
        for version in ("6.7.5", "6.8.1", "6.8.2-1.1", "6.8.3", None):
            with self.subTest(version=version), self.assertRaises(ValueError):
                build_clock_candidate(self.config, self.fixture, plasma_version=version,
                                      schema_xml=SCHEMA.read_bytes())
        for xml in (b"", SCHEMA.read_bytes().replace(b'BelowTime', b'AboveTime')):
            with self.assertRaises(ValueError):
                build_clock_candidate(self.config, self.fixture, plasma_version="6.8.2", schema_xml=xml)

    def test_supported_settings_are_strict_and_enum_meanings_are_reviewed(self):
        from desktop_clock_candidate import validate_clock_settings
        meanings = validate_clock_settings(SETTINGS, plasma_version="6.8.2", schema_xml=SCHEMA.read_bytes())
        self.assertEqual(meanings["Appearance/use24hFormat"], "24-Hour")
        self.assertEqual(meanings["Appearance/dateDisplayFormat"], "BelowTime")
        self.assertEqual(meanings["Appearance/showSeconds"], "Never")
        for key, value in (("Appearance/use24hFormat", 1), ("Appearance/use24hFormat", True),
                           ("Appearance/showSeconds", False), ("Appearance/fontSize", 38),
                           ("Appearance/selectedTimeZones", ["UTC"]), ("Appearance/showDate", 1),
                           ("Appearance/customDateFormat", "yyyy")):
            wrong = {**SETTINGS, key: value}
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                validate_clock_settings(wrong, plasma_version="6.8.2", schema_xml=SCHEMA.read_bytes())
        with self.assertRaises(ValueError):
            validate_clock_settings({}, plasma_version="6.8.2", schema_xml=SCHEMA.read_bytes())

    def test_existing_and_ambiguous_desktop_clocks_are_refused_not_reused(self):
        for count in (1, 2):
            with self.subTest(count=count):
                self.fixture = json.loads(FIXTURE.read_text())
                for ident in range(40, 40 + count):
                    self.fixture["applets"].append(dict(id=ident, containment_id=10,
                        plugin="org.kde.plasma.digitalclock", geometry=None,
                        config={"Appearance": {"selectedTimeZones": ["UTC"]}}))
                self.fixture["bindings"]["clock"] = 40
                with self.assertRaisesRegex(ValueError, "existing|ambiguous"):
                    self.candidate()
        self.fixture["bindings"]["clock"] = None
        with self.assertRaises(ValueError):
            self.candidate()

    def test_preserves_complete_fixture_and_repeated_plans_do_not_allocate_ids(self):
        self.fixture["applets"][5]["config"].update({"timezone": "opaque", "calendar": ["opaque"],
                                                   "locale": "opaque", "wallpaper": "opaque"})
        before = copy.deepcopy(self.fixture)
        first = self.candidate()
        self.assertEqual(self.fixture, before)
        self.assertEqual(first["preserved_fixture"], before)
        first["preserved_fixture"]["applets"][5]["config"].clear()
        self.assertEqual(self.fixture, before)
        self.assertEqual(self.candidate(), self.candidate())
        self.assertIsNone(self.candidate()["instance_id"])
        self.assertEqual(self.fixture["desktop_count"], 1)
        self.assertEqual(self.fixture["panels"][0]["applet_ids"], [21, 22, 23, 24, 25, 26, 27])

    def test_both_size_preferences_are_shared_across_five_flavors(self):
        for flavor in ("minimal", "cyber", "gothic", "hybrid", "pandawave", "wave"):
            plan = self.candidate(flavor=flavor)
            self.assertEqual(plan["size_preferences"], {"compact": [288, 88], "expanded": [352, 104]})
            self.assertEqual(plan["geometry_method"], "future-operator-edit-mode-only")
            self.assertFalse(plan["native_size_verified"])
            self.assertEqual(plan["settings"], SETTINGS)
        with self.assertRaises(ValueError):
            self.candidate(flavor="unreviewed")

    def test_modified_claims_settings_preservation_and_unknown_keys_are_rejected(self):
        from desktop_clock_candidate import validate_clock_candidate
        plan = self.candidate()
        validate_clock_candidate(plan, self.config, schema_xml=SCHEMA.read_bytes())
        mutations = (("instance_id", 41), ("native_verified", True), ("ready_for_native_test", True),
                     ("operations", ["create"]), ("extra", True), ("settings", {}),
                     ("size_preferences", {"compact": [288, 88], "expanded": [352, 105]}),
                     ("fixture_sha256", "0" * 64), ("schema_version", True))
        for key, value in mutations:
            wrong = copy.deepcopy(plan)
            wrong[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_clock_candidate(wrong, self.config, schema_xml=SCHEMA.read_bytes())


class ClockCandidateCLITests(unittest.TestCase):
    def test_cli_requires_explicit_reviewed_inputs_and_never_writes_home(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            (home / "sentinel").write_bytes(b"preserve")
            env = {**os.environ, "HOME": td, "PYTHONDONTWRITEBYTECODE": "1",
                   "DBUS_SESSION_BUS_ADDRESS": "disabled-for-offline-test"}
            for name in ("CONFIG", "DATA", "CACHE", "STATE"):
                env[f"XDG_{name}_HOME"] = str(home / name.lower())
            def snapshot():
                return {str(p.relative_to(home)): (p.stat().st_mode, p.stat().st_mtime_ns,
                        hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None)
                        for p in home.rglob("*")}
            before = snapshot()
            cmd = [sys.executable, "-B", str(ROOT / "theme/panda/common/desktop_cli.py"),
                   "clock-candidate", "--fixture", str(FIXTURE)]
            flags = ["--plasma-version", "6.8.2", "--clock-schema", str(SCHEMA)]
            good = subprocess.run(cmd + flags, env=env, capture_output=True, text=True, timeout=5)
            self.assertEqual(good.returncode, 0, good.stderr)
            plan = json.loads(good.stdout)
            self.assertEqual(plan["scope"], "offline-clock-only-candidate")
            self.assertEqual(plan["settings"], SETTINGS)
            again = subprocess.run(cmd + flags, env=env, capture_output=True, text=True, timeout=5)
            self.assertEqual(again.returncode, 0, again.stderr)
            self.assertEqual(again.stdout, good.stdout)
            for extra in ([], flags[:2], flags[2:], flags + ["--apply"],
                          flags + ["--scale", "1.5"], flags + ["--presentation", "expanded"]):
                bad = subprocess.run(cmd + extra, env=env, capture_output=True, text=True, timeout=5)
                self.assertNotEqual(bad.returncode, 0)
                self.assertEqual(bad.stdout, "")
                self.assertNotIn("Traceback", bad.stderr)
            self.assertEqual(snapshot(), before)
