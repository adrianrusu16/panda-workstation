"""Pure selection precedence, local-clock boundaries and proposal contracts."""

from datetime import datetime
import importlib
from pathlib import Path
import sys
import unittest
from zoneinfo import ZoneInfo


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "theme/panda/common"))
from state import ThemeState


class ThemeSelectionContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.api = importlib.import_module("selection")
        except ModuleNotFoundError:
            cls.api = None

    def setUp(self):
        self.assertIsNotNone(self.api, "Phase 2 selector is not implemented")

    def auto(self, now=None, **signals):
        return self.api.select_auto(now, self.api.ContextSignals(**signals))

    def test_exact_time_boundaries_and_midnight(self):
        for hour, minute, slug in ((6, 59, "gothic"), (7, 0, "hybrid"),
                                   (17, 59, "hybrid"), (18, 0, "cyber"),
                                   (20, 59, "cyber"), (21, 0, "gothic"), (0, 0, "gothic")):
            with self.subTest(hour=hour, minute=minute):
                decision = self.auto(datetime(2026, 10, 9, hour, minute))
                self.assertEqual(decision.slug, slug)
                self.assertEqual(decision.source, "schedule")
                self.assertIn("local time", decision.reason)

    def test_clock_timezone_is_already_local_including_dst(self):
        for day in (25, 26):
            now = datetime(2026, 10, day, 7, 0, tzinfo=ZoneInfo("Europe/Bucharest"))
            self.assertEqual(self.auto(now).slug, "hybrid")
        for fold in (0, 1):
            now = datetime(2026, 10, 25, 3, 30, fold=fold,
                           tzinfo=ZoneInfo("Europe/Bucharest"))
            self.assertEqual(self.auto(now).slug, "gothic")

    def test_no_time_or_providers_has_explicit_hybrid_fallback(self):
        decision = self.auto(gaming=None, focus=None)
        self.assertEqual((decision.slug, decision.source, decision.reason),
                         ("hybrid", "fallback", "time unavailable; safe Hybrid fallback"))

    def test_all_special_flavors_and_wave_alias_outrank_all_contexts(self):
        for name, want in (("minimal", "minimal"), ("cyber", "cyber"),
                           ("gothic", "gothic"), ("hybrid", "hybrid"),
                           ("pandawave", "pandawave"), ("wave", "pandawave")):
            with self.subTest(name=name):
                decision = self.auto(special=name, project="pandawave", gaming=True, focus=True)
                self.assertEqual((decision.slug, decision.source, decision.reason),
                                 (want, "special", "explicit special flavor"))

    def test_context_priority_and_stable_reasons(self):
        for signals, want, source, reason in (
                ({"project": "pandawave", "gaming": True, "focus": True},
                 "pandawave", "project", "PandaWave project context"),
                ({"project": "wave", "focus": True},
                 "pandawave", "project", "PandaWave project context"),
                ({"gaming": True, "focus": True}, "cyber", "gaming", "gaming context"),
                ({"focus": True}, "minimal", "focus", "focus context")):
            with self.subTest(signals=signals):
                decision = self.auto(datetime(2026, 10, 9, 21), **signals)
                self.assertEqual((decision.slug, decision.source, decision.reason),
                                 (want, source, reason))
                self.assertEqual(decision, self.auto(datetime(2026, 10, 9, 21), **signals))

    def test_unrelated_project_does_not_override_clock(self):
        self.assertEqual(self.auto(datetime(2026, 10, 9, 7), project="other-project").slug,
                         "hybrid")

    def test_rejects_malformed_signals_even_when_higher_priority_matches(self):
        for signals in ({"special": "unknown"}, {"special": 1}, {"gaming": "true"},
                        {"gaming": 1}, {"focus": []}, {"project": "/private/path"},
                        {"project": "bad\nvalue"}, {"project": []},
                        {"special": "cyber", "focus": "false"}):
            with self.subTest(signals=signals), self.assertRaises(self.api.SelectionError):
                self.auto(**signals)
        with self.assertRaises(self.api.SelectionError):
            self.auto("07:00")
        with self.assertRaises(self.api.SelectionError):
            self.api.select_auto(None, {})

    def test_manual_state_survives_reload_and_all_automatic_evaluations(self):
        import tempfile
        from state import read_state
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "theme-state.toml"
            path.write_text('mode = "manual"\nactive = "gothic"\n'
                            'last_manual = "gothic"\ncontext = "legacy"\n')
            before = path.read_bytes()
            for signals in ({"special": "hybrid"}, {"project": "pandawave"},
                            {"gaming": True}, {"focus": True}, {}):
                state = read_state(path)
                decision = self.auto(datetime(2026, 10, 9, 7), **signals)
                effective = self.api.effective_decision(state, decision)
                self.assertEqual((effective.slug, effective.source, effective.reason),
                                 ("gothic", "manual", "persistent manual selection"))
                self.assertEqual(read_state(path), state)
            self.assertEqual(path.read_bytes(), before)

    def test_explicit_auto_proposes_return_and_preserves_last_manual_and_context(self):
        state = ThemeState("manual", "gothic", "gothic", "legacy")
        proposal = self.api.propose_command(state, "auto", self.auto(project="pandawave"))
        self.assertEqual(proposal, ThemeState("auto", "pandawave", "gothic", "legacy"))
        self.assertEqual(state.mode, "manual")

    def test_manual_commands_canonicalize_all_names(self):
        for name, want in (("minimal", "minimal"), ("cyber", "cyber"),
                           ("gothic", "gothic"), ("hybrid", "hybrid"),
                           ("pandawave", "pandawave"), ("wave", "pandawave")):
            proposal = self.api.propose_command(None, name, self.auto())
            self.assertEqual(proposal, ThemeState("manual", want, want, ""))

    def test_cycling_both_directions_and_wraps_enters_manual_mode(self):
        for active, next_slug, prev_slug in (("minimal", "cyber", "pandawave"),
                                            ("cyber", "gothic", "minimal"),
                                            ("gothic", "hybrid", "cyber"),
                                            ("hybrid", "pandawave", "gothic"),
                                            ("pandawave", "minimal", "hybrid")):
            state = ThemeState("auto", active, "gothic", "legacy")
            for command, want in (("next", next_slug), ("previous", prev_slug)):
                with self.subTest(active=active, command=command):
                    proposal = self.api.propose_command(state, command, self.auto())
                    self.assertEqual(proposal, ThemeState("manual", want, want, "legacy"))
        self.assertEqual(self.api.propose_command(None, "next", self.auto()).active, "minimal")
        self.assertEqual(self.api.propose_command(None, "previous", self.auto()).active, "pandawave")

    def test_unknown_commands_reject_without_changing_input(self):
        state = ThemeState("manual", "gothic", "gothic", "legacy")
        for command in ("unknown", "status", "MANUAL", "manual", "", None):
            with self.subTest(command=command), self.assertRaises(self.api.SelectionError):
                self.api.propose_command(state, command, self.auto())
        self.assertEqual(state, ThemeState("manual", "gothic", "gothic", "legacy"))

    def test_decision_rejects_unknown_or_noncanonical_candidates(self):
        for slug in ("wave", "unknown", None):
            with self.assertRaises(self.api.SelectionError):
                self.api.Decision(slug, "reason", "special")


if __name__ == "__main__":
    unittest.main()
