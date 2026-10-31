"""Offline Android installer contracts. All vendor/network boundaries are fakes."""

import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile


ROOT = Path(__file__).resolve().parents[1]
HELPERS = ROOT / "bootstrap/lib/android"
RELEASE_FIXTURE = ROOT / "tests/fixtures/android/command-line-tools-22.0.json"


def load(name):
    path = HELPERS / f"{name}.py"
    if not path.is_file():
        raise AssertionError(f"Missing implementation: {path.name}")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class AutomationContracts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="panda-android-automation-")
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.sdk = self.home / "custom sdk"
        self.jdk = self.home / "jdk 21"
        self.executable(self.jdk / "bin/java")
        self.executable(self.jdk / "bin/javac")
        (self.jdk / "release").write_text('JAVA_VERSION="21.0.8"\n')
        self.env = {"HOME": str(self.home), "JAVA_HOME": str(self.jdk),
                    "ANDROID_HOME": str(self.sdk), "PATH": "/usr/bin:/bin"}
        self.archive = load("android_archive")
        load("android_cli")
        self.api = load("automation")
        self.manifest = self.api.load_manifest(ROOT / "config/android/toolchain.toml")
        # Failure fixtures must exercise disabled trust even after the production
        # release pin has been independently verified.
        self.manifest["command_line_tools"] = {"verified": False}
        self.output = io.StringIO()

    def executable(self, path, body="exit 99"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/bin/sh\n" + body + "\n")
        path.chmod(0o755)

    def package(self, package):
        if package == "cmdline-tools;latest":
            root = self.sdk / "cmdline-tools/19.0"
            self.executable(root / "bin/sdkmanager")
            (root / "source.properties").write_text("Pkg.Revision=19.0\n")
            (root / "lib").mkdir(exist_ok=True)
            (root / "lib/sdkmanager-classpath.jar").write_bytes(b"fixture")
        elif package == "platform-tools":
            root = self.sdk / "platform-tools"
            self.executable(root / "adb")
            (root / "source.properties").write_text("Pkg.Revision=36.0.0\n")
        elif package == "platforms;android-36.1":
            root = self.sdk / "platforms/android-36.1"
            root.mkdir(parents=True, exist_ok=True)
            (root / "android.jar").write_bytes(b"fixture")
            (root / "source.properties").write_text(
                "Pkg.Revision=1\nPlatform.Version=16\nAndroidVersion.ApiLevel=36.1\n")
        elif package == "build-tools;36.0.0":
            root = self.sdk / "build-tools/36.0.0"
            self.executable(root / "aapt2")
            (root / "source.properties").write_text("Pkg.Revision=36.0.0\n")

    def complete(self):
        for package in self.manifest["sdk"]["packages"]:
            self.package(package)

    def state(self):
        return self.api.inspect(self.manifest, self.env)

    def run_install(self, mode="--install", approve=True, runner=None):
        with contextlib.redirect_stdout(self.output):
            return self.api.install(self.manifest, self.state(), mode,
                                    approve=lambda text: approve,
                                    run=runner or self.fake_run)

    def fake_run(self, args, capture=False):
        self.calls.append(args)
        if "--list" in args:
            return "Available Packages:\n  Path | Version | Description\n" + "\n".join(
                f"  {p} | 1 | fixture" for p in self.manifest["sdk"]["packages"])
        if "--licenses" not in args:
            for package in args[2:]:
                self.package(package)
        return ""

    def test_plan_reads_metadata_without_vendor_execution_or_creating_sdk(self):
        with contextlib.redirect_stdout(self.output):
            self.api.plan(self.manifest, self.state())
        self.assertFalse(self.sdk.exists())
        self.assertIn(str(self.sdk), self.output.getvalue())
        self.assertIn("UNCONFIGURED", self.output.getvalue())
        self.assertIn("platforms;android-36.1", self.output.getvalue())

    def test_production_pin_matches_authenticated_archive_metadata(self):
        pinned = self.api.archive_metadata(self.api.load_manifest(ROOT / "config/android/toolchain.toml"))
        observed = json.loads(RELEASE_FIXTURE.read_text())
        for field in ("url", "sha256", "revision", "publisher_source", "verified_on"):
            with self.subTest(field=field):
                self.assertEqual(pinned[field], observed["archive_url" if field == "url" else field])
        self.assertIn("Pkg.Revision=" + pinned["revision"] + "\n", observed["source_properties"])
        self.assertIn("Pkg.Path=cmdline-tools;" + pinned["revision"] + "\n", observed["source_properties"])
        self.assertNotEqual(pinned["revision"], "15859902")
        with contextlib.redirect_stdout(self.output):
            production = self.api.load_manifest(ROOT / "config/android/toolchain.toml")
            self.api.plan(production, self.api.inspect(production, self.env))
        self.assertIn("Pinned CLI revision=22.0", self.output.getvalue())
        self.assertNotIn("UNCONFIGURED", self.output.getvalue())
        self.assertFalse(self.sdk.exists())

    def test_complete_install_and_repair_are_noops(self):
        self.complete()
        platform = self.sdk / "platforms/android-36.1"
        before = {p.name: p.read_bytes() for p in platform.iterdir()}
        self.calls = []
        for mode in ("--install", "--repair"):
            self.run_install(mode, approve=False)
        self.assertEqual(self.calls, [])
        self.assertIn("No changes", self.output.getvalue())
        self.assertEqual({p.name: p.read_bytes() for p in platform.iterdir()}, before)

    def test_platform_dotted_api_without_minor_property_is_healthy(self):
        self.package("platforms;android-36.1")
        meta = self.api.properties(self.sdk / "platforms/android-36.1/source.properties")
        self.assertEqual(meta["AndroidVersion.ApiLevel"], "36.1")
        self.assertNotIn("AndroidVersion.ApiMinorLevel", meta)
        self.assertTrue(self.state()["packages"]["platforms;android-36.1"]["healthy"])

    def test_platform_retains_exact_split_api_compatibility(self):
        self.package("platforms;android-36.1")
        (self.sdk / "platforms/android-36.1/source.properties").write_text(
            "Pkg.Revision=1\nAndroidVersion.ApiLevel=36\nAndroidVersion.ApiMinorLevel=1\n")
        self.assertTrue(self.state()["packages"]["platforms;android-36.1"]["healthy"])

    def test_platform_rejects_wrong_or_malformed_api_identifiers(self):
        self.package("platforms;android-36.1")
        metadata = self.sdk / "platforms/android-36.1/source.properties"
        for identifier in (None, "", "36", "37", "36.0", "36.2", "36.10", "136.1",
                           "360.1", "36.1.0", "036.1", "36.01", "36.x", "NaN",
                           "3.61e1", "36.1-preview", "-36.1"):
            with self.subTest(api=identifier):
                api = "" if identifier is None else f"AndroidVersion.ApiLevel={identifier}\n"
                metadata.write_text("Pkg.Revision=1\n" + api)
                self.assertFalse(self.state()["packages"]["platforms;android-36.1"]["healthy"])

    def test_platform_rejects_invalid_split_or_conflicting_minor_metadata(self):
        self.package("platforms;android-36.1")
        metadata = self.sdk / "platforms/android-36.1/source.properties"
        for major, minor in (("36", ""), ("36", "0"), ("36", "2"), ("36", "01"),
                             ("36", "x"), ("36", "1.0"), ("37", "1"), ("", "1"),
                             ("36.1", "1"), ("36.1", "2"), ("36.1", "x")):
            with self.subTest(major=major, minor=minor):
                metadata.write_text(f"Pkg.Revision=1\nAndroidVersion.ApiLevel={major}\n"
                                    f"AndroidVersion.ApiMinorLevel={minor}\n")
                self.assertFalse(self.state()["packages"]["platforms;android-36.1"]["healthy"])

    def test_platform_requires_numeric_package_revision(self):
        self.package("platforms;android-36.1")
        metadata = self.sdk / "platforms/android-36.1/source.properties"
        for revision, healthy in ((None, False), ("", False), ("invalid", False),
                                  ("1a", False), ("-1", False), ("1..0", False),
                                  ("1", True), ("1.2", True)):
            with self.subTest(revision=revision):
                pkg = "" if revision is None else f"Pkg.Revision={revision}\n"
                metadata.write_text(pkg + "AndroidVersion.ApiLevel=36.1\n")
                self.assertEqual(self.state()["packages"]["platforms;android-36.1"]["healthy"], healthy)

    def test_platform_requires_jar_and_metadata_files(self):
        for name in ("android.jar", "source.properties"):
            with self.subTest(missing=name):
                self.package("platforms;android-36.1")
                (self.sdk / "platforms/android-36.1" / name).unlink()
                self.assertFalse(self.state()["packages"]["platforms;android-36.1"]["healthy"])

    def test_platform_rejects_symlinked_jar_or_metadata(self):
        self.package("platforms;android-36.1")
        for name in ("android.jar", "source.properties"):
            with self.subTest(symlink=name):
                path = self.sdk / "platforms/android-36.1" / name
                target = self.home / name
                path.rename(target)
                path.symlink_to(target)
                try:
                    self.assertFalse(self.state()["packages"]["platforms;android-36.1"]["healthy"])
                finally:
                    path.unlink()
                    target.rename(path)

    def test_platform_rejects_symlinked_sdk_or_platform_directories(self):
        self.package("platforms;android-36.1")
        for path in (self.sdk, self.sdk / "platforms", self.sdk / "platforms/android-36.1"):
            with self.subTest(symlink=path):
                target = self.home / "linked directory"
                path.rename(target)
                path.symlink_to(target, target_is_directory=True)
                try:
                    with self.assertRaisesRegex(self.api.Error, "Unsafe SDK symlink"):
                        self.state()
                finally:
                    path.unlink()
                    target.rename(path)

    def test_custom_sdk_missing_package_only_and_no_substitution(self):
        self.complete()
        shutil.rmtree(self.sdk / "platforms/android-36.1")
        self.calls = []
        self.run_install()
        self.assertTrue((self.sdk / "platforms/android-36.1/android.jar").is_file())
        self.assertTrue(self.state()["packages"]["platforms;android-36.1"]["healthy"])
        self.assertIn("Metadata/layout verified", self.output.getvalue())
        self.assertEqual(self.calls[-1][2:], ["platforms;android-36.1"])
        self.assertTrue(all(f"--sdk_root={self.sdk}" in c for c in self.calls))

    def test_post_install_rejects_wrong_platform_identity(self):
        self.complete()
        platform = self.sdk / "platforms/android-36.1"
        for identifier in ("36", "37", "36.2", "36.1.0", "invalid"):
            with self.subTest(api=identifier):
                shutil.rmtree(platform)
                self.calls = []

                def install_wrong_platform(args, capture=False):
                    result = self.fake_run(args, capture)
                    if "platforms;android-36.1" in args[2:]:
                        (platform / "source.properties").write_text(
                            f"Pkg.Revision=1\nAndroidVersion.ApiLevel={identifier}\n")
                    return result

                with self.assertRaisesRegex(self.api.Error, "Post-install metadata/layout check failed: platforms;android-36.1"):
                    self.run_install(runner=install_wrong_platform)
                self.assertFalse(self.state()["packages"]["platforms;android-36.1"]["healthy"])
                self.assertEqual(self.calls[-1][2:], ["platforms;android-36.1"])

    def test_denial_prevents_even_sdkmanager_startup(self):
        self.package("cmdline-tools;latest")
        self.calls = []
        with self.assertRaisesRegex(self.api.Error, "declined"):
            self.run_install(approve=False)
        self.assertEqual(self.calls, [])

    def test_unconfigured_bootstrap_fails_before_any_download(self):
        self.calls = []
        with self.assertRaisesRegex(self.api.Error, "UNCONFIGURED"):
            self.run_install()
        self.assertFalse(self.sdk.exists())
        self.assertEqual(self.calls, [])

    def configure_archive(self):
        archive = self.home / "fixture.zip"
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("cmdline-tools/bin/sdkmanager", "#!/bin/sh\nexit 0\n")
            z.writestr("cmdline-tools/lib/sdkmanager-classpath.jar", "fixture")
            z.writestr("cmdline-tools/source.properties", "Pkg.Revision=19.0\n")
        # Synthetic metadata is only used through an in-process fake transport.
        # This URL is never resolved and is not a claimed Google release.
        self.manifest["command_line_tools"] = {
            "verified": True, "revision": "19.0",
            "url": "https://dl.google.com/android/repository/commandlinetools-linux-1_latest.zip",
            "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            "publisher_source": "https://developer.android.com/studio",
            "verified_on": "2026-01-01"}
        return archive

    def test_clean_bootstrap_without_manager_and_second_install_noop(self):
        archive = self.configure_archive()
        self.calls = []
        with patch.object(self.api, "download", side_effect=lambda url, dest: shutil.copyfile(archive, dest)):
            self.run_install()
        self.assertTrue((self.sdk / "cmdline-tools/19.0/bin/sdkmanager").is_file())
        self.assertTrue(all(p["healthy"] for p in self.state()["packages"].values()))
        self.assertNotIn("cmdline-tools;latest", self.calls[-1][2:])
        before = len(self.calls)
        self.run_install(approve=False)
        self.assertEqual(len(self.calls), before)
        self.assertFalse(list(self.sdk.rglob(".panda-android-stage-*")))

    def test_bootstrap_approval_refusal_leaves_sdk_untouched(self):
        archive = self.configure_archive()
        for answers in ([False], [True, False]):
            consent = iter(answers)
            with contextlib.redirect_stdout(self.output), \
                    patch.object(self.api, "download", side_effect=lambda url, dest: shutil.copyfile(archive, dest)), \
                    self.assertRaisesRegex(self.api.Error, "declined"):
                self.api.install(self.manifest, self.state(), "--install",
                                 approve=lambda text: next(consent), run=self.fake_run)
            self.assertFalse(self.sdk.exists())

    def test_bootstrap_occupied_version_slot_is_never_replaced(self):
        archive = self.configure_archive()
        destination = self.sdk / "cmdline-tools/19.0"
        destination.mkdir(parents=True)
        marker = destination / "custom"
        marker.write_text("keep")
        with self.assertRaisesRegex(self.api.Error, "occupied"), \
                patch.object(self.api, "download", side_effect=AssertionError("download must not start")):
            self.run_install("--repair")
        self.assertEqual(marker.read_text(), "keep")

    def test_invalid_cli_executable_layout_never_reaches_sdk(self):
        archive = self.configure_archive()
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("cmdline-tools/bin/sdkmanager/", "")
            z.writestr("cmdline-tools/lib/sdkmanager-classpath.jar", "fixture")
            z.writestr("cmdline-tools/source.properties", "Pkg.Revision=19.0\n")
        self.manifest["command_line_tools"]["sha256"] = hashlib.sha256(archive.read_bytes()).hexdigest()
        with patch.object(self.api, "download", side_effect=lambda url, dest: shutil.copyfile(archive, dest)), \
                self.assertRaises(self.archive.ArchiveError):
            self.run_install()
        self.assertFalse(self.sdk.exists())

    def test_external_cli_classpath_link_is_not_healthy_or_executed(self):
        self.complete()
        jar = self.sdk / "cmdline-tools/19.0/lib/sdkmanager-classpath.jar"
        external = self.home / "external.jar"
        external.write_bytes(b"outside SDK")
        jar.unlink()
        jar.symlink_to(external)
        self.assertFalse(self.state()["packages"]["cmdline-tools;latest"]["healthy"])
        self.calls = []
        with self.assertRaisesRegex(self.api.Error, "UNCONFIGURED"):
            self.run_install()
        self.assertEqual(self.calls, [])

    def test_invalid_trust_fields_fail_closed(self):
        self.configure_archive()
        original = dict(self.manifest["command_line_tools"])
        for key, value in (("sha256", ""), ("publisher_source", "https://evil.invalid"),
                           ("revision", "../outside"), ("url", "https://evil.invalid/tools.zip"),
                           ("verified_on", "not-a-date")):
            with self.subTest(key=key):
                self.manifest["command_line_tools"] = {**original, key: value}
                with self.assertRaises(self.api.Error):
                    self.api.archive_metadata(self.manifest)

    def test_real_runner_propagates_exit_and_inherits_license_stdin(self):
        manager = self.home / "fake manager"
        self.executable(manager, "echo visible-failure; exit 7")
        with contextlib.redirect_stdout(self.output):
            with self.assertRaises(self.api.Error) as ctx:
                self.api.run_vendor([str(manager), "--list"], capture=True)
        self.assertEqual(ctx.exception.code, 7)
        self.assertIn("exit=7", self.output.getvalue())
        self.assertIn("visible-failure", self.output.getvalue())
        self.executable(manager, 'read answer; test "$answer" = "operator chose"')
        # Inspect only the subprocess boundary for the inherit-stdin contract.
        observed = {}
        real_popen = subprocess.Popen
        def boundary(args, **kwargs):
            observed.update(kwargs)
            process = real_popen(args, **kwargs, stdin=subprocess.PIPE)
            process.stdin.write(b"operator chose\n")
            process.stdin.close()
            return process
        with patch.object(self.api.android_cli.subprocess, "Popen", side_effect=boundary), \
                contextlib.redirect_stdout(self.output):
            self.api.run_vendor([str(manager), "--licenses"])
        self.assertNotIn("stdin", observed)
        self.assertNotIn("input", observed)

    def test_postinstall_failure_is_not_reported_as_success(self):
        self.package("cmdline-tools;latest")
        self.calls = []
        def incomplete(args, capture=False):
            if "--list" in args or "--licenses" in args:
                return self.fake_run(args, capture)
            self.calls.append(args)
            return ""  # A vendor exit 0 alone is insufficient.
        with self.assertRaisesRegex(self.api.Error, "Post-install"):
            self.run_install(runner=incomplete)

    def test_package_failure_preserves_existing_configuration_sentinels(self):
        self.package("cmdline-tools;latest")
        targets = [self.home / p for p in ("protected-checkout/marker", "ghostty/config",
                   "chezmoi/config.toml", "config/fish/config.fish", "ide/plugins/custom")]
        for target in targets:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("preserve fixture")
        self.calls = []
        def failed(args, capture=False):
            if "platform-tools" in args:
                raise self.api.Error("failed", 17)
            return self.fake_run(args, capture)
        with self.assertRaises(self.api.Error):
            self.run_install(runner=failed)
        self.assertTrue(all(t.read_text() == "preserve fixture" for t in targets))

    def test_stale_plan_does_not_overwrite_package_created_during_approval(self):
        self.package("cmdline-tools;latest")
        self.calls = []
        approvals = 0
        def consent(text):
            nonlocal approvals
            approvals += 1
            if approvals == 4:
                self.package("platform-tools")
            return True
        with contextlib.redirect_stdout(self.output), self.assertRaisesRegex(self.api.Error, "changed"):
            self.api.install(self.manifest, self.state(), "--install", approve=consent, run=self.fake_run)
        self.assertEqual(len(self.calls), 2)  # listing and licenses, never package install

    def test_unavailable_exact_package_stops_before_licenses(self):
        self.package("cmdline-tools;latest")
        self.calls = []
        def unavailable(args, capture=False):
            self.calls.append(args)
            return "Available Packages:\nplatforms;android-36 | 1 | wrong platform\n"
        with self.assertRaisesRegex(self.api.Error, "unavailable"):
            self.run_install(runner=unavailable)
        self.assertEqual(len(self.calls), 1)

    def test_license_failure_is_propagated_without_package_install(self):
        self.package("cmdline-tools;latest")
        self.calls = []
        def denied(args, capture=False):
            if "--licenses" in args:
                raise self.api.Error("license command failed", 7)
            return self.fake_run(args, capture)
        with self.assertRaises(self.api.Error) as ctx:
            self.run_install(runner=denied)
        self.assertEqual(ctx.exception.code, 7)
        self.assertEqual(len(self.calls), 1)

    def test_declined_license_consent_prevents_terms_command(self):
        self.package("cmdline-tools;latest")
        self.calls = []
        answers = iter([True, True, False])
        with contextlib.redirect_stdout(self.output), self.assertRaisesRegex(self.api.Error, "declined"):
            self.api.install(self.manifest, self.state(), "--install",
                             approve=lambda text: next(answers), run=self.fake_run)
        self.assertEqual(len(self.calls), 1)

    def test_unconfirmed_process_cleanup_retains_backups_without_repair_rollback(self):
        self.assertTrue(hasattr(self.api.android_cli, "ProcessCleanupError"),
                        "cleanup uncertainty must be distinguishable from an ordinary vendor exit")
        self.complete()
        old = self.sdk / "build-tools/36.0.0/source.properties"
        old.write_text("Pkg.Revision=35.0.0\n")
        self.calls = []
        def active_vendor(args, capture=False):
            if "build-tools;36.0.0" in args:
                self.package("build-tools;36.0.0")
                raise self.api.android_cli.ProcessCleanupError("Vendor cleanup unconfirmed; manual recovery required")
            return self.fake_run(args, capture)
        with self.assertRaises(self.api.android_cli.ProcessCleanupError):
            self.run_install("--repair", runner=active_vendor)
        self.assertEqual(old.read_text(), "Pkg.Revision=36.0.0\n")
        backups = list((self.sdk / "build-tools").glob(".panda-android-backup-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / "source.properties").read_text(), "Pkg.Revision=35.0.0\n")
        self.assertEqual(list((self.sdk / "build-tools").glob(".panda-android-failed-*")), [])
        self.assertIn("rollback withheld", self.output.getvalue())

    def test_legacy_vendor_preserves_unconfirmed_cleanup_for_install_policy(self):
        self.assertTrue(hasattr(self.api.android_cli, "ProcessCleanupError"))
        failure = self.api.android_cli.ProcessCleanupError("Vendor cleanup unconfirmed; manual recovery required")
        with patch.object(self.api.android_cli, "run_command", side_effect=failure), \
             self.assertRaises(self.api.android_cli.ProcessCleanupError) as caught:
            self.api.run_vendor(["/fictional-sdkmanager"])
        self.assertIs(caught.exception, failure)

    def test_corruption_requires_repair_and_failed_repair_restores_old_files(self):
        self.complete()
        old = self.sdk / "build-tools/36.0.0/source.properties"
        old.write_text("Pkg.Revision=35.0.0\n")
        self.calls = []
        with self.assertRaisesRegex(self.api.Error, "repair"):
            self.run_install()
        def failing(args, capture=False):
            if "build-tools;36.0.0" in args:
                self.package("build-tools;36.0.0")
                raise self.api.Error("package failed", 9)
            return self.fake_run(args, capture)
        with self.assertRaises(self.api.Error):
            self.run_install("--repair", runner=failing)
        self.assertEqual(old.read_text(), "Pkg.Revision=35.0.0\n")
        self.assertTrue(list(self.sdk.glob("build-tools/.panda-android-failed-*")))
        self.run_install("--repair")
        before = len(self.calls)
        self.run_install("--repair")
        self.assertEqual(before, len(self.calls))

    def test_failed_repair_quarantines_symlink_without_following_and_restores_all(self):
        self.complete()
        for relative in ("platform-tools/source.properties", "build-tools/36.0.0/source.properties"):
            (self.sdk / relative).write_text("Pkg.Revision=invalid\n")
        outside = self.home / "preserve outside"
        outside.mkdir()
        (outside / "marker").write_text("keep")
        self.calls = []
        def failed(args, capture=False):
            if "build-tools;36.0.0" in args:
                (self.sdk / "build-tools/36.0.0").symlink_to(outside, target_is_directory=True)
                raise self.api.Error("original vendor failure", 17)
            return self.fake_run(args, capture)
        with self.assertRaises(self.api.Error) as caught:
            self.run_install("--repair", runner=failed)
        self.assertEqual(caught.exception.code, 17)
        self.assertEqual(str(caught.exception), "original vendor failure")
        self.assertTrue((self.sdk / "platform-tools/adb").is_file())
        self.assertEqual((self.sdk / "build-tools/36.0.0/source.properties").read_text(), "Pkg.Revision=invalid\n")
        self.assertEqual((outside / "marker").read_text(), "keep")

    def test_one_recovery_error_does_not_mask_vendor_status_or_stop_other_restores(self):
        self.complete()
        for relative in ("platform-tools/source.properties", "build-tools/36.0.0/source.properties"):
            (self.sdk / relative).write_text("Pkg.Revision=invalid\n")
        self.calls = []
        def failed(args, capture=False):
            if "build-tools;36.0.0" in args:
                raise self.api.Error("original failure", 17)
            return self.fake_run(args, capture)
        real_rename = self.api.rename_noreplace
        def recovery_error(source, target):
            if source.name.startswith(".panda-android-backup-") and target.name == "36.0.0":
                raise OSError("injected recovery failure")
            return real_rename(source, target)
        with patch.object(self.api, "rename_noreplace", side_effect=recovery_error), \
                self.assertRaises(self.api.Error) as caught:
            self.run_install("--repair", runner=failed)
        self.assertEqual(caught.exception.code, 17)
        self.assertTrue((self.sdk / "platform-tools/adb").is_file())
        self.assertTrue(list((self.sdk / "build-tools").glob(".panda-android-backup-*")))
        self.assertIn("MANUAL RECOVERY REQUIRED", self.output.getvalue())

    def test_sdk_conflict_and_symlink_roots_refused(self):
        self.env["ANDROID_SDK_ROOT"] = str(self.home / "other")
        with self.assertRaisesRegex(self.api.Error, "conflict"):
            self.state()
        del self.env["ANDROID_SDK_ROOT"]
        other = self.home / "other"
        other.mkdir()
        self.sdk.symlink_to(other, target_is_directory=True)
        with self.assertRaisesRegex(self.api.Error, "symlink"):
            self.state()

    def test_wrong_jdk_blocks_mutation(self):
        (self.jdk / "release").write_text('JAVA_VERSION="25.0.1"\n')
        self.calls = []
        with self.assertRaisesRegex(self.api.Error, "JDK 21"):
            self.run_install()
        self.assertEqual(self.calls, [])

    def test_unsupported_plugins_preview_build_and_preserve_settings(self):
        studio = self.home / "studio"
        self.executable(studio / "bin/studio")
        (studio / "product-info.json").write_text(
            '{"name":"Android Studio","version":"fixture","buildNumber":"AI-fixture"}')
        self.env["ANDROID_STUDIO_HOME"] = str(studio)
        prefs = self.home / ".config/Google/AndroidStudio/options.xml"
        prefs.parent.mkdir(parents=True)
        prefs.write_text("preserve private preferences")
        with contextlib.redirect_stdout(self.output):
            self.api.plan(self.manifest, self.state())
        self.assertIn("AI-fixture", self.output.getvalue())
        self.assertIn("manual", self.output.getvalue().lower())
        self.assertEqual(prefs.read_text(), "preserve private preferences")

    def test_unapproved_manifest_packages_rejected(self):
        self.manifest["sdk"]["packages"].append("emulator")
        with self.assertRaisesRegex(self.api.Error, "baseline"):
            self.api.validate_manifest(self.manifest)

    def test_noninteractive_consent_refused(self):
        with patch.object(sys, "stdin", io.StringIO("yes\n")):
            with self.assertRaisesRegex(self.api.Error, "terminal"):
                self.api.confirm("Download?")


class ArchiveContracts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="panda-android-archive-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.api = load("android_archive")
        self.zip = self.root / "tools.zip"

    def make_zip(self, extra=None):
        with zipfile.ZipFile(self.zip, "w") as archive:
            for name, data in {"cmdline-tools/bin/sdkmanager": b"#!/bin/sh\nexit 0\n",
                               "cmdline-tools/lib/sdkmanager-classpath.jar": b"fixture",
                               "cmdline-tools/source.properties": b"Pkg.Revision=19.0\n",
                               **(extra or {})}.items():
                archive.writestr(name, data)
        return hashlib.sha256(self.zip.read_bytes()).hexdigest()

    def extract(self, sha):
        return self.api.stage_archive(self.zip, self.root / "stage", sha, "19.0")

    def test_valid_layout_and_checksum(self):
        staged = self.extract(self.make_zip())
        self.assertTrue(os.access(staged / "bin/sdkmanager", os.X_OK))

    def official_layout_zip(self):
        """Observed names/modes only; no Google binaries or executable content."""
        observed = json.loads(RELEASE_FIXTURE.read_text())
        with zipfile.ZipFile(self.zip, "w", compression=zipfile.ZIP_STORED) as archive:
            for entry in observed["entries"]:
                info = zipfile.ZipInfo(entry["path"])
                info.create_system = entry["create_system"]
                info.external_attr = int(entry["unix_mode"], 8) << 16
                data = observed["source_properties"] if info.filename == "cmdline-tools/source.properties" else "nonexecutable fixture payload\n"
                archive.writestr(info, data)
        return hashlib.sha256(self.zip.read_bytes()).hexdigest()

    def test_observed_google_layout_strips_execute_bits_from_libraries_and_metadata(self):
        sha = self.official_layout_zip()
        staged = self.api.stage_archive(self.zip, self.root / "stage", sha, "22.0")
        files = [p for p in staged.rglob("*") if p.is_file()]
        self.assertEqual(len(files), 141)
        self.assertEqual((staged / "source.properties").read_text(),
                         "Pkg.Revision=22.0\nPkg.Path=cmdline-tools;22.0\nPkg.Desc=Android SDK Command-line Tools\n")
        for path in files:
            with self.subTest(path=path.relative_to(staged)):
                self.assertEqual(path.stat().st_mode & 0o777,
                                 0o755 if path.parent == staged / "bin" else 0o644)

    def test_observed_layout_does_not_allow_arbitrary_executables_outside_bin(self):
        self.official_layout_zip()
        with zipfile.ZipFile(self.zip, "a") as archive:
            info = zipfile.ZipInfo("cmdline-tools/lib/install.sh")
            info.external_attr = 0o100755 << 16
            archive.writestr(info, "not executable fixture content")
        sha = hashlib.sha256(self.zip.read_bytes()).hexdigest()
        with self.assertRaisesRegex(self.api.ArchiveError, "executable"):
            self.api.stage_archive(self.zip, self.root / "stage", sha, "22.0")
        self.assertFalse((self.root / "stage").exists())

    def test_archive_build_number_is_not_the_package_revision(self):
        sha = self.official_layout_zip()
        with self.assertRaisesRegex(self.api.ArchiveError, "revision"):
            self.api.stage_archive(self.zip, self.root / "stage", sha, "15859902")
        self.assertFalse((self.root / "stage").exists())

    def test_checksum_mismatch_has_no_extracted_files(self):
        self.make_zip()
        with self.assertRaisesRegex(self.api.ArchiveError, "checksum"):
            self.extract("0" * 64)
        self.assertFalse((self.root / "stage").exists())

    def test_hostile_paths_and_unexpected_executables_rejected(self):
        for name in ("../escape", "/absolute", "cmdline-tools/../../escape",
                     "cmdline-tools/../escape", "cmdline-tools\\escape", "other/bin/tool"):
            with self.subTest(name=name):
                with self.assertRaises(self.api.ArchiveError):
                    self.extract(self.make_zip({name: b"bad"}))
        self.assertFalse((self.root / "escape").exists())

    def test_symlinks_rejected(self):
        self.make_zip()
        with zipfile.ZipFile(self.zip, "a") as archive:
            link = zipfile.ZipInfo("cmdline-tools/lib/link")
            link.create_system = 3
            link.external_attr = 0o120777 << 16
            archive.writestr(link, "../../../escape")
        with self.assertRaises(self.api.ArchiveError):
            self.extract(hashlib.sha256(self.zip.read_bytes()).hexdigest())

    def test_executable_outside_bin_and_revision_mismatch_rejected(self):
        self.make_zip()
        with zipfile.ZipFile(self.zip, "a") as archive:
            member = zipfile.ZipInfo("cmdline-tools/evil.sh")
            member.external_attr = 0o100755 << 16
            archive.writestr(member, "exit 0")
        with self.assertRaisesRegex(self.api.ArchiveError, "executable"):
            self.extract(hashlib.sha256(self.zip.read_bytes()).hexdigest())
        sha = self.make_zip({"cmdline-tools/source.properties": b"Pkg.Revision=18.0\n"})
        with self.assertRaisesRegex(self.api.ArchiveError, "revision"):
            self.extract(sha)
        self.assertFalse((self.root / "stage").exists())

    def test_duplicate_paths_and_bad_zip_rejected(self):
        self.make_zip()
        with zipfile.ZipFile(self.zip, "a") as archive:
            with contextlib.redirect_stderr(io.StringIO()):
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    archive.writestr("cmdline-tools/bin/sdkmanager", "malicious duplicate")
        with self.assertRaises(self.api.ArchiveError):
            self.extract(hashlib.sha256(self.zip.read_bytes()).hexdigest())
        self.zip.write_bytes(b"interrupted zip")
        with self.assertRaises(self.api.ArchiveError):
            self.extract(hashlib.sha256(self.zip.read_bytes()).hexdigest())

    def test_interrupted_extraction_cleans_staging(self):
        sha = self.make_zip()
        with patch.object(shutil, "copyfileobj", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.extract(sha)
        self.assertFalse((self.root / "stage").exists())

    def test_atomic_publish_never_replaces_existing_tree(self):
        staged = self.extract(self.make_zip())
        dest = self.root / "sdk/cmdline-tools/19.0"
        dest.mkdir(parents=True)
        marker = dest / "keep"
        marker.write_text("existing")
        with self.assertRaises(self.api.ArchiveError):
            self.api.publish(staged, dest)
        self.assertEqual(marker.read_text(), "existing")

    def test_atomic_publish_failure_preserves_stage(self):
        staged = self.extract(self.make_zip())
        dest = self.root / "sdk/cmdline-tools/19.0"
        dest.parent.mkdir(parents=True)
        with patch.object(self.api, "rename_noreplace", side_effect=OSError("interrupted")):
            with self.assertRaises(self.api.ArchiveError):
                self.api.publish(staged, dest)
        self.assertTrue(staged.is_dir())
        self.assertFalse(dest.exists())

    def test_transport_refuses_untrusted_hosts_and_redirects(self):
        for url in ("http://dl.google.com/android/repository/tools.zip",
                    "https://evil.invalid/tools.zip", "https://dl.google.com.evil.invalid/tools.zip"):
            with self.assertRaises(self.api.ArchiveError):
                self.api.validate_url(url)
        with self.assertRaises(self.api.ArchiveError):
            self.api.GoogleRedirect().redirect_request(None, None, 302, "", {},
                                                       "https://evil.invalid/tools.zip")

    def test_unavailable_url_and_interruption_leave_no_archive(self):
        dest = self.root / "download.zip"
        for error in (OSError("unavailable"), KeyboardInterrupt()):
            with patch.object(self.api.urllib.request.OpenerDirector, "open", side_effect=error):
                with self.assertRaises((self.api.ArchiveError, KeyboardInterrupt)):
                    self.api.download("https://dl.google.com/android/repository/fixture.zip", dest)
            self.assertFalse(dest.exists())


@unittest.skipUnless(shutil.which("fish"), "Fish required")
class CommandContracts(unittest.TestCase):
    def test_new_plan_and_help_modes_are_readonly(self):
        with tempfile.TemporaryDirectory(prefix="panda-android-command-") as home:
            env = {"HOME": home, "PATH": "/usr/bin:/bin", "XDG_CONFIG_HOME": home + "/config"}
            for mode in ("--plan", "--help"):
                result = subprocess.run(["fish", "--no-config", str(ROOT / "bootstrap/setup-android.fish"), mode],
                                        env=env, capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("--repair" if mode == "--help" else "Pinned CLI revision=22.0", result.stdout)
            self.assertFalse((Path(home) / "Android").exists())

    def test_noninteractive_install_fails_safely(self):
        with tempfile.TemporaryDirectory(prefix="panda-android-command-") as home:
            env = {"HOME": home, "PATH": "/usr/bin:/bin", "ANDROID_HOME": home + "/selected sdk"}
            script = ROOT / "bootstrap/setup-android.fish"
            result = subprocess.run(["fish", "--no-config", str(script), "--install"],
                                    env=env, capture_output=True, text=True, timeout=10)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse((Path(home) / "selected sdk").exists())

    def test_missing_python_is_reported_without_installing_it(self):
        with tempfile.TemporaryDirectory(prefix="panda-android-command-") as home:
            empty_bin = Path(home) / "bin"
            empty_bin.mkdir()
            result = subprocess.run([shutil.which("fish"), "--no-config",
                                     str(ROOT / "bootstrap/setup-android.fish"), "--plan"],
                                    env={"HOME": home, "PATH": str(empty_bin)},
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("Python 3.11+", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
