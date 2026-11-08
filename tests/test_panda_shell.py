"""Repository-local Fish commands in disposable homes, without health tools."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "theme/panda/common/scripts"


class PandaShellContracts(unittest.TestCase):
    def test_artwork_and_health_commands_work_from_unrelated_directory(self):
        with tempfile.TemporaryDirectory(prefix="panda-shell-") as directory:
            root = Path(directory)
            env = {**os.environ, "HOME": directory, "XDG_CONFIG_HOME": directory + "/config",
                   "XDG_STATE_HOME": directory + "/state", "XDG_DATA_HOME": directory + "/data",
                   "XDG_CACHE_HOME": directory + "/cache", "PATH": "/usr/bin:/bin"}
            for command in ("panda", "panda-big", "panda-status"):
                path = SCRIPTS / (command + ".fish")
                self.assertTrue(path.is_file(), f"{command} wrapper missing")
                result = subprocess.run(["fish", "--no-config", str(path), "--no-health"],
                                        env=env, cwd=directory, capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("Panda", result.stdout)
                self.assertNotIn("Traceback", result.stderr)
            self.assertFalse((root / "config/panda/theme-state.toml").exists())

    def test_heading_hierarchy_on_tty_and_clean_redirected_output(self):
        import pty

        command = ["fish", "--no-config", str(SCRIPTS / "panda.fish"), "--no-health"]
        headings = {
            "minimal": ("111;207;151", "221;227;230"),
            "cyber": ("32;215;242", "82;227;151"),
            "gothic": ("219;165;181", "185;181;183"),
            "hybrid": ("54;197;232", "85;217;139"),
            "pandawave": ("251;42;169", "246;120;178"),
        }
        with tempfile.TemporaryDirectory(prefix="panda-shell-") as home:
            env = {**os.environ, "HOME": home, "XDG_CONFIG_HOME": home + "/config",
                   "TERM": "xterm-256color", "COLORTERM": "truecolor"}
            env.pop("NO_COLOR", None)

            def terminal_output(environment, *flags):
                master, slave = pty.openpty()
                try:
                    result = subprocess.run(command + list(flags), env=environment,
                                            stdout=slave, stderr=subprocess.PIPE, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    return os.read(master, 4096).decode()
                finally:
                    os.close(master)
                    os.close(slave)

            for slug, (prominent, secondary) in headings.items():
                with self.subTest(slug=slug):
                    styled = terminal_output(env, "--theme", slug)
                    self.assertIn(f"\x1b[1;38;2;{prominent}mPanda\x1b[0m", styled)
                    self.assertIn(f"\x1b[1;38;2;{secondary}mPalette\x1b[0m", styled)
            self.assertNotIn("\x1b", terminal_output({**env, "NO_COLOR": ""}))
            self.assertNotIn("\x1b", terminal_output({**env, "TERM": "dumb"}))
            self.assertNotIn("\x1b", terminal_output(env, "--no-color"))
            plain = subprocess.check_output(command + ["--theme", "minimal"], env=env,
                                            text=True, timeout=10)
            self.assertIn("Panda Minimal", plain)
            self.assertNotIn("\x1b", plain)

    def test_fastfetch_cannot_add_ansi_to_redirected_output(self):
        import shutil

        with tempfile.TemporaryDirectory(prefix="panda-shell-") as directory:
            root = Path(directory)
            (root / "python3").symlink_to(shutil.which("python3"))
            fastfetch = root / "fastfetch"
            fastfetch.write_text("#!/bin/sh\n"
                                 "test \"$*\" = '--config none --logo none --structure OS:Kernel:Memory --pipe true' || exit 1\n"
                                 "printf '\\033[31mOS: fixture\\033[0m\\n'\n")
            fastfetch.chmod(0o755)
            env = {**os.environ, "HOME": directory, "PATH": directory,
                   "XDG_CONFIG_HOME": directory + "/config", "TERM": "xterm-ghostty"}
            result = subprocess.run([shutil.which("fish"), "--no-config", str(SCRIPTS / "panda.fish")],
                                    env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("OS: fixture", result.stdout)
            self.assertNotIn("\x1b", result.stdout)

    def test_health_output_has_honest_missing_tool_fallbacks(self):
        import shutil
        with tempfile.TemporaryDirectory(prefix="panda-shell-") as directory:
            root = Path(directory)
            (root / "bin").mkdir()
            (root / "bin/python3").symlink_to(shutil.which("python3"))
            env = {**os.environ, "HOME": directory, "PATH": str(root / "bin"),
                   "XDG_CONFIG_HOME": directory + "/config", "XDG_STATE_HOME": directory + "/state",
                   "XDG_CACHE_HOME": directory + "/cache", "XDG_DATA_HOME": directory + "/data"}
            result = subprocess.run([shutil.which("fish"), "--no-config", str(SCRIPTS / "panda-status.fish")],
                                    env=env, cwd=directory, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("unavailable", result.stdout)
            self.assertIn("GPU", result.stdout)
            self.assertIn("unverified", result.stdout)


if __name__ == "__main__":
    unittest.main()
