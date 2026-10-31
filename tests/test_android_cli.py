"""Android CLI contracts against disposable SDKs; no real vendor execution."""

import contextlib
import importlib.util
import io
import os
import pty
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import test_android_automation as fixtures
import test_android_profile as profiles

ROOT = Path(__file__).resolve().parents[1]


class AndroidCliContracts(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.AutomationContracts()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.f.complete()
        (self.f.sdk / "platform-tools/source.properties").write_text("Pkg.Revision=36.0.0\n")
        self.f.calls = []
        self.api = self.f.api
        self.cli = fixtures.load("android_cli")
        self.sdk = self.f.sdk
        self.slot = self.sdk / "cmdline-tools/22.0"
        self.f.executable(self.slot / "bin/android")
        self.f.executable(self.slot / "bin/sdkmanager")
        (self.slot / "lib").mkdir()
        (self.slot / "lib/sdkmanager-classpath.jar").write_bytes(b"fixture")
        (self.slot / "source.properties").write_text("Pkg.Revision=22.0\n")
        self.calls = []
        self.version = "Android CLI 1.0.12345"
        self.root_output = str(self.sdk)
        self.available_revision = "1"

    def candidate(self):
        return self.cli.discover(self.sdk, "22.0")

    def fake(self, args, capture=False):
        self.calls.append((list(map(str, args)), capture))
        tail = list(args[2:])
        if tail == ["-V"]:
            return self.version + "\n"
        if tail == ["--help"]:
            return "Usage: android [--sdk=PARAM]\nCommands:\n  info  Environment\n  sdk  SDK management\n"
        if tail == ["info", "sdk"]:
            return self.root_output + "\n"
        if tail == ["sdk", "--help"]:
            return "Usage: android sdk [--ignore-outdated-xmls]\nCommands:\n  list  Packages\n  install  Packages\n"
        if tail == ["sdk", "install", "--help"]:
            return "Usage: android sdk install [--no-downgrade] <package>[@<version>]\n"
        if tail[:2] == ["sdk", "list"]:
            return ("Installed packages:\n  cmdline-tools/22.0 22.0 CLI tools\n"
                    "  platform-tools 36.0.0 Platform Tools\n"
                    + ("  platforms/android-36.1 1 Android SDK\n" if (self.sdk / "platforms/android-36.1").exists() else "")
                    + "  build-tools/36.0.0 36.0.0 Build Tools\n"
                    "  example-extra/one 2.0.0 Synthetic Extra One\n  example-extra/two 3.0.0 Synthetic Extra Two\n\n"
                    f"Available packages:\n  platforms/android-36.1 {self.available_revision} Android SDK\n")
        if tail[:4] == ["sdk", "--ignore-outdated-xmls", "install", "--no-downgrade"]:
            self.assertEqual(tail[4:], ["platforms/android-36.1@1"])
            self.f.package("platforms;android-36.1")
            return ""
        raise AssertionError(f"Unexpected CLI command: {args}")

    def verify(self, approve=lambda text: True, runner=None):
        return self.cli.verify(self.candidate(), self.sdk, runner or self.fake, approve)

    def install(self, approve=lambda text: True, runner=None):
        with contextlib.redirect_stdout(self.f.output):
            return self.api.install(self.f.manifest, self.f.state(), "--install", approve=approve,
                                    run=runner or self.fake)

    def test_prefers_22_slot_and_ignores_shadowing(self):
        self.f.executable(self.sdk / "cmdline-tools/latest/bin/android")
        (self.sdk / "cmdline-tools/latest/source.properties").write_text("Pkg.Revision=99.0\n")
        candidate = self.candidate()
        self.assertEqual(candidate["path"], self.slot / "bin/android")
        self.assertEqual(candidate["package_revision"], "22.0")
        self.assertNotIn("product_version", candidate)
        self.f.env["PATH"] = str(self.f.home / "shadow") + ":/usr/bin:/bin"
        self.f.executable(self.f.home / "shadow/android")
        with contextlib.redirect_stdout(self.f.output):
            self.api.plan(self.f.manifest, self.f.state())
        self.assertIn("PATH shadow", self.f.output.getvalue())
        self.assertIn(str(candidate["path"]), self.f.output.getvalue())
        self.assertIn("runtime", self.f.output.getvalue())
        self.assertEqual(self.calls, [])

    def test_candidate_missing_wrong_metadata_and_permissions_fail_closed(self):
        path = self.slot / "bin/android"
        path.chmod(0o644)
        self.assertIsNone(self.candidate())
        path.chmod(0o777)
        with self.assertRaisesRegex(self.cli.CliError, "writable"):
            self.candidate()
        path.chmod(0o755)
        (self.slot / "source.properties").write_text("Pkg.Revision=wrong\n")
        self.assertIsNone(self.candidate())

    def test_candidate_symlink_and_external_path_refused(self):
        path = self.slot / "bin/android"
        path.unlink()
        path.symlink_to(self.sdk / "cmdline-tools/19.0/bin/sdkmanager")
        with self.assertRaises(self.cli.CliError):
            self.candidate()

    def test_runtime_uses_explicit_root_and_checks_product_version_variance(self):
        for version in ("Android CLI 1.0.12345", "android-cli version 2.3.4", "1.5.6-beta.1"):
            with self.subTest(version=version):
                self.version = version
                result = self.verify()
                self.assertIn("version", result)
        self.assertTrue(all(args[:2] == [str(self.slot / "bin/android"), f"--sdk={self.sdk}"] for args, _ in self.calls))
        self.assertFalse(any("update" in args or "remove" in args or "init" in args for args, _ in self.calls))

    def test_runtime_refusal_starts_no_vendor(self):
        with self.assertRaisesRegex(self.cli.CliError, "declined"):
            self.verify(approve=lambda text: False)
        self.assertEqual(self.calls, [])

    def test_runtime_rejects_wrong_root_bad_version_and_unsupported_commands(self):
        self.root_output = str(self.f.home / "wrong sdk")
        with self.assertRaisesRegex(self.cli.CliError, "SDK root"):
            self.verify()
        self.root_output = str(self.sdk)
        self.version = "not a version"
        with self.assertRaisesRegex(self.cli.CliError, "version"):
            self.verify()
        self.version = "Android CLI 1.2.3"

        def unsupported(args, capture=False):
            if list(args[2:]) == ["sdk", "install", "--help"]:
                return "Usage: unsupported\n"
            return self.fake(args, capture)

        with self.assertRaisesRegex(self.cli.CliError, "install"):
            self.verify(runner=unsupported)

    def test_listing_parser_distinguishes_installed_available_and_all_revisions(self):
        installed, available, updates = self.cli.parse_listing(
            "Installed packages:\n  platforms/android-36.1 1 -> 2 Android\n\n"
            "Available packages:\n  platforms/android-36.1 1 Android\n  platforms/android-36.1 2 Android\n")
        self.assertEqual(installed, {"platforms/android-36.1": "1"})
        self.assertEqual(updates, {"platforms/android-36.1": "2"})
        self.assertEqual(available, {"platforms/android-36.1": {"1", "2"}})
        for text in ("[]", "Installed Packages:\n", "Installed packages:\n malformed\n",
                     "Installed packages:\n platforms;android-36.1 1 Android\n",
                     "Installed packages:\n platforms/android-36.1 broken Android\n",
                     "Installed packages:\n x 1\n x 2\n"):
            with self.subTest(text=text), self.assertRaises(self.cli.CliError):
                self.cli.parse_listing(text)

    def test_healthy_install_noop_preserves_extra_packages_and_never_verifies(self):
        extra = self.sdk / "example-extra/one/sentinel"
        extra.parent.mkdir(parents=True)
        extra.write_bytes(b"preserve synthetic unrelated packages")
        self.install(approve=lambda text: self.fail("No-op must not prompt"))
        self.assertEqual(extra.read_bytes(), b"preserve synthetic unrelated packages")
        self.assertEqual(self.calls, [])
        self.assertIn("No changes", self.f.output.getvalue())

    def test_missing_platform_installs_exact_revision_without_legacy_update_or_removal(self):
        shutil.rmtree(self.sdk / "platforms/android-36.1")
        self.install()
        self.assertTrue(self.f.state()["packages"]["platforms;android-36.1"]["healthy"])
        self.assertEqual(self.calls[-1], ([str(self.slot / "bin/android"), f"--sdk={self.sdk}",
                                        "sdk", "--ignore-outdated-xmls", "install", "--no-downgrade",
                                        "platforms/android-36.1@1"], False))

    def test_unavailable_exact_revision_stops_before_install(self):
        shutil.rmtree(self.sdk / "platforms/android-36.1")
        self.available_revision = "2"
        with self.assertRaisesRegex(self.api.Error, "unavailable"):
            self.install()
        self.assertFalse(any("--no-downgrade" in args for args, _ in self.calls))

    def test_license_review_refusal_prevents_package_command(self):
        shutil.rmtree(self.sdk / "platforms/android-36.1")
        with self.assertRaisesRegex(self.api.Error, "declined"):
            self.install(approve=lambda text: "licenses" not in text.lower())
        self.assertFalse(any("--no-downgrade" in args for args, _ in self.calls))

    def test_unconfirmed_cleanup_never_requests_or_runs_legacy_fallback(self):
        shutil.rmtree(self.sdk / "platforms/android-36.1")
        approvals, attempts = [], []
        def active_vendor(args, capture=False):
            attempts.append(args)
            raise self.api.android_cli.ProcessCleanupError("Vendor cleanup unconfirmed; manual recovery required")
        with self.assertRaisesRegex(self.api.Error, "cleanup unconfirmed"):
            self.install(approve=lambda text: approvals.append(text) or True, runner=active_vendor)
        self.assertEqual(len(attempts), 1)
        self.assertFalse(any("fallback" in prompt.lower() for prompt in approvals))
        self.assertFalse((self.sdk / "platforms/android-36.1").exists())

    def test_failed_contract_never_silently_falls_back(self):
        shutil.rmtree(self.sdk / "platforms/android-36.1")
        self.root_output = "/wrong-sdk"
        with self.assertRaisesRegex(self.api.Error, "declined"):
            self.install(approve=lambda text: "fallback" not in text.lower())
        self.assertFalse(any(Path(args[0]).name == "sdkmanager" for args, _ in self.calls))

    def test_failed_contract_can_use_separately_approved_legacy_fallback(self):
        shutil.rmtree(self.sdk / "platforms/android-36.1")
        self.root_output = "/wrong-sdk"
        approvals = []

        def runner(args, capture=False):
            if Path(args[0]).name == "sdkmanager":
                return self.f.fake_run(args, capture)
            return self.fake(args, capture)

        self.install(approve=lambda text: approvals.append(text) or True, runner=runner)
        self.assertTrue(any("fallback" in text.lower() for text in approvals))
        self.assertEqual(self.f.calls[-1][2:], ["platforms;android-36.1"])

    def test_rechecks_executable_after_approval_before_vendor_execution(self):
        def replace(text):
            (self.slot / "bin/android").write_text("#!/bin/sh\nexit 97\n")
            return True

        with self.assertRaisesRegex(self.cli.CliError, "changed"):
            self.verify(approve=replace)
        self.assertEqual(self.calls, [])

    def test_bounded_runner_preserves_stderr_exit_and_timeout(self):
        binary = self.f.home / "fake vendor"
        self.f.executable(binary, "echo diagnostic >&2; exit 7")
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(self.cli.CliError) as caught:
            self.cli.run_command([str(binary)], env=self.f.env, timeout=2)
        self.assertEqual(caught.exception.code, 7)
        self.assertIn("diagnostic", err.getvalue())
        self.f.executable(binary, "sleep 5")
        with self.assertRaises(self.cli.CliError) as caught:
            self.cli.run_command([str(binary)], env=self.f.env, timeout=0.05)
        self.assertEqual(caught.exception.code, 124)

    def test_runner_interrupt_is_propagated_without_fallback_or_install(self):
        def interrupt(args, capture=False):
            raise KeyboardInterrupt

        shutil.rmtree(self.sdk / "platforms/android-36.1")
        with self.assertRaises(KeyboardInterrupt):
            self.install(runner=interrupt)
        self.assertFalse((self.sdk / "platforms/android-36.1").exists())

    def test_missing_candidate_runtime_check_refuses_without_execution(self):
        (self.slot / "bin/android").unlink()
        with self.assertRaisesRegex(self.cli.CliError, "No safe"):
            self.verify()
        self.assertEqual(self.calls, [])

    def test_unowned_candidate_is_refused(self):
        with patch.object(self.cli.os, "getuid", return_value=-1), self.assertRaisesRegex(self.cli.CliError, "owned"):
            self.candidate()

    def test_runtime_environment_excludes_launcher_overrides_and_auth_variables(self):
        env = {**self.f.env, "ANDROID_CLI_DOWNLOAD_URL": "https://evil.invalid/cli",
               "ANDROID_USER_HOME": "/other", "CODEX_HOME": "/never-read", "PATH": "/shadow"}
        result = self.cli.runtime_env(env, self.sdk, self.slot / "bin/android")
        for key in ("ANDROID_CLI_DOWNLOAD_URL", "ANDROID_USER_HOME", "CODEX_HOME"):
            self.assertNotIn(key, result)
        self.assertEqual(result["HOME"], self.f.env["HOME"])
        self.assertEqual(result["ANDROID_HOME"], str(self.sdk))
        self.assertEqual(result["ANDROID_SDK_ROOT"], str(self.sdk))
        self.assertNotIn("/shadow", result["PATH"])

    def test_runtime_rejects_malformed_inventory_and_candidate_from_another_sdk(self):
        def malformed(args, capture=False):
            if list(args[2:])[:2] == ["sdk", "list"]:
                return '{"packages": []}'
            return self.fake(args, capture)

        with self.assertRaisesRegex(self.cli.CliError, "format"):
            self.verify(runner=malformed)
        with self.assertRaisesRegex(self.cli.CliError, "another SDK"):
            self.cli.verify(self.candidate(), self.f.home / "wrong sdk", self.fake, lambda text: True)

    def test_install_rejects_inventory_disagreement_before_any_package_command(self):
        shutil.rmtree(self.sdk / "platforms/android-36.1")

        def inconsistent(args, capture=False):
            text = self.fake(args, capture)
            return text.replace("platform-tools 36.0.0", "platform-tools 99.0")

        with self.assertRaisesRegex(self.api.Error, "declined"):
            self.install(approve=lambda text: "fallback" not in text.lower(), runner=inconsistent)
        self.assertFalse(any("--no-downgrade" in args for args, _ in self.calls))

    def test_existing_wrong_platform_revision_requires_manual_review_not_downgrade(self):
        (self.sdk / "platforms/android-36.1/source.properties").write_text(
            "Pkg.Revision=2\nAndroidVersion.ApiLevel=36.1\n")
        with self.assertRaisesRegex(self.api.Error, "revision"):
            self.install()
        self.assertEqual(self.calls, [])

    def test_cli_license_rejection_and_wrong_postinstall_revision_are_failures(self):
        shutil.rmtree(self.sdk / "platforms/android-36.1")

        def license_rejected(args, capture=False):
            if "--no-downgrade" in args:
                raise self.cli.CliError("Vendor license refusal", 17)
            return self.fake(args, capture)

        with self.assertRaises(self.cli.CliError) as caught:
            self.install(runner=license_rejected)
        self.assertEqual(caught.exception.code, 17)
        self.assertFalse((self.sdk / "platforms/android-36.1").exists())

        def wrong_revision(args, capture=False):
            output = self.fake(args, capture)
            if "--no-downgrade" in args:
                (self.sdk / "platforms/android-36.1/source.properties").write_text(
                    "Pkg.Revision=2\nAndroidVersion.ApiLevel=36.1\n")
            return output

        with self.assertRaisesRegex(self.api.Error, "revision mismatch"):
            self.install(runner=wrong_revision)

    def test_timeout_stops_descendants_in_interactive_and_captured_modes(self):
        for capture in (False, True):
            with self.subTest(capture=capture):
                marker = self.f.home / f"late-{capture}"
                binary = self.f.home / "forking vendor"
                self.f.executable(binary, f'(trap "" TERM; sleep 0.3; echo late > "{marker}") &\nwait')
                with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(self.cli.CliError) as caught:
                    self.cli.run_command([str(binary)], capture=capture, env=self.f.env, timeout=0.05)
                self.assertEqual(caught.exception.code, 124)
                time.sleep(0.4)
                self.assertFalse(marker.exists(), 'Vendor descendant continued writing after timeout')

    def test_legacy_timeout_uses_same_descendant_cleanup(self):
        marker = self.f.home / "legacy child"
        binary = self.f.home / "forking legacy manager"
        self.f.executable(binary, f'(trap "" TERM; sleep 0.3; echo late > "{marker}") &\nwait')
        real_command = self.api.android_cli.run_command

        def short_timeout(args, **kwargs):
            return real_command(args, **{**kwargs, "timeout": 0.05})

        with patch.object(self.api.android_cli, "run_command", side_effect=short_timeout), \
                contextlib.redirect_stdout(io.StringIO()), self.assertRaises(self.api.Error) as caught:
            self.api.run_vendor([str(binary)])
        self.assertEqual(caught.exception.code, 124)
        time.sleep(0.4)
        self.assertFalse(marker.exists())

    def test_capture_limit_stops_vendor_before_post_output_side_effect(self):
        marker = self.f.home / "after huge output"
        binary = self.f.home / "noisy vendor"
        binary.write_text('#!/usr/bin/python3\nimport os,time\n'
                          'for _ in range(64): os.write(1, b"x" * 65536)\n'
                          f'time.sleep(0.2)\nopen({str(marker)!r}, "w").write("late")\n')
        binary.chmod(0o755)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()), \
                self.assertRaisesRegex(self.cli.CliError, "output"):
            self.cli.run_command([str(binary)], capture=True, env=self.f.env, timeout=3)
        time.sleep(0.3)
        self.assertFalse(marker.exists(), 'Output bound enforced only after vendor finished')

    def test_fallback_refuses_unavailable_or_ambiguous_platform_revision(self):
        (self.slot / "bin/android").unlink()
        shutil.rmtree(self.sdk / "platforms/android-36.1")
        for rows in ("platforms;android-36.1 | 2 | Platform", "platforms;android-36.1 | bad | Platform",
                     "platforms;android-36.1 | 1 | Platform\n platforms;android-36.1 | 2 | Platform"):
            with self.subTest(rows=rows):
                self.f.calls = []

                def runner(args, capture=False):
                    if "--list" in args:
                        return "Available Packages:\n Path | Version | Description\n " + rows
                    return self.f.fake_run(args, capture)

                with self.assertRaisesRegex(self.api.Error, "revision"):
                    self.install(runner=runner)
                self.assertFalse(self.f.calls, 'Legacy package/license command ran for unapproved revision')

    def test_fallback_postinstall_checks_revision_even_if_listing_was_correct(self):
        (self.slot / "bin/android").unlink()
        shutil.rmtree(self.sdk / "platforms/android-36.1")

        def runner(args, capture=False):
            result = self.f.fake_run(args, capture)
            if "platforms;android-36.1" in args[2:]:
                (self.sdk / "platforms/android-36.1/source.properties").write_text(
                    "Pkg.Revision=2\nAndroidVersion.ApiLevel=36.1\n")
            return result

        with self.assertRaisesRegex(self.api.Error, "revision mismatch"):
            self.install(runner=runner)

    def test_unsafe_sdk_permissions_do_not_bypass_checks_through_fallback(self):
        shutil.rmtree(self.sdk / "platforms/android-36.1")
        self.sdk.chmod(0o777)
        with self.assertRaisesRegex(self.api.android_cli.CliError, "writable"):
            self.install(runner=self.f.fake_run)
        self.assertEqual(self.f.calls, [])

    def test_interactive_process_group_preserves_terminal_input(self):
        binary = self.f.home / "fake interactive licenses"
        self.f.executable(binary, 'test -t 0 && test -t 1 && read answer && test "$answer" = "operator chose"')
        master, slave = pty.openpty()
        self.addCleanup(os.close, master)
        self.addCleanup(os.close, slave)
        real_popen = self.cli.subprocess.Popen
        observed = {}

        def terminal_boundary(args, **kwargs):
            observed.update(kwargs)
            return real_popen(args, **{**kwargs, "stdin": slave, "stdout": slave, "stderr": slave})

        os.write(master, b"operator chose\n")
        with patch.object(self.cli.subprocess, "Popen", side_effect=terminal_boundary), \
                contextlib.redirect_stdout(io.StringIO()):
            self.cli.run_command([str(binary)], capture=False, env=self.f.env, timeout=2)
        self.assertNotIn("stdin", observed)
        self.assertIsNone(observed["stdout"])
        self.assertIsNone(observed["stderr"])


@unittest.skipUnless(shutil.which("fish"), "Fish required")
class CliFishContracts(unittest.TestCase):
    def setUp(self):
        self.f = profiles.AndroidProfileContracts()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.f.jdk()
        self.sdk = self.f.sdk(tools="22.0")
        self.f.env["PANDA_ANDROID"] = "1"
        self.path = self.sdk / "cmdline-tools/22.0/bin/android"
        self.f.executable(self.path, 'echo forbidden >> "$HOME/forbidden"; exit 98')
        (self.path.parents[1] / "source.properties").write_text("Pkg.Revision=22.0\n")

    def test_existing_cli_bin_wins_over_shadowing_and_source_is_idempotent(self):
        self.f.executable(self.sdk / "cmdline-tools/latest/bin/sdkmanager", "exit 98")
        self.f.executable(self.sdk / "cmdline-tools/latest/bin/android", "exit 98")
        result = self.f.source('set -l before $PATH; set -l universal $fish_user_paths; '
                               'source "$argv[1]"; test (string join : -- $before) = '
                               '(string join : -- $PATH); or exit 9; '
                               'test "$universal" = "$fish_user_paths"; or exit 10; command -s android')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(self.path))
        self.assertFalse((self.f.home / "config/fish/fish_variables").exists())

    def test_symlinked_cli_directory_is_not_added_to_path(self):
        slot = self.path.parents[1]
        relocated = self.f.home / "external cli"
        slot.rename(relocated)
        slot.symlink_to(relocated, target_is_directory=True)
        # Existing legacy sdkmanager selection remains outside this new CLI
        # promise; the new CLI-only bin must not be added through another slot.
        (relocated / "bin/sdkmanager").unlink()
        result = self.f.source('command -s android; exit 0')
        self.assertEqual(result.stdout.strip(), "")

    def test_plan_and_legacy_check_never_execute_android_cli(self):
        for mode in ("--plan", "--check", "--dry-run"):
            result = self.f.setup(mode)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_noninteractive_cli_check_refuses_before_vendor_execution(self):
        result = self.f.setup("--cli-check")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)


@unittest.skipUnless(shutil.which("fish"), "Fish required")
class MasterAndroidContracts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="panda-master-android-")
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.root = self.home / "source/bootstrap"
        (self.root / "lib").mkdir(parents=True)
        shutil.copy2(ROOT / "bootstrap/setup-workstation.fish", self.root / "setup-workstation.fish")
        shutil.copy2(ROOT / "bootstrap/lib/ui.fish", self.root / "lib/ui.fish")
        for name in ("install-core", "setup-machine", "setup-chezmoi", "setup-github", "install-desktop",
                     "setup-plugins", "setup-development", "validate", "setup-android"):
            path = self.root / f"{name}.fish"
            path.write_text(f'#!/usr/bin/env fish\necho {name} $argv >> "$HOME/calls"\nexit 0\n')
            path.chmod(0o755)
        self.env = {"HOME": str(self.home), "PATH": "/usr/bin:/bin", "TERM": "dumb", "PANDA_ANDROID": "1"}

    def run_master(self, *args):
        return subprocess.run(["fish", "--no-config", str(self.root / "setup-workstation.fish"), *args],
                              env=self.env, capture_output=True, text=True, timeout=10)

    def test_default_setup_does_not_start_android_even_when_profile_enabled(self):
        result = self.run_master()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("setup-android", (self.home / "calls").read_text())
        self.assertIn("setup-development", (self.home / "calls").read_text())

    def test_help_and_list_are_read_only_and_show_optional_stage(self):
        for mode in ("--help", "--list"):
            result = self.run_master(mode)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Android", result.stdout)
            self.assertFalse((self.home / "calls").exists())

    def test_android_dispatch_is_separate_and_defaults_to_plan(self):
        for args, expected in ((["--android"], "--plan"), (["--android", "--check"], "--check"),
                               (["--android", "--cli-check"], "--cli-check"), (["--android", "--install"], "--install")):
            with self.subTest(args=args):
                (self.home / "calls").unlink(missing_ok=True)
                result = self.run_master(*args)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual((self.home / "calls").read_text(), f"setup-android {expected}\n")

    def test_android_dispatch_propagates_refusal_and_failure(self):
        for code in (20, 7, 130):
            path = self.root / "setup-android.fish"
            path.write_text(f"#!/usr/bin/env fish\nexit {code}\n")
            result = self.run_master("--android", "--install")
            self.assertEqual(result.returncode, code)

    def test_extra_or_mixed_master_flags_fail_before_any_stage(self):
        for args in (("--help", "extra"), ("--list", "extra"),
                     ("--android", "--with-audit-lab"), ("--android", "--plan", "extra")):
            with self.subTest(args=args):
                result = self.run_master(*args)
                self.assertEqual(result.returncode, 2)
                self.assertFalse((self.home / "calls").exists())

    def test_invalid_android_mode_never_runs_any_stage(self):
        for args in (("--android", "--update"), ("--android", "--plan", "extra")):
            result = self.run_master(*args)
            self.assertEqual(result.returncode, 2)
            self.assertFalse((self.home / "calls").exists())


if __name__ == "__main__":
    unittest.main()
