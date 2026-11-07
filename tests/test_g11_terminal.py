"""Real disposable subprocess coverage for G11's test-only terminal lifecycle."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]

# This outer test oracle owns any children left by a broken runner. It never
# signals a PID without first establishing direct-child ownership, and is not
# part of the implementation under test.
ORACLE = r'''
import ctypes, json, os, select, signal, subprocess, sys, time
from pathlib import Path
signal.signal(signal.SIGCHLD, signal.SIG_DFL)
libc = ctypes.CDLL(None, use_errno=True)
if libc.prctl(36, 1, 0, 0, 0) != 0:
    raise OSError(ctypes.get_errno(), 'test subreaper unavailable')

def no_children():
    try:
        os.waitpid(-1, os.WNOHANG)
    except ChildProcessError:
        return True
    return False

def finish_owned_children():
    deadline = time.monotonic() + 3
    while True:
        try:
            pid, status = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            return
        if pid:
            continue
        children = Path(f'/proc/self/task/{os.getpid()}/children').read_text().split()
        for raw in children:
            pid = int(raw)
            state = os.waitid(os.P_PID, pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
            if state is not None:
                os.waitpid(pid, 0)
                continue
            fd = os.pidfd_open(pid)
            try:
                signal.pidfd_send_signal(fd, signal.SIGKILL)
                if not select.select([fd], [], [], max(0, deadline-time.monotonic()))[0]:
                    raise RuntimeError('synthetic child did not terminate')
                os.waitpid(pid, 0)
            finally:
                os.close(fd)
        if time.monotonic() >= deadline:
            raise RuntimeError('synthetic cleanup deadline exceeded')
'''

ORPHAN = r'''
import os, signal, sys
from pathlib import Path
reader, writer = os.pipe()
pid = os.fork()
if pid == 0:
    os.close(reader)
    os.setsid()
    Path(sys.argv[1]).write_text('owned descendant')
    os.close(0); os.close(1); os.close(2)
    os.write(writer, b'1'); os.close(writer)
    signal.pause()
else:
    os.close(writer)
    assert os.read(reader, 1) == b'1'
    os.close(reader)
    print('OUT', flush=True)
    print('ERR', file=sys.stderr, flush=True)
    if len(sys.argv) > 2:
        signal.pause()
'''


class G11TerminalLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='panda-g11-lifecycle-'))
        self.safe = False
        self.addCleanup(self.cleanup_fixture)

    def cleanup_fixture(self):
        if not self.safe:
            raise RuntimeError(f'synthetic cleanup not proved; retained {self.root}')
        shutil.rmtree(self.root)

    def run_case(self, body):
        receipt = self.root / 'oracle-cleanup.json'
        program = ORACLE + '\n'
        program += f'sys.path.insert(0, {str(ROOT / "tests")!r})\n'
        program += f'root = Path({str(self.root)!r})\n'
        program += f'orphan = {ORPHAN!r}\n'
        program += 'try:\n    import g11_terminal as api\n'
        program += textwrap.indent(textwrap.dedent(body), '    ')
        program += '\nfinally:\n    finish_owned_children()\n'
        program += f'    Path({str(receipt)!r}).write_text(\'{{"complete": true}}\')\n'
        env = {**os.environ, 'HOME': str(self.root), 'PYTHONDONTWRITEBYTECODE': '1',
               'DBUS_SESSION_BUS_ADDRESS': 'disabled-for-offline-test',
               'DBUS_SYSTEM_BUS_ADDRESS': 'disabled-for-offline-test'}
        for key in ('DISPLAY', 'WAYLAND_DISPLAY', 'PYTHONPATH', 'PYTHONHOME'):
            env.pop(key, None)
        for key in ('CONFIG', 'CACHE', 'DATA', 'STATE'):
            env['XDG_' + key + '_HOME'] = str(self.root / key.lower())
        result = subprocess.run([sys.executable, '-I', '-S', '-B', '-c', program],
                                env=env, capture_output=True, text=True, timeout=20)
        self.safe = receipt.exists() and json.loads(receipt.read_text()) == {'complete': True}
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(self.safe)
        return json.loads(result.stdout)

    def test_normal_child_is_reaped_and_text_output_is_preserved(self):
        result = self.run_case('''
            result = api.run_terminal([sys.executable, '-S', '-B', '-c',
                "import sys; sys.stdout.buffer.write(bytes([111,107,13,10]))"], '',
                cwd=root, env=os.environ, timeout=2, cleanup_timeout=1)
            assert (result.returncode, result.stdout, result.stderr) == (0, 'ok\\n', '')
            assert result.cleanup_complete and no_children()
            print(json.dumps({'returncode': result.returncode, 'stdout': result.stdout}))
        ''')
        self.assertEqual(result, {'returncode': 0, 'stdout': 'ok\n'})

    def test_failed_child_retains_its_status_and_stderr(self):
        result = self.run_case('''
            result = api.run_terminal([sys.executable, '-S', '-B', '-c',
                "import sys; print('bad', file=sys.stderr); sys.exit(7)"], '',
                cwd=root, env=os.environ, timeout=2, cleanup_timeout=1)
            assert result.cleanup_complete and no_children()
            print(json.dumps({'returncode': result.returncode, 'stderr': result.stderr}))
        ''')
        self.assertEqual(result, {'returncode': 7, 'stderr': 'bad\n'})

    def test_timeout_retains_original_partial_bytes_after_cleanup(self):
        result = self.run_case('''
            command = [sys.executable, '-S', '-B', '-c',
                "import signal,sys; print('OUT',flush=True); print('ERR',file=sys.stderr,flush=True); signal.pause()"]
            try:
                api.run_terminal(command, '', cwd=root, env=os.environ,
                                 timeout=1, cleanup_timeout=1)
                raise AssertionError('timeout was swallowed')
            except subprocess.TimeoutExpired as error:
                assert error.timeout == 1 and error.output == b'OUT\\n' and error.stderr == b'ERR\\n'
                assert error.cleanup_complete and no_children()
                print(json.dumps({'timeout': error.timeout, 'clean': error.cleanup_complete}))
        ''')
        self.assertEqual(result, {'timeout': 1, 'clean': True})

    def test_detached_descendant_is_reaped_before_resource_removal(self):
        result = self.run_case('''
            resource = root/'resource'; resource.mkdir()
            result = api.run_terminal([sys.executable, '-S', '-B', '-c', orphan,
                str(resource/'child')], '', cwd=root, env=os.environ, timeout=2, cleanup_timeout=1)
            assert result.returncode == 0 and result.cleanup_complete and no_children()
            assert (resource/'child').read_text() == 'owned descendant'
            assert result.descendants_reaped >= 1
            import shutil
            shutil.rmtree(resource)
            print(json.dumps({'parent': result.returncode, 'removed_after_reaping': not resource.exists()}))
        ''')
        self.assertEqual(result, {'parent': 0, 'removed_after_reaping': True})

    def test_spawn_error_is_preserved_with_safe_cleanup(self):
        result = self.run_case('''
            missing = str(root/'missing-command')
            try:
                subprocess.Popen([missing])
                raise AssertionError('synthetic command unexpectedly exists')
            except FileNotFoundError as before:
                expected = (before.errno, before.strerror, before.filename, before.args, str(before))
            try:
                api.run_terminal([missing], '', cwd=root,
                                 env=os.environ, timeout=1, cleanup_timeout=1)
                raise AssertionError('spawn error was swallowed')
            except FileNotFoundError as error:
                assert error.errno == 2 and error.cleanup_complete and no_children()
                assert (error.errno, error.strerror, error.filename, error.args, str(error)) == expected
                for before in (OSError(5, 'synthetic I/O failure'),
                               OSError(18, 'synthetic rename failure', 'source', None, 'destination')):
                    report = {'version': 1, 'command': [missing], 'returncode': None,
                              'stdout': '', 'stderr': '',
                              'error': {'kind': 'os', 'args': before.args,
                                        'filename': before.filename, 'filename2': before.filename2},
                              'cleanup': {'complete': True, 'errors': [], 'reaped': []}}
                    try:
                        api._result([missing], report)
                        raise AssertionError('OS error was swallowed')
                    except OSError as rebuilt:
                        assert rebuilt.args == before.args and str(rebuilt) == str(before)
                print(json.dumps({'errno': error.errno, 'clean': error.cleanup_complete}))
        ''')
        self.assertEqual(result, {'errno': 2, 'clean': True})

    def test_cleanup_failure_keeps_original_timeout_and_resources(self):
        result = self.run_case('''
            resource = root/'retained'; resource.mkdir()
            command = [sys.executable, '-S', '-B', '-c', orphan, str(resource/'child'), 'wait']
            real_signal = api.signal.pidfd_send_signal
            def denied(*args, **kwargs):
                raise PermissionError(1, 'synthetic owned-child signal refusal')
            try:
                api.signal.pidfd_send_signal = denied
                report = api._execute({'command': command, 'answers': '', 'cwd': str(root),
                                       'timeout': 1, 'cleanup_timeout': 0.2})
            finally:
                api.signal.pidfd_send_signal = real_signal
            try:
                api._result(command, report)
                raise AssertionError('unsafe cleanup was accepted')
            except api.CleanupError as error:
                assert not error.cleanup_complete and resource.exists()
                assert isinstance(error.original_error, subprocess.TimeoutExpired)
                assert error.__cause__ is error.original_error
                assert error.original_error.output == b'OUT\\n'
                assert error.original_error.stderr == b'ERR\\n'
                assert not no_children()
                print(json.dumps({'unsafe': True, 'original_timeout': True, 'retained': True}))
        ''')
        self.assertEqual(result, {'unsafe': True, 'original_timeout': True, 'retained': True})

    def test_g11_fixture_refuses_deletion_when_cleanup_is_unproved(self):
        result = self.run_case('''
            from unittest.mock import patch
            import test_panda_setup_manager as manager_tests
            case = manager_tests.G11MockedApplyTests('test_terminal_apply_still_requires_literal_uppercase_confirmation')
            case.setUp()
            retained = case.root
            try:
                failure = api.CleanupError('synthetic unproved worker cleanup')
                with patch.object(manager_tests, 'run_terminal', side_effect=failure):
                    try:
                        case.run_terminal_manager('5\\nAPPLY\\n', '--apply')
                        raise AssertionError('cleanup error was swallowed')
                    except api.CleanupError as error:
                        assert error is failure
                marker = retained/'must-not-relaunch'
                def unsafe_relaunch(*args, **kwargs):
                    marker.write_text('unexpected second command')
                    result = subprocess.CompletedProcess([], 0, '', '')
                    result.cleanup_complete = True
                    return result
                with patch.object(manager_tests, 'run_terminal', side_effect=unsafe_relaunch):
                    try:
                        case.run_terminal_manager('5\\nAPPLY\\n', '--apply')
                        raise AssertionError('unproved earlier cleanup was forgotten')
                    except api.CleanupError:
                        assert not marker.exists()
                try:
                    case._cleanup_fixture()
                    raise AssertionError('unsafe fixture was deleted')
                except api.CleanupError:
                    assert retained.exists() and case.events.read_text() == ''
                print(json.dumps({'retained': True, 'no_transaction': True}))
            finally:
                # The injected runner never spawned a process; only this oracle
                # may release the synthetic failure's retention guard.
                case._terminal_cleanup_safe = True
                assert case.doCleanups()
            assert not retained.exists() and no_children()
        ''')
        self.assertEqual(result, {'retained': True, 'no_transaction': True})

    def test_transport_failure_preserves_primary_error_when_wait_also_fails(self):
        result = self.run_case('''
            from unittest.mock import patch
            primary = OSError(5, 'synthetic transport failure')
            with patch.object(api.subprocess.Popen, 'communicate',
                    side_effect=[primary, subprocess.TimeoutExpired('worker', 5)]), \\
                 patch.object(api.subprocess.Popen, 'wait', side_effect=PermissionError(1, 'synthetic wait refusal')):
                try:
                    api.run_terminal([sys.executable, '-c', 'pass'], '', cwd=root,
                                     env=os.environ, timeout=1, cleanup_timeout=1)
                    raise AssertionError('worker cleanup failure was swallowed')
                except api.CleanupError as error:
                    assert error.original_error is primary and error.__cause__ is primary
                    assert not error.cleanup_complete
                    print(json.dumps({'primary_retained': True, 'unsafe': True}))
        ''')
        self.assertEqual(result, {'primary_retained': True, 'unsafe': True})

    def test_cleanup_wait_failure_does_not_replace_original_timeout(self):
        result = self.run_case('''
            from unittest.mock import patch
            command = [sys.executable, '-S', '-B', '-c', orphan, str(root/'child'), 'wait']
            with patch.object(api.selectors.DefaultSelector, 'select',
                              side_effect=OSError(5, 'synthetic cleanup wait failure')):
                report = api._execute({'command': command, 'answers': '', 'cwd': str(root),
                                       'timeout': 1, 'cleanup_timeout': 1})
            try:
                api._result(command, report)
                raise AssertionError('cleanup wait failure was swallowed')
            except api.CleanupError as error:
                assert not error.cleanup_complete
                assert isinstance(error.original_error, subprocess.TimeoutExpired)
                assert error.original_error.output == b'OUT\\n'
                print(json.dumps({'original_timeout': True, 'unsafe': True}))
        ''')
        self.assertEqual(result, {'original_timeout': True, 'unsafe': True})

    def test_timeout_bytes_survive_without_text_decoding(self):
        result = self.run_case('''
            command = ['synthetic-report']
            report = {'version': 1, 'command': command, 'returncode': -9,
                      'stdout': '4g==', 'stderr': '/w==',
                      'error': {'kind': 'timeout', 'timeout': 1, 'output': '4g==', 'stderr': '/w=='},
                      'cleanup': {'complete': True, 'errors': [], 'reaped': []}}
            try:
                api._result(command, report)
                raise AssertionError('timeout was swallowed')
            except subprocess.TimeoutExpired as error:
                assert error.output == bytes([226]) and error.stderr == bytes([255])
                assert error.cleanup_complete and no_children()
                print(json.dumps({'raw_bytes_preserved': True, 'clean': True}))
        ''')
        self.assertEqual(result, {'raw_bytes_preserved': True, 'clean': True})

    def test_completed_decoding_error_keeps_safe_cleanup_proof(self):
        result = self.run_case('''
            command = ['synthetic-report']
            report = {'version': 1, 'command': command, 'returncode': 0,
                      'stdout': '4g==', 'stderr': '', 'error': None,
                      'cleanup': {'complete': True, 'errors': [], 'reaped': []}}
            try:
                api._result(command, report)
                raise AssertionError('invalid text was accepted')
            except UnicodeDecodeError as error:
                assert error.object == bytes([226]) and error.cleanup_complete and no_children()
                print(json.dumps({'decoding_error': True, 'clean': True}))
        ''')
        self.assertEqual(result, {'decoding_error': True, 'clean': True})

    def test_worker_refuses_preexisting_child_without_signalling_it(self):
        result = self.run_case('''
            protected = subprocess.Popen([sys.executable, '-S', '-B', '-c',
                "import signal; print('ready',flush=True); signal.pause()"], stdout=subprocess.PIPE)
            try:
                assert select.select([protected.stdout], [], [], 2)[0]
                assert protected.stdout.readline() == b'ready\\n'
                command = [sys.executable, '-S', '-B', '-c', 'pass']
                report = api._execute({'command': command, 'answers': '', 'cwd': str(root),
                                       'timeout': 1, 'cleanup_timeout': 0.2})
                try:
                    api._result(command, report)
                    raise AssertionError('non-dedicated worker was accepted')
                except api.CleanupError as error:
                    assert not error.cleanup_complete and protected.poll() is None
                    print(json.dumps({'refused': True, 'existing_child_alive': True}))
            finally:
                protected.kill()
                protected.communicate(timeout=2)
            assert no_children()
        ''')
        self.assertEqual(result, {'refused': True, 'existing_child_alive': True})
