"""Fake transport/kernel only. Never execute the native custodian."""
import importlib.util
import array
import io
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

MODULE = Path(__file__).with_name('host_canary_lifecycle.py')
SESSION = 'a' * 32


def load():
    spec = importlib.util.spec_from_file_location('canary_lifecycle_test', MODULE)
    api = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(api)
    return api


class Ledger:
    def __init__(self):
        self.events = []
        self.fail = None
    def append(self, event):
        if event['kind'] == self.fail:
            raise OSError('injected durability failure')
        self.events.append(event)


class Transport:
    def __init__(self):
        self.packets = [f'BIRTH {SESSION} 100 200 1 2',
                        f'TASK {SESSION} 1 BIRTH 2 1',
                        f'TASK {SESSION} 2 BIRTH 3 2',
                        f'TASK {SESSION} 3 EXIT 2 0',
                        f'TASK {SESSION} 4 EXIT 3 0',
                        f'DONE {SESSION} 0', f'CLOSED {SESSION}']
        self.sent, self.bound = [], False
        self.wait_code = 0
        self.failed_witness = False
    def receive(self, timeout):
        if not self.packets:
            raise TimeoutError('no closure evidence')
        return self.packets.pop(0)
    def bind_birth(self, pid, namespace):
        if self.bound:
            raise ValueError('duplicate birth')
        self.bound = True
        return {'pid': pid, 'namespace': namespace, 'pidfd': 10, 'nsfd': 11}
    def check(self):
        if self.failed_witness:
            raise OSError('lost retained namespace descriptor')
    def send(self, text):
        self.sent.append(text)
    def wait_closed(self):
        self.check()
        if self.wait_code:
            raise ValueError('helper failed after closure message')
        return {'helper_status': 0, 'init_pidfd_exited': True, 'namespace_retained': True}


class Kernel:
    def __init__(self):
        self.transport = Transport()
        self.pin = {'dev': 1, 'ino': 2}
    def snapshot(self, fd):
        return dict(self.pin)
    def process_transport(self, *args):
        return self.transport


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.api, self.k, self.ledger = load(), Kernel(), Ledger()
    def start(self):
        return self.api.NativeLifecycle.start(self.k, self.ledger, 4, 'b' * 64,
                                             ['/reviewed/worker'], SESSION, 5, dict(self.k.pin))
    def test_birth_is_durable_before_start_and_each_task_before_ack(self):
        scope = self.start()
        self.assertEqual(self.k.transport.sent, [])
        self.assertEqual(self.ledger.events[-1]['kind'], 'namespace-born')
        self.assertEqual(scope.run(), 0)
        self.assertEqual(len([e for e in self.ledger.events if e['kind'] == 'task']), 4)
        self.assertEqual(self.k.transport.sent, [f'START {SESSION}',
                         *[f'ACK {SESSION} {n}' for n in range(1, 5)]])
        scope.finish()
        self.assertEqual(self.k.transport.sent[-1], f'STOP {SESSION}')
        self.assertEqual(self.ledger.events[-1]['kind'], 'namespace-closed')
    def test_durability_failure_never_acknowledges_or_authorizes_teardown(self):
        for failure in ('namespace-born', 'worker-intent', 'task', 'namespace-closed'):
            with self.subTest(failure=failure):
                self.setUp()
                self.ledger.fail = failure
                with self.assertRaises((ValueError, OSError)):
                    scope = self.start()
                    scope.run()
                    scope.finish()
                sent = self.k.transport.sent
                if failure == 'namespace-born': self.assertEqual(sent, [])
                if failure == 'worker-intent': self.assertEqual(sent, [])
                if failure == 'task': self.assertEqual(sent, [f'START {SESSION}'])
    def test_unknown_task_duplicate_gap_and_wrong_session_preserve(self):
        for replacement in (f'TASK {SESSION} 1 EXIT 2 0',
                            f'TASK {SESSION} 2 BIRTH 2 1',
                            f'TASK {SESSION} 1 BIRTH 3 99',
                            f'TASK {"c" * 32} 1 BIRTH 2 1',
                            f'DONE {SESSION} 0', 'CLOSED true'):
            with self.subTest(packet=replacement):
                self.setUp()
                self.k.transport.packets[1] = replacement
                scope = self.start()
                with self.assertRaises(ValueError): scope.run()
                with self.assertRaises(ValueError): scope.finish()
                self.assertNotIn(f'STOP {SESSION}', self.k.transport.sent)
    def test_incomplete_run_root_drift_lost_namespace_and_failed_helper_refuse(self):
        scope = self.start()
        with self.assertRaises(ValueError): scope.finish()
        for failure in ('root', 'namespace', 'helper', 'closed'):
            with self.subTest(failure=failure):
                self.setUp()
                scope = self.start()
                scope.run()
                if failure == 'root': self.k.pin['ino'] = 77
                elif failure == 'namespace': self.k.transport.failed_witness = True
                elif failure == 'helper': self.k.transport.wait_code = 70
                else: self.k.transport.packets[-1] = 'CLOSED stale'
                with self.assertRaises((ValueError, OSError)): scope.finish()
                self.assertFalse(any(e['kind'] == 'namespace-closed' for e in self.ledger.events))

    def test_concrete_transport_authenticates_sender_and_exact_birth_descriptors(self):
        api = self.api
        for fault in ('none', 'peer', 'one-fd', 'truncated', 'duplicate-credential', 'unexpected-before-rights'):
            with self.subTest(fault=fault):
                transport = api.LinuxTransport()
                transport._retained_streams = lambda: None  # isolate protocol/overflow; pipe custody has its own suite
                transport.process = SimpleNamespace(pid=900, returncode=None)
                transport.channel = Mock()
                transport.streams, transport.rights, transport.birth = {}, [], None
                rights = array.array('i', [10] if fault == 'one-fd' else [10, 11]).tobytes()
                credentials = struct.pack('3i', 899 if fault == 'peer' else 900, 1000, 1000)
                ancillary = [(api.socket.SOL_SOCKET, api.socket.SCM_RIGHTS, rights),
                             (api.socket.SOL_SOCKET, api.socket.SCM_CREDENTIALS, credentials)]
                if fault == 'duplicate-credential': ancillary.append(ancillary[-1])
                if fault == 'unexpected-before-rights': ancillary.insert(0, (12345, 67890, b'unknown'))
                transport.channel.recvmsg.return_value = (f'BIRTH {SESSION} 100 200'.encode(),
                    ancillary, api.socket.MSG_CTRUNC if fault == 'truncated' else 0, None)
                with patch.object(api.select, 'select', return_value=([transport.channel], [], [])), \
                     patch.object(api.os, 'geteuid', return_value=1000), \
                     patch.object(api.os, 'getegid', return_value=1000):
                    if fault == 'none': self.assertEqual(transport.receive(1), f'BIRTH {SESSION} 100 200')
                    else:
                        with self.assertRaises(api.LifecycleError): transport.receive(1)
                self.assertEqual(transport.rights, [10] if fault == 'one-fd' else [10, 11])

    def test_concrete_retained_namespace_pidfd_and_lifetime_flags_are_rechecked(self):
        api = self.api
        transport = api.LinuxTransport()
        transport._retained_streams = lambda: None  # isolate protocol/overflow; pipe custody has its own suite
        transport.helper_pin, transport.helper_identity = 'held', lambda: 'held'
        transport.nsfd, transport.pidfd = 11, 10
        transport.ns_pin = (2, 200)
        transport.birth, transport.stopping = {'pid': 100}, False
        # This unit isolates namespace/Pid/flag checks. Concrete retained-launch
        # and pidfs identity are separately tested under fully mocked syscalls.
        transport._retained_launch = lambda: None
        transport.pidfd_identity = lambda: (3, 300, 0)
        transport.pid_pin = (3, 300, 0)
        transport.birth_handles, transport.rights = (10, 11), [10, 11]
        transport.birth_pin = dict(transport.birth)
        with patch.object(api.os, 'fstat', return_value=SimpleNamespace(st_dev=2, st_ino=200)), \
             patch.object(api.fcntl, 'ioctl', return_value=api.LinuxTransport.CLONE_NEWPID), \
             patch.object(api.fcntl, 'fcntl', return_value=api.fcntl.FD_CLOEXEC), \
             patch('builtins.open', side_effect=lambda *a, **kw: io.StringIO('Pid:\t100\n')) as opened:
            transport.check()
            self.assertEqual(opened.call_args.args[0], '/proc/self/fdinfo/10')
            with patch.object(api.fcntl, 'fcntl', return_value=0):
                with self.assertRaises(api.LifecycleError): transport.check()
            with patch.object(api.os, 'fstat', return_value=SimpleNamespace(st_dev=2, st_ino=201)):
                with self.assertRaises(api.LifecycleError): transport.check()
            with patch('builtins.open', side_effect=lambda *a, **kw: io.StringIO('Pid:\t-1\n')):
                with self.assertRaises(api.LifecycleError): transport.check()
                transport.stopping = True
                transport.check()

    def test_concrete_timeout_eintr_and_output_overflow_keep_evidence(self):
        api = self.api
        transport = api.LinuxTransport()
        transport._retained_streams = lambda: None  # isolate protocol/overflow; pipe custody has its own suite
        transport.channel, transport.streams = Mock(), {}
        with patch.object(api.time, 'monotonic', side_effect=[0, 0, 31]), \
             patch.object(api.select, 'select', side_effect=InterruptedError) as select_call:
            with self.assertRaisesRegex(api.LifecycleError, 'deadline'): transport.receive(30)
        self.assertEqual(select_call.call_count, 1)
        stream, buffer = Mock(), bytearray(b'x' * 1048576)
        transport.streams = {stream: buffer}
        with patch.object(api.os, 'read', return_value=b'!'):
            with self.assertRaisesRegex(api.LifecycleError, 'bounded'): transport.capture([stream])
        self.assertEqual(len(buffer), 1048577)

    def test_partial_spawn_failure_retains_lifecycle_and_transport(self):
        error = OSError('post-spawn helper identity failure')
        error.transport = self.k.transport
        self.k.process_transport = Mock(side_effect=error)
        with self.assertRaises(OSError) as caught: self.start()
        self.assertTrue(getattr(caught.exception, 'lifecycle', None), 'partial lifecycle not retained')
        self.assertIs(caught.exception.lifecycle.transport, self.k.transport)
        self.assertTrue(caught.exception.lifecycle.preserved)

    def test_birth_requires_received_root_identity(self):
        # The previous protocol accepted BIRTH without echoing the inherited root.
        for packet in (f'BIRTH {SESSION} 100 200', f'BIRTH {SESSION} 100 200 1 99'):
            with self.subTest(packet=packet):
                self.k.transport.packets[0] = packet
                with self.assertRaises(ValueError): self.start()
                self.assertEqual(self.k.transport.sent, [])

    def test_reused_numeric_task_pid_cannot_replace_original_worker_status(self):
        for final, accepted in ((0, False), (7, True)):
            with self.subTest(final=final):
                self.setUp()
                self.k.transport.packets = [f'BIRTH {SESSION} 100 200 1 2',
                    f'TASK {SESSION} 1 BIRTH 2 1', f'TASK {SESSION} 2 BIRTH 3 2',
                    f'TASK {SESSION} 3 EXIT 2 7', f'TASK {SESSION} 4 BIRTH 2 3',
                    f'TASK {SESSION} 5 EXIT 2 0', f'TASK {SESSION} 6 EXIT 3 0',
                    f'DONE {SESSION} {final}']
                scope = self.start()
                if accepted: self.assertEqual(scope.run(), 7)
                else:
                    with self.assertRaises(ValueError): scope.run()


class NativeMockTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('cc'), 'C compiler unavailable; native mock regression unexecuted')
    def test_deadline_and_child_first_wait_order_with_only_mocked_native_syscalls(self):
        source = Path(__file__).parent / 'native/host_canary/custodian.c'
        if not source.is_file(): source = Path(__file__).with_name('custodian.c')
        harness = r'''
#define _GNU_SOURCE
#include <errno.h>
#include <poll.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
static int fake_clock(clockid_t, struct timespec *);
static int fake_poll(struct pollfd *, nfds_t, int);
static int fake_waitid(idtype_t, id_t, siginfo_t *, int);
static pid_t fake_waitpid(pid_t, int *, int);
#define clock_gettime fake_clock
#define poll fake_poll
#define waitid fake_waitid
#define waitpid fake_waitpid
#define main unused_custodian_main
#include "source.c"
#undef main
#undef clock_gettime
#undef poll
#undef waitid
#undef waitpid
static long elapsed;
static int polls, waits, clocks, phase, unregistered_wait;
static int fake_clock(clockid_t id, struct timespec *value) {
    (void)id; ++clocks; value->tv_sec = elapsed; value->tv_nsec = 0; return 0;
}
static int fake_poll(struct pollfd *fds, nfds_t count, int timeout) {
    (void)fds; (void)count; (void)timeout;
    ++polls; elapsed = 31; errno = polls == 1 ? EINTR : EIO; return -1;
}
static int fake_waitid(idtype_t kind, id_t id, siginfo_t *info, int options) {
    (void)kind; (void)id; (void)info; (void)options;
    ++waits; elapsed = 31; errno = waits == 1 ? EINTR : EIO; return -1;
}
static pid_t fake_waitpid(pid_t pid, int *status, int options) {
    (void)options;
    *status = (SIGSTOP << 8) | 0x7f;
    if (pid == -1) { ++unregistered_wait; return 3; } /* child stop wins race */
    if (!phase && pid == 2) return 2; /* creator's fork event */
    if (phase && pid == 3) return 3;
    return 0;
}
int main(void) {
    control = 100; child_pidfd = 101; child_pid = 102;
    int result = request("START", "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa");
    if (result != -1 || polls != 1 || clocks < 2) return 1;
    elapsed = 0; clocks = 0;
    result = wait_contained();
    if (result != -1 || waits != 1 || clocks < 2) return 2;
    tasks[0] = (struct task){.pid=2, .alive=1};
    int status;
    if (wait_known(&status) != 2 || unregistered_wait) return 3;
    phase = 1; tasks[1] = (struct task){.pid=3, .alive=1};
    if (wait_known(&status) != 3 || unregistered_wait) return 4;
    puts("mock deadlines/order passed; production custodian main never called");
    return 0;
}
'''
        with tempfile.TemporaryDirectory(prefix='panda-native-mock-build-') as directory:
            root = Path(directory)
            (root / 'source.c').write_bytes(source.read_bytes())
            (root / 'harness.c').write_text(harness)
            # Compile only mocked entry points into a separate disposable test.
            # No custodian, clone, namespace, worker, signal or teardown runs.
            built = subprocess.run([shutil.which('cc'), '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                                    str(root / 'harness.c'), '-o', str(root / 'mock-check')],
                                   capture_output=True, text=True, timeout=30)
            self.assertEqual(built.returncode, 0, built.stderr)
            checked = subprocess.run([str(root / 'mock-check')], capture_output=True, text=True, timeout=5)
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)


if __name__ == '__main__':
    unittest.main()
