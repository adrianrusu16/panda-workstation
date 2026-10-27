"""D4C1 assessment uses disposable fixtures only; no host files or services."""
import errno
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "theme/panda/common"))


class PreservedReadTests(unittest.TestCase):
    def setUp(self):
        from desktop_assessment import read_preserved, AccessRefused
        self.read = read_preserved
        self.refused = AccessRefused

    def test_bytes_and_all_stat_times_are_unchanged(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "fixture"
            p.write_bytes(b"[Group]\nKey=value\\nraw\n")
            os.utime(p, ns=(1_000_000_000, 2_000_000_000))
            before = p.stat()
            data, receipt = self.read(p)
            after = p.stat()
            self.assertEqual(data, b"[Group]\nKey=value\\nraw\n")
            self.assertEqual(before, after)
            self.assertEqual(receipt["before"], receipt["after"])
            self.assertEqual(receipt["before"]["atime_ns"], 1_000_000_000)
            self.assertEqual(len(receipt["sha256"]), 64)
            self.assertTrue(receipt["parent_bindings_verified"])

    def test_symlink_parent_and_leaf_are_refused(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            (base / "real").mkdir()
            (base / "real/file").write_bytes(b"keep")
            (base / "alias").symlink_to(base / "real", target_is_directory=True)
            (base / "leaf").symlink_to(base / "real/file")
            for p in (base / "alias/file", base / "leaf"):
                with self.subTest(path=p), self.assertRaises(self.refused):
                    self.read(p)

    def test_hardlink_fifo_oversize_and_wrong_owner_are_refused(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "file"
            p.write_bytes(b"data")
            with self.assertRaises(self.refused):
                self.read(p, max_bytes=2)
            with self.assertRaises(self.refused):
                self.read(p, expected_uid=os.getuid() + 1)
            os.link(p, Path(td) / "hard")
            with self.assertRaises(self.refused):
                self.read(p)
            os.mkfifo(Path(td) / "fifo")
            with self.assertRaises(self.refused):
                self.read(Path(td) / "fifo")

    def test_permission_failure_never_falls_back_to_plain_read(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "file"
            p.write_bytes(b"data")
            original = os.open
            calls = []
            def deny_noatime(path, flags, *args, **kwargs):
                if flags & os.O_NOATIME:
                    calls.append(flags)
                    raise PermissionError(errno.EPERM, "fixture refusal")
                return original(path, flags, *args, **kwargs)
            with patch("desktop_assessment.os.open", side_effect=deny_noatime):
                with self.assertRaises(self.refused):
                    self.read(p)
            self.assertEqual(len(calls), 1)

    def test_source_mutation_during_read_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "file"
            p.write_bytes(b"data")
            original = os.read
            changed = False
            def mutate(fd, size):
                nonlocal changed
                data = original(fd, size)
                if data and not changed:
                    changed = True
                    p.write_bytes(b"DIFFERENT")
                return data
            with patch("desktop_assessment.os.read", side_effect=mutate):
                with self.assertRaises(self.refused):
                    self.read(p)


    def test_parent_binding_drift_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            parent = Path(td) / "parent"
            parent.mkdir()
            p = parent / "file"
            p.write_bytes(b"data")
            original = os.read
            changed = False
            def replace_parent(fd, size):
                nonlocal changed
                data = original(fd,size)
                if data and not changed:
                    changed = True
                    parent.rename(Path(td)/"retained")
                    parent.mkdir()
                return data
            with patch("desktop_assessment.os.read",side_effect=replace_parent):
                with self.assertRaises(self.refused):
                    self.read(p)

    def test_supported_xattrs_are_preserved_and_fingerprinted(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"file";p.write_bytes(b"data")
            try:
                os.setxattr(p,"user.panda-fixture",b"metadata-marker")
            except OSError as error:
                if error.errno in (errno.ENOTSUP,errno.EOPNOTSUPP):
                    self.skipTest("fixture filesystem lacks xattrs")
                raise
            _,receipt=self.read(p)
            self.assertIn("user.panda-fixture",receipt["xattr_sha256"])
            self.assertEqual(os.getxattr(p,"user.panda-fixture"),b"metadata-marker")
            self.assertEqual(receipt["before"],receipt["after"])

    def test_missing_noatime_support_is_refused_without_open(self):
        with patch("desktop_assessment.os.O_NOATIME",create=False) as flag:
            # Remove the attribute entirely to model a platform without the flag.
            import desktop_assessment
            del desktop_assessment.os.O_NOATIME
            try:
                with self.assertRaises(self.refused):
                    self.read(Path("/unused-fixture"))
            finally:
                desktop_assessment.os.O_NOATIME=flag


class KConfigAssessmentTests(unittest.TestCase):
    def test_raw_values_are_not_expanded_or_interpreted(self):
        from desktop_assessment import parse_groups
        groups = parse_groups(b"[Containments][10]\nplugin=org.kde.plasma.folder\n[General]\nPath[$e]=$HOME/private\nList=a\\,b,c\n")
        self.assertEqual(groups[("General",)]["Path[$e]"], "$HOME/private")
        self.assertEqual(groups[("General",)]["List"], r"a\,b,c")

    def test_duplicate_and_malformed_input_is_refused(self):
        from desktop_assessment import parse_groups
        for raw in (b"[G]\na=1\na=2", b"[G]\na=1\n[G]\nb=2", b"[G", b"bad", b"a=\x00"):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                parse_groups(raw)

    def test_panel_clock_is_not_reused_and_ambiguous_desktop_instances_are_gated(self):
        from desktop_assessment import parse_groups, classify_instances
        raw = b"[Containments][10]\nplugin=org.kde.plasma.folder\n[Containments][20]\nplugin=org.kde.panel\n[Containments][20][Applets][21]\nplugin=org.kde.plasma.digitalclock\n"
        groups = parse_groups(raw)
        result = classify_instances(groups, "org.kde.plasma.digitalclock", 10)
        self.assertEqual(result["status"], "absent")
        self.assertEqual(result["other_instances"][0]["id"], 21)
        for ident in (11, 12):
            groups[("Containments", "10", "Applets", str(ident))] = {"plugin": "org.kde.plasma.digitalclock"}
        result = classify_instances(groups, "org.kde.plasma.digitalclock", 10)
        self.assertEqual(result["status"], "ambiguous")
        self.assertEqual([x["id"] for x in result["matches"]], [11, 12])
        del groups[("Containments", "10", "Applets", "12")]
        self.assertEqual(classify_instances(groups, "org.kde.plasma.digitalclock", 10)["status"], "existing")
        self.assertEqual(groups[("Containments", "20", "Applets", "21")]["plugin"], "org.kde.plasma.digitalclock")


    def test_unassessed_identity_syntax_is_refused_instead_of_reported_absent(self):
        from desktop_assessment import parse_groups, classify_instances
        prefix = b"[Containments][10]\nplugin=org.kde.plasma.folder\n"
        for entry in (
                b"[Containments][10][Applets][11]\nplugin[$i]=org.kde.plasma.digitalclock\n",
                b"[Containment\\x73][10][Applets][11]\nplugin=org.kde.plasma.digitalclock\n",
                b"[Containments][10][Applets][11]\nplu\\x67in=org.kde.plasma.digitalclock\n",
                b"[Containments][10][Applets][11][$i]\nplugin=org.kde.plasma.digitalclock\n",
                b"[Containments][10][Applets][1\\x31]\nplugin=org.kde.plasma.digitalclock\n",
                b"[Containments][10][Applets][11]\nplugin=org.kde.plasma.digitalclock\\x20\n"):
            with self.subTest(entry=entry), self.assertRaises(ValueError):
                groups = parse_groups(prefix + entry)
                classify_instances(groups, "org.kde.plasma.digitalclock", 10)

    def test_nested_tray_role_is_reported_without_reparenting(self):
        from desktop_assessment import parse_groups, classify_instances
        groups = parse_groups(b"[Containments][10]\nplugin=org.kde.plasma.folder\n[Containments][20]\nplugin=org.kde.panel\n[Containments][20][Applets][22]\nplugin=org.kde.plasma.systemtray\n[Containments][20][Applets][22][Applets][23]\nplugin=org.kde.plasma.weather\n")
        result = classify_instances(groups, "org.kde.plasma.weather", 10)
        self.assertEqual(result["status"], "absent")
        self.assertEqual(len(result["other_instances"]), 1)
        self.assertEqual(result["other_instances"][0]["parent_id"], 22)
        self.assertEqual(result["other_instances"][0]["parent_kind"], "applet")


class CandidateTests(unittest.TestCase):
    def setUp(self):
        import json
        from desktop_layout import load_config
        self.root = Path(__file__).resolve().parents[1]
        self.config = load_config(self.root / "theme/panda/common/desktop/layout.toml")
        self.fixture = json.loads((self.root / "tests/fixtures/desktop/assessment/sanitized-shape.json").read_text())

    def test_only_clock_media_are_proposed_and_panel_clock_pins_count_are_preserved(self):
        import copy
        from desktop_assessment import build_candidate, validate_candidate
        before = copy.deepcopy(self.fixture)
        candidate = build_candidate(self.config, self.fixture, installed_plasma="6.8.1")
        validate_candidate(candidate,self.config)
        self.assertEqual(self.fixture, before)
        self.assertEqual(candidate["preserved_fixture"], before)
        self.assertEqual([x["role"] for x in candidate["roles"]], ["clock","media"])
        self.assertTrue(all(x["instance_id"] is None for x in candidate["roles"]))
        self.assertTrue(all(x["binding"] == "new_instance_proposed" for x in candidate["roles"]))
        self.assertEqual(candidate["roles"][0]["rect"], [1608,72,288,88])
        self.assertEqual(candidate["roles"][1]["rect"], [1608,172,288,120])
        self.assertFalse(candidate["ready_for_native_test"])
        self.assertIn("installed-version-differs-from-baseline", candidate["stop_conditions"])
        self.assertFalse(candidate["native_verified"])
        self.assertEqual(candidate["roles"][1]["settings"], {})

    def test_existing_desktop_clock_reuses_identity_and_panel_binding_is_rejected(self):
        import copy
        from desktop_assessment import build_candidate
        value = copy.deepcopy(self.fixture)
        value["applets"].append(dict(id=11,containment_id=10,plugin="org.kde.plasma.digitalclock",geometry=[0,0,100,100],config={"preserve":"sentinel"}))
        value["bindings"]["clock"] = 11
        candidate = build_candidate(self.config,value,installed_plasma="6.7.5")
        self.assertEqual(candidate["roles"][0]["binding"],"reuse_existing_desktop_instance")
        self.assertEqual(candidate["roles"][0]["instance_id"],11)
        self.assertEqual(candidate["preserved_fixture"]["applets"][-1]["config"],{"preserve":"sentinel"})
        value["bindings"]["clock"] = 26
        with self.assertRaises(ValueError):
            build_candidate(self.config,value,installed_plasma="6.7.5")

    def test_candidate_rejects_unknown_keys_native_claims_plugins_faces_and_settings(self):
        import copy
        from desktop_assessment import build_candidate, validate_candidate
        candidate=build_candidate(self.config,self.fixture,installed_plasma="6.8.1")
        for mutate in (lambda x:x.update(extra=True),
                       lambda x:x.update(native_verified=True),
                       lambda x:x.update(ready_for_native_test=True),
                       lambda x:x["roles"][1].update(rect=[3000,172,288,120]),
                       lambda x:x["roles"][0].update(plugin="arbitrary.plugin"),
                       lambda x:x["roles"][0]["settings"].update({"Appearance/unknown":True}),
                       lambda x:x["roles"][1].update(settings={"face":"arbitrary.face"})):
            value=copy.deepcopy(candidate);mutate(value)
            with self.assertRaises(ValueError):
                validate_candidate(value,self.config)


    def test_published_candidate_is_reproducible_and_remains_synthetic(self):
        import json
        from desktop_assessment import build_candidate,validate_candidate
        path=self.root/"docs/panda-theme/d4c1/clock-media-candidate.json"
        published=json.loads(path.read_text())
        self.assertEqual(published,build_candidate(self.config,self.fixture,installed_plasma="6.8.1"))
        validate_candidate(published,self.config)
        self.assertEqual(published["preserved_fixture"]["scope"],"panda-desktop-offline-fixture")


if __name__ == "__main__":
    unittest.main()
