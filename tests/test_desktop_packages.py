"""Offline inventory and installer contracts using disposable executables."""
import importlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "theme/panda/common"))


class DesktopPackageTests(unittest.TestCase):
    def setUp(self):
        self.packages = importlib.import_module("desktop_packages")
        self.temp = tempfile.TemporaryDirectory(prefix="panda-desktop-packages-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_repository_requirements_once_and_installed_inventory_idempotence(self):
        inventory = self.packages.read_manifests(ROOT / "packages")
        self.assertTrue(set(self.packages.REQUIRED) <= set(inventory))
        plan = self.packages.package_plan(ROOT / "packages", list(self.packages.REQUIRED))
        self.assertEqual(plan["missing"], [])
        self.assertEqual(plan, self.packages.package_plan(ROOT / "packages", list(self.packages.REQUIRED)))
        self.assertEqual(self.packages.package_plan(ROOT / "packages", [])["missing"], sorted(self.packages.REQUIRED))

    def test_duplicate_names_and_invalid_tokens_fail_before_planning(self):
        for text in ("valid\nvalid\n", "valid\n--bad\n", "bad name\n", "valid;echo\n"):
            (self.root / "one.txt").write_text(text)
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.packages.read_manifests(self.root)
        (self.root / "one.txt").write_text("valid\n")
        (self.root / "two.txt").write_text("valid\n")
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.packages.read_manifests(self.root)

    def fish(self, manifest_text="alpha\nbeta\n", *, dry=False, installed="pacman",
             install_fail=False, query_exit=0, malformed="", missing_executable=False,
             post_query_exit=0, entry=False, profile=None, environment_profile=None):
        manifest = self.root / "manifest.txt"
        manifest.write_text(manifest_text)
        command = self.root / "command.py"
        command.write_text("#!" + sys.executable + "\n" + '''
import os,sys
from pathlib import Path
name=Path(sys.argv[0]).name
with Path(os.environ["CALL_LOG"]).open("a") as f:f.write(name+" "+" ".join(sys.argv[1:])+"\\n")
if name=="sudo":
    if os.environ["INSTALL_FAIL"]=="1":sys.exit(7)
    p=Path(os.environ["INSTALLED_FILE"])
    p.write_text(p.read_text()+" "+" ".join(sys.argv[4:]))
    sys.exit(0)
if name=="pacman":
    # Support old per-package queries while reproducing the pre-fix failures.
    if sys.argv[1:]==["-Qq"]:
        count=Path(os.environ["QUERY_COUNT"])
        n=int(count.read_text())+1;count.write_text(str(n))
        code=int(os.environ["QUERY_EXIT"] if n==1 else os.environ["POST_QUERY_EXIT"])
        mode=os.environ["MALFORMED"]
        if mode=="empty":out=""
        elif mode=="duplicate":out="pacman\\npacman\\n"
        elif mode=="token":out="pacman\\n--invalid\\n"
        elif mode=="whitespace":out="pacman\\nalpha beta\\n"
        else:out="\\n".join(Path(os.environ["INSTALLED_FILE"]).read_text().split())+"\\n"
        sys.stdout.write(out)
        sys.exit(code)
    if sys.argv[1:2]==["-Q"]:
        code=int(os.environ["QUERY_EXIT"])
        if code:sys.exit(code)
        sys.exit(0 if sys.argv[2] in Path(os.environ["INSTALLED_FILE"]).read_text().split() else 1)
sys.exit(91)
''')
        command.chmod(0o755)
        for name in ("sudo", "pacman"):
            p = self.root / name
            if p.is_symlink():
                p.unlink()
            if name != "pacman" or not missing_executable:
                p.symlink_to(command)
        installed_file = self.root / "installed"
        installed_file.write_text(installed)
        log = self.root / "calls"
        log.write_text("")
        (self.root / "query-count").write_text("0")
        env = {**os.environ, "HOME": str(self.root), "XDG_CONFIG_HOME": str(self.root / "config"),
               "XDG_DATA_HOME": str(self.root / "data"), "XDG_CACHE_HOME": str(self.root / "cache"),
               "PATH": str(self.root), "CALL_LOG": str(log), "INSTALLED_FILE": str(installed_file),
               "INSTALL_FAIL": str(int(install_fail)), "QUERY_EXIT": str(query_exit),
               "POST_QUERY_EXIT": str(post_query_exit), "MALFORMED": malformed,
               "QUERY_COUNT": str(self.root / "query-count")}
        env.pop("PANDA_DESKTOP_PROFILE", None)
        if environment_profile is not None:
            env["PANDA_DESKTOP_PROFILE"] = environment_profile
        if entry:
            args = ["/usr/bin/fish", "--no-config", str(ROOT / "bootstrap/install-desktop.fish")]
            if dry:
                args.append("--dry-run")
            if profile is not None:
                args.extend(["--profile", profile])
        else:
            script = 'source "$argv[1]"; source "$argv[2]"; install_manifest "$argv[3]" "test" $argv[4..-1]'
            args = ["/usr/bin/fish", "--no-config", "-c", script, "--",
                    str(ROOT / "bootstrap/lib/ui.fish"), str(ROOT / "bootstrap/lib/packages.fish"),
                    str(manifest), *(["--dry-run"] if dry else [])]
        result = subprocess.run(args, env=env, capture_output=True, text=True, timeout=5)
        return result, log.read_text()

    def test_fish_dry_run_queries_once_without_sudo_and_installed_run_is_idempotent(self):
        result, log = self.fish(dry=True, installed="pacman alpha")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Would install: beta", result.stdout)
        self.assertEqual(log.splitlines(), ["pacman -Qq"])
        result, log = self.fish(installed="pacman alpha beta")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(log.splitlines(), ["pacman -Qq"])

    def test_query_statuses_one_two_and_127_fail_closed_for_dry_and_normal(self):
        for code in (1, 2, 127):
            for dry in (True, False):
                with self.subTest(code=code, dry=dry):
                    result, log = self.fish(dry=dry, query_exit=code)
                    self.assertEqual(result.returncode, code)
                    self.assertNotIn("Would install:", result.stdout)
                    self.assertNotIn("sudo", log)
                    self.assertEqual(log.splitlines(), ["pacman -Qq"])

    def test_malformed_successful_inventory_fails_without_plan_or_install(self):
        for malformed in ("empty", "duplicate", "token", "whitespace"):
            for dry in (True, False):
                with self.subTest(malformed=malformed, dry=dry):
                    result, log = self.fish(dry=dry, malformed=malformed)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertNotIn("Would install:", result.stdout)
                    self.assertNotIn("sudo", log)

    def test_unavailable_pacman_fails_before_any_command(self):
        result, log = self.fish(dry=True, missing_executable=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(log, "")
        self.assertNotIn("Would install:", result.stdout)

    def test_fish_duplicate_and_malformed_entries_refuse_without_any_command(self):
        for text in ("alpha\nalpha\n", "--option\n", "bad name\n"):
            result, log = self.fish(text)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(log, "")

    def test_successful_missing_only_install_refreshes_and_verifies_inventory(self):
        result, log = self.fish(installed="pacman alpha")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(log.splitlines(), ["pacman -Qq", "sudo pacman -S --needed beta", "pacman -Qq"])
        self.assertIn("2/2 packages verified", result.stdout)

    def test_post_install_inventory_error_is_propagated(self):
        result, log = self.fish(installed="pacman alpha", post_query_exit=2)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("packages verified", result.stdout)
        self.assertEqual(log.count("pacman -Qq"), 2)

    def test_fish_install_failure_is_propagated(self):
        result, log = self.fish(installed="pacman alpha", install_fail=True)
        self.assertEqual(result.returncode, 7, result.stdout + result.stderr)
        self.assertIn("sudo pacman -S --needed beta", log)
        self.assertEqual(log.count("pacman -Qq"), 1)

    def test_normal_desktop_install_requires_explicit_plasma_profile_before_query(self):
        for profile in (None, "gnome"):
            result, log = self.fish(entry=True, profile=profile)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(log, "")
        desktop = "pacman wl-clipboard xclip " + " ".join(self.packages.REQUIRED)
        for options in ({"profile": "plasma"}, {"environment_profile": "plasma"}):
            result, log = self.fish(entry=True, installed=desktop, **options)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(log.splitlines(), ["pacman -Qq"])
        result, log = self.fish(entry=True, dry=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(log.splitlines(), ["pacman -Qq"])


if __name__ == "__main__":
    unittest.main()
