"""Offline contracts only: never builds/executes a VM, supervisor or Qt worker."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest
try:
    import jsonschema
except ImportError:
    jsonschema = None
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "tests/native/external_vm"


class ExternalVmPreparation(unittest.TestCase):
    def module(self):
        path = BASE / "prepare.py"
        self.assertTrue(path.is_file(), "source preparation checker is missing")
        spec = importlib.util.spec_from_file_location("external_vm_prepare", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_canonical_inputs_and_package_closure_validate_without_execution(self):
        result = self.module().check_sources(ROOT)
        self.assertEqual(result["frame_count"], 1)
        self.assertFalse(result["execution_enabled"])
        self.assertFalse(result["native_worker_executed"])
        self.assertGreater(result["package_count"], 10)

    def test_changed_asset_is_refused_before_preparation(self):
        module = self.module()
        candidate = json.loads((BASE / "candidate.json").read_text())
        changed = copy.deepcopy(candidate)
        changed["inputs"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "input receipt"):
            module.check_candidate(ROOT, changed)

    def test_scope_changes_are_refused(self):
        module = self.module()
        candidate = json.loads((BASE / "candidate.json").read_text())
        for key, value in (("flavor", "gothic"), ("logical_size", [352, 168]),
                           ("device_pixel_ratio", 2), ("execution_enabled", True)):
            changed = copy.deepcopy(candidate)
            changed[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                module.check_candidate(ROOT, changed)

    def test_dependency_removal_or_digest_drift_is_refused(self):
        module = self.module()
        lock = json.loads((BASE / "packages.lock.json").read_text())
        changed = copy.deepcopy(lock)
        changed["packages"] = [p for p in changed["packages"] if p["name"] != "glibc"]
        with self.assertRaises(ValueError):
            module.check_lock(changed)
        changed = copy.deepcopy(lock)
        changed["packages"][0]["sha256"] = "not-a-hash"
        with self.assertRaises(ValueError):
            module.check_lock(changed)

    def test_native_seal_has_no_argument_environment_or_macro_override(self):
        source = (BASE / "single_frame_candidate.cpp").read_text()
        main = source[source.index("int main()") :]
        self.assertIn("return 78;", main)
        self.assertNotIn("captureCandidate", main)
        self.assertNotIn("getenv", main)
        self.assertNotIn("#if", main)

    def test_manual_workflow_has_no_native_command(self):
        text = (ROOT / ".github/workflows/panda-native-vm-preparation.yml").read_text()
        self.assertIn("runs-on: ubuntu-24.04", text)
        self.assertIn("workflow_dispatch:", text)
        self.assertIn("if: ${{ github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main' }}", text)
        for forbidden in ("ubuntu-latest", "ubuntu-slim", "self-hosted", "sudo ",
                          "docker run", "workflow_run:", "pull_request:", "push:",
                          "schedule:", "secrets.", "plasma_frame_worker", "sandbox_supervisor"):
            self.assertNotIn(forbidden, text)

    def test_prepare_refuses_local_context_before_writing_or_setting_limits(self):
        module = self.module()
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(ValueError, "hosted Ubuntu VM context"):
                module.prepare_packet(ROOT)

    def test_epoch_filenames_are_accepted_but_path_traversal_is_refused(self):
        module = self.module()
        lock = json.loads((BASE / "packages.lock.json").read_text())
        self.assertTrue(any(":" in p["filename"] for p in lock["packages"]))
        module.check_lock(lock)
        lock["packages"][0]["filename"] = "../outside.pkg.tar.zst"
        with self.assertRaisesRegex(ValueError, "filename"):
            module.check_lock(lock)

    def test_metadata_resolver_checks_versioned_virtual_providers(self):
        path = BASE / "lock_snapshot.py"
        spec = importlib.util.spec_from_file_location("snapshot_metadata", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        rows = {
            "app": {"VERSION": ["1"], "DEPENDS": ["libfoo.so=2-64"]},
            "good": {"VERSION": ["1"], "PROVIDES": ["libfoo.so=2-64"]},
            "wrong": {"VERSION": ["1"], "PROVIDES": ["libfoo.so=1-64"]},
        }
        compare = lambda a, b: (a > b) - (a < b)  # synthetic equal ABI strings only
        selected, edges = module.resolve(rows, ["app"], compare)
        self.assertEqual(selected, {"app", "good"})
        self.assertEqual(edges[0]["provider"], "good")
        rows["ambiguous"] = rows["good"]
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            module.resolve(rows, ["app"], compare)
        del rows["good"]
        del rows["ambiguous"]
        with self.assertRaisesRegex(ValueError, "missing provider"):
            module.resolve(rows, ["app"], compare)

    def test_runner_links_use_release_tag_without_image_patch_component(self):
        module = self.module()
        self.assertTrue(hasattr(module, "runner_image_links"), "runner image tag mapping missing")
        links = module.runner_image_links("20261021.1.0")
        self.assertEqual(links["image_release_url"],
                         "https://github.com/actions/runner-images/releases/tag/ubuntu24%2F20261021.1")
        self.assertIn("/ubuntu24/20261021.1/images/ubuntu/Ubuntu2404-Readme.md", links["included_software_url"])
        for value in ("", "current", "20261021.1.0/../../x"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                module.runner_image_links(value)

    def test_failed_setup_can_report_unavailable_provenance(self):
        schema = json.loads((BASE / "artifact.schema.json").read_text())
        provenance = schema["properties"]["dependency_provenance"]["properties"]
        self.assertEqual(provenance["signatures_verified"], {"type": "boolean"})
        for name in ("trusted_keyring_sha256", "runtime_manifest_sha256", "build_receipt_sha256",
                     "loaded_mappings_sha256"):
            self.assertIn("null", provenance[name]["type"])
        self.assertEqual(schema["properties"]["files"]["required"], ["stdout.txt", "stderr.txt"])


    @unittest.skipUnless(jsonschema, "JSON Schema validator required")
    def test_capture_sections_require_each_named_section_once(self):
        schema = json.loads((BASE / "capture.schema.json").read_text())["properties"]["sections"]
        names = [prefix + part for prefix in ("", "mask-") for part in
                 ("topleft", "top", "topright", "left", "center", "right",
                  "bottomleft", "bottom", "bottomright")]
        sections = [{"id": name, "rect": [0, 0, 1, 1]} for name in names]
        validator = jsonschema.Draft202012Validator(schema)
        validator.validate(sections)
        sections[-1] = {"id": "center", "rect": [1, 0, 1, 1]}
        with self.assertRaises(jsonschema.ValidationError):
            validator.validate(sections)

    def test_success_requires_loaded_mappings_and_authenticated_provenance(self):
        schema = json.loads((BASE / "artifact.schema.json").read_text())
        captured = schema["allOf"][0]["then"]["properties"]
        self.assertIn("loaded-mappings.json", captured["files"]["required"])
        provenance = captured["dependency_provenance"]["properties"]
        self.assertEqual(provenance["signatures_verified"], {"const": True})
        self.assertEqual(provenance["runtime_manifest_sha256"]["type"], "string")


if __name__ == "__main__":
    unittest.main()
