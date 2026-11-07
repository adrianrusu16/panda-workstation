"""Portable deployment intent and fresh-directory export, never a session test."""
import copy
import hashlib
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "theme/panda/common"))
from desktop_layout import load_config


def inventory():
    return dict(schema_version=1, scope="panda-deployment-synthetic-inventory",
                installed_plasma="6.8.2", running_plasma="6.8.2",
                packages={name: "6.8.2-1" for name in (
                    "plasma-desktop", "plasma-workspace", "kdeplasma-addons", "libksysguard", "ksystemstats")},
                plugins=["org.kde.plasma.digitalclock", "org.kde.plasma.mediacontroller",
                         "org.kde.plasma.weather", "org.kde.plasma.systemmonitor.cpu",
                         "org.kde.plasma.systemmonitor.memory", "org.kde.plasma.icontasks"],
                sensor_faces=["org.kde.ksysguard.linechart", "org.kde.ksysguard.horizontalbars"])


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec("desktop_deployment"), "offline bundle exporter is not implemented")
        self.module = importlib.import_module("desktop_deployment")
        self.config = load_config(ROOT / "theme/panda/common/desktop/layout.toml")
        self.fixture = json.loads((ROOT / "tests/fixtures/desktop/visual/dock-seven.json").read_text())
        self.inventory = inventory()
        self.temp = tempfile.TemporaryDirectory(prefix="panda-deployment-test-")
        self.addCleanup(self.temp.cleanup)
        self.private = Path(self.temp.name)

    def bundle(self):
        return self.module.build_bundle(self.config, self.fixture, self.inventory)

    def test_bundle_contains_checked_native_style_bytes_and_hashes(self):
        files = self.bundle()
        self.assertEqual(files, self.bundle())
        manifest = json.loads(files["manifest.json"])
        self.assertFalse(manifest["native_verified"])
        self.assertFalse(manifest["ready_for_activation"])
        self.assertEqual(manifest["first_flavor"], "hybrid")
        self.assertEqual(set(manifest["sha256"]), set(files) - {"manifest.json"})
        for name, expected in manifest["sha256"].items():
            self.assertEqual(hashlib.sha256(files[name]).hexdigest(), expected)
        styles = {name: data for name, data in files.items() if name.startswith("plasma-styles/")}
        self.assertEqual(len(styles), 45)
        for name, data in styles.items():
            self.assertEqual(data, (ROOT / "theme/panda" / name).read_bytes())
        self.assertIn("fragments/clock-appearance.json", files)
        self.assertIn("operator-guide.md", files)

    def test_matrix_keeps_existing_fit_refusal_and_flavor_structure(self):
        files = self.bundle()
        matrix = json.loads(files["plans/layout-matrix.json"])
        self.assertEqual(sum(row["status"] == "accepted-model-only" for row in matrix), 55)
        self.assertEqual(sum(row["status"] == "refused-does-not-fit" for row in matrix), 5)
        refused = [row for row in matrix if row["status"] == "refused-does-not-fit"]
        self.assertTrue(all((row["resolution"], row["scale"], row["presentation"]) == ("fhd", 1.5, "expanded") for row in refused))
        for row in matrix:
            if row["status"] == "accepted-model-only":
                self.assertIn(row["preview"], files)
                self.assertIn(b"OFFLINE SCHEMATIC", files[row["preview"]])
        by_profile = {}
        for row in matrix:
            if row["status"] == "accepted-model-only":
                key = (row["resolution"], row["scale"], row["presentation"])
                by_profile.setdefault(key, set()).add(row["structure_sha256"])
        self.assertTrue(all(len(shapes) == 1 for shapes in by_profile.values()))

    def test_dock_fragment_has_only_known_panel_properties_and_floating_ui_gate(self):
        files = self.bundle()
        self.assertIn("fragments/dock-properties.json", list(files))
        dock = json.loads(files["fragments/dock-properties.json"])
        self.assertEqual(dock["panel_property_intent"], dict(height=56, alignment="center", lengthMode="fit", location="bottom"))
        self.assertEqual(dock["native_config_write_set"], {})
        self.assertTrue(dock["requires_native_ui_serialization_review"])
        plan = json.loads(files["plans/write-set.json"])
        self.assertEqual(plan["preserve_desktop_count"], 1)
        self.assertFalse(plan["top_panels"]["native_shape_verified"])

    def test_input_preserved_and_existing_instance_identity_never_recreated(self):
        self.fixture["bindings"]["cpu"] = 811
        self.fixture["applets"].append(dict(id=811, containment_id=149,
            plugin="org.kde.plasma.systemmonitor.cpu", geometry=[1, 2, 300, 150],
            config={"preserve": "opaque config"}))
        before = copy.deepcopy((self.config, self.fixture, self.inventory))
        files = self.bundle()
        plan = json.loads(files["plans/write-set.json"])
        self.assertEqual(plan["native_operations"], [])
        self.assertEqual(plan["top_panels"]["proposed_writes"], [])
        self.assertEqual(plan["dock"]["action"], "propose-addition-only")
        self.assertEqual(plan["dock"]["reparent_existing_applets"], False)
        cpu = next(role for role in plan["roles"] if role["role"] == "cpu")
        self.assertEqual(cpu["identity"], "<existing-cpu-instance>")
        self.assertEqual(cpu["action"], "retain-identity-and-parent")
        self.assertEqual(cpu["native_config_write_set"], {})
        self.assertEqual(before, (self.config, self.fixture, self.inventory))

    def test_private_fixture_content_cannot_enter_portable_package(self):
        self.fixture["output"]["name"] = "private-connector-DO-NOT-EXPORT"
        self.fixture["providers"]["media"] = "SECRET-PRIVATE-TRACK"
        self.fixture["applications"] = ["private-PROJECT.desktop"]
        self.fixture["applets"][0]["config"] = {"private": "/home/private-user/SECRET-IDENTITY"}
        raw = b"\n".join(self.bundle().values())
        for secret in (b"private-connector", b"SECRET-PRIVATE", b"private-PROJECT", b"private-user", b"SECRET-IDENTITY"):
            self.assertNotIn(secret, raw)

    def test_exact_release_and_inventory_gates_report_missing_without_native_claim(self):
        self.inventory["running_plasma"] = "6.9.0"
        self.inventory["packages"].pop("ksystemstats")
        self.inventory["plugins"].remove("org.kde.plasma.weather")
        self.inventory["sensor_faces"] = []
        report = json.loads(self.bundle()["plans/prerequisites.json"])
        self.assertFalse(report["synthetic_prerequisites_satisfied"])
        self.assertFalse(report["release_matches_reviewed_source"])
        self.assertEqual(report["packages"]["missing"], ["ksystemstats"])
        self.assertEqual(report["missing_plugins"], ["org.kde.plasma.weather"])
        self.assertEqual(report["missing_sensor_faces"], ["org.kde.ksysguard.horizontalbars", "org.kde.ksysguard.linechart"])
        writes = json.loads(self.bundle()["plans/write-set.json"])
        self.assertTrue(all(not role["native_config_write_set"] for role in writes["roles"]))

    def test_clock_fragment_is_proven_subset_and_existing_clock_keeps_settings(self):
        fragment = json.loads(self.bundle()["fragments/clock-appearance.json"])
        self.assertEqual(fragment["group"], ["Appearance"])
        self.assertEqual(fragment["values"]["use24hFormat"], 2)
        self.assertEqual(fragment["values"]["showSeconds"], 0)
        self.assertNotIn("fontFamily", fragment["values"])
        self.fixture["bindings"]["clock"] = 812
        self.fixture["applets"].append(dict(id=812, containment_id=149,
            plugin="org.kde.plasma.digitalclock", geometry=None, config={"timezones": ["keep"]}))
        files = self.bundle()
        role = json.loads(files["plans/write-set.json"])["roles"][0]
        self.assertEqual(role["native_config_write_set"], {})
        self.assertEqual(json.loads(files["fragments/clock-appearance.json"])["values"], {})

    def test_inventory_rejects_extra_keys_duplicate_plugins_and_untrusted_version_strings(self):
        for mutation in (
            lambda v: v.update(extra="unknown"),
            lambda v: v["plugins"].append(v["plugins"][0]),
            lambda v: v.update(installed_plasma="$(touch SHOULD-NOT-EXIST)"),
            lambda v: v["packages"].update({"plasma-workspace": "/home/private/path"}),
        ):
            with self.subTest(mutation=mutation):
                self.inventory = inventory()
                mutation(self.inventory)
                with self.assertRaises(ValueError):
                    self.bundle()

    def test_mismatched_sensor_package_release_blocks_source_preset_writes(self):
        self.inventory["packages"]["libksysguard"] = "6.7.5-1"
        report = json.loads(self.bundle()["plans/prerequisites.json"])
        self.assertEqual(report["package_release_mismatches"], ["libksysguard"])
        self.assertFalse(report["synthetic_prerequisites_satisfied"])

    def test_ambiguous_instances_and_unreviewed_face_preset_combinations_refuse(self):
        self.config["widgets"]["cpu"]["face"] = "org.kde.ksysguard.horizontalbars"
        with self.assertRaises(ValueError):
            self.bundle()
        self.config = load_config(ROOT / "theme/panda/common/desktop/layout.toml")
        self.fixture["bindings"]["ram"] = 811
        for identity in (811, 812):
            self.fixture["applets"].append(dict(id=identity, containment_id=149,
                plugin="org.kde.plasma.systemmonitor.memory", geometry=None, config={}))
        with self.assertRaises(ValueError):
            self.bundle()

    def test_monitor_fragments_use_effective_groups_json_strings_and_post_init_gate(self):
        files = self.bundle()
        self.assertIn("fragments/cpu-controller.json", list(files))
        cpu = json.loads(files["fragments/cpu-controller.json"])
        ram = json.loads(files["fragments/ram-controller.json"])
        self.assertEqual(cpu["groups"]["Appearance"]["chartFace"], "org.kde.ksysguard.linechart")
        self.assertEqual(cpu["groups"]["Appearance"]["title"], "CPU")
        self.assertTrue(cpu["groups"]["Appearance"]["showTitle"])
        self.assertEqual(cpu["groups"]["Appearance"]["updateRateLimit"], 1000)
        self.assertEqual(ram["groups"]["Appearance"]["title"], "Memory")
        self.assertEqual(cpu["groups"]["Sensors"]["highPrioritySensorIds"], '["cpu/all/usage"]')
        self.assertEqual(cpu["groups"]["Sensors"]["lowPrioritySensorIds"], '[]')
        self.assertEqual(cpu["groups"]["org.kde.ksysguard.linechart/General"]["rangeToY"], 100.0)
        self.assertIs(type(cpu["groups"]["org.kde.ksysguard.linechart/General"]["rangeToY"]), float)
        self.assertEqual(ram["groups"]["Sensors"]["totalSensors"], '["memory/physical/usedPercent"]')
        self.assertEqual(ram["groups"]["Sensors"]["lowPrioritySensorIds"], '["memory/physical/free","memory/physical/total"]')
        self.assertTrue(cpu["requires_stock_preset_initialization"])
        self.assertEqual(cpu["applet_root_writes"], {})
        self.assertFalse(cpu["native_verified"])
        plan = json.loads(files["plans/write-set.json"])
        new_cpu = next(role for role in plan["roles"] if role["role"] == "cpu")
        self.assertEqual(new_cpu["native_config_write_set"]["Sensors/highPrioritySensorIds"], '["cpu/all/usage"]')
        self.assertNotIn("Sensors/sensorIds", new_cpu["native_config_write_set"])
        self.inventory["running_plasma"] = None
        blocked = json.loads(self.bundle()["fragments/cpu-controller.json"])
        self.assertEqual(blocked["groups"], {})
        self.assertEqual(blocked["status"], "blocked-release-or-inventory")

    def test_fresh_export_matches_manifest_and_refuses_existing_even_identical(self):
        files = self.bundle()
        target = self.private / "review"
        self.module.export_bundle(target, files)
        self.assertEqual({str(p.relative_to(target)): p.read_bytes() for p in target.rglob("*") if p.is_file()}, files)
        with self.assertRaises((OSError, ValueError)):
            self.module.export_bundle(target, files)
        self.assertEqual((target / "manifest.json").read_bytes(), files["manifest.json"])

    def test_export_rejects_unsafe_paths_symlinks_modes_and_payloads_before_creating(self):
        files = self.bundle()
        link = self.private / "link"
        link.symlink_to(self.private, target_is_directory=True)
        unsafe = self.private / "unsafe"
        unsafe.mkdir(mode=0o777)
        unsafe.chmod(0o777)
        for target in (self.private / ".." / "escape", link / "review", unsafe / "review", self.private / "missing" / "review"):
            with self.subTest(target=target):
                with self.assertRaises((OSError, ValueError)):
                    self.module.export_bundle(target, files)
        for name in ("../escape.json", "/absolute.json", "dir/../../escape.json", "dir\\escape.json", "script.fish"):
            with self.subTest(name=name):
                target = self.private / "not-created"
                with self.assertRaises(ValueError):
                    self.module.export_bundle(target, {name: b"not safe"})
                self.assertFalse(target.exists())
        with self.assertRaises(ValueError):
            self.module.export_bundle(self.private / "oversized", {"manifest.json": b"x" * (2 * 1024 * 1024 + 1)})
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.private)}):
            with self.assertRaises(ValueError):
                self.module.export_bundle(self.private / "native-config", files)

    def test_export_refuses_protected_xdg_root_aliases_before_mkdir(self):
        files = self.bundle()
        protected = self.private / "config"
        protected.mkdir(mode=0o700)
        alias = self.private / "config-alias"
        alias.symlink_to(protected, target_is_directory=True)
        cases = (
            (str(protected), "/" + str(protected / "double-slash-destination")),
            ("/" + str(protected), str(protected / "double-slash-root")),
            (str(self.private / ".." / self.private.name / "config"), str(protected / "traversal-root")),
            (str(alias), str(protected / "resolved-root")),
        )
        for xdg_root, destination in cases:
            with self.subTest(destination=destination), patch.dict(os.environ, {"XDG_CONFIG_HOME": xdg_root}):
                with self.assertRaises(ValueError):
                    self.module.export_bundle(destination, files)
                self.assertFalse(Path(destination).exists())
        self.assertEqual(list(protected.iterdir()), [])

    def test_export_refuses_manifest_tamper_before_creating_destination(self):
        files = self.bundle()
        files["fragments/clock-appearance.json"] += b" "
        target = self.private / "tampered"
        with self.assertRaises(ValueError):
            self.module.export_bundle(target, files)
        self.assertFalse(target.exists())

    def test_cli_requires_explicit_inventory_and_fresh_output_and_never_writes_home(self):
        inv = self.private / "inventory.json"
        inv.write_text(json.dumps(self.inventory))
        home = self.private / "home"
        home.mkdir(mode=0o700)
        env = {**os.environ, "HOME": str(home), "XDG_CONFIG_HOME": str(home / "config"),
               "XDG_DATA_HOME": str(home / "data"), "XDG_CACHE_HOME": str(home / "cache"),
               "XDG_STATE_HOME": str(home / "state"), "DBUS_SESSION_BUS_ADDRESS": "disabled-for-offline-test",
               "DISPLAY": "", "WAYLAND_DISPLAY": "", "PYTHONDONTWRITEBYTECODE": "1"}
        base = [sys.executable, "-B", str(ROOT / "theme/panda/common/desktop_cli.py"),
                "deployment-export", "--fixture", str(ROOT / "tests/fixtures/desktop/fhd.json")]
        result = subprocess.run([*base, "--inventory", str(inv), "--output-dir", str(self.private / "package")],
                                env=env, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["native_verified"], False)
        self.assertEqual(list(home.iterdir()), [])
        for args in ([], ["--inventory", str(inv)], ["--output-dir", str(self.private / "other")],
                     ["--inventory", str(inv), "--output-dir", str(self.private / "other"), "--scale", "1.25"]):
            result = subprocess.run([*base, *args], env=env, capture_output=True, text=True, timeout=15)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("Traceback", result.stderr)
        self.assertFalse((self.private / "other").exists())


if __name__ == "__main__":
    unittest.main()
