"""Contribution policy regressions against disposable local Git history."""
from pathlib import Path
import importlib.util
import json
import os
import re
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

    def test_workflow_rejects_bad_history_even_when_head_replaces_policy(self):
        self.commit('.github/scripts/check_contribution.py', SCRIPT.read_text(),
                    'ci: establish trusted policy fixture')
        self.base = self.git('rev-parse', 'HEAD').strip()
        self.commit('.github/scripts/check_contribution.py',
                    "from pathlib import Path\nPath('executed').touch()\n",
                    'invalid subject intended to be rejected')
        head = self.git('rev-parse', 'HEAD').strip()
        event = self.repo / 'event.json'
        event.write_text(json.dumps({'pull_request': {
            'title': 'ci: exercise trusted policy',
            'head': {'ref': 'ci/trust-fixture', 'sha': head},
            'base': {'ref': 'main', 'sha': self.base},
        }}))
        workflow = (ROOT / '.github/workflows/contribution-policy.yml').read_text()
        # Exercise the declared checkout revision and validation command against
        # real Git objects; the hostile head policy must never be executed.
        refs = re.findall(r'^          ref: (.+)$', workflow, re.M)
        self.assertEqual(len(refs), 1, 'Exactly one trusted checkout is required')
        revisions = {'${{ github.event.pull_request.base.sha }}': self.base,
                     '${{ github.event.pull_request.head.sha }}': head}
        self.assertIn(refs[0], revisions)
        self.git('checkout', '--detach', '-q', revisions[refs[0]])
        command = re.search(r'run: (python3[^\n]+check_contribution.py[^\n]+)', workflow)
        self.assertIsNotNone(command)
        env = dict(self.env, GITHUB_EVENT_PATH=str(event))
        result = subprocess.run(['sh', '-c', command.group(1)], cwd=self.repo,
                                env=env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0, 'PR policy replacement bypassed validation')
        self.assertIn('commit subject', result.stdout)
        self.assertFalse((self.repo / 'executed').exists())
        self.assertIn('\n  pull_request_target:', workflow)
        self.assertNotIn('\n  pull_request:', workflow)

    def test_rejects_assistant_author_and_committer_names_and_emails(self):
        cases = (('author', 'name', 'Codex'),
                 ('author', 'email', 'codex@openai.com'),
                 ('committer', 'name', 'GitHub Copilot'),
                 ('committer', 'email', 'assistant@example.invalid'))
        for role, field, value in cases:
            with self.subTest(role=role, field=field):
                key = 'GIT_' + role.upper() + '_' + field.upper()
                self.env[key] = value  # Deliberately invalid fixture-only identity.
                self.commit('source.py', value, 'test: exercise identity rejection')
                self.env.pop(key)
                result = self.check()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(role + ' identity', result.stdout)
                self.base = self.git('rev-parse', 'HEAD').strip()

    def test_rejects_malformed_author_and_committer_email(self):
        for role in ('author', 'committer'):
            with self.subTest(role=role):
                key = 'GIT_' + role.upper() + '_EMAIL'
                self.env[key] = 'missing-domain'
                self.commit('source.py', role, 'test: exercise malformed identity')
                self.env.pop(key)
                result = self.check()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(role + ' identity', result.stdout)
                self.base = self.git('rev-parse', 'HEAD').strip()

    def test_accepts_distinct_normal_author_and_committer(self):
        self.env.update(GIT_AUTHOR_NAME='Fixture Author',
                        GIT_AUTHOR_EMAIL='human@openai.com',
                        GIT_COMMITTER_NAME='Fixture Reviewer',
                        GIT_COMMITTER_EMAIL='reviewer@example.invalid')
        self.commit('source.py', 'fixture', 'test: preserve normal contributor identities')
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_merge_subject_exemption_does_not_exempt_committer_identity(self):
        self.commit('source.py', 'fixture', 'test: add primary fixture')
        self.git('branch', 'fixture-side', self.base)
        self.git('checkout', '-q', 'fixture-side')
        self.commit('side.py', 'fixture', 'test: add side fixture')
        self.git('checkout', '-q', 'main')
        self.env['GIT_COMMITTER_NAME'] = 'Codex'
        self.git('merge', '--no-ff', '-q', '-m', 'Merge fixture branch', 'fixture-side')
        self.env.pop('GIT_COMMITTER_NAME')
        result = self.check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('committer identity', result.stdout)
        self.assertNotIn('commit subject', result.stdout)

    def test_missing_or_invalid_commit_metadata_fails_closed(self):
        self.commit('source.py', 'value = 1\n', 'feat: recover source')
        self.base = '--all'
        self.assertNotEqual(self.check().returncode, 0)


if __name__ == '__main__':
    unittest.main()
