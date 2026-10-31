"""SDK-local Android CLI discovery and explicitly approved runtime contracts.

No installation, cached trust record, standalone download, or PATH execution.
Documented formats are deliberately narrow; changed behavior fails closed.
"""

import hashlib
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import sys
import time


class CliError(Exception):
    def __init__(self, message, code=1):
        super().__init__(message)
        self.code = code


class ProcessCleanupError(CliError):
    """The vendor may still be active; no fallback or repair rollback is safe."""


def safe(path, sdk):
    """Check path components, ownership and write permissions without resolving links."""
    path, sdk = Path(path), Path(sdk)
    if not sdk.is_absolute() or sdk == Path('/') or '..' in sdk.parts or \
            any(ord(c) < 32 for c in str(sdk)) or not path.is_relative_to(sdk):
        raise CliError('Unsafe SDK-local executable path')
    for item in [*reversed(path.parents), path]:
        if item.is_symlink():
            raise CliError(f'Unsafe Android CLI symlink: {item}')
        if item.exists() and item.is_relative_to(sdk):
            stat = item.stat()
            if stat.st_uid != os.getuid():
                raise CliError(f'Android CLI path is not user-owned: {item}')
            if stat.st_mode & 0o022:
                raise CliError(f'Android CLI path is group/other writable: {item}')


def identity(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def discover(sdk, preferred_revision='22.0'):
    sdk = Path(sdk)
    root = sdk / 'cmdline-tools'
    safe(root, sdk)
    if not root.is_dir():
        return None
    slots = [p for p in root.iterdir() if p.name == 'latest' or re.fullmatch(r'[0-9]+(?:\.[0-9]+)*', p.name)]
    slots.sort(key=lambda p: (p.name == preferred_revision, p.name == 'latest',
               tuple(int(x) for x in p.name.split('.')) if p.name != 'latest' else ()), reverse=True)
    for slot in slots:
        path, metadata = slot / 'bin/android', slot / 'source.properties'
        safe(path, sdk)
        safe(metadata, sdk)
        if not path.is_file() or not os.access(path, os.X_OK) or not metadata.is_file():
            continue
        properties = dict(line.split('=', 1) for line in metadata.read_text().splitlines()
                          if '=' in line and not line.lstrip().startswith(('#', '!')))
        revision = properties.get('Pkg.Revision', '').strip()
        if not re.fullmatch(r'[0-9]+(?:\.[0-9]+)*', revision):
            continue
        if slot.name != 'latest' and revision != slot.name:
            continue
        data = path.read_bytes()
        launcher = b'ANDROID_CLI_DOWNLOAD_URL' in data and b'ANDROID_CLI_LAUNCHER_VERSION' in data
        embedded = re.search(rb'version=([0-9]+(?:\.[0-9]+)+)\n', data) if launcher else None
        return {'path': path, 'sdk': sdk, 'package_revision': revision,
                'sha256': hashlib.sha256(data).hexdigest(), 'launcher': launcher,
                'launcher_version': embedded[1].decode() if embedded else 'unknown'}
    return None


def unchanged(candidate):
    path, sdk = candidate['path'], candidate['sdk']
    safe(path, sdk)
    if not path.is_file() or not os.access(path, os.X_OK) or identity(path) != candidate['sha256']:
        raise CliError('Android CLI executable changed during approval/verification; rerun --plan')


def runtime_env(env, sdk, executable):
    """Do not forward CLI download/user-home overrides or unrelated agent variables."""
    result = {key: env[key] for key in ('HOME', 'JAVA_HOME', 'LANG', 'LC_ALL', 'TERM') if key in env}
    bins = [str(Path(executable).parent)]
    if env.get('JAVA_HOME'):
        bins.append(str(Path(env['JAVA_HOME']) / 'bin'))
    result.update(PATH=os.pathsep.join([*bins, '/usr/bin', '/bin']),
                  ANDROID_HOME=str(sdk), ANDROID_SDK_ROOT=str(sdk))
    return result


def stop_group(process):
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass
    process.wait(timeout=2)


def run_command(args, capture=True, env=None, timeout=120, label='Android CLI'):
    """Bound execution time/output, retain live terminal for installation terms."""
    print(label + ':', ' '.join(repr(str(a)) for a in args), flush=True)
    process = subprocess.Popen(list(map(str, args)), env=env, start_new_session=True,
                               stdout=subprocess.PIPE if capture else None,
                               stderr=subprocess.PIPE if capture else None)
    output, errors = bytearray(), bytearray()
    failure = None
    try:
        deadline = time.monotonic() + timeout
        # Selector setup belongs inside the post-spawn lifetime boundary too.
        # Every error must stop/reap the vendor before an installer can roll back.
        with selectors.DefaultSelector() as selector:
            if capture:
                selector.register(process.stdout, selectors.EVENT_READ, output)
                selector.register(process.stderr, selectors.EVENT_READ, errors)
                while selector.get_map():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise subprocess.TimeoutExpired(args, timeout)
                    for key, _ in selector.select(min(remaining, 0.1)):
                        buffer = key.data
                        data = os.read(key.fd, min(65536, 1048577 - len(buffer)))
                        if not data:
                            selector.unregister(key.fileobj)
                            continue
                        buffer.extend(data)
                        if len(buffer) > 1048576:
                            raise CliError('Vendor output exceeds supported bound')
            process.wait(timeout=max(0.001, deadline - time.monotonic()))
    except BaseException as exc:
        failure = exc
        try:
            stop_group(process)
        except BaseException as cleanup:
            code = 130 if isinstance(exc, KeyboardInterrupt) else 124 if isinstance(exc, subprocess.TimeoutExpired) else getattr(exc, 'code', 1)
            failure = ProcessCleanupError(
                f'Vendor cleanup unconfirmed ({type(cleanup).__name__}); manual recovery required. '
                'Do not start another installer or restore backups until its process group is stopped.', code)
            failure.__cause__ = cleanup
    finally:
        if capture:
            for stream in (process.stdout, process.stderr):
                try:
                    stream.close()
                except BaseException as close_error:
                    # Never replace an unconfirmed-cleanup signal with an ordinary
                    # close error that could let the installer start rollback.
                    if failure is None:
                        failure = close_error
    if isinstance(failure, ProcessCleanupError):
        # Reporting must not replace the manual-recovery classification.
        raise failure
    text = output.decode('utf-8', errors='replace')
    diagnostic = errors.decode('utf-8', errors='replace')
    if capture:
        if diagnostic:
            print(diagnostic, file=sys.stderr, end='' if diagnostic.endswith('\n') else '\n')
        if text:
            print(text, end='' if text.endswith('\n') else '\n')
    if failure is not None and not isinstance(failure, subprocess.TimeoutExpired):
        raise failure
    if failure is not None:
        raise CliError('Android CLI timed out; inspect partial cache/package state', 124)
    if process.returncode:
        code = process.returncode if process.returncode > 0 else 128 - process.returncode
        raise CliError(f'Android CLI failed with exit {process.returncode}; inspect visible diagnostics', code)
    return text


def revision_key(value):
    """Numeric package revisions only; preserve all nonzero components."""
    if not isinstance(value, str) or len(value) > 128 or not re.fullmatch(r'(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*))*', value):
        return None
    parts = [int(part) for part in value.split('.')]
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return tuple(parts)


def revisions_equal(left, right):
    left_key, right_key = revision_key(left), revision_key(right)
    return left_key is not None and right_key is not None and left_key == right_key


def parse_listing(output):
    """Return installed, available and suggested updates as distinct evidence.

    CLI 1.1 may report an unknown installed revision (None). An arrow target
    never fills that unknown or becomes an available revision implicitly.
    """
    installed, available, updates = {}, {}, {}
    section, seen = None, set()
    output = re.sub(r'\x1b\[[0-9;]*m', '', output).replace('\r\n', '\n')
    if any(ord(char) < 32 and char not in '\t\n' or 127 <= ord(char) <= 159
           or char in '\u2028\u2029' for char in output):
        raise CliError('Unsupported Android CLI listing format: control characters')
    if not output.endswith('\n'):
        raise CliError('Unsupported/truncated Android CLI listing format: missing line terminator')
    for raw in output.split('\n'):
        line = raw.strip(' \t')
        if '|' in line:
            raise CliError('Unsupported Android CLI listing format: pipe table')
        if not line:
            continue
        if line in ('Installed packages:', 'Available packages:'):
            if line in seen or line == 'Installed packages:' and seen or \
                    line == 'Available packages:' and 'Installed packages:' not in seen:
                raise CliError('Duplicate or out-of-order Android CLI listing section')
            seen.add(line)
            section = line
            continue
        match = re.fullmatch(r'([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*)[ \t]+'
                             r'(unknown|[0-9]+(?:\.[0-9]+)*)'
                             r'(?:[ \t]+->[ \t]+([0-9]+(?:\.[0-9]+)*))?[ \t]+(\S(?:.*\S)?)', line)
        if not section or not match:
            raise CliError('Unsupported Android CLI listing format; use explicit legacy fallback or review output')
        package, revision, target, description = match.groups()
        first_word = description.split()[0]
        if any(part in ('.', '..') for part in package.split('/')) or '->' in description \
                or first_word.lower() == 'unknown' or first_word[0].isdigit() \
                or re.fullmatch(r'(?:rc|preview|alpha|beta)(?:[0-9].*|[-.].*|$)',
                                first_word.strip('()[],').lstrip('-'), re.I) \
                or revision != 'unknown' and revision_key(revision) is None \
                or target is not None and revision_key(target) is None:
            raise CliError('Unsafe or ambiguous Android CLI listing row')
        if section == 'Installed packages:':
            if package in installed:
                raise CliError('Duplicate Android CLI installed package')
            installed[package] = None if revision == 'unknown' else revision
            if target is not None:
                updates[package] = target
        else:
            if revision == 'unknown' or target is not None:
                raise CliError('Unsupported Android CLI available revision')
            available.setdefault(package, set()).add(revision)
    if 'Installed packages:' not in seen:
        raise CliError('Unsupported Android CLI listing format: installed section missing')
    return installed, available, updates


def verify(candidate, sdk, run, approve, all_versions=False):
    if not candidate:
        raise CliError('No safe SDK-local Android CLI candidate; explicitly review legacy fallback')
    if Path(sdk) != candidate['sdk']:
        raise CliError('Android CLI candidate belongs to another SDK root')
    message = (f"Execute Android CLI {candidate['path']} SHA-256={candidate['sha256']} with --sdk={sdk} "
               'for version/help/root and SDK inventory? May access network, download launcher payload, '
               'write ~/.android/cache and read ~/.androidrc; no SDK package changes. '
               'Launcher/application versions differ; review publisher/download effects first')
    if not approve(message):
        raise CliError('Operator declined Android CLI runtime verification', 20)
    command = [str(candidate['path']), f'--sdk={sdk}']

    def execute(tail):
        unchanged(candidate)
        return run([*command, *tail], capture=True)

    version_text = execute(['-V']).strip()
    version = re.fullmatch(r'(?:(?:Android CLI|android-cli)(?: version)?\s+)?([0-9]+(?:\.[0-9]+){1,3}(?:[-+][0-9A-Za-z.-]+)?)', version_text)
    if not version:
        raise CliError('Unsupported Android CLI product version output')
    help_text = execute(['--help'])
    if '--sdk' not in help_text or not all(re.search(r'^\s*' + name + r'\s', help_text, re.M) for name in ('info', 'sdk')):
        raise CliError('Required Android CLI info/sdk commands unsupported')
    if execute(['info', 'sdk']).strip() != str(sdk):
        raise CliError('Android CLI reported a different SDK root; refuse package operations')
    help_text = execute(['sdk', '--help'])
    if '--ignore-outdated-xmls' not in help_text or not all(re.search(r'^\s*' + name + r'\s', help_text, re.M) for name in ('list', 'install')):
        raise CliError('Required Android CLI sdk list/install contract unsupported')
    help_text = execute(['sdk', 'install', '--help'])
    if '--no-downgrade' not in help_text or '<package>' not in help_text:
        raise CliError('Required Android CLI install revision/no-downgrade contract unsupported')
    listing = execute(['sdk', 'list', *(['--all', '--all-versions'] if all_versions else [])])
    installed, available, updates = parse_listing(listing)
    return {'version': version[1], 'installed': installed, 'available': available,
            'updates': updates, 'candidate': candidate}


def package_id(package):
    return package.replace(';', '/')


def install_id(package):
    path = package_id(package)
    return path + ('@1' if package == 'platforms;android-36.1' else
                   '@36.0.0' if package == 'build-tools;36.0.0' else '')
