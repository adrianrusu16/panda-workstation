"""Validate new PR metadata/history without changing Git or executing metadata."""
from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import re
import subprocess

BRANCH = re.compile(r'(feat|fix|docs|refactor|test|ci|chore)/[a-z0-9]+(?:-[a-z0-9]+)*')
SUBJECT = re.compile(r'(feat|fix|refactor|perf|docs|test|chore|build|ci|revert)(?:\([a-z0-9][a-z0-9./_-]*\))?!?: \S[^\r\n]*')
EMAIL = re.compile(r'[^\s<>@]+@[^\s<>@]+')
ASSISTANT = re.compile(r'(?:^|[^a-z0-9])(?:codex|chatgpt|copilot|openai|assistant|claude[ ._-]?code)(?:$|[^a-z0-9])', re.I)
OID = re.compile(r'(?:[0-9a-f]{40}|[0-9a-f]{64})')
ATTRIBUTION = re.compile(r'^(?:Co-authored-by|Generated[ -]by|Generated[ -]with):?[^\n]*(?:Codex|OpenAI|ChatGPT|Copilot|Claude)', re.I | re.M)


def git(*args: str) -> bytes:
    return subprocess.check_output(['git', *args], stderr=subprocess.PIPE)


def conventional(value: object) -> bool:
    return isinstance(value, str) and bool(SUBJECT.fullmatch(value)) and not value.endswith('.')


def private_path(name: str) -> bool:
    path = PurePosixPath(name)
    private_parts = {'.local-ai', '.serena', 'graphify-out', '__pycache__',
                     'secrets', 'private', '.venv', 'venv'}
    return (bool(private_parts.intersection(path.parts))
            or path.parts[0] == 'tmp'
            or name.startswith('docs/superpowers/plans/')
            or path.name == '.env' or path.name.startswith('.env.')
            or path.name in {'id_rsa', 'id_ed25519', 'id_ecdsa', 'credentials'}
            or path.suffix.lower() in {'.pyc', '.pyo', '.key', '.pem', '.p12', '.pfx'})


def check(event: dict) -> list[str]:
    pr = event['pull_request']
    failures = []
    if pr['base']['ref'] != 'main':
        failures.append('Recovery contributions must target main')
    if not BRANCH.fullmatch(pr['head']['ref']):
        failures.append('Branch must use an allowed prefix and lowercase kebab name')
    if not conventional(pr['title']):
        failures.append('PR title must use a Conventional Commit subject without a trailing period')
    base, head = pr['base']['sha'], pr['head']['sha']
    if not all(isinstance(oid, str) and OID.fullmatch(oid) for oid in (base, head)):
        raise ValueError('Expected full base/head commit IDs')
    for oid in (base, head):
        git('cat-file', '-e', oid + '^{commit}')
    commits = git('rev-list', base + '..' + head).decode('ascii').splitlines()
    if not commits:
        failures.append('PR must contain at least one new commit')
    for oid in commits:
        subject = git('show', '-s', '--format=%s', oid).decode('utf-8', errors='replace').rstrip('\n')
        parents = git('show', '-s', '--format=%P', oid).split()
        if len(parents) < 2 and not conventional(subject):
            failures.append('Invalid commit subject: ' + oid[:12])
        identities = git('show', '-s', '--format=%an%x00%ae%x00%cn%x00%ce', oid).decode('utf-8', errors='replace').rstrip('\n').split('\0')
        for role, offset in (('author', 0), ('committer', 2)):
            name, email = identities[offset:offset + 2]
            if (not name.strip() or any(ord(char) < 32 for char in name)
                    or not EMAIL.fullmatch(email)
                    or ASSISTANT.search(name) or ASSISTANT.search(email.partition("@")[0])):
                failures.append('Invalid ' + role + ' identity: ' + oid[:12])
        message = git('show', '-s', '--format=%B', oid).decode('utf-8', errors='replace')
        if ATTRIBUTION.search(message):
            failures.append('Remove automatic assistant attribution: ' + oid[:12])
    # Compare against the actual fork point so unrelated main advances do not
    # become additions/deletions in this PR's hygiene check.
    names = git('diff', '--name-only', '--diff-filter=ACR', '-z', base + '...' + head).decode('utf-8', errors='surrogateescape').split('\0')
    for name in filter(None, names):
        if private_path(name):
            failures.append('New private/generated path must remain outside Git: ' + repr(name))
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--event', type=Path, required=True, help='GitHub pull_request event JSON')
    args = parser.parse_args()
    try:
        failures = check(json.loads(args.event.read_text()))
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        # Do not dump event bodies or Git stderr, which may contain private data.
        print('Contribution policy could not validate the PR (' + type(error).__name__ + ')')
        return 1
    for failure in failures:
        print(failure)
    if not failures:
        print('Contribution metadata, new commits and file paths passed')
    return int(bool(failures))


if __name__ == '__main__':
    raise SystemExit(main())
