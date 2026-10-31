"""Android source contracts in disposable homes; no vendor tools or installers."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "home/dot_config/fish/conf.d/panda-android.fish"
SCRIPT = ROOT / "bootstrap/setup-android.fish"
FISH = shutil.which("fish")


@unittest.skipUnless(FISH, "Fish is required")
class AndroidProfileContracts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="panda-android-")
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.bin = self.home / "bin"
        self.bin.mkdir()
        self.env = {"HOME": str(self.home), "XDG_CONFIG_HOME": str(self.home / "config"),
                    "XDG_CACHE_HOME": str(self.home / "cache"), "LANG": "C.UTF-8",
                    "PATH": f"{self.bin}:/usr/bin:/bin"}
        # Every forbidden external operation fails and leaves evidence.
        for name in ("sudo", "pacman", "curl", "wget", "chezmoi", "rustup", "codex"):
            self.executable(self.bin / name,
                            'echo forbidden >> "$HOME/forbidden"; exit 98')

    def executable(self, path, body):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/bin/sh\n" + body + "\n")
        path.chmod(0o755)
        return path

    def jdk(self, major=21):
        root = self.home / f"custom jdk {major}"
        root.mkdir()
        (root / "release").write_text(f'JAVA_VERSION="{major}.0.8"\nIMPLEMENTOR="Fixture"\n')
        self.executable(root / "bin/java", f'echo \'openjdk version "{major}.0.8"\' >&2')
        self.executable(root / "bin/javac", f"echo 'javac {major}.0.8'")
        self.env["JAVA_HOME"] = str(root)
        return root

    def sdk(self, default=False, tools="latest"):
        root = self.home / ("Android/Sdk" if default else "custom sdk")
        self.executable(root / "platform-tools/adb", 'echo adb')
        self.executable(root / f"cmdline-tools/{tools}/bin/sdkmanager",
                        'echo vendor-executed >> "$HOME/forbidden"; exit 98')
        platform = root / "platforms/android-36.1"
        platform.mkdir(parents=True)
        (platform / "android.jar").write_text("fixture, not a real SDK\n")
        build = root / "build-tools/36.0.0"
        self.executable(build / "aapt2", 'echo aapt2')
        (build / "source.properties").write_text("Pkg.Revision=36.0.0\n")
        if not default:
            self.env["ANDROID_HOME"] = str(root)
        return root

    def run_fish(self, code, *args):
        result = subprocess.run([FISH, "--no-config", "-c", code, "--", *map(str, args)],
                                env=self.env, capture_output=True, text=True, timeout=10)
        self.assertFalse((self.home / "forbidden").exists(), result.stdout + result.stderr)
        return result

    def source(self, tail=""):
        self.assertTrue(CONFIG.is_file(), "Android Fish environment is missing")
        return self.run_fish('source "$argv[1]"; ' + tail, CONFIG)

    def setup(self, *args):
        self.assertTrue(SCRIPT.is_file(), "Android review/check command is missing")
        return self.run_fish('fish --no-config "$argv[1]" $argv[2..]', SCRIPT, *args)

    def test_disabled_profile_leaves_environment_unchanged(self):
        self.jdk()
        self.sdk(default=True)
        result = self.source('printf "%s\\n" "$ANDROID_HOME"; contains -- "$JAVA_HOME/bin" $PATH; '
                             'and exit 9; exit 0')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "")

    def test_absent_sdk_is_not_created_or_exported(self):
        self.env["PANDA_ANDROID"] = "1"
        result = self.source('set -q ANDROID_HOME; and exit 9; exit 0')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.home / "Android").exists())

    def test_default_sdk_and_explicit_jdk_are_exported_with_existing_paths_only(self):
        self.env["PANDA_ANDROID"] = "1"
        jdk = self.jdk()
        sdk = self.sdk(default=True)
        result = self.source('printf "%s\\n" "$JAVA_HOME" "$ANDROID_HOME"; command -s java; '
                             'command -s javac; command -s sdkmanager; command -s adb; '
                             'set -q ANDROID_SDK_ROOT; and exit 9; exit 0')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), [str(jdk), str(sdk), str(jdk / "bin/java"),
                         str(jdk / "bin/javac"), str(sdk / "cmdline-tools/latest/bin/sdkmanager"),
                         str(sdk / "platform-tools/adb")])

    def test_valid_explicit_choices_win_and_repeated_source_preserves_paths(self):
        self.env["PANDA_ANDROID"] = "1"
        jdk = self.jdk(25)
        sdk = self.sdk(tools="19.0")
        self.sdk(default=True)
        result = self.source('set -l before $PATH; set -l universal $fish_user_paths; '
                             'source "$argv[1]"; test (string join : -- $before) = '
                             '(string join : -- $PATH); or exit 9; '
                             'test "$universal" = "$fish_user_paths"; or exit 10; '
                             'printf "%s\\n" "$JAVA_HOME" "$ANDROID_HOME"; command -s sdkmanager')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), [str(jdk), str(sdk),
                         str(sdk / "cmdline-tools/19.0/bin/sdkmanager")])
        self.assertFalse((self.home / "config/fish/fish_variables").exists())

    def test_empty_default_directory_is_not_an_sdk(self):
        self.env["PANDA_ANDROID"] = "1"
        (self.home / "Android/Sdk").mkdir(parents=True)
        result = self.source('set -q ANDROID_HOME; and exit 9; exit 0')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_intentionally_selected_jdk_on_path_is_preserved_without_java_home(self):
        self.env["PANDA_ANDROID"] = "1"
        jdk = self.jdk(25)
        del self.env["JAVA_HOME"]
        self.env["PATH"] = f"{jdk / 'bin'}:{self.env['PATH']}"
        result = self.source('printf "%s\\n" "$JAVA_HOME"; command -s java')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), [str(jdk), str(jdk / "bin/java")])

    def test_highest_versioned_tools_selected_when_latest_is_absent(self):
        self.env["PANDA_ANDROID"] = "1"
        sdk = self.sdk(tools="9.0")
        self.executable(sdk / "cmdline-tools/19.0/bin/sdkmanager", "exit 98")
        result = self.source('command -s sdkmanager')
        self.assertEqual(result.stdout.strip(), str(sdk / "cmdline-tools/19.0/bin/sdkmanager"))

    def test_conflicting_legacy_sdk_root_is_reported_without_changing_it(self):
        self.jdk()
        self.sdk()
        self.env["ANDROID_SDK_ROOT"] = str(self.home / "another sdk")
        result = self.setup("--check")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("ANDROID_SDK_ROOT", result.stdout)

    def test_dry_run_and_no_arguments_report_gaps_without_executing_tools(self):
        for args in ((), ("--dry-run",)):
            with self.subTest(args=args):
                result = self.setup(*args)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("jdk21-openjdk", result.stdout)
                self.assertIn("platforms;android-36.1", result.stdout)
                self.assertIn("build-tools;36.0.0", result.stdout)
                self.assertFalse((self.home / "Android").exists())

    def test_dry_run_does_not_execute_even_installed_java(self):
        jdk = self.jdk()
        self.sdk()
        self.executable(jdk / "bin/java", 'echo forbidden >> "$HOME/forbidden"')
        result = self.setup("--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_check_fails_for_missing_components(self):
        self.jdk()  # Keep the runtime check inside the disposable fixture.
        result = self.setup("--check")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("ANDROID_HOME", result.stdout)

    def test_check_installed_fixture_is_repeatable_without_vendor_execution(self):
        self.jdk()
        sdk = self.sdk()
        for _ in range(2):
            result = self.setup("--check")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("javac 21.0.8", result.stdout)
            self.assertIn("openjdk version", result.stdout)
            self.assertIn(str(sdk), result.stdout)
            self.assertIn("--list_installed", result.stdout)

    def test_check_rejects_valid_non_21_jdk_without_replacing_it(self):
        jdk = self.jdk(25)
        self.sdk()
        result = self.setup("--check")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(str(jdk), result.stdout)
        self.assertIn("21", result.stdout)

    def test_check_rejects_runtime_metadata_mismatch_and_failed_javac(self):
        jdk = self.jdk()
        self.sdk()
        self.executable(jdk / "bin/java", 'echo \'openjdk version "25.0.1"\' >&2')
        self.executable(jdk / "bin/javac", "echo 'javac 21.0.8'; exit 1")
        result = self.setup("--check")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_check_rejects_incomplete_sdk_even_if_other_sdk_tools_are_on_path(self):
        self.jdk()
        sdk = self.sdk()
        (sdk / "platforms/android-36.1/android.jar").unlink()
        (sdk / "build-tools/36.0.0/source.properties").write_text("Pkg.Revision=35.0.0\n")
        result = self.setup("--check")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("platforms;android-36.1", result.stdout)
        self.assertIn("build-tools;36.0.0", result.stdout)

    def test_check_requires_sdkmanager_inside_selected_sdk(self):
        self.jdk()
        sdk = self.sdk()
        (sdk / "cmdline-tools/latest/bin/sdkmanager").unlink()
        self.executable(self.bin / "sdkmanager", "exit 0")
        result = self.setup("--check")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("Command-Line Tools", result.stdout)

    def test_invalid_sdk_does_not_add_nonexistent_directories(self):
        self.env.update(PANDA_ANDROID="1", ANDROID_HOME=str(self.home / "missing sdk"))
        result = self.source('for entry in $PATH; string match -q "*missing sdk*" -- "$entry"; '
                             'and exit 9; end; exit 0')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_bad_arguments_fail_without_any_installer(self):
        for args in (("--not-a-mode",), ("--check", "--dry-run"), ("unexpected",)):
            with self.subTest(args=args):
                result = self.setup(*args)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
