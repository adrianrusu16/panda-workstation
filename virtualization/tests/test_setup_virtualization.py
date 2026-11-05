"""Exercise the recovered shortcut without invoking a host package or VM tool."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(shutil.which("fish"), "Requires Fish")
class SetupVirtualizationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        bootstrap = self.root / "bootstrap"
        (bootstrap / "lib").mkdir(parents=True)
        shutil.copy2(ROOT / "bootstrap/setup-virtualization.fish", bootstrap)
        for name in ("ui.fish", "packages.fish"):
            shutil.copy2(ROOT / "bootstrap/lib" / name, bootstrap / "lib")
        (bootstrap / "panda-setup.fish").write_text(
            "printf '%s\\n' $argv > $CALL_LOG\n")
        fake_bin = self.root / "bin"
        fake_bin.mkdir()
        for name in ("pacman", "sudo", "python", "virsh", "systemctl"):
            executable = fake_bin / name
            executable.write_text("#!/bin/sh\nexit 97\n")
            executable.chmod(0o755)
        self.log = self.root / "calls"
        self.tool_log = self.root / "tool-calls"
        self.env = {
            key: value for key, value in os.environ.items()
            if not key.startswith("XDG_") and key not in {
                "DISPLAY", "WAYLAND_DISPLAY", "DBUS_SESSION_BUS_ADDRESS",
                "DBUS_SYSTEM_BUS_ADDRESS", "SESSION_MANAGER",
            }
        }
        for key, name in (
            ("HOME", "home"), ("XDG_CONFIG_HOME", "config"),
            ("XDG_DATA_HOME", "data"), ("XDG_CACHE_HOME", "cache"),
            ("XDG_STATE_HOME", "state"), ("XDG_RUNTIME_DIR", "runtime"),
            ("XDG_CONFIG_DIRS", "system-config"), ("XDG_DATA_DIRS", "system-data"),
        ):
            directory = self.root / name
            directory.mkdir(mode=0o700)
            self.env[key] = str(directory)
        self.env.update(CALL_LOG=str(self.log), TOOL_CALL_LOG=str(self.tool_log),
                        PATH=str(fake_bin) + os.pathsep + os.environ["PATH"])
        for executable in fake_bin.iterdir():
            executable.write_text(
                "#!/bin/sh\n"
                + "printf '%s\\n' '" + executable.name + "' >> \"$TOOL_CALL_LOG\"\n"
                + "exit 97\n")

    def run_wrapper(self, *args):
        return subprocess.run(["fish", "--no-config", str(self.root / "bootstrap/setup-virtualization.fish"), *args],
                              capture_output=True, text=True, env=self.env, timeout=10)

    def test_modes_delegate_only_selected_packages_to_existing_manager(self):
        for args in ((), ("--dry-run",), ("--check",), ("--verify",), ("--apply", "--yes")):
            with self.subTest(args=args):
                result = self.run_wrapper(*args)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(self.log.read_text().splitlines(), ["--modules", "virtualization", *args])
                self.assertFalse(self.tool_log.exists())

    def test_shortcut_refuses_module_override(self):
        result = self.run_wrapper("--modules", "workspace")
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.log.exists())

    def test_nested_fish_never_sources_user_configuration(self):
        config = Path(self.env["XDG_CONFIG_HOME"]) / "fish"
        (config / "conf.d").mkdir(parents=True)
        marker = self.root / "config-sourced"
        self.env["CONFIG_MARKER"] = str(marker)
        hook = "printf 'sourced\\n' >> \"$CONFIG_MARKER\"\n"
        (config / "conf.d/fixture.fish").write_text(hook)
        (config / "config.fish").write_text(hook)
        result = self.run_wrapper("--dry-run")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(marker.exists(), "nested Fish loaded user configuration")
        self.assertFalse(self.tool_log.exists())
