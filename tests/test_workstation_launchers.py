import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "bootstrap/assets"


@unittest.skipUnless(shutil.which("fish"), "Fish is required")
class WorkstationLaunchers(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name)
        self.bin = self.home / "bin"
        self.bin.mkdir()
        self.desktop = self.home / "data/applications/panda-gog-heroic.desktop"
        self.shortcut = self.home / "config/fish/functions/gog.fish"

    def stub(self, name, script):
        target = self.bin / name
        target.write_text("#!/bin/sh\n" + script)
        target.chmod(0o755)

    def launchers(self, mode):
        return subprocess.run(
            ["fish", "--no-config", "-c",
             'function ui_error; echo $argv >&2; end; function ui_info; echo $argv; end; '
             'set -gx XDG_CONFIG_HOME "$HOME/config"; set -gx XDG_DATA_HOME "$HOME/data"; '
             'source "$argv[1]"; panda_setup_gog_launchers "$argv[2]" "$argv[3]"',
             str(ROOT / "bootstrap/lib/workstation.fish"), str(ASSETS), mode],
            env={**os.environ, "HOME": str(self.home),
                 "XDG_CONFIG_HOME": str(self.home / "fish-startup/config"),
                 "XDG_DATA_HOME": str(self.home / "fish-startup/data"),
                 "PATH": f"{self.bin}{os.pathsep}{os.defpath}"},
            capture_output=True, text=True, timeout=5,
        )

    def test_verify_missing_is_read_only_and_apply_is_idempotent(self):
        self.assertNotEqual(self.launchers("verify").returncode, 0)
        self.assertFalse(self.desktop.parent.parent.exists())
        self.assertFalse(self.shortcut.parent.parent.parent.exists())
        self.assertEqual(self.launchers("apply").returncode, 0)
        paths = (self.desktop, self.shortcut)
        before = [(p.read_bytes(), p.stat().st_ino, p.stat().st_mtime_ns) for p in paths]
        self.assertEqual(self.launchers("verify").returncode, 0)
        self.assertEqual(self.launchers("apply").returncode, 0)
        self.assertEqual([(p.read_bytes(), p.stat().st_ino, p.stat().st_mtime_ns) for p in paths], before)

    def test_custom_launchers_require_review_and_are_preserved(self):
        for target in (self.desktop, self.shortcut):
            target.parent.mkdir(parents=True)
            target.write_text("custom")
        for mode in ("apply", "verify"):
            result = self.launchers(mode)
            self.assertNotEqual(result.returncode, 0)
            for target in (self.desktop, self.shortcut):
                self.assertIn(str(target), result.stderr)
                self.assertEqual(target.read_text(), "custom")
            self.assertIn("manual review", result.stderr)

    def test_conflicting_gog_command_in_both_modes(self):
        self.assertEqual(self.launchers("apply").returncode, 0)
        self.shortcut.unlink()
        self.stub("gog", "exit 0\n")
        for mode in ("apply", "verify"):
            result = self.launchers(mode)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(str(self.bin / "gog"), result.stderr)
            self.assertFalse(self.shortcut.exists())

    def test_publication_race_with_custom_file(self):
        self.stub("ln", 'printf custom > "$4"\nexit 1\n')
        result = self.launchers("apply")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(str(self.desktop), result.stderr)
        self.assertEqual(self.desktop.read_text(), "custom")
        self.assertFalse(list(self.desktop.parent.glob(".panda-gog.*")))

    def test_symlinked_launcher_directory_requires_review(self):
        redirected = self.home / "redirected"
        redirected.mkdir()
        self.desktop.parent.parent.mkdir()
        self.desktop.parent.symlink_to(redirected, target_is_directory=True)
        for mode in ("apply", "verify"):
            result = self.launchers(mode)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("manual review", result.stderr)
            self.assertIn(str(self.desktop.parent), result.stderr)
            self.assertEqual(list(redirected.iterdir()), [])

    def test_publication_race_with_fifo(self):
        self.stub("ln", 'mkfifo -- "$4"\nexit 1\n')
        result = self.launchers("apply")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("manual review", result.stderr)
        self.assertTrue(self.desktop.is_fifo())

    def test_publication_race_with_matching_file(self):
        self.stub("ln", 'cp -- "$3" "$4"\nexit 1\n')
        self.assertEqual(self.launchers("apply").returncode, 0)
        self.assertEqual(self.launchers("verify").returncode, 0)

    def test_chatgpt_inventory_rejects_apply(self):
        result = subprocess.run(
            ["fish", "--no-config", str(ROOT / "bootstrap/panda-setup.fish"),
             "--chatgpt-desktop", "--apply", "--yes"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("standalone read-only inventory", result.stdout + result.stderr)

    def test_gog_requires_user_heroic(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [shutil.which("fish"), "--no-config", "-c", 'source "$argv[1]"; gog',
                 str(ASSETS / "gog.fish")],
                env={**os.environ, "PATH": directory}, capture_output=True, text=True,
            )
        self.assertEqual(result.returncode, 1)
        self.assertIn("user-scoped Heroic", result.stderr)

    def test_gog_launches_user_heroic_in_background(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory)
            flatpak = fixture / "flatpak"
            flatpak.write_text(
                '#!/bin/sh\n'
                'case "$1" in\n'
                '  info) test "$*" = "info --user com.heroicgameslauncher.hgl";;\n'
                '  run) printf "%s\\n" "$*" > "$PANDA_LAUNCH_LOG";;\n'
                '  *) exit 1;;\n'
                'esac\n'
            )
            flatpak.chmod(0o755)
            log = fixture / "launch"
            subprocess.run(
                ["fish", "--no-config", "-c",
                 'source "$argv[1]"; gog; or exit $status; '
                 'for attempt in (seq 50); test -s "$PANDA_LAUNCH_LOG"; and exit 0; sleep 0.02; end; exit 1',
                 str(ASSETS / "gog.fish")],
                env={**os.environ, "PATH": f"{directory}{os.pathsep}{os.defpath}",
                     "PANDA_LAUNCH_LOG": str(log)}, check=True, timeout=5,
            )
            self.assertEqual(log.read_text().strip(), "run --user com.heroicgameslauncher.hgl")

    def test_detached_launch_reports_flatpak_failure(self):
        self.stub("flatpak", 'case "$1" in info) exit 0;; run) exit 42;; esac\n')
        result = subprocess.run(
            [shutil.which("fish"), "--no-config", "-c", 'source "$argv[1]"; gog',
             str(ASSETS / "gog.fish")],
            env={**os.environ, "HOME": str(self.home),
                 "XDG_CONFIG_HOME": str(self.home / "config"),
                 "XDG_DATA_HOME": str(self.home / "data"),
                 "PATH": f"{self.bin}{os.pathsep}{os.defpath}"},
            capture_output=True, text=True, timeout=5,
        )
        self.assertIn("Heroic Flatpak exited with status 42", result.stderr)

    @unittest.skipUnless(shutil.which("desktop-file-validate"), "desktop-file-utils is required")
    def test_desktop_entry(self):
        subprocess.run(
            ["desktop-file-validate", str(ASSETS / "panda-gog-heroic.desktop")], check=True,
        )
