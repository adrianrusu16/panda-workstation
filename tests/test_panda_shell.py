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
