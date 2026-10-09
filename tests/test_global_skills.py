"""Offline integrity contracts for the reviewed global skill packages (stdlib only)."""

import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import unittest
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "home/dot_agents/skills"
LOCAL = ROOT / ".agents/skills"
UPSTREAM = "https://github.com/jakubkrehel/skills"
REVISION = "d574cc8a576dc24256ad38268b8d03d86724a1b3"
LICENSE_SHA256 = "ed1dfe988fc40511b4845ccd9050a143a2002fee3bedc8064c47fa342b5d8d4f"
COMMON = {"SKILL.md", "LICENSE", "agents/openai.yaml"}
PACKAGES = {
    "better-ui": COMMON | {
        "animations.md", "enter-exit.md", "icon-transitions.md", "icons.md",
        "performance.md", "surfaces.md",
    },
    "better-layout": COMMON | {"grouping-and-alignment.md", "spacing-and-adaptivity.md"},
    "better-colors": COMMON | {
        "color-formats.md", "color-usage.md", "contrast.md", "palette-generation.md",
        "palette-structure.md", "token-naming.md",
    },
    "better-accessibility": COMMON | {
        "focus-and-keyboard.md", "forms.md", "hit-areas.md", "motion-and-zoom.md",
        "screen-readers.md", "semantics-and-aria.md",
    },
}
SPECIALTY = {"animate", "prototype", "graphify", "panda-theme-system"}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_blob_sha1(path):
    content = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()


class GlobalSkillContracts(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SOURCE.is_dir(), "global skill sources have not been prepared")
        provenance = SOURCE / "PROVENANCE.json"
        self.assertTrue(provenance.is_file(), "global provenance manifest is missing")
        self.raw_manifest = provenance.read_text(encoding="utf-8")
        self.manifest = json.loads(self.raw_manifest)

    def test_only_approved_complete_packages_are_present(self):
        self.assertEqual({p.name for p in SOURCE.iterdir()}, set(PACKAGES) | {"PROVENANCE.json"})
        for name, expected in PACKAGES.items():
            with self.subTest(skill=name):
                package = SOURCE / name
                actual = {p.relative_to(package).as_posix()
                          for p in package.rglob("*") if p.is_file()}
                self.assertEqual(actual, expected)
                self.assertEqual({p.relative_to(package).as_posix()
                                  for p in package.rglob("*") if p.is_dir()}, {"agents"})

    def test_provenance_has_pinned_origins_and_explicit_verification_states(self):
        self.assertEqual(set(self.manifest), {
            "schema_version", "source_root", "target_root", "migration_phase", "skills",
        })
        self.assertEqual(self.manifest["schema_version"], 1)
        self.assertIn(self.manifest["migration_phase"], {"source-prepared", "finalized"})
        self.assertEqual(set(self.manifest["skills"]), set(PACKAGES))
        self.assertEqual(self.raw_manifest,
                         json.dumps(self.manifest, indent=2, sort_keys=True) + "\n")
        for name, entry in self.manifest["skills"].items():
            with self.subTest(skill=name):
                self.assertEqual(set(entry), {
                    "upstream", "license", "license_file", "scope", "adaptations",
                    "verification", "files",
                })
                self.assertEqual(entry["upstream"], {
                    "repository": UPSTREAM, "commit": REVISION,
                    "skill_directory": f"skills/{name}", "license_path": "LICENSE",
                })
                self.assertEqual(entry["license"], "MIT")
                self.assertEqual(entry["license_file"], "LICENSE")
                self.assertEqual(entry["scope"], "user")
                self.assertEqual(entry["adaptations"], [])
                verification = entry["verification"]
                self.assertEqual(set(verification), {
                    "upstream_git_blobs", "repository_copy_sha256", "deployment",
                    "cli_discovery_and_invocation", "desktop_discovery_and_invocation",
                })
                self.assertEqual(verification["upstream_git_blobs"], "verified")
                self.assertEqual(verification["repository_copy_sha256"], "verified")
                for check in ("deployment", "cli_discovery_and_invocation",
                              "desktop_discovery_and_invocation"):
                    self.assertIn(verification[check], {"pending", "verified"})

    def test_inventory_hashes_match_every_file_and_recorded_upstream_blob(self):
        for name, expected in PACKAGES.items():
            with self.subTest(skill=name):
                entries = self.manifest["skills"][name]["files"]
                paths = [entry["path"] for entry in entries]
                self.assertEqual(paths, sorted(expected))
                for entry in entries:
                    self.assertEqual(set(entry), {
                        "path", "sha256", "upstream_path", "upstream_git_blob_sha1",
                    })
                    relative = PurePosixPath(entry["path"])
                    self.assertFalse(relative.is_absolute())
                    self.assertNotIn("..", relative.parts)
                    path = SOURCE / name / relative
                    self.assertEqual(sha256(path), entry["sha256"], str(path))
                    self.assertEqual(git_blob_sha1(path), entry["upstream_git_blob_sha1"], str(path))
                    upstream_path = "LICENSE" if relative.as_posix() == "LICENSE" else (
                        f"skills/{name}/{relative.as_posix()}"
                    )
                    self.assertEqual(entry["upstream_path"], upstream_path)

    def test_license_copies_retain_the_reviewed_mit_notice(self):
        for name in PACKAGES:
            with self.subTest(skill=name):
                self.assertEqual(sha256(SOURCE / name / "LICENSE"), LICENSE_SHA256)

    def test_skill_headers_have_names_and_nonempty_descriptions(self):
        # Structural checks for these unchanged scalar headers, not a YAML parser.
        names = []
        for name in PACKAGES:
            text = (SOURCE / name / "SKILL.md").read_text(encoding="utf-8")
            header = re.match(r"\A---\n(.*?)\n---\n", text, re.DOTALL)
            self.assertIsNotNone(header, name)
            field = re.search(r"(?m)^name: (\S+)\s*$", header.group(1))
            self.assertIsNotNone(field, name)
            names.append(field.group(1))
            self.assertEqual(field.group(1), name)
            self.assertRegex(header.group(1), r"(?m)^description: \S.+$")
        self.assertEqual(len(names), len(set(names)))

    def test_relative_markdown_references_stay_in_their_complete_package(self):
        for name in PACKAGES:
            package = (SOURCE / name).resolve()
            for path in package.rglob("*.md"):
                for target in re.findall(r"\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
                    parsed = urlsplit(target)
                    if parsed.scheme or parsed.netloc or not parsed.path:
                        continue
                    destination = (path.parent / unquote(parsed.path)).resolve()
                    with self.subTest(file=str(path), reference=target):
                        self.assertTrue(destination.is_relative_to(package))
                        self.assertTrue(destination.is_file(), str(destination))

    def test_deployment_tree_contains_only_regular_nonexecutable_reviewed_files(self):
        forbidden = {".local-ai", ".serena", "graphify-out", "tmp", "__pycache__",
                     ".git", "secrets", "private", "plans", ".env"}
        paths = [ROOT / "home/dot_agents", SOURCE, *SOURCE.rglob("*")]
        for path in paths:
            with self.subTest(path=str(path)):
                self.assertFalse(path.is_symlink())
                self.assertFalse(set(path.relative_to(ROOT).parts) & forbidden)
                self.assertFalse(path.name.startswith(("exact_", "symlink_", "run_", ".chezmoi")))
                if path.is_file():
                    self.assertTrue(stat.S_ISREG(path.stat().st_mode))
                    self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
                    self.assertNotRegex(path.read_text(encoding="utf-8"),
                                        r"-----BEGIN (?:[A-Z]+ )*PRIVATE KEY-----")

    def test_mapping_uses_existing_home_root_and_preserves_specialty_skills(self):
        self.assertEqual((ROOT / ".chezmoiroot").read_text().strip(), "home")
        self.assertEqual(self.manifest["source_root"], "home/dot_agents/skills")
        self.assertEqual(self.manifest["target_root"], ".agents/skills")
        for name in SPECIALTY:
            self.assertTrue((LOCAL / name / "SKILL.md").is_file(), name)
        self.assertTrue((ROOT / "home/dot_codex/AGENTS.md").is_file())

    def test_repo_local_copies_follow_the_explicit_migration_phase(self):
        local_names = {p.name for p in LOCAL.iterdir() if p.is_dir()}
        phase = self.manifest["migration_phase"]
        if phase == "finalized":
            self.assertEqual(local_names & set(PACKAGES), set(), "global/local name collision")
            self.assertEqual(local_names, SPECIALTY)
        else:
            self.assertEqual(local_names, SPECIALTY | set(PACKAGES))
            for name, expected in PACKAGES.items():
                original = LOCAL / name
                self.assertEqual({p.relative_to(original).as_posix()
                                  for p in original.rglob("*") if p.is_file()}, expected)
                for relative in expected:
                    self.assertEqual(sha256(original / relative), sha256(SOURCE / name / relative),
                                     f"temporary copy diverged: {name}/{relative}")


if __name__ == "__main__":
    unittest.main()
