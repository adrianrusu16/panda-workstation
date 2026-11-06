"""Non-mutating CI tests for Panda Setup Manager contracts and CLI behavior."""
from __future__ import annotations
import re
import os
import tempfile
import shutil
import subprocess
import unittest
from pathlib import Path

from g11_terminal import CleanupError, run_terminal

ROOT = Path(__file__).resolve().parents[1]
MANIFESTS = ROOT / 'setup' / 'manifests'
MAIN = ROOT / 'bootstrap' / 'panda-setup.fish'
HELPERS = ROOT / 'bootstrap' / 'lib' / 'panda-setup.fish'
GAMING = ROOT / 'bootstrap' / 'panda-gaming.fish'


@unittest.skipUnless(shutil.which('fish'), 'Requires Fish')
class ModuleRegistryContracts(unittest.TestCase):
    def query(self, function, *args):
        with tempfile.TemporaryDirectory(prefix='panda-contract-') as home:
            env = dict(os.environ, HOME=home, XDG_CONFIG_HOME=home,
                       XDG_CACHE_HOME=home, XDG_DATA_HOME=home)
            return subprocess.run(
                ['fish', '--no-config', '-c',
                 'source "$argv[1]"; set -e argv[1]; $argv',
                 str(HELPERS), function, *args], env=env,
                stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=10)

    def values(self, module, field):
        result = self.query('panda_setup_module_get', module, field)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.splitlines()

    def test_five_unique_registered_modules_in_existing_menu_order(self):
        result = self.query('panda_setup_module_ids')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(),
                         ['workspace', 'desktop', 'gaming', 'android', 'virtualization'])
        records = self.query('panda_setup_module_contracts')
        self.assertEqual(records.returncode, 0, records.stderr)
        self.assertTrue(all(len(row.split('|')) == 13 for row in records.stdout.splitlines()))

    def test_current_names_status_and_operations(self):
        expected = {
            'workspace': ('Workspace', 'implemented'),
            'desktop': ('Panda Desktop', 'packages-only'),
            'gaming': ('Gaming', 'implemented'),
            'android': ('Android / AOSP', 'preview-only'),
            'virtualization': ('Virtualization', 'packages-only'),
        }
        for module, (name, status) in expected.items():
            with self.subTest(module=module):
                self.assertEqual(self.values(module, 'name'), [name])
                self.assertEqual(self.values(module, 'status'), [status])
                self.assertEqual(self.values(module, 'operations'), ['dry-run'] if module == 'android'
                                 else ['dry-run', 'check', 'verify', 'apply'])
                self.assertTrue(self.values(module, 'limitations'))

    def test_unknown_module_and_property_are_refused(self):
        for module, field in [('bogus', 'name'), ('workspace', 'HOME')]:
            result = self.query('panda_setup_module_get', module, field)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, '')

    def test_manifest_selectors_and_script_references_are_complete(self):
        for module in ('workspace', 'desktop', 'gaming', 'android', 'virtualization'):
            manifests = self.values(module, 'manifests')
            self.assertEqual(len(manifests), len(self.values(module, 'selectors')))
            self.assertTrue(set(self.values(module, 'selectors')) <=
                            {'always', 'steam', 'heroic', 'other', 'intel', 'amd'})
            self.assertEqual(len(manifests), len(set(manifests)))
            for relative in manifests + self.values(module, 'scripts'):
                self.assertTrue((ROOT / relative).is_file(), relative)
                self.assertFalse(Path(relative).is_absolute())
        self.assertEqual(self.values('workspace', 'scripts'), [
            'bootstrap/install-core.fish', 'bootstrap/setup-chezmoi.fish',
            'bootstrap/setup-github.fish', 'bootstrap/setup-development.fish'])
        self.assertEqual(self.values('desktop', 'arguments'), ['--profile', 'plasma'])
        for module in ('gaming', 'android', 'virtualization'):
            self.assertEqual(self.values(module, 'scripts'), [])

    def test_store_gpu_manifest_selection_preserves_order_and_heroic_dedup(self):
        result = self.query('panda_setup_module_manifests', 'gaming', 'amd',
                            'other', 'epic', 'gog', 'steam', 'steam')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), [
            'setup/manifests/gaming-base.txt', 'setup/manifests/gaming-steam.txt',
            'setup/manifests/gaming-heroic.txt', 'setup/manifests/gaming-other.txt',
            'setup/manifests/gaming-amd.txt'])


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



class G11PreflightContracts(unittest.TestCase):
    def test_no_unsupported_fish_exact_match_option(self):
        # Fish string match has no -x switch; this previously broke preflight.
        self.assertNotIn('string match -qx', HELPERS.read_text())
        self.assertIn('contains -- multilib $repos', HELPERS.read_text())
        self.assertIn('contains -- flathub $remotes', HELPERS.read_text())

    def test_readiness_is_strict_and_read_only(self):
        src = MAIN.read_text()
        self.assertIn("'check'", src)
        self.assertIn('panda_setup_preflight_scripts', src)
        self.assertIn('panda_setup_preflight_packages', src)
        self.assertIn("if test $check -eq 1", src)
        self.assertLess(src.index('panda_setup_preflight_packages'),
                        src.index('panda_setup_install_selected $transaction_manifests'))
        self.assertLess(src.index('panda_setup_preflight_packages'),
                        src.index('flatpak remote-add --user'))

    def test_manifests_are_preflighted_for_all_modules(self):
        helpers = HELPERS.read_text()
        self.assertIn('packages/core', helpers)
        self.assertIn('packages/development', helpers)
        self.assertIn('packages/desktop', helpers)
        self.assertIn('panda_setup_repo_available "$manifest"', helpers)
        self.assertIn('Arch rust conflicts', helpers)

    def test_heroic_is_user_scoped_in_all_paths(self):
        source = MAIN.read_text() + HELPERS.read_text()
        self.assertIn('flatpak info --user com.heroicgameslauncher.hgl', source)
        self.assertNotRegex(source, r'flatpak info (?!\-\-user)com\.heroicgameslauncher\.hgl')


class G13Contracts(unittest.TestCase):
    def test_one_installer_performs_post_apply_verification(self):
        source=MAIN.read_text()
        self.assertIn('panda_setup_verify_installation "$heroic" $transaction_manifests',source)
        self.assertIn('--verify',source)
        self.assertLess(source.index('panda_setup_guard_transaction $transaction_manifests'),
                        source.index('panda_setup_install_selected $transaction_manifests'))
        self.assertLess(source.index('panda_setup_check_disk_space'),
                        source.index('panda_setup_install_selected $transaction_manifests'))

    def test_disk_and_verification_helpers_are_read_only(self):
        source=HELPERS.read_text()
        self.assertIn('function panda_setup_check_disk_space',source)
        self.assertIn('function panda_setup_verify_installation',source)
        self.assertIn('df -Pk --',source)
        self.assertIn('flatpak info --user com.heroicgameslauncher.hgl',source)
        # These helpers must not start apps or modify the host.
        for forbidden in ('sudo ', 'systemctl ', 'modprobe ', 'pacman -Sy', 'flatpak install'):
            guarded=source[source.index('function panda_setup_check_disk_space'):source.index('# Collect missing packages')]
            self.assertNotIn(forbidden,guarded)



class G14Contracts(unittest.TestCase):
    def test_one_combined_pacman_transaction_and_preflight(self):
        main=MAIN.read_text()
        self.assertIn('panda_setup_install_selected $transaction_manifests',main)
        self.assertNotIn('install_manifest "$repo_root/setup/manifests/',main)
        self.assertLess(main.index('panda_setup_guard_transaction $transaction_manifests'),
                        main.index('panda_setup_install_selected $transaction_manifests'))
        helpers=HELPERS.read_text()
        self.assertIn('sudo pacman -S --needed -- $missing',helpers)
        self.assertIn('function panda_setup_missing_targets',helpers)
        self.assertIn('function panda_setup_limine_hash',helpers)
        self.assertIn('function panda_setup_helios_limine_lts',helpers)
        self.assertIn('panda_setup_helios_validate "$repo_root"',main)

    def test_lutris_battlenet_dependency_is_in_manifest(self):
        other=(MANIFESTS/'gaming-other.txt').read_text().splitlines()
        self.assertIn('python-protobuf',other)

class G141SafetyContracts(unittest.TestCase):
    def test_pacman_failure_cannot_skip_post_transaction_safety(self):
        main=MAIN.read_text()
        begin=main.index('panda_setup_install_selected $transaction_manifests')
        end=main.index('if test $heroic -eq 1',begin)
        stage=main[begin:end]
        self.assertIn('set -l package_status $status',stage)
        self.assertIn('panda_setup_helios_validate "$repo_root"',stage)
        self.assertIn('panda_setup_helios_limine_lts',stage)
        self.assertIn('panda_setup_limine_hash',stage)
        self.assertNotIn('or exit $status',stage)
        self.assertLess(stage.index('panda_setup_limine_hash'),
                        stage.index('if test $package_status -ne 0'))
        self.assertIn('exit $package_status',stage)


@unittest.skipUnless(shutil.which('fish'), 'Requires Fish on the host or CI')
class G11MockedApplyTests(unittest.TestCase):
    '''Run real Fish setup manager against disposable fake pacman/flatpak programs.

    The fake utilities cannot invoke system package managers. Only temp paths
    are ever mutated. No user config, Git, VMs, or actual packages are touched.
    '''

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='panda-g11-'))
        self._terminal_cleanup_safe = True
        self.addCleanup(self._cleanup_fixture)
        self.repo = self.root / 'repo'
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        for rel in ['bootstrap/panda-setup.fish',
                    'bootstrap/lib/panda-setup.fish',
                    'bootstrap/lib/packages.fish',
                    'bootstrap/lib/ui.fish',
                    'packages/core.txt', 'packages/desktop.txt',
                    'packages/development.txt']:
            dest = self.repo / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            if (ROOT / rel).exists():
                shutil.copy2(ROOT / rel, dest)
            else:
                dest.write_text('fixture-package\n')
        for manifest in MANIFESTS.glob('*.txt'):
            dest = self.repo / 'setup/manifests' / manifest.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(manifest, dest)
        for stage in ['install-core.fish', 'setup-chezmoi.fish',
                      'setup-github.fish', 'setup-development.fish',
                      'install-desktop.fish']:
            path = self.repo / 'bootstrap' / stage
            path.write_text('''#!/usr/bin/env fish
if test "$MOCK_FAIL_STAGE" = "'''+stage+'''"
    exit 61
end
printf '%s\\n' "'''+stage+'''" >> "$MOCK_STAGE_LOG"
''')

        self.installed = self.root / 'installed'
        self.installed.write_text('fish\n')
        self.events = self.root / 'events'
        self.events.write_text('')
        self.flat_state = self.root / 'flat-state'
        self.flat_state.write_text('')
        self.stage_log = self.root / 'stages'
        self.stage_log.write_text('')

        self.make_exe('pacman', r'''#!/usr/bin/env python3
import os,sys,pathlib
args=sys.argv[1:]
state=pathlib.Path(os.environ['MOCK_INSTALLED'])
entries=set(state.read_text().splitlines())
events=pathlib.Path(os.environ['MOCK_EVENTS'])
if args[:1]==['-Qq']:
    if os.getenv('MOCK_INVENTORY_FAIL')=='1':sys.exit(70)
    if len(args)==1:
        print('\n'.join(sorted(entries)))
        sys.exit(0)
    if args[1] in entries:
        print(args[1]);sys.exit(0)
    sys.exit(1)
if args[:1]==['-Qu']:
    if os.getenv('MOCK_UPGRADE_QUERY_FAIL')=='1':
        print('error: sync database could not be read',file=sys.stderr);sys.exit(45)
    if os.getenv('MOCK_UPGRADE_QUERY_ERROR_ONE')=='1':
        print('error: sync database could not be read',file=sys.stderr);sys.exit(1)
    if os.getenv('MOCK_UPGRADE_NO_UPDATES_EXIT_ONE')=='1':sys.exit(1)
    if os.getenv('MOCK_PENDING_UPGRADES')=='1':print('glibc 2.0 -> 2.1')
    sys.exit(0)
if args[:1]==['-Sp']:
    if os.getenv('MOCK_TRANSACTION_FAIL')=='1':
        print('error: unresolved dependency',file=sys.stderr);sys.exit(46)
    targets=args[args.index('--')+1:] if '--' in args else []
    for target in targets:
        print(target+' 1.0')
    if os.getenv('MOCK_TRANSACTION_EXISTING')=='1':print('glibc 2.1')
    if os.getenv('MOCK_TRANSACTION_GARBLED')=='1':print('unexpected output!')
    sys.exit(0)
if args[:1]==['-Si']:
    if args[1]==os.getenv('MOCK_REPO_QUERY_ERROR'):
        print('error: openai-chatgpt: missing required signature', file=sys.stderr)
        sys.exit(44)
    sys.exit(1 if args[1]==os.getenv('MOCK_MISSING_PACKAGE') else 0)
if args[:2]==['-S','--needed']:
    targets=args[2:]
    if targets and targets[0]=='--': targets=targets[1:]
    with events.open('a') as f:f.write('pacman-install '+','.join(targets)+'\n')
    if os.getenv('MOCK_PACMAN_FAIL')=='1':sys.exit(51)
    entries.update(targets);state.write_text('\n'.join(sorted(entries))+'\n')
    sys.exit(0)
sys.exit(88)
''')
        self.make_exe('sudo', '''#!/bin/sh
exec "$@"
''')
        self.make_exe('pacman-conf', '''#!/bin/sh
if [ "$1" = "--repo-list" ]; then
    if [ "$MOCK_MULTILIB_DISABLED" = "1" ]; then echo core; else echo multilib; fi
    exit 0
fi
if [ "$MOCK_CONFIG_FAIL" = "1" ]; then exit 48; fi
if [ "$MOCK_IGNOREPKG" = "1" ]; then echo 'IgnorePkg = linux-cachyos-lts'; fi
if [ "$MOCK_IGNOREGROUP" = "1" ]; then echo 'IgnoreGroup = graphics'; fi
''')
        self.make_exe('hostname', '''#!/bin/sh
echo panda-test-host
''')
        self.make_exe('lspci', '''#!/bin/sh
echo 'Kernel driver in use: i915'
''')
        # Disk checks are run against a fake df, never host storage.
        self.make_exe('df', '''#!/bin/sh
if [ "$MOCK_DF_FAIL" = "1" ]; then echo 'df: unavailable' >&2; exit 42; fi
echo 'Filesystem 1024-blocks Used Available Capacity Mounted on'
if [ "$MOCK_DF_LOW" = "1" ]; then
    echo '/dev/test 1000000 999900 100 100% /'
else
    echo '/dev/test 20000000 1000000 19000000 5% /'
fi
''')
        self.make_exe('flatpak', r'''#!/usr/bin/env python3
import os,sys,pathlib
args=sys.argv[1:]
state=pathlib.Path(os.environ['MOCK_FLAT_STATE'])
events=pathlib.Path(os.environ['MOCK_EVENTS'])
parts=set(state.read_text().splitlines())
if args[:1]==['info']:
    assert '--user' in args, 'Heroic info must always be user-scoped'
    sys.exit(0 if 'heroic' in parts else 1)
if args[:1]==['remotes']:
    if 'flathub' in parts:print('flathub')
    sys.exit(0)
if args[:1]==['remote-add']:
    assert '--user' in args
    with events.open('a') as f:f.write('flatpak-add\n')
    if os.getenv('MOCK_FLATPAK_FAIL')=='remote':sys.exit(42)
    parts.add('flathub');state.write_text('\n'.join(sorted(parts))+'\n');sys.exit(0)
if args[:1]==['install']:
    assert '--user' in args
    with events.open('a') as f:f.write('flatpak-install\n')
    if os.getenv('MOCK_FLATPAK_FAIL')=='install':sys.exit(43)
    parts.add('heroic');state.write_text('\n'.join(sorted(parts))+'\n');sys.exit(0)
sys.exit(89)
''')
        self.env = dict(os.environ)
        self.env.update({
            'PATH': str(self.bin)+os.pathsep+os.environ.get('PATH',''),
            'MOCK_INSTALLED': str(self.installed),
            'MOCK_EVENTS': str(self.events),
            'MOCK_FLAT_STATE': str(self.flat_state),
            'MOCK_STAGE_LOG': str(self.stage_log),
        })
        home = self.root / 'home'
        home.mkdir()
        self.env.update(HOME=str(home), XDG_CONFIG_HOME=str(home / 'config'),
                        XDG_CACHE_HOME=str(home / 'cache'), XDG_DATA_HOME=str(home / 'data'),
                        XDG_STATE_HOME=str(home / 'state'))
        self.forbidden_calls = self.root / 'forbidden-calls'
        self.forbidden_calls.write_text('')
        self.env['MOCK_FORBIDDEN_CALLS'] = str(self.forbidden_calls)
        for name in ('systemctl', 'virsh', 'qemu-system-x86_64', 'java', 'javac',
                     'sdkmanager', 'android', 'android-cli', 'gradle', 'curl', 'wget'):
            self.make_exe(name, '#!/bin/sh\nprintf "%s\\n" "$0" >> "$MOCK_FORBIDDEN_CALLS"\nexit 97\n')

    def make_exe(self, name, source):
        path = self.bin / name
        path.write_text(source)
        path.chmod(0o755)

    def run_manager(self, *args, env=None):
        # Keep the fake apply invocation noninteractive even when the test runner
        # itself was started from a terminal. subprocess.run() otherwise inherits
        # the terminal on stdin and Fish correctly prompts for APPLY indefinitely.
        p = subprocess.run(['fish', str(self.repo / 'bootstrap/panda-setup.fish'),
                            *args], cwd=self.repo, env=(env or self.env),
                           stdin=subprocess.DEVNULL, capture_output=True,
                           text=True, timeout=30)
        return p

    def assert_no_apply(self):
        self.assertNotIn('pacman-install', self.events.read_text())
        self.assertNotIn('flatpak-add', self.events.read_text())
        self.assertNotIn('flatpak-install', self.events.read_text())
        self.assertEqual(self.stage_log.read_text(), '')
        self.assertEqual(self.forbidden_calls.read_text(), '')

    def run_terminal_manager(self, answers, *args):
        if not self._terminal_cleanup_safe:
            raise CleanupError(f'earlier terminal cleanup unproved; retained {self.root}')
        self._terminal_cleanup_safe = False
        try:
            result = run_terminal(['fish', str(self.repo / 'bootstrap/panda-setup.fish'), *args],
                                  answers, cwd=self.repo, env=self.env, timeout=20, cleanup_timeout=5)
        except BaseException as error:
            self._terminal_cleanup_safe = getattr(error, 'cleanup_complete', False)
            raise
        self._terminal_cleanup_safe = result.cleanup_complete
        return result

    def _cleanup_fixture(self):
        if not self._terminal_cleanup_safe:
            raise CleanupError(f'owned terminal cleanup unproved; retained {self.root}')
        shutil.rmtree(self.root)

    def test_interactive_unknown_numbers_are_refused_without_numeric_overflow(self):
        for answer in ('0', '01', '6', '9' * 100):
            with self.subTest(answer=answer):
                result = self.run_terminal_manager(answer + '\n', '--dry-run')
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn('Unknown module selection', result.stdout + result.stderr)
                self.assert_no_apply()

    def test_terminal_apply_still_requires_literal_uppercase_confirmation(self):
        for confirmation in ('apply', 'no', ''):
            with self.subTest(confirmation=confirmation):
                result = self.run_terminal_manager('5\n' + confirmation + '\n', '--apply')
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn('Cancelled', result.stdout)
                self.assert_no_apply()
        result = self.run_terminal_manager('5\nAPPLY\n', '--apply')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('pacman-install', self.events.read_text())
        self.assertEqual(self.forbidden_calls.read_text(), '')

    def test_preview_and_check_preserve_disposable_state(self):
        args = ['--modules', 'workspace,desktop,gaming,virtualization',
                '--stores', 'steam,gog,epic,other', '--gpu', 'intel', '--enable-flathub']
        files = (self.installed, self.events, self.flat_state, self.stage_log)
        before = [path.read_bytes() for path in files]
        for mode in ('--dry-run', '--check'):
            result = self.run_manager(*args, mode)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual([path.read_bytes() for path in files], before)
            self.assert_no_apply()

    def test_android_blocks_combined_strict_modes_before_any_apply(self):
        for mode in ('--check', '--verify', '--apply'):
            args = ['--modules', 'workspace,desktop,gaming,android,virtualization',
                    '--gpu', 'intel', '--enable-flathub', mode]
            if mode == '--apply':
                args.append('--yes')
            result = self.run_manager(*args)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn('no selected modules were applied', result.stdout + result.stderr)
            self.assert_no_apply()

    def test_virtualization_apply_is_packages_only(self):
        result = self.run_manager('--modules', 'virtualization', '--apply', '--yes')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.events.read_text().splitlines(), [
            'pacman-install qemu-base,libvirt,virt-manager,virt-install,edk2-ovmf'])
        self.assertEqual(self.stage_log.read_text(), '')
        self.assertEqual(self.forbidden_calls.read_text(), '')

    def test_contract_script_dependency_is_used_by_preflight_and_dispatch(self):
        helper = self.repo / 'bootstrap/lib/panda-setup.fish'
        helper.write_text(helper.read_text().replace('bootstrap/setup-development.fish',
                                                     'bootstrap/custom-development.fish'))
        result = self.run_manager('--modules', 'workspace', '--apply', '--yes')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('custom-development.fish', result.stdout + result.stderr)
        self.assert_no_apply()
        (self.repo / 'bootstrap/setup-development.fish').rename(
            self.repo / 'bootstrap/custom-development.fish')
        result = self.run_manager('--modules', 'workspace', '--apply', '--yes')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.stage_log.read_text().splitlines(), [
            'install-core.fish', 'setup-chezmoi.fish', 'setup-github.fish', 'setup-development.fish'])

    def test_combined_transaction_matches_legacy_manifest_order(self):
        # Oracle is the pre-refactor manifest sequence, independent of the registry.
        ordered = ['setup/manifests/gaming-base.txt', 'setup/manifests/gaming-steam.txt',
                   'setup/manifests/gaming-heroic.txt', 'setup/manifests/gaming-other.txt',
                   'setup/manifests/gaming-intel.txt', 'setup/manifests/virtualization-base.txt',
                   'packages/core.txt', 'packages/development.txt', 'packages/desktop.txt']
        expected = []
        for relative in ordered:
            for raw in (self.repo / relative).read_text().splitlines():
                package = raw.strip()
                if package and not package.startswith('#') and package != 'fish' and package not in expected:
                    expected.append(package)
        result = self.run_manager('--modules', 'desktop,virtualization,workspace,gaming,gaming',
                                  '--stores', 'other,epic,gog,steam,steam', '--gpu', 'intel',
                                  '--enable-flathub', '--apply', '--yes')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        installs = [line for line in self.events.read_text().splitlines() if line.startswith('pacman-install ')]
        self.assertEqual(installs, ['pacman-install ' + ','.join(expected)])
        self.assertEqual(self.stage_log.read_text().splitlines(), [
            'install-core.fish', 'setup-chezmoi.fish', 'setup-github.fish',
            'setup-development.fish', 'install-desktop.fish'])
        self.assertEqual(self.forbidden_calls.read_text(), '')

    def configure_mock_helios(self):
        # Only disposable fake commands and a fake validator are executed here.
        # No actual /boot files, kernels or host services are touched.
        self.make_exe('hostname', '#!/bin/sh\necho panda-helios\n')
        validator=self.repo/'machines/panda-helios/validate.fish'
        validator.parent.mkdir(parents=True,exist_ok=True)
        validator.write_text('''#!/usr/bin/env fish
printf 'helios-validate\\n' >> "$MOCK_EVENTS"
if test "$MOCK_HELIOS_VALIDATE_FAIL_AFTER" = 1
    if string match -q '*pacman-install*' -- (string collect < "$MOCK_EVENTS")
        exit 65
    end
end
exit 0
''')
        self.make_exe('sudo', r'''#!/bin/sh
if [ "$1" = "grep" ] && [ "$2" = "-F" ]; then
    printf 'limine-lts-check\n' >> "$MOCK_EVENTS"
    echo ' comment: kernel-id=linux-cachyos-lts'
    echo ' module_path: boot():/mock/initramfs'
    echo ' path: boot():/mock/vmlinuz'
    if [ "$MOCK_LIMINE_INVALID_AFTER" = "1" ] &&
       grep -q '^pacman-install ' "$MOCK_EVENTS"; then
        echo ' cmdline: quiet splash'
    else
        echo ' cmdline: quiet module_blacklist=nvidia,nvidia_drm,nvidia_modeset,nvidia_uvm,nouveau'
    fi
    exit 0
fi
if [ "$1" = "sha256sum" ]; then
    printf 'limine-hash-check\n' >> "$MOCK_EVENTS"
    if [ "$MOCK_LIMINE_HASH_CHANGED" = "1" ] &&
       grep -q '^pacman-install ' "$MOCK_EVENTS"; then
        printf '%064d  /boot/limine.conf\n' 1
    else
        printf '%064d  /boot/limine.conf\n' 0
    fi
    exit 0
fi
exec "$@"
''')

    def test_failed_pacman_still_validates_helios_and_keeps_exit_code(self):
        self.configure_mock_helios()
        env=dict(self.env,MOCK_PACMAN_FAIL='1',MOCK_LIMINE_HASH_CHANGED='1')
        r=self.run_manager('--modules','virtualization','--apply','--yes',env=env)
        self.assertEqual(r.returncode,51,r.stdout+r.stderr)
        log=self.events.read_text().splitlines()
        self.assertEqual(log.count('helios-validate'),2,log)
        self.assertEqual(log.count('limine-lts-check'),2,log)
        self.assertEqual(log.count('limine-hash-check'),2,log)
        self.assertIn('Pacman hooks changed /boot/limine.conf',r.stdout+r.stderr)
        self.assertIn('Package transaction failed (exit 51)',r.stdout+r.stderr)
        self.assertEqual(self.stage_log.read_text(),'')

    def test_failed_pacman_still_detects_corrupted_helios_lts(self):
        self.configure_mock_helios()
        env=dict(self.env,MOCK_PACMAN_FAIL='1',MOCK_LIMINE_INVALID_AFTER='1')
        r=self.run_manager('--modules','virtualization','--apply','--yes',env=env)
        self.assertEqual(r.returncode,51,r.stdout+r.stderr)
        self.assertIn('lost its NVIDIA hard blacklist',r.stdout+r.stderr)
        self.assertIn('Post-transaction safety validation failed',r.stdout+r.stderr)
        log=self.events.read_text().splitlines()
        self.assertEqual(log.count('helios-validate'),2,log)
        self.assertEqual(log.count('limine-lts-check'),2,log)
        self.assertEqual(log.count('limine-hash-check'),2,log)
        self.assertEqual(self.stage_log.read_text(),'')

    def test_successful_helios_transaction_warns_about_limine_change(self):
        self.configure_mock_helios()
        env=dict(self.env,MOCK_LIMINE_HASH_CHANGED='1')
        r=self.run_manager('--modules','virtualization','--apply','--yes',env=env)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        self.assertIn('Pacman hooks changed /boot/limine.conf',r.stdout+r.stderr)
        log=self.events.read_text().splitlines()
        self.assertGreaterEqual(log.count('helios-validate'),3,log)
        self.assertEqual(log.count('limine-lts-check'),2,log)

    def test_successful_pacman_stops_when_post_helios_check_fails(self):
        self.configure_mock_helios()
        env=dict(self.env,MOCK_HELIOS_VALIDATE_FAIL_AFTER='1')
        r=self.run_manager('--modules','virtualization','--apply','--yes',env=env)
        self.assertEqual(r.returncode,1,r.stdout+r.stderr)
        self.assertIn('Post-transaction safety validation failed',r.stdout+r.stderr)
        log=self.events.read_text().splitlines()
        self.assertEqual(log.count('helios-validate'),2,log)
        self.assertEqual(log.count('limine-lts-check'),2,log)
        self.assertEqual(log.count('limine-hash-check'),2,log)
        self.assertEqual(self.stage_log.read_text(),'')

    def test_combined_pacman_transaction_covers_all_selected_stores(self):
        args=['--modules','gaming','--stores','steam,gog,epic,other',
              '--gpu','intel','--enable-flathub']
        r=self.run_manager(*args,'--apply','--yes')
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        installs=[line for line in self.events.read_text().splitlines()
                  if line.startswith('pacman-install ')]
        self.assertEqual(len(installs),1,installs)
        self.assertIn('steam',installs[0])
        self.assertIn('lutris',installs[0])
        self.assertIn('flatpak',installs[0])
        self.assertIn('python-protobuf',installs[0])
        self.assertIn('gamemode',installs[0])
        self.assertEqual(len(installs[0].split(',') ),len(set(installs[0].split(','))))

    def test_check_is_non_mutating_and_apply_is_idempotent(self):
        args=['--modules', 'gaming', '--stores', 'steam,gog,epic,other',
              '--gpu', 'intel', '--enable-flathub']
        r=self.run_manager(*args, '--check')
        self.assertEqual(r.returncode, 0, r.stdout+r.stderr)
        self.assertIn('READINESS CHECK PASSED', r.stdout)
        self.assert_no_apply()
        first=self.run_manager(*args, '--apply', '--yes')
        self.assertEqual(first.returncode, 0, first.stdout+first.stderr)
        events=self.events.read_text()
        self.assertIn('pacman-install', events)
        self.assertIn('flatpak-add', events)
        self.assertIn('flatpak-install', events)
        second=self.run_manager(*args, '--apply', '--yes')
        self.assertEqual(second.returncode, 0, second.stdout+second.stderr)
        self.assertEqual(self.events.read_text(), events)

    def test_pacman_signature_failure_is_not_reported_as_missing_package(self):
        env=dict(self.env, MOCK_REPO_QUERY_ERROR='gamemode')
        r=self.run_manager('--modules','gaming','--stores','steam',
                           '--gpu','intel','--check',env=env)
        self.assertNotEqual(r.returncode, 0, r.stdout+r.stderr)
        self.assertIn('missing required signature', r.stdout+r.stderr)
        self.assertIn('Cannot verify package: gamemode', r.stdout+r.stderr)
        self.assertNotIn('Package not available in synchronized repositories', r.stdout+r.stderr)
        self.assert_no_apply()

    def test_missing_workspace_package_blocks_all(self):
        env=dict(self.env, MOCK_MISSING_PACKAGE='tree')
        args=['--modules','workspace,gaming', '--stores','steam',
              '--gpu','intel', '--apply','--yes']
        r=self.run_manager(*args, env=env)
        self.assertNotEqual(r.returncode, 0, r.stdout+r.stderr)
        self.assert_no_apply()

    def test_missing_desktop_package_blocks_all(self):
        env=dict(self.env, MOCK_MISSING_PACKAGE='fixture-package')
        # Overwrite a disposable fixture desktop manifest only.
        (self.repo/'packages/desktop.txt').write_text('fixture-package\n')
        r=self.run_manager('--modules','desktop,gaming','--stores','steam',
                           '--gpu','intel','--apply','--yes',env=env)
        self.assertNotEqual(r.returncode, 0, r.stdout+r.stderr)
        self.assert_no_apply()

    def test_missing_workspace_stage_blocks_all(self):
        (self.repo/'bootstrap/setup-development.fish').unlink()
        r=self.run_manager('--modules','workspace,gaming','--stores','steam',
                           '--gpu','intel','--apply','--yes')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('Missing setup stage', r.stdout+r.stderr)
        self.assert_no_apply()

    def test_rust_conflict_blocks_all(self):
        self.installed.write_text('fish\nrust\n')
        r=self.run_manager('--modules','workspace,gaming','--stores','steam',
                           '--gpu','intel','--apply','--yes')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('rustup', r.stdout+r.stderr)
        self.assert_no_apply()

    def test_no_multilib_blocks_gaming(self):
        env=dict(self.env, MOCK_MULTILIB_DISABLED='1')
        r=self.run_manager('--modules','gaming','--stores','steam',
                           '--gpu','intel','--apply','--yes',env=env)
        self.assertNotEqual(r.returncode, 0)
        self.assert_no_apply()

    def test_heroic_missing_flathub_blocks_all(self):
        r=self.run_manager('--modules','gaming','--stores','gog,epic',
                           '--gpu','intel','--apply','--yes')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('Flathub', r.stdout+r.stderr)
        self.assert_no_apply()

    def test_flatpak_failure_stops_following_desktop_stage(self):
        env=dict(self.env, MOCK_FLATPAK_FAIL='install')
        r=self.run_manager('--modules','gaming,desktop','--stores','gog',
                           '--gpu','intel','--enable-flathub','--apply','--yes',env=env)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('flatpak-install', self.events.read_text())
        self.assertEqual(self.stage_log.read_text(), '')

    def test_flatpak_remote_failure_stops_following_stages(self):
        env=dict(self.env, MOCK_FLATPAK_FAIL='remote')
        r=self.run_manager('--modules','gaming,desktop','--stores','epic',
                           '--gpu','intel','--enable-flathub','--apply','--yes',env=env)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('flatpak-add', self.events.read_text())
        self.assertNotIn('flatpak-install', self.events.read_text())
        self.assertEqual(self.stage_log.read_text(), '')

    def test_broken_package_inventory_blocks_all(self):
        env=dict(self.env, MOCK_INVENTORY_FAIL='1')
        r=self.run_manager('--modules','gaming','--stores','steam',
                           '--gpu','intel','--apply','--yes',env=env)
        self.assertNotEqual(r.returncode, 0)
        self.assert_no_apply()

    def test_pacman_failure_stops_following_stages(self):
        env=dict(self.env, MOCK_PACMAN_FAIL='1')
        r=self.run_manager('--modules','gaming,desktop','--stores','gog',
                           '--gpu','intel','--enable-flathub','--apply','--yes',env=env)
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn('flatpak-add', self.events.read_text())
        self.assertEqual(self.stage_log.read_text(), '')

    def test_noninteractive_apply_needs_yes(self):
        r=self.run_manager('--modules','gaming','--stores','steam',
                           '--gpu','intel','--apply')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('--yes', r.stdout+r.stderr)
        self.assert_no_apply()

    def test_helios_safe_boot_required_for_check(self):
        # Simulates a Helios hostname without touching the actual host boot.
        self.make_exe('hostname', '#!/bin/sh\necho panda-helios\n')
        # Force an experimental kernel in the fake environment regardless of host.
        self.make_exe('uname', '#!/bin/sh\necho 6.0.0-cachyos\n')
        r=self.run_manager('--modules','gaming','--stores','steam',
                           '--gpu','intel','--check')
        self.assertNotEqual(r.returncode, 0)
        self.assert_no_apply()

    def test_failed_workspace_stage_stops_desktop(self):
        env=dict(self.env, MOCK_FAIL_STAGE='setup-chezmoi.fish')
        r=self.run_manager('--modules','workspace,desktop','--apply','--yes',env=env)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('install-core.fish', self.stage_log.read_text())
        self.assertNotIn('install-desktop.fish', self.stage_log.read_text())

    def test_check_and_apply_conflict(self):
        r=self.run_manager('--modules','virtualization','--check','--apply')
        self.assertEqual(r.returncode, 2)
        self.assert_no_apply()

    def test_disk_space_failure_blocks_gaming_apply(self):
        env=dict(self.env, MOCK_DF_LOW='1')
        r=self.run_manager('--modules','gaming','--stores','steam',
                           '--gpu','intel','--apply','--yes',env=env)
        self.assertNotEqual(r.returncode,0)
        self.assertIn('Less than 8 GiB',r.stdout+r.stderr)
        self.assert_no_apply()

    def test_unreadable_disk_capacity_blocks_gaming_check(self):
        env=dict(self.env, MOCK_DF_FAIL='1')
        r=self.run_manager('--modules','gaming','--stores','steam',
                           '--gpu','intel','--check',env=env)
        self.assertNotEqual(r.returncode,0)
        self.assertIn('Cannot determine free space',r.stdout+r.stderr)
        self.assert_no_apply()

    def test_apply_then_verify_is_one_idempotent_workflow(self):
        args=['--modules','gaming','--stores','steam,gog,epic,other',
              '--gpu','intel','--enable-flathub']
        before=self.run_manager(*args,'--verify')
        self.assertNotEqual(before.returncode,0)
        self.assertIn('package missing',before.stdout+before.stderr)
        self.assert_no_apply()
        applied=self.run_manager(*args,'--apply','--yes')
        self.assertEqual(applied.returncode,0,applied.stdout+applied.stderr)
        self.assertIn('Automatic installation verification',applied.stdout)
        expected=self.events.read_text()
        verified=self.run_manager(*args,'--verify')
        self.assertEqual(verified.returncode,0,verified.stdout+verified.stderr)
        self.assertIn('VERIFICATION COMPLETE',verified.stdout)
        self.assertEqual(self.events.read_text(),expected)
        again=self.run_manager(*args,'--apply','--yes')
        self.assertEqual(again.returncode,0,again.stdout+again.stderr)
        self.assertEqual(self.events.read_text(),expected)

    def test_verify_blocks_when_installed_package_missing(self):
        # Verifies user package inventory; never starts game clients.
        self.installed.write_text('fish\nsteam\n')
        r=self.run_manager('--modules','gaming','--stores','steam',
                           '--gpu','intel','--verify')
        self.assertNotEqual(r.returncode,0)
        self.assertIn('package missing',r.stdout+r.stderr)
        self.assert_no_apply()

    def test_verify_and_apply_are_exclusive(self):
        r=self.run_manager('--modules','gaming','--stores','steam',
                           '--gpu','intel','--verify','--apply')
        self.assertEqual(r.returncode,2)
        self.assert_no_apply()


    def test_pending_upgrades_block_check_and_apply(self):
        env=dict(self.env, MOCK_PENDING_UPGRADES='1')
        for mode in ('--check', '--apply'):
            args=['--modules','gaming','--stores','steam','--gpu','intel',mode]
            if mode=='--apply':args.append('--yes')
            result=self.run_manager(*args,env=env)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('pending upgrades',result.stdout+result.stderr)
        self.assert_no_apply()

    def test_no_pending_upgrades_exit_one_allows_check_and_apply(self):
        # pacman -Qu may return 1 with *empty* output on an up-to-date host.
        env=dict(self.env, MOCK_UPGRADE_NO_UPDATES_EXIT_ONE='1')
        args=['--modules','gaming','--stores','steam','--gpu','intel']
        check=self.run_manager(*args,'--check',env=env)
        self.assertEqual(check.returncode,0,check.stdout+check.stderr)
        self.assertIn('READINESS CHECK PASSED',check.stdout)
        self.assert_no_apply()
        apply=self.run_manager(*args,'--apply','--yes',env=env)
        self.assertEqual(apply.returncode,0,apply.stdout+apply.stderr)
        self.assertIn('pacman-install',self.events.read_text())

    def test_upgrade_query_exit_one_with_error_still_blocks(self):
        env=dict(self.env, MOCK_UPGRADE_QUERY_ERROR_ONE='1')
        r=self.run_manager('--modules','gaming','--stores','steam',
                           '--gpu','intel','--check',env=env)
        self.assertNotEqual(r.returncode,0)
        self.assertIn('Cannot query pending upgrades',r.stdout+r.stderr)
        self.assertIn('sync database could not be read',r.stdout+r.stderr)
        self.assert_no_apply()

    def test_failed_upgrade_query_blocks(self):
        env=dict(self.env, MOCK_UPGRADE_QUERY_FAIL='1')
        r=self.run_manager('--modules','gaming','--stores','steam',
                           '--gpu','intel','--check',env=env)
        self.assertNotEqual(r.returncode,0)
        self.assertIn('Cannot query pending upgrades',r.stdout+r.stderr)
        self.assert_no_apply()

    def test_package_holds_block(self):
        for hold in ('MOCK_IGNOREPKG','MOCK_IGNOREGROUP'):
            env=dict(self.env,**{hold:'1'})
            r=self.run_manager('--modules','gaming','--stores','steam',
                               '--gpu','intel','--apply','--yes',env=env)
            self.assertNotEqual(r.returncode,0)
            self.assertIn('IgnorePkg or IgnoreGroup',r.stdout+r.stderr)
        self.assert_no_apply()

    def test_failed_config_query_blocks(self):
        env=dict(self.env,MOCK_CONFIG_FAIL='1')
        r=self.run_manager('--modules','gaming','--stores','steam',
                           '--gpu','intel','--check',env=env)
        self.assertNotEqual(r.returncode,0)
        self.assertIn('Unable to inspect pacman configuration',r.stdout+r.stderr)
        self.assert_no_apply()

    def test_upgrade_dependency_in_preview_blocks(self):
        self.installed.write_text('fish\nglibc\n')
        env=dict(self.env, MOCK_TRANSACTION_EXISTING='1')
        r=self.run_manager('--modules','gaming','--stores','steam',
                           '--gpu','intel','--apply','--yes',env=env)
        self.assertNotEqual(r.returncode,0)
        self.assertIn('modify installed package: glibc',r.stdout+r.stderr)
        self.assert_no_apply()

    def test_transaction_preview_failure_blocks(self):
        env=dict(self.env, MOCK_TRANSACTION_FAIL='1')
        r=self.run_manager('--modules','gaming','--stores','steam',
                           '--gpu','intel','--apply','--yes',env=env)
        self.assertNotEqual(r.returncode,0)
        self.assertIn('Cannot resolve package transaction',r.stdout+r.stderr)
        self.assert_no_apply()

    def test_unexpected_transaction_output_blocks(self):
        env=dict(self.env,MOCK_TRANSACTION_GARBLED='1')
        r=self.run_manager('--modules','gaming','--stores','steam',
                           '--gpu','intel','--check',env=env)
        self.assertNotEqual(r.returncode,0)
        self.assertIn('Unexpected package transaction output',r.stdout+r.stderr)
        self.assert_no_apply()


if __name__ == '__main__':
    unittest.main()
