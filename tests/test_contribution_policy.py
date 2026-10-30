"""Contribution policy regressions against disposable local Git history."""
from pathlib import Path
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / '.github/scripts/check_contribution.py'


class ContributionPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='panda-contribution-')
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.env = os.environ.copy()
        # Test-only Git identity; never used by repository commits.
        for key in list(self.env):
            if key.startswith('GIT_'):
                self.env.pop(key)
        self.env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)
        self.git('init', '-q', '-b', 'main')
        self.git('config', 'user.name', 'Fixture Contributor')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.commit('README.md', 'base\n', 'docs: establish fixture')
        self.base = self.git('rev-parse', 'HEAD').strip()

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.repo,
                                       env=self.env, text=True, stderr=subprocess.PIPE)

    def commit(self, path, content, subject):
        target = self.repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        self.git('add', '--', path)
        self.git('commit', '-q', '-m', subject)

    def check(self, branch='feat/recover-fixture', title='feat(fixture): recover source'):
        event = self.repo / 'event.json'
        event.write_text(json.dumps({'pull_request': {
            'title': title,
            'head': {'ref': branch, 'sha': self.git('rev-parse', 'HEAD').strip()},
            'base': {'ref': 'main', 'sha': self.base},
        }}))
        return subprocess.run(['python3', '-B', str(SCRIPT), '--event', str(event)],
                              cwd=self.repo, env=self.env, capture_output=True, text=True)

    def test_accepts_conventional_feature_and_does_not_scan_unchanged_history(self):
        # Old history is not rewritten to conform to a newly introduced policy.
        self.commit('old.txt', 'old', 'historical nonconventional subject')
        self.base = self.git('rev-parse', 'HEAD').strip()
        self.commit('source.py', 'value = 1\n', 'feat(fixture): recover source')
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_rejects_unapproved_or_malformed_branch_prefix(self):
        self.commit('source.py', 'value = 1\n', 'feat: recover source')
        for branch in ('codex/recovery', 'feat/Bad-name', 'feat/recover/fixture',
                       'feat/recover_fixture', 'feat/-recovery'):
            with self.subTest(branch=branch):
                self.assertNotEqual(self.check(branch=branch).returncode, 0)

    def test_rejects_bad_title_and_nonconventional_new_commit(self):
        self.commit('source.py', 'value = 1\n', 'misc changes')
        result = self.check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('commit subject', result.stdout + result.stderr)
        self.assertNotEqual(self.check(title='Update source').returncode, 0)

    def test_rejects_unintended_private_or_generated_new_paths(self):
        for path in ('.local-ai/recovery/report.md', '.env', 'private/token.txt',
                     'folder/id_ed25519', 'cache/__pycache__/module.pyc',
                     'docs/superpowers/plans/disposable.md'):
            with self.subTest(path=path):
                self.commit(path, 'fixture', 'test: add fixture')
                result = self.check()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('private/generated', result.stdout + result.stderr)
                self.base = self.git('rev-parse', 'HEAD').strip()

    def test_rejects_assistant_attribution_trailer(self):
        self.commit('source.py', 'value = 1\n',
                    'feat: recover source\n\nCo-authored-by: Codex <fixture@example.invalid>')
        result = self.check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('assistant attribution', result.stdout + result.stderr)

    def test_title_is_data_and_cannot_execute_shell(self):
        self.commit('source.py', 'value = 1\n', 'feat: recover source')
        marker = self.repo / 'executed'
        result = self.check(title='feat: handle $(touch ' + str(marker) + ')')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(marker.exists())

    def test_missing_or_invalid_commit_metadata_fails_closed(self):
        self.commit('source.py', 'value = 1\n', 'feat: recover source')
        self.base = '--all'
        self.assertNotEqual(self.check().returncode, 0)


if __name__ == '__main__':
    unittest.main()
