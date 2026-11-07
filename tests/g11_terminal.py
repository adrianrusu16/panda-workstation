"""Linux test-only PTY runner; each invocation owns an isolated subreaper.

Fish's read prompt can launch a detached completion generator. The dedicated
worker adopts that command's orphans, signals only verified unreaped children
through pidfds, and proves ECHILD before the fixture may delete its resources.
This is not a production setup or native-desktop executor.
"""
import base64
import ctypes
import io
import json
import locale
import math
import os
from pathlib import Path
import pty
import selectors
import signal
import subprocess
import sys
import time


class CleanupError(RuntimeError):
    def __init__(self, message, *, cleanup_complete=False, original_error=None, result=None):
        super().__init__(message)
        self.cleanup_complete = cleanup_complete
        self.original_error = original_error
        self.result = result


def _pack(data):
    return None if data is None else base64.b64encode(data).decode('ascii')


def _unpack(data):
    return None if data is None else base64.b64decode(data, validate=True)


def _remaining(deadline):
    return max(0, deadline - time.monotonic())


def _quiesce(deadline):
    """Called only in the dedicated, single-threaded, SIGCHLD-default worker."""
    errors, reaped = [], []
    while True:
        try:
            while True:
                pid, status = os.waitpid(-1, os.WNOHANG)
                if not pid:
                    break
                reaped.append({'pid': pid, 'status': os.waitstatus_to_exitcode(status)})
        except ChildProcessError:
            return {'complete': True, 'errors': errors, 'reaped': reaped}
        except OSError as error:
            errors.append(f'reap: {error}')
        if not _remaining(deadline):
            return {'complete': False, 'errors': errors + ['cleanup deadline exceeded'], 'reaped': reaped}
        try:
            children = Path(f'/proc/self/task/{os.getpid()}/children').read_text().split()
        except OSError as error:
            return {'complete': False, 'errors': errors + [f'own children: {error}'], 'reaped': reaped}
        with selectors.DefaultSelector() as poller:
            descriptors = []
            try:
                for value in children:
                    pid = int(value)
                    try:
                        state = os.waitid(os.P_PID, pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
                        if state is not None:
                            # The next waitpid sweep reaps exited children.
                            continue
                        # No other reaper runs here. A verified live direct
                        # child cannot have its PID reused before this open.
                        fd = os.pidfd_open(pid)
                        descriptors.append(fd)
                        poller.register(fd, selectors.EVENT_READ)
                        signal.pidfd_send_signal(fd, signal.SIGKILL)
                    except (OSError, ValueError) as error:
                        errors.append(f'owned child cleanup: {error}')
                if descriptors:
                    poller.select(_remaining(deadline))
                elif errors:
                    # One final waitpid sweep can still establish ECHILD, but
                    # errors are never erased even if all children exited.
                    try:
                        while True:
                            pid, status = os.waitpid(-1, os.WNOHANG)
                            if not pid:
                                return {'complete': False, 'errors': errors, 'reaped': reaped}
                            reaped.append({'pid': pid, 'status': os.waitstatus_to_exitcode(status)})
                    except ChildProcessError:
                        return {'complete': True, 'errors': errors, 'reaped': reaped}
            finally:
                for fd in descriptors:
                    os.close(fd)


def _execute(request):
    command = request['command']
    timeout, cleanup_timeout = request['timeout'], request['cleanup_timeout']
    master = slave = None
    process = None
    stdout = stderr = b''
    original = None
    cleanup_errors = []
    admitted = False
    try:
        if len(list(Path('/proc/self/task').iterdir())) != 1:
            raise RuntimeError('terminal worker must be single-threaded')
        try:
            os.waitid(os.P_ALL, 0, os.WEXITED | os.WNOHANG | os.WNOWAIT)
        except ChildProcessError:
            admitted = True
        else:
            raise RuntimeError('terminal worker must start without children')
        signal.signal(signal.SIGCHLD, signal.SIG_DFL)
        signal.pthread_sigmask(signal.SIG_UNBLOCK, {signal.SIGCHLD})
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
            raise OSError(ctypes.get_errno(), 'test subreaper unavailable')
        master, slave = pty.openpty()
        process = subprocess.Popen(command, cwd=request['cwd'], stdin=slave,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=True)
        answers = request['answers'].encode()
        if os.write(master, answers) != len(answers):
            raise OSError('incomplete synthetic terminal input')
        stdout, stderr = process.communicate(timeout=timeout)
    except BaseException as error:
        original = error
    # Every cleanup phase shares one deadline, including the final pipe drain.
    deadline = time.monotonic() + cleanup_timeout
    cleanup = {'complete': False, 'errors': cleanup_errors, 'reaped': []}
    try:
        if not admitted:
            raise RuntimeError('worker ownership was not established; no cleanup signals sent')
        if process is not None and process.returncode is None:
            try:
                process.kill()  # Still our unreaped Popen child, never a group.
                process.wait(timeout=_remaining(deadline))
            except (OSError, subprocess.TimeoutExpired) as error:
                cleanup_errors.append(f'direct child: {error}')
        finished = _quiesce(deadline)
        finished['errors'][:0] = cleanup_errors
        cleanup = finished
        if process is not None:
            if process.returncode is None:
                main_status = next((r['status'] for r in cleanup['reaped'] if r['pid'] == process.pid), None)
                process.returncode = main_status
            if original is not None:
                try:
                    stdout, stderr = process.communicate(timeout=_remaining(deadline))
                except (OSError, subprocess.TimeoutExpired) as error:
                    cleanup['errors'].append(f'output drain: {error}')
    except BaseException as error:
        # A failed observation cannot establish quiescence. Retain the
        # execution error separately rather than replacing it with this one.
        cleanup['complete'] = False
        cleanup['errors'].append(f'cleanup observation: {type(error).__name__}: {error}')
    finally:
        for fd in (slave, master):
            if fd is not None:
                try:
                    os.close(fd)
                except OSError as error:
                    cleanup['errors'].append(f'PTY close: {error}')
        if process is not None:
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except OSError as error:
                        cleanup['errors'].append(f'pipe close: {error}')
    error = None
    if isinstance(original, subprocess.TimeoutExpired):
        error = {'kind': 'timeout', 'timeout': original.timeout,
                 'output': _pack(original.output), 'stderr': _pack(original.stderr)}
    elif isinstance(original, OSError):
        error = {'kind': 'os', 'args': original.args,
                 'filename': original.filename, 'filename2': original.filename2}
    elif original is not None:
        error = {'kind': 'error', 'type': type(original).__name__, 'message': str(original)}
    return {'version': 1, 'command': command,
            'returncode': None if process is None else process.returncode,
            'stdout': _pack(stdout), 'stderr': _pack(stderr), 'error': error, 'cleanup': cleanup}


def _text(data):
    with io.TextIOWrapper(io.BytesIO(data), encoding=locale.getpreferredencoding(False), newline=None) as stream:
        return stream.read()


def _result(command, report):
    try:
        if (type(report['version']) is not int or report['version'] != 1
                or report['command'] != command or type(report['cleanup']['complete']) is not bool
                or type(report['cleanup']['errors']) is not list
                or any(type(item) is not str for item in report['cleanup']['errors'])
                or type(report['cleanup']['reaped']) is not list):
            raise ValueError('invalid worker identity/cleanup report')
        cleanup = report['cleanup']
        result = subprocess.CompletedProcess(command, report['returncode'],
                                             _unpack(report['stdout']), _unpack(report['stderr']))
        if type(result.stdout) is not bytes or type(result.stderr) is not bytes:
            raise ValueError('worker output must contain bytes')
        error = report['error']
        original = None
        if error is not None:
            if error['kind'] == 'timeout':
                original = subprocess.TimeoutExpired(command, error['timeout'],
                    output=_unpack(error['output']), stderr=_unpack(error['stderr']))
            elif error['kind'] == 'os':
                original = OSError(*error['args'])
                if error['filename'] is not None:
                    original.filename = error['filename']
                if error['filename2'] is not None:
                    original.filename2 = error['filename2']
            elif error['kind'] == 'error':
                original = RuntimeError(error['type'] + ': ' + error['message'])
            else:
                raise ValueError('unknown execution error')
        elif type(result.returncode) is not int:
            raise ValueError('completed worker must retain its child status')
    except (KeyError, TypeError, ValueError) as error:
        raise CleanupError('invalid terminal worker report') from error
    if not cleanup['complete'] or cleanup['errors']:
        failure = CleanupError('terminal cleanup failed: ' + '; '.join(cleanup['errors']),
                               cleanup_complete=cleanup['complete'], original_error=original, result=result)
        raise failure from original
    if original is not None:
        original.cleanup_complete = True
        raise original
    # Optional text conversion must never mask an original execution failure.
    # A conversion error also cannot invalidate the established ECHILD proof.
    try:
        result.stdout = _text(result.stdout)
        result.stderr = _text(result.stderr)
    except UnicodeError as error:
        error.cleanup_complete = True
        raise
    result.cleanup_complete = True
    result.descendants_reaped = len(cleanup['reaped'])
    return result


def run_terminal(command, answers, *, cwd, env, timeout=20, cleanup_timeout=5):
    for value in (timeout, cleanup_timeout):
        if type(value) not in (int, float) or not 0 < value <= 60 or not math.isfinite(value):
            raise ValueError('bounded positive terminal timeout required')
    if len(answers.encode()) > 1024:
        raise ValueError('bounded test terminal input required')
    request = {'command': [str(arg) for arg in command], 'answers': answers, 'cwd': str(cwd),
               'timeout': timeout, 'cleanup_timeout': cleanup_timeout}
    worker_command = [sys.executable, '-I', '-S', '-B', str(Path(__file__).resolve())]
    process = subprocess.Popen(worker_command, cwd=cwd, env=env,
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               start_new_session=True)
    try:
        stdout, stderr = process.communicate(json.dumps(request).encode(),
                                              timeout=timeout + cleanup_timeout + 5)
    except BaseException as original:
        errors = []
        deadline = time.monotonic() + 5
        try:
            process.kill()  # Only the still-owned worker; never a PID/group scan.
        except OSError as error:
            errors.append(str(error))
        try:
            process.communicate(timeout=_remaining(deadline))
        except (OSError, subprocess.TimeoutExpired) as error:
            errors.append(str(error))
            try:
                process.wait(timeout=_remaining(deadline))
            except (OSError, subprocess.TimeoutExpired) as error:
                errors.append(str(error))
        finally:
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except OSError as error:
                        errors.append(str(error))
        raise CleanupError('terminal worker did not establish cleanup; ' + '; '.join(errors),
                           original_error=original) from original
    if process.returncode != 0:
        original = subprocess.CalledProcessError(process.returncode, worker_command, stdout, stderr)
        raise CleanupError('terminal worker exited without cleanup proof', original_error=original) from original
    try:
        report = json.loads(stdout)
    except (ValueError, UnicodeError) as error:
        raise CleanupError('terminal worker returned no valid cleanup proof') from error
    return _result(request['command'], report)


if __name__ == '__main__':
    print(json.dumps(_execute(json.load(sys.stdin))))
