"""A bounded include model is not an installed native parser."""

import importlib
import sys
import unittest

from live_fixture_support import COMMON, BASE
sys.path.insert(0, str(COMMON))


class GhosttyModelContracts(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec("adapters.live_ghostty"), "Ghostty model missing")
        self.api = importlib.import_module("adapters.live_ghostty")

    def test_optional_hook_preserves_every_baseline_byte_and_resolves_target(self):
        modeled = self.api.model_hook(BASE)
        self.assertEqual(modeled, BASE + b"config-file = ?../panda/generated/ghostty.conf\n")
        self.assertEqual(self.api.resolve_hook("config/ghostty/config.ghostty"),
                         "config/panda/generated/ghostty.conf")
        self.assertEqual(self.api.effective_model(modeled, None)["background"], "#010203")

    def test_fragment_loaded_after_enclosing_config_wins_in_model(self):
        modeled = self.api.model_hook(BASE) + b"background = #040506\n"
        effective = self.api.effective_model(modeled, b"background = #070809\nbackground-opacity = 1\n")
        self.assertEqual(effective["background"], "#070809")
        self.assertEqual(effective["font-size"], "11.5")
        self.assertEqual(effective["cursor-style"], "bar")

    def test_duplicate_or_unsupported_include_graph_is_refused(self):
        for content in (self.api.model_hook(BASE), BASE + b"config-file = other.conf\n",
                        BASE + b"theme = other\n", b"font-size = 11.5", b"bad line\n"):
            with self.assertRaises(ValueError):
                self.api.model_hook(content)
        with self.assertRaises(ValueError):
            self.api.effective_model(BASE, b"config-file = ../other\n")

    def test_refresh_model_never_claims_native_verification(self):
        result = self.api.GhosttyModel().refresh()
        self.assertTrue(result.success)
        self.assertIn("unverified", result.message)

    def test_existing_ansi_slots_are_preserved_and_overridden_individually(self):
        baseline = BASE + b"palette = 0=#111111\npalette = 1=#222222\n"
        effective = self.api.effective_model(self.api.model_hook(baseline), b"palette = 0=#333333\n")
        self.assertEqual(effective["palette:0"], "0=#333333")
        self.assertEqual(effective["palette:1"], "1=#222222")

    def test_hook_proposal_itself_obeys_the_metadata_limit(self):
        baseline = b"#" * 65535 + b"\n"
        with self.assertRaises(ValueError): self.api.model_hook(baseline)
