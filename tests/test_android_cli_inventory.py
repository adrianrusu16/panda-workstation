"""Synthetic CLI 1.1 layout contracts; no captured machine inventory."""

import contextlib
import copy
import io
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

import test_android_cli as fixtures

ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC = (ROOT / 'tests/fixtures/android/cli-1.1-synthetic-installed.txt').read_text()


class CliInventoryContracts(unittest.TestCase):
    def setUp(self):
        self.context = fixtures.AndroidCliContracts()
        self.context.setUp()
        self.addCleanup(self.context.doCleanups)
        self.f = self.context.f
        self.api = self.context.api
        self.cli = self.api.android_cli
        self.context.version = 'Android CLI 1.1.0'

    def pinned(self):
        slot = self.context.slot
        self.f.executable(slot / 'bin/android',
            '# ANDROID_CLI_DOWNLOAD_URL ANDROID_CLI_LAUNCHER_VERSION\n# version=1.0.15498356\nexit 98')
        (slot / 'source.properties').write_text(
            'Pkg.Revision=22.0\nPkg.Path=cmdline-tools;22.0\nPkg.Desc=Android SDK Command-line Tools\n')
        data = self.api.load_manifest(ROOT / 'config/android/toolchain.toml')
        # A synthetic, owned launcher identity; never real vendor bytes/execution.
        data['android_cli']['bundled_launcher_sha256'] = self.cli.identity(slot / 'bin/android')
        return data

    def run_synthetic(self, args, capture=False):
        if list(args[2:])[:2] == ['sdk', 'list']:
            self.context.calls.append((list(args), capture))
            return SYNTHETIC
        return self.context.fake(args, capture)

    def result(self):
        return self.cli.verify(self.cli.discover(self.f.sdk), self.f.sdk,
                               self.run_synthetic, lambda text: True)

    def test_synthetic_eight_rows_keep_unknown_and_update_distinct(self):
        installed, available, updates = self.cli.parse_listing(SYNTHETIC)
        self.assertEqual(len(installed), 8)
        self.assertEqual(set(installed), {'build-tools/36.0.0', 'cmdline-tools/22.0',
                         'platform-tools', 'platforms/android-36.1', 'example-extra/one',
                         'example-extra/two', 'example-extra/three', 'example-extra/four'})
        self.assertEqual(installed['platform-tools'], '36.0.0')
        self.assertIsNone(installed['cmdline-tools/22.0'])
        self.assertEqual(updates, {'cmdline-tools/22.0': '22.0.0'})
        self.assertEqual(installed['platforms/android-36.1'], '1.0.0')
        self.assertEqual(available, {})

    def test_current_target_and_available_are_separate_evidence(self):
        installed, available, updates = self.cli.parse_listing(
            'Installed packages:\n  platforms/android-36.1 1.0.0 -> 2.0.0 Android\n'
            '  cmdline-tools/22.0 unknown CLI\nAvailable packages:\n'
            '  platforms/android-36.1 3.0.0 Android\n')
        self.assertEqual(installed, {'platforms/android-36.1': '1.0.0', 'cmdline-tools/22.0': None})
        self.assertEqual(updates, {'platforms/android-36.1': '2.0.0'})
        self.assertEqual(available, {'platforms/android-36.1': {'3.0.0'}})

    def test_rejects_unsafe_ambiguous_preview_or_truncated_rows(self):
        rows = ('../escape 1 Bad', '/absolute 1 Bad', 'platforms/../escape 1 Bad',
                'platforms/./android-36.1 1 Bad', 'x//y 1 Bad', 'C:/x 1 Bad',
                'x;bad 1 Bad', 'x 1 | Pipe', 'x | 1 | Pipe', 'x 1.0.0-rc1 Preview',
                'x 1.0.0rc1 Preview', 'x 1.0.0 rc1 Android', 'x 1.0.0 rc 1 Android',
                'x 1.0.0 preview Android', 'x 1.0.0 -rc1 Android', 'x 1.0.0 02 Android',
                'x 1.0.0 2rc1 Android', 'x 1..0 Bad', 'x unknown -> unknown Bad',
                'x unknown -> Bad', 'x 1 -> 2 -> 3 Bad', 'x 1 2 Ambiguous',
                'x 1 -> 2', 'x 1', 'x unknown', 'x 1\x00 Bad', 'x 1 \x1b[2J Bad')
        for row in rows:
            with self.subTest(row=row), self.assertRaises(self.cli.CliError):
                self.cli.parse_listing('Installed packages:\n  ' + row + '\n')
        for text in (SYNTHETIC.rstrip('\n'), 'Installed packages:\n x 1 Name\n x 1 Name\n',
                     'Installed packages:\nInstalled packages:\n',
                     'Available packages:\n x 1 Name\nInstalled packages:\n',
                     'Installed packages:\nAvailable packages:\n x unknown Name\n',
                     'Installed packages:\nOther packages:\n', '{"installed": []}\n'):
            with self.subTest(text=text[:80]), self.assertRaises(self.cli.CliError):
                self.cli.parse_listing(text)

    def test_numeric_equivalence_never_discards_preview_or_meaningful_components(self):
        for left, right in (('1', '1.0'), ('1', '1.0.0'), ('22.0', '22.0.0'), ('36.0.0', '36')):
            with self.subTest(left=left, right=right):
                self.assertTrue(self.cli.revisions_equal(left, right))
        for left, right in (('1', '2'), ('36.0.0', '36.1.0'), (None, None), ('unknown', 'unknown'),
                            ('1-rc1', '1'), ('1-rc1', '1-rc1'), ('1.0-preview', '1'),
                            ('1.0+build', '1'), ('1..0', '1'), (' 1', '1'), ('01', '1'), ('١', '1'),
                            ('9' * 5000, '1')):
            with self.subTest(left=left, right=right):
                self.assertFalse(self.cli.revisions_equal(left, right))

    def test_controls_cannot_be_erased_or_create_extra_rows(self):
        for control in ('\x00', '\x0b', '\x0c', '\x1c', '\x1d', '\x1e', '\x7f', '\x85', '\u2028', '\u2029'):
            for text in ('Installed packages:\n  platforms/android-36.1 1 Android' + control + '\n',
                         'Installed packages:\n  platforms/android-36.1 1 Android' + control + ' platform-tools 36.0.0 Tools\n'):
                with self.subTest(control=repr(control)), self.assertRaises(self.cli.CliError):
                    self.cli.parse_listing(text)

    def test_sgr_and_crlf_preserve_the_same_synthetic_inventory(self):
        decorated = '\x1b[32m' + SYNTHETIC.replace('\n', '\r\n') + '\x1b[0m'
        self.assertEqual(self.cli.parse_listing(decorated), self.cli.parse_listing(SYNTHETIC))

    def test_synthetic_listing_cli_check_warns_only_for_identified_pinned_tools(self):
        data = self.pinned()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = self.api.cli_check(data, self.f.state(), approve=lambda text: True, run=self.run_synthetic)
        self.assertIsNone(result['installed']['cmdline-tools/22.0'])
        self.assertIn('unknown', output.getvalue())
        self.assertIn('unverified', output.getvalue())
        self.assertIn('source metadata', output.getvalue())
        self.assertIn('1.1.0', output.getvalue())
        self.assertFalse(any(flag in args for args, _ in self.context.calls
                             for flag in ('update', 'remove', 'init', 'skills', 'completion', '--no-metrics')))

    def test_numeric_listing_needs_no_unknown_exception_or_archive_trust(self):
        result = self.result()
        result['installed']['cmdline-tools/22.0'] = '22.0.0'
        self.api.check_cli_inventory(result, self.f.state()['packages'])

    def test_other_unknowns_missing_rows_and_update_target_cannot_satisfy_baseline(self):
        data = self.pinned()
        good = self.result()
        for path, value in (('platform-tools', None), ('build-tools/36.0.0', None),
                            ('platforms/android-36.1', None), ('platforms/android-36.1', '2.0.0'),
                            ('platform-tools', '99.0'), ('build-tools/36.0.0', '36.1.0')):
            result = copy.deepcopy(good)
            result['installed'][path] = value
            result['updates'][path] = self.f.state()['packages'][path.replace('/', ';', 1) if path != 'platform-tools' else path]['revision']
            with self.subTest(path=path, value=value), self.assertRaises(self.cli.CliError):
                self.api.check_cli_inventory(result, self.f.state()['packages'], data)
        result = copy.deepcopy(good)
        del result['installed']['cmdline-tools/22.0']
        with self.assertRaisesRegex(self.cli.CliError, 'missing'):
            self.api.check_cli_inventory(result, self.f.state()['packages'], data)

    def test_missing_invalid_or_conflicting_archive_identity_never_gets_exception(self):
        good_data = self.pinned()
        result = self.result()
        changes = (('command_line_tools', 'verified', False), ('command_line_tools', 'revision', '23.0'),
                   ('command_line_tools', 'sha256', '0' * 64), ('command_line_tools', 'sha256', 'f' * 64),
                   ('command_line_tools', 'url', 'https://evil.invalid/tools.zip'),
                   ('android_cli', 'bundled_archive_sha256', ''),
                   ('android_cli', 'bundled_launcher_sha256', ''),
                   ('android_cli', 'bundled_launcher_sha256', None),
                   ('android_cli', 'bundled_launcher_sha256', 'f' * 64))
        for section, field, value in changes:
            data = copy.deepcopy(good_data)
            data[section][field] = value
            with self.subTest(section=section, field=field), self.assertRaises(self.cli.CliError):
                self.api.check_cli_inventory(result, self.f.state()['packages'], data)
        for data in (None, {}, {**good_data, 'command_line_tools': {}}):
            with self.subTest(missing=data is None), self.assertRaises(self.cli.CliError):
                self.api.check_cli_inventory(result, self.f.state()['packages'], data)

    def test_candidate_and_local_source_identity_must_still_match(self):
        data = self.pinned()
        good = self.result()
        for key, value in (('path', self.context.slot / 'bin/sdkmanager'), ('package_revision', '23.0'),
                           ('sha256', '0' * 64), ('launcher', False), ('sdk', self.f.home / 'other sdk')):
            result = copy.deepcopy(good)
            result['candidate'][key] = value
            with self.subTest(key=key), self.assertRaises(self.cli.CliError):
                self.api.check_cli_inventory(result, self.f.state()['packages'], data)
        meta = self.context.slot / 'source.properties'
        original = meta.read_text()
        for text in ('Pkg.Revision=22.0\n', original.replace('cmdline-tools;22.0', 'cmdline-tools;23.0')):
            meta.write_text(text)
            with self.assertRaises(self.cli.CliError):
                self.api.check_cli_inventory(good, self.f.state()['packages'], data)
        meta.write_text(original)
        meta.chmod(0o666)
        with self.assertRaises(self.cli.CliError):
            self.api.check_cli_inventory(good, self.f.state()['packages'], data)

    def test_cli_check_rejects_conflicting_platform_api_or_revision(self):
        data = self.pinned()
        for text in ('Pkg.Revision=2\nAndroidVersion.ApiLevel=36.1\n',
                     'Pkg.Revision=1\nAndroidVersion.ApiLevel=36\n',
                     'Pkg.Revision=1\nAndroidVersion.ApiLevel=36.1\nAndroidVersion.ApiMinorLevel=2\n'):
            (self.f.sdk / 'platforms/android-36.1/source.properties').write_text(text)
            with self.subTest(text=text), self.assertRaises((self.api.Error, self.cli.CliError)):
                self.api.cli_check(data, self.f.state(), approve=lambda text: True, run=self.run_synthetic)

    def test_unknown_exception_rechecks_files_symlinks_and_permissions(self):
        data = self.pinned()
        result = self.result()
        items = self.f.state()['packages']
        for relative in ('source.properties', 'lib/sdkmanager-classpath.jar'):
            path = self.context.slot / relative
            target = self.f.home / 'external data'
            path.rename(target)
            path.symlink_to(target)
            try:
                with self.subTest(relative=relative), self.assertRaises(self.cli.CliError):
                    self.api.check_cli_inventory(result, items, data)
            finally:
                path.unlink()
                target.rename(path)
        binary = self.context.slot / 'bin/android'
        binary.write_text('#!/bin/sh\nexit 97\n')
        with self.assertRaises(self.cli.CliError):
            self.api.check_cli_inventory(result, items, data)

    def test_equivalent_local_revision_is_noop_and_preserves_all_extra_packages(self):
        (self.f.sdk / 'platforms/android-36.1/source.properties').write_text('Pkg.Revision=1.0.0\nAndroidVersion.ApiLevel=36.1\n')
        extra = ('example-extra/one', 'example-extra/two', 'example-extra/three', 'example-extra/four')
        for name in extra:
            path = self.f.sdk / name / 'sentinel'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'preserve')
        self.context.install(approve=lambda text: self.fail('No-op must not prompt or execute vendors'))
        self.assertEqual(self.context.calls, [])
        self.assertTrue(all((self.f.sdk / p / 'sentinel').read_bytes() == b'preserve' for p in extra))

    def test_available_and_postinstall_zero_padding_obey_same_revision_rule(self):
        shutil.rmtree(self.f.sdk / 'platforms/android-36.1')
        self.context.available_revision = '1.0.0'

        def runner(args, capture=False):
            output = self.context.fake(args, capture)
            if '--no-downgrade' in args:
                (self.f.sdk / 'platforms/android-36.1/source.properties').write_text('Pkg.Revision=1.0.0\nAndroidVersion.ApiLevel=36.1\n')
            return output

        self.context.install(runner=runner)
        self.assertEqual(self.context.calls[-1][0][-1], 'platforms/android-36.1@1')

    def test_legacy_available_zero_padding_does_not_change_requested_package_id(self):
        (self.context.slot / 'bin/android').unlink()
        shutil.rmtree(self.f.sdk / 'platforms/android-36.1')

        def runner(args, capture=False):
            return self.f.fake_run(args, capture).replace('platforms;android-36.1 | 1 |', 'platforms;android-36.1 | 1.0.0 |')

        self.context.install(runner=runner)
        self.assertEqual(self.f.calls[-1][2:], ['platforms;android-36.1'])
