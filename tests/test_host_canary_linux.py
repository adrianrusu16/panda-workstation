"""Concrete Linux transport over mocked syscalls only; no native launch/fixture."""
import importlib.util
import contextlib
import io
from pathlib import Path
import stat
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location('linux_phase_fixture', HERE / 'host_canary_phase_fixture.py')
fixture = importlib.util.module_from_spec(spec); sys.modules[spec.name] = fixture; spec.loader.exec_module(fixture)


def load():
    spec = importlib.util.spec_from_file_location('linux_transport_unit', HERE / 'host_canary_lifecycle.py')
    api = importlib.util.module_from_spec(spec); spec.loader.exec_module(api)
    return api


class LinuxTransportTests(unittest.TestCase):
    def setUp(self):
        self.api = load()
        self.f = fixture.Fixture(); self.addCleanup(self.f.close)
        self.owner = self.f.controller()
        self.owner.state = 'starting'
        self.grant = self.f.api.BirthGrant(self.owner, 1, 'a' * 32, [{'action': 'initialize'}])
        self.owner._grant = self.grant
        self.capture = self.f.api.Capture(self.owner, self.grant)

    @contextlib.contextmanager
    def bound(self):
        api = self.api
        parent, child = Mock(), Mock()
        parent.fileno.return_value, child.fileno.return_value = 8, 9
        parent.getsockopt.return_value = api.socket.SOCK_SEQPACKET
        process = Mock(pid=900, returncode=None)
        process.stdout.fileno.return_value, process.stderr.fileno.return_value = 20, 21
        inode = {20: (8, 20, stat.S_IFIFO), 21: (8, 21, stat.S_IFIFO), 8: (2, 8, stat.S_IFSOCK), 10: (3, 300, stat.S_IFREG), 11: (2, 200, stat.S_IFREG)}
        def info(fd):
            dev, ino, mode = inode[fd]
            return SimpleNamespace(st_dev=dev, st_ino=ino, st_mode=mode)
        def wait(**kwargs): process.returncode = 0; return 0
        process.wait.side_effect = wait
        poller = Mock(); poller.poll.return_value = [(10, api.select.POLLIN)]
        with patch.object(api.LinuxTransport, 'helper_identity', return_value='held'), \
             patch.object(api.socket, 'socketpair', return_value=(parent, child)), \
             patch.object(api.subprocess, 'Popen', return_value=process), \
             patch.object(api.os, 'fstat', side_effect=info), \
             patch.object(api.os, 'read', return_value=b''), \
             patch.object(api.fcntl, 'fcntl', return_value=1), \
             patch.object(api.fcntl, 'ioctl', return_value=api.LinuxTransport.CLONE_NEWPID), \
             patch.object(api.LinuxTransport, 'pidfs_type', return_value=0x50494446), \
             patch('builtins.open', side_effect=lambda *a, **kw: io.StringIO('Pid:\t100\n')), \
             patch.object(api.select, 'poll', return_value=poller), \
             patch.object(api.select, 'select', side_effect=lambda streams, *a: (streams, [], [])):
            t = api.LinuxTransport.spawn(4, 'b'*64, ['/bin/python3'], 'a'*32, 5, 6, output_budget=self.capture)
            t.rights.extend((10, 11)); t.bind_birth(100, 200)
            yield t, process, parent, inode, poller

    def test_closed_reverification_never_waits_reaps_or_signals_again(self):
        with self.bound() as (t, process, channel, inode, poller):
            t.stopping = True
            witness = t.wait_closed()
            for _ in range(3): t.check_closed()
            self.assertEqual(witness['stdout_sha256'], self.capture.witness()['stdout_sha256'])
            process.wait.assert_called_once_with(timeout=2)
            channel.send.assert_not_called()
            process.kill.assert_not_called(); process.terminate.assert_not_called()
            with self.assertRaises(ValueError): t.wait_closed()
            self.assertEqual(process.wait.call_count, 1)

    def test_closed_process_channel_rights_output_and_poll_drift_refuse(self):
        for fault in ('process', 'channel', 'rights', 'namespace', 'dead-pidfd', 'output', 'hash', 'status', 'poll-empty', 'poll-error'):
            with self.subTest(fault=fault), self.bound() as (t, process, channel, inode, poller):
                t.stopping = True; t.wait_closed()
                if fault == 'process': t.process = Mock(pid=900, returncode=0)
                elif fault == 'channel': t.channel = Mock()
                elif fault == 'rights': t.rights.append(99)
                elif fault == 'namespace': inode[11] = (2, 201, stat.S_IFREG)
                elif fault == 'dead-pidfd': inode[10] = (3, 301, stat.S_IFREG)
                elif fault == 'output': t.output.extend(b'foreign')
                elif fault == 'hash': t.closed_proof['stdout_sha256'] = '0'*64
                elif fault == 'status': process.returncode = 7
                elif fault == 'poll-empty': poller.poll.return_value = []
                else: poller.poll.return_value = [(10, self.api.select.POLLIN | self.api.select.POLLERR)]
                with self.assertRaises(ValueError): t.check_closed()
                self.assertEqual(process.wait.call_count, 1)

    def test_closure_drains_and_charges_late_output_before_acceptance(self):
        with self.bound() as (t, process, channel, inode, poller):
            t.stopping = True
            self.owner.output['stderr'] = 1048576
            with patch.object(self.api.os, 'read', side_effect=lambda fd, n: b'x' if fd==21 else b''):
                with self.assertRaises(ValueError): t.wait_closed()
            self.assertEqual(t.errors, b'x')
            self.assertEqual(self.owner.output['stderr'], 1048577)
            self.assertIsNone(t.closed_proof)
            self.assertTrue(self.f.s.preserved)

    def test_output_pipe_descriptor_and_identity_replacement_refuse_before_read(self):
        for fault in ("number", "inode", "foreign-stream", "missing-stream", "paired-buffer", "missing-capture"):
            self.owner.state = "starting"
            with self.subTest(fault=fault), self.bound() as (t, process, channel, inode, poller):
                if fault == "number": process.stdout.fileno.return_value = 999
                elif fault == "inode": inode[20] = (8, 999, stat.S_IFIFO)
                elif fault == "foreign-stream": t.streams[Mock()] = bytearray()
                elif fault == "paired-buffer":
                    t.output = bytearray(); t.streams[process.stdout] = t.output
                elif fault == "missing-capture": t.output_budget = None
                else: del t.streams[process.stdout]
                with patch.object(self.api.os, "read", return_value=b"") as read:
                    with self.assertRaises(ValueError): t.capture(list(t.streams))
                read.assert_not_called()

    def test_pidfs_fstatfs_abi_magic_error_and_unsupported_word_size(self):
        api = self.api; t = api.LinuxTransport(); t.pidfd = 42
        libc = Mock()
        def fstatfs(fd, pointer):
            self.assertEqual(fd, 42)
            api.ctypes.c_long.from_buffer(pointer._obj).value = 0x50494446
            return 0
        libc.fstatfs.side_effect = fstatfs
        with patch.object(api.ctypes, "CDLL", return_value=libc) as load_libc:
            self.assertEqual(t.pidfs_type(), 0x50494446)
            libc.fstatfs.side_effect = lambda *args: -1
            with self.assertRaises(OSError): t.pidfs_type()
            with patch.object(api.struct, "calcsize", return_value=4):
                with self.assertRaises(ValueError): t.pidfs_type()
            self.assertEqual(load_libc.call_count, 2)

    def test_unknown_pidfd_filesystem_is_refused_before_original_pin(self):
        with self.bound() as (t, *rest):
            with patch.object(self.api.LinuxTransport, 'pidfs_type', return_value=0x09041934):
                with self.assertRaisesRegex(ValueError, 'pidfs'): t.check()

    def test_spawn_retains_partial_handles_before_socket_configuration(self):
        api = self.api
        for failure in ('identity', 'socketpair', 'setsockopt', 'nonblocking', 'popen', 'post-identity', 'child-close'):
            with self.subTest(failure=failure):
                parent, child = Mock(), Mock()
                parent.fileno.return_value, child.fileno.return_value = 8, 9
                process = Mock(pid=900, returncode=None)
                process.stdout.fileno.return_value, process.stderr.fileno.return_value = 20, 21
                identity = OSError('identity') if failure == 'identity' else None
                identities = [identity or 'held', OSError('post identity') if failure == 'post-identity' else 'held']
                if failure == 'setsockopt': parent.setsockopt.side_effect = OSError('setsockopt')
                if failure == 'nonblocking': parent.setblocking.side_effect = OSError('nonblocking')
                if failure == 'child-close': child.close.side_effect = OSError('close')
                with patch.object(api.LinuxTransport, 'helper_identity', side_effect=identities), \
                     patch.object(api.socket, 'socketpair', side_effect=OSError('socketpair') if failure == 'socketpair' else None,
                                  return_value=(parent, child)), \
                     patch.object(api.subprocess, 'Popen', side_effect=OSError('popen') if failure == 'popen' else None,
                                  return_value=process), \
                     patch.object(api.os, 'fstat', side_effect=lambda fd: SimpleNamespace(st_dev=2, st_ino=fd, st_mode=stat.S_IFSOCK if fd==8 else stat.S_IFIFO)), \
                     patch.object(api.fcntl, 'fcntl', return_value=1):
                    parent.getsockopt.return_value = api.socket.SOCK_SEQPACKET
                    with self.assertRaises(OSError) as caught:
                        api.LinuxTransport.spawn(4, 'b' * 64, ['/bin/python3'], 'a' * 32, 5, 6)
                transport = getattr(caught.exception, 'transport', None)
                self.assertIsNotNone(transport, 'first acquisition failure lost its transport')
                if failure not in ('identity', 'socketpair'):
                    self.assertIs(transport.channel, parent)
                    self.assertIs(transport.launch_child, child)
                if failure in ('post-identity', 'child-close'):
                    self.assertIs(transport.process, process)
                process.kill.assert_not_called(); process.terminate.assert_not_called()

    def test_capture_uses_aggregate_remaining_plus_one_and_preserves_overflow(self):
        api = self.api
        stream, buffer = Mock(), bytearray()
        transport = api.LinuxTransport()
        transport._retained_streams = lambda: None  # isolate capture accounting
        transport.streams = {stream: buffer}
        transport.stream_roles = {stream: 'stdout'}
        transport.output_budget = self.capture
        self.owner.output['stdout'] = 1048575
        with patch.object(api.os, 'read', return_value=b'xy') as read:
            with self.assertRaises(ValueError): transport.capture([stream])
        self.assertEqual(read.call_args.args[1], 2)
        self.assertEqual(buffer, b'xy')
        self.assertEqual(self.owner.output['stdout'], 1048577)
        self.assertTrue(self.f.s.preserved)

    def test_stale_capture_refuses_before_read(self):
        transport = self.api.LinuxTransport()
        transport._retained_streams = lambda: None  # isolate stale grant accounting
        stream = Mock(); transport.streams = {stream: bytearray()}
        transport.stream_roles = {stream: 'stderr'}; transport.output_budget = self.capture
        self.owner._grant = None
        with patch.object(self.api.os, 'read') as read:
            with self.assertRaises(ValueError): transport.capture([stream])
        read.assert_not_called()

    def test_different_dead_pidfd_at_same_number_is_not_original_identity(self):
        api = self.api
        transport = api.LinuxTransport()
        transport.helper_pin, transport.helper_identity = 'held', lambda: 'held'
        transport._retained_launch = lambda: None
        transport.pidfd, transport.nsfd = 10, 11
        transport.rights = [10, 11]; transport.birth = dict(pid=100, namespace=200, pidfd=10, nsfd=11)
        transport.birth_pin = dict(transport.birth); transport.birth_handles = (10, 11)
        transport.ns_pin = (2, 200); transport.pid_pin = (3, 300, stat.S_IFREG)
        transport.stopping = True
        def info(fd):
            return SimpleNamespace(st_dev=2 if fd==11 else 3, st_ino=200 if fd==11 else 301,
                                   st_mode=stat.S_IFREG)
        with patch.object(api.os, 'fstat', side_effect=info), \
             patch.object(api.fcntl, 'ioctl', return_value=api.LinuxTransport.CLONE_NEWPID), \
             patch.object(api.fcntl, 'fcntl', return_value=1), \
             patch.object(api.LinuxTransport, 'pidfs_type', return_value=0x50494446, create=True), \
             patch('builtins.open', side_effect=lambda *a, **kw: io.StringIO('Pid:\t-1\n')):
            with self.assertRaisesRegex(ValueError, 'pidfd'): transport.check()


if __name__ == '__main__': unittest.main(verbosity=2)
