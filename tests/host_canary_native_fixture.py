"""Concrete Linux adapter protocol over entirely fake OS handles and kernel state.

No socketpair/Popen/fstat/ioctl/procfs read/namespace/fixture is real. The sole task
is the existing cooperative in-memory engine thread, never a custody witness.
"""
import array
import contextlib
import importlib.util
import io
from pathlib import Path
import queue
import stat
import struct
import sys
import time
from types import SimpleNamespace
from unittest.mock import patch

HERE = Path(__file__).parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    api = importlib.util.module_from_spec(spec); sys.modules[name] = api; spec.loader.exec_module(api)
    return api


class Bridge:
    def __init__(self, *, real_program=False):
        unit = load('native_bridge_case', HERE / 'test_host_canary_native_grant.py')
        self.case = unit.NativeGrantTests(); self.case.real_program = real_program; self.case.setUp()
        self.f, self.stack = self.case.f, contextlib.ExitStack()
        api = load('native_bridge_linux', HERE / 'host_canary_lifecycle.py')
        self.api, self.pipes, self.channels, self.fds, self.processes = api, {}, {}, {}, []
        self.next_fd = 40000
        self.waits, self.signals, self.polls, self.launches = 0, 0, 0, 0
        self.hook = lambda point, item: None
        self.stack.enter_context(patch.object(self.f.api.life, 'LinuxTransport', api.LinuxTransport))
        for owner, name, value in (
            (api.socket, 'socketpair', self.socketpair), (api.subprocess, 'Popen', self.popen),
            (api.os, 'fstat', self.fstat), (api.os, 'pread', self.f.k.read),
            (api.os, 'listxattr', lambda fd: []), (api.os, 'read', self.read),
            (api.fcntl, 'fcntl', lambda fd, operation: 1),
            (api.fcntl, 'ioctl', lambda fd, operation: api.LinuxTransport.CLONE_NEWPID),
            (api.select, 'select', self.select), (api.select, 'poll', self.poll),
            (api.LinuxTransport, 'pidfs_type', lambda transport: 0x50494446)):
            self.stack.enter_context(patch.object(owner, name, new=value))
        self.stack.enter_context(patch('builtins.open', new=self.open_fdinfo))

    def fd(self, dev, ino, mode, **extra):
        self.next_fd += 1
        self.fds[self.next_fd] = dict(st_dev=dev, st_ino=ino, st_mode=mode, **extra)
        return self.next_fd

    def socketpair(self, family, kind):
        parent = Channel(self, self.fd(7, self.next_fd, stat.S_IFSOCK))
        child = Channel(self, self.fd(7, self.next_fd, stat.S_IFSOCK))
        self.channels[child.number] = parent
        return parent, child

    def popen(self, argv, **kwargs):
        self.launches += 1
        helper = int(argv[0].rsplit('/', 1)[1]); nonce = argv[3]; root = int(argv[5])
        worker = argv[argv.index('--') + 1:]
        # The fake task retains output; only actual LinuxTransport.capture charges.
        no_charge = SimpleNamespace(charge=lambda *args: None)
        peer = self.f.__class__.__module__
        fixture = sys.modules[peer]
        transport = fixture.Transport(self.f, helper, worker, nonce, root, no_charge)
        self.f.transports.append(transport); self.f.spawn_count += 1
        parent = self.channels[int(argv[2])]
        process = Process(self, transport)
        parent.peer, parent.process = transport, process
        self.processes.append(process)
        self.hook('spawn', process)
        return process

    def fstat(self, fd):
        if fd in self.fds:
            return SimpleNamespace(**self.fds[fd])
        pin = self.f.k.snapshot(fd)
        return SimpleNamespace(st_dev=pin['dev'], st_ino=pin['ino'], st_mode=pin['mode'],
            st_uid=pin['uid'], st_gid=pin['gid'], st_nlink=pin['nlink'], st_size=pin['size'],
            st_ctime_ns=pin['ctime'], st_mtime_ns=pin['mtime'])

    def read(self, fd, bound):
        return self.pipes[fd].read(bound)

    def select(self, readers, writes, errors, timeout):
        end = time.monotonic() + timeout
        while True:
            ready = [item for item in readers if item.ready()]
            if ready: return ready, [], []
            channels = [item for item in readers if isinstance(item, Channel)]
            if not channels:
                return [], [], []
            left = end - time.monotonic()
            if left <= 0: return [], [], []
            channel = channels[0]
            try: channel.pending = channel.peer.events.get(timeout=min(left, 0.05))
            except queue.Empty: pass

    def poll(self):
        bridge = self
        class Poll:
            def register(self, fd, events): self.fd = fd
            def poll(self, timeout):
                bridge.polls += 1
                process = next(p for p in bridge.processes if p.pidfd == self.fd)
                return [(self.fd, bridge.api.select.POLLIN)] if process.returncode == 0 else []
        return Poll()

    def open_fdinfo(self, path, **kwargs):
        if not path.startswith('/proc/self/fdinfo/'):
            raise AssertionError('unmocked open '+str(path))
        fd = int(path.rsplit('/', 1)[1])
        process = next(p for p in self.processes if p.pidfd == fd)
        pid = '-1' if process.returncode == 0 else str(100 + process.peer.epoch)
        return io.StringIO('Pid:\t'+pid+'\n')

    def controller(self):
        return self.f.s.linux_phases(self.case.grant())

    def close(self):
        self.stack.close()
        self.case.doCleanups()


class Channel:
    def __init__(self, bridge, number):
        self.bridge, self.number, self.pending = bridge, number, None
        self.peer = self.process = None
        self.closed = False
    def fileno(self): return self.number
    def setsockopt(self, *args): pass
    def getsockopt(self, *args): return self.bridge.api.socket.SOCK_SEQPACKET
    def setblocking(self, value): assert value is False
    def close(self): self.closed = True
    def ready(self): return self.pending is not None or self.peer is not None and not self.peer.events.empty()
    def recvmsg(self, *args):
        packet = self.pending if self.pending is not None else self.peer.events.get_nowait()
        self.pending = None
        api = self.bridge.api
        credentials = struct.pack('3i', self.process.pid, self.bridge.f.k.uid, self.bridge.f.k.gid)
        ancillary = [(api.socket.SOL_SOCKET, api.socket.SCM_CREDENTIALS, credentials)]
        if packet.startswith('BIRTH '):
            self.peer.bind_birth(100+self.peer.epoch, 500+self.peer.epoch)
            ancillary.append((api.socket.SOL_SOCKET, api.socket.SCM_RIGHTS,
                              array.array('i',[self.process.pidfd,self.process.nsfd]).tobytes()))
        self.bridge.hook('receive', self.process)
        return packet.encode('ascii'), ancillary, 0, None
    def send(self, raw, flags):
        self.peer.send(raw.decode('ascii'))
        return len(raw)


class Pipe:
    def __init__(self, bridge, peer, role):
        self.peer, self.role, self.offset = peer, role, 0
        self.number = bridge.fd(8, bridge.next_fd, stat.S_IFIFO)
        bridge.pipes[self.number] = self
    def fileno(self): return self.number
    def data(self): return self.peer.stdout if self.role=='stdout' else self.peer.stderr
    def ready(self):
        return len(self.data()) > self.offset or self.peer.closed or self.peer.thread is not None and not self.peer.thread.is_alive()
    def read(self, bound):
        raw = bytes(self.data()[self.offset:self.offset+bound]); self.offset += len(raw); return raw


class Process:
    def __init__(self, bridge, peer):
        self.bridge, self.peer, self.returncode = bridge, peer, None
        self.pid = 900 + peer.epoch
        self.pidfd = bridge.fd(9, 1000+peer.epoch, stat.S_IFREG)
        self.nsfd = bridge.fd(10, 500+peer.epoch, stat.S_IFREG)
        self.stdout, self.stderr = Pipe(bridge,peer,'stdout'), Pipe(bridge,peer,'stderr')
    def wait(self, timeout):
        self.bridge.waits += 1
        if not self.peer.closed: raise ValueError('fake helper not closed')
        if self.peer.thread is not None:
            self.peer.thread.join(timeout)
            if self.peer.thread.is_alive(): raise ValueError('fake task still active')
        self.returncode = 0
        return 0
    def kill(self): self.bridge.signals += 1; raise AssertionError('unexpected process signal')
    terminate = kill
