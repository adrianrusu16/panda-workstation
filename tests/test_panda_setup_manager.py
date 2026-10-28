"""Non-mutating CI tests for Panda Setup Manager contracts and CLI behavior."""
from __future__ import annotations
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFESTS = ROOT / 'setup' / 'manifests'
MAIN = ROOT / 'bootstrap' / 'panda-setup.fish'
HELPERS = ROOT / 'bootstrap' / 'lib' / 'panda-setup.fish'
GAMING = ROOT / 'bootstrap' / 'panda-gaming.fish'


class SetupManagerContracts(unittest.TestCase):
    def test_manifests_are_safe_package_names(self):
        for file in MANIFESTS.glob('*.txt'):
            entries = [s.strip() for s in file.read_text().splitlines()
                       if s.strip() and not s.lstrip().startswith('#')]
            self.assertTrue(entries, f'Empty manifest: {file.name}')
            self.assertEqual(len(entries), len(set(entries)), file.name)
            for entry in entries:
                self.assertRegex(entry, r'^[a-z0-9][a-z0-9@+_.-]*$')

    def test_all_expected_manifest_modules_exist(self):
        names = {p.stem for p in MANIFESTS.glob('*.txt')}
        self.assertEqual(names, {
            'gaming-base', 'gaming-steam', 'gaming-heroic', 'gaming-other',
            'gaming-intel', 'gaming-amd', 'virtualization-base'
        })

    def test_no_nvidia_packages_or_kernel_tools(self):
        for file in MANIFESTS.glob('*.txt'):
            for line in file.read_text().splitlines():
                if line.strip() and not line.lstrip().startswith('#'):
                    self.assertNotRegex(line, r'(nvidia|limine|mkinitcpio|linux-cachyos)')
        manager = MAIN.read_text()
        for forbidden in ('setup-machine.fish"', 'setup-workstation.fish"',
                          'sudo pacman -Sy', 'git add .', 'git commit ', 'git push ',
                          'nvidia-smi', 'systemctl enable'):
            self.assertNotIn(forbidden, manager)

    def test_explicit_apply_and_confirm(self):
        source = MAIN.read_text()
        self.assertIn("if test $apply -eq 0", source)
        self.assertIn("if not set -q _flag_yes", source)
        self.assertIn("if test \"$confirmation\" != APPLY", source)
        self.assertIn("if contains android $modules", source)
        self.assertIn("panda_setup_check_gpu_safety", source)
        self.assertIn("--enable-flathub", source)

    def test_no_aur_and_heroic_is_user_scoped(self):
        source = MAIN.read_text()
        self.assertIn('flatpak install --user', source)
        self.assertIn('flatpak remote-add --user', source)
        for forbidden in ('yay -S', 'paru -S', 'curl | sh', 'sudo flatpak'):
            self.assertNotIn(forbidden, source)

    def test_gaming_shortcut_never_autoinstalls(self):
        src = GAMING.read_text()
        self.assertIn('--modules gaming $argv', src)
        self.assertNotIn('--apply $argv', src)


@unittest.skipUnless(shutil.which('fish'), 'Requires Fish; GitHub CI installs Fish')
class FishSmokeTests(unittest.TestCase):
    def run_fish(self, *args):
        return subprocess.run(['fish', str(MAIN), *args],
                              cwd=ROOT, capture_output=True, text=True,
                              timeout=20)

    def test_syntax(self):
        proc = subprocess.run(['fish', '-n', str(MAIN), str(HELPERS), str(GAMING)],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_help(self):
        result = self.run_fish('--help')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_invalid_module(self):
        result = self.run_fish('--modules', 'not-a-module', '--dry-run')
        self.assertEqual(result.returncode, 2)

    def test_android_apply_refused(self):
        result = self.run_fish('--modules', 'android', '--apply', '--yes')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('no selected modules were applied', result.stdout + result.stderr)

    def test_virtualization_preview_without_pacman(self):
        result = self.run_fish('--modules', 'virtualization', '--dry-run')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('DRY RUN COMPLETE', result.stdout)

    def test_gaming_preview_does_not_require_repos(self):
        result = self.run_fish('--modules', 'gaming', '--stores', 'steam,gog,epic,other',
                               '--gpu', 'intel', '--dry-run')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('DRY RUN COMPLETE', result.stdout)

    def test_all_selected_modules_preview(self):
        result = self.run_fish('--modules', 'workspace,desktop,gaming,android,virtualization',
                               '--stores', 'steam,gog,epic,other', '--gpu', 'intel', '--dry-run')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('NOT IMPLEMENTED', result.stdout)


if __name__ == '__main__':
    unittest.main()
