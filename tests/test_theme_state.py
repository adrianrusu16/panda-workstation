"""Read-only state contracts; every fixture lives in a temporary directory."""

import importlib
import os
from pathlib import Path
import sys
import tempfile
import unittest


COMMON = Path(__file__).resolve().parents[1] / "theme/panda/common"
sys.path.insert(0, str(COMMON))


class ThemeStateContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.api = importlib.import_module("state")
        except ModuleNotFoundError:
            cls.api = None

    def setUp(self):
        self.assertIsNotNone(self.api, "Phase 2 state reader is not implemented")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "panda/theme-state.toml"

    def write(self, content):
        self.path.parent.mkdir(exist_ok=True)
        self.path.write_text(content)

    def fixture(self, mode="auto", active="hybrid", last_manual="gothic", context=""):
        return (f'mode = "{mode}"\nactive = "{active}"\n'
                f'last_manual = "{last_manual}"\ncontext = "{context}"\n')

    def test_missing_state_does_not_establish_active_theme_or_create_directories(self):
        self.assertIsNone(self.api.read_state(self.path))
        self.assertEqual(list(self.root.iterdir()), [])

    def test_reads_all_canonical_themes_without_modifying_bytes(self):
        for slug in ("minimal", "cyber", "gothic", "hybrid", "pandawave"):
            with self.subTest(slug=slug):
                self.write(self.fixture("manual", slug, slug, "legacy context"))
                before = self.path.read_bytes()
                state = self.api.read_state(self.path)
                self.assertEqual((state.mode, state.active, state.last_manual, state.context),
                                 ("manual", slug, slug, "legacy context"))
                self.assertEqual(self.path.read_bytes(), before)
                self.assertEqual(state, self.api.read_state(self.path))

    def test_empty_last_manual_is_valid_in_auto_mode(self):
        self.write(self.fixture(last_manual=""))
        self.assertEqual(self.api.read_state(self.path).last_manual, "")

    def test_rejects_invalid_modes_names_and_persisted_aliases(self):
        for args in (("unknown", "hybrid", ""), ("auto", "wave", ""),
                     ("auto", "unknown", ""), ("auto", "hybrid", "wave")):
            with self.subTest(args=args):
                self.write(self.fixture(*args))
                before = self.path.read_bytes()
                with self.assertRaises(self.api.StateError):
                    self.api.read_state(self.path)
                self.assertEqual(self.path.read_bytes(), before)

    def test_rejects_malformed_unsupported_or_extra_fields_without_disclosing_values(self):
        for content in ('mode = [\n', 'mode = "auto"\n',
                        self.fixture() + 'schema_version = 2\n',
                        self.fixture().replace('context = ""', 'context = []'),
                        self.fixture().replace('mode = "auto"', 'mode = false'),
                        self.fixture(context="PRIVATE_VALUE").replace('active = "hybrid"',
                                                                      'active = "SECRET"')):
            with self.subTest(content=content):
                self.write(content)
                before = self.path.read_bytes()
                with self.assertRaises(self.api.StateError) as caught:
                    self.api.read_state(self.path)
                self.assertNotIn("SECRET", str(caught.exception))
                self.assertNotIn("PRIVATE_VALUE", str(caught.exception))
                self.assertEqual(self.path.read_bytes(), before)
        self.path.write_bytes(b"\xff")
        with self.assertRaises(self.api.StateError):
            self.api.read_state(self.path)

    def test_rejects_symlink_file_dangling_link_and_symlink_parent(self):
        target = self.root / "original.toml"
        target.write_text(self.fixture())
        self.path.parent.mkdir()
        self.path.symlink_to(target)
        with self.assertRaises(self.api.StateError):
            self.api.read_state(self.path)
        self.path.unlink()
        self.path.symlink_to(self.root / "absent")
        with self.assertRaises(self.api.StateError):
            self.api.read_state(self.path)
        self.path.unlink()
        self.path.parent.rmdir()
        self.path.parent.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(self.api.StateError):
            self.api.read_state(self.path)
        self.assertEqual(target.read_text(), self.fixture())

    def test_rejects_directory_fifo_and_conflicting_parent(self):
        self.path.parent.mkdir()
        self.path.mkdir()
        with self.assertRaises(self.api.StateError):
            self.api.read_state(self.path)
        self.path.rmdir()
        os.mkfifo(self.path)
        with self.assertRaises(self.api.StateError):
            self.api.read_state(self.path)
        self.path.unlink()
        self.path.parent.rmdir()
        self.path.parent.write_text("unrelated")
        with self.assertRaises(self.api.StateError):
            self.api.read_state(self.path)
        self.assertEqual(self.path.parent.read_text(), "unrelated")

    def test_context_must_be_plain_text_and_state_size_is_bounded(self):
        self.write(self.fixture().replace('context = ""', 'context = "bad\\ncontext"'))
        with self.assertRaises(self.api.StateError):
            self.api.read_state(self.path)
        self.path.write_text(self.fixture() + "#" * 70000)
        with self.assertRaises(self.api.StateError):
            self.api.read_state(self.path)

    def test_direct_state_construction_is_validated(self):
        with self.assertRaises(self.api.StateError):
            self.api.ThemeState("invalid", "hybrid", "", "")

    def test_parent_traversal_cannot_hide_symlinks_missing_or_conflicting_components(self):
        direct = self.root / "theme-state.toml"
        direct.write_text(self.fixture())
        (self.root / "link").symlink_to("/tmp", target_is_directory=True)
        (self.root / "file").write_text("unrelated")
        for component in ("link", "absent", "file"):
            with self.subTest(component=component), self.assertRaises(self.api.StateError):
                self.api.read_state(self.root / component / "../theme-state.toml")
        self.assertEqual(direct.read_text(), self.fixture())

    def test_deeply_nested_toml_is_a_diagnostic_not_a_parser_traceback(self):
        for content in ("mode = " + "[" * 2000 + "0" + "]" * 2000,
                        "mode = " + "1" * 5000):
            self.write(content)
            before = self.path.read_bytes()
            with self.subTest(size=len(content)), self.assertRaises(self.api.StateError):
                self.api.read_state(self.path)
            self.assertEqual(self.path.read_bytes(), before)

    def test_root_directory_is_a_conflicting_path_not_absent_state(self):
        with self.assertRaises(self.api.StateError):
            self.api.read_state(Path("/"))


if __name__ == "__main__":
    unittest.main()
