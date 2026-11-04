"""Unexecuted Linux native-custodian binding; fake transports in offline tests.

No PATH lookup, inherited environment, PGID, JSON closure or journal replay.
Only an already trusted controller may call this API with its held descriptors.
Native code must be independently built/reviewed and its exact binary approved.
The original Host operator deliberately has no integration with these adapters.
"""
import array
import ctypes
import fcntl
import hashlib
import importlib.util
import json
import os
import re
import select
import signal
import socket
import stat
import struct
import subprocess
import sys
import time
from pathlib import Path


class LifecycleError(ValueError):
    """Retain all filesystem/process evidence. No teardown or retry grant."""


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')


class RuntimeGrant:
    """Original curated runtime FDs plus an externally reviewed manifest digest.

    This does not allocate/adopt a fixture. The caller supplies its original,
    private runtime root. Every regular file and directory is retained, without
    links, special files, procfs, foreign mounts or writable group/other access.
    Missing kernel support for the native read-only clone remains a hard gate.
    No digest read from this tree is accepted as review authority.
    """
    def __init__(self, kernel, root_fd, reviewed_digest):
        self.k, self.fd, self.objects, self.rows = kernel, root_fd, {}, []
        self.bytes, self.failed = 0, False
        if not isinstance(reviewed_digest, str) or not re.fullmatch('[0-9a-f]{64}', reviewed_digest):
            raise LifecycleError('external runtime manifest digest required')
        self.digest = reviewed_digest
        try:
            self.root_pin = kernel.snapshot(root_fd)
            if self.root_pin['mode'] != stat.S_IFDIR | 0o700:
                raise LifecycleError('original runtime root must be private')
            self._capture('', root_fd, None, None)
            if hashlib.sha256(canonical(self.rows)).hexdigest() != reviewed_digest:
                raise LifecycleError('curated runtime manifest was not approved')
            self.check()
        except BaseException as exc:
            self.failed = True
            exc.runtime_grant = self  # retain partial descriptors, never reopen or delete
            raise

    def _capture(self, path, fd, parent, name):
        if len(self.objects) >= 4096 or len(path) > 1024:
            raise LifecycleError('runtime manifest budget exceeded')
        pin = self.k.snapshot(fd)
        uid, gid = self.k.identity()
        directory = stat.S_ISDIR(pin['mode'])
        if (not directory and not stat.S_ISREG(pin['mode']) or pin['uid'] != uid or pin['gid'] != gid
                or pin['mode'] & 0o7022 or pin['xattrs'] or pin['fdflags'] != fcntl.FD_CLOEXEC
                or pin['flags'] & os.O_ACCMODE or not pin['flags'] & os.O_NOATIME
                or pin['filesystem'] not in (0xEF53, 0x9123683E)
                or directory and pin['filesystem'] == 0x9123683E and pin['ino'] == 256
                or (pin['dev'], pin['mount'], pin['namespace']) !=
                   (self.root_pin['dev'], self.root_pin['mount'], self.root_pin['namespace'])
                or not directory and pin['nlink'] != 1
                or directory and (pin['nlink'] != 1 if pin['filesystem'] == 0x9123683E else pin['nlink'] < 2)
                or any((o['pin']['dev'], o['pin']['ino']) == (pin['dev'], pin['ino']) for o in self.objects.values())):
            raise LifecycleError('unsupported runtime descriptor/type/ownership/mount/link state')
        obj = dict(fd=fd, pin=pin, parent=parent, name=name, directory=directory)
        self.objects[path] = obj
        row = dict(path=path, mode=stat.S_IMODE(pin['mode']), directory=directory)
        if directory:
            names = self.k.entries(fd)
            if (type(names) is not list or names != sorted(set(names)) or len(names) > 4096
                    or any(not isinstance(n, str) or not n or n in ('.','..') or '/' in n or '\\' in n
                           or len(n) > 255 or any(ord(c) < 32 or ord(c) > 126 for c in n) for n in names)):
                raise LifecycleError('unsupported runtime names')
            obj['names'] = names
            self.rows.append(row)
            for child in names:
                child_fd = self.k.runtime_open(fd, child)
                # Store descriptor immediately, including failures before validation.
                obj.setdefault('opened', []).append(child_fd)
                self._capture(path + '/' + child if path else child, child_fd, fd, child)
        else:
            if not 0 <= pin['size'] <= 16 * 1024 * 1024:
                raise LifecycleError('runtime file size budget exceeded')
            self.bytes += pin['size']
            if self.bytes > 128 * 1024 * 1024:
                raise LifecycleError('runtime total size budget exceeded')
            data = self.k.read(fd, pin['size'] + 1, 0)
            if len(data) != pin['size']: raise LifecycleError('incomplete runtime read')
            obj['data'] = data
            row.update(sha256=hashlib.sha256(data).hexdigest(), bytes=len(data))
            self.rows.append(row)
        if self.k.snapshot(fd) != pin:
            raise LifecycleError('runtime changed while recording original evidence')

    def check(self):
        if self.failed: raise LifecycleError('runtime grant revoked')
        try:
            for obj in self.objects.values():
                if self.k.snapshot(obj['fd']) != obj['pin']:
                    raise LifecycleError('original runtime descriptor changed')
                if obj['parent'] is not None:
                    observed = self.k.observe(obj['parent'], obj['name'])
                    if {k:v for k,v in observed.items() if k != 'flags'} != {k:v for k,v in obj['pin'].items() if k != 'flags'}:
                        raise LifecycleError('original runtime binding changed')
                if obj['directory']:
                    if self.k.entries(obj['fd']) != obj['names']: raise LifecycleError('runtime has unexpected children')
                elif self.k.read(obj['fd'], len(obj['data']) + 1, 0) != obj['data']:
                    raise LifecycleError('original runtime bytes changed')
        except BaseException:
            self.failed = True
            raise

    def file(self, path):
        self.check()
        if not isinstance(path, str) or not path.startswith('/') or path[1:] not in self.objects:
            raise LifecycleError('runtime file is not in approved manifest')
        obj = self.objects[path[1:]]
        if obj['directory']: raise LifecycleError('runtime file required')
        return obj['data']


class LinuxTransport:
    """Owns authenticated helper socket, original pidfd/nsfd and helper child.

    Offline tests exercise these methods only with fake OS boundaries. The helper
    requires existing PID-namespace privilege; no privilege/userns/policy setup
    or alternate backend is attempted. Descriptor ownership is exclusive and
    external writers/reapers are unsupported. All errors retain the transport.
    """
    NS_GET_NSTYPE = 0xb703
    CLONE_NEWPID = 0x20000000

    @classmethod
    def spawn(cls, helper_fd, digest, argv, session, root_fd, runtime_fd=None, *, output_budget=None):
        self = cls()
        self.helper_fd, self.digest, self.root_fd, self.runtime_fd = helper_fd, digest, root_fd, runtime_fd
        self.birth, self.closed_proof = None, None
        self.rights, self.streams, self.stream_roles = [], {}, {}
        self.channel = self.launch_child = self.process = None
        self.stopping = False
        self.output, self.errors = bytearray(), bytearray()
        self.output_budget = output_budget
        try:
            if output_budget is not None:
                phases = sys.modules.get('_panda_host_phases')
                if phases is None or type(output_budget) is not phases.Capture:
                    raise LifecycleError('original phase capture required')
                output_budget.remaining('stdout'); output_budget.remaining('stderr')
            self.helper_pin = self.helper_identity()
            parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET | socket.SOCK_CLOEXEC)
            self.channel, self.launch_child = parent, child  # retain before configuration
            parent.setsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED, 1)
            parent.setblocking(False)
            runtime_args = [] if runtime_fd is None else ['--runtime-fd', str(runtime_fd)]
            inherited = (helper_fd, child.fileno(), root_fd) + (() if runtime_fd is None else (runtime_fd,))
            self.process = subprocess.Popen(
                [f'/proc/self/fd/{helper_fd}', '--control-fd', str(child.fileno()),
                 session, '--root-fd', str(root_fd), *runtime_args, '--', *argv],
                pass_fds=inherited, close_fds=True,
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env={'PATH': '/usr/bin:/bin', 'LANG': 'C'})
            self.streams = {self.process.stdout: self.output, self.process.stderr: self.errors}
            self.stream_roles = {self.process.stdout: 'stdout', self.process.stderr: 'stderr'}
            self.launch_pin = dict(helper_fd=helper_fd, root_fd=root_fd, runtime_fd=runtime_fd,
                channel=parent, channel_fd=parent.fileno(), process=self.process, pid=self.process.pid,
                stdout=self.process.stdout, stderr=self.process.stderr, output=self.output, errors=self.errors,
                capture=output_budget)
            self.channel_pin = self.socket_identity()
            self.stream_pins = {stream: self.pipe_identity(stream) for stream in self.streams}
            self.stream_eof = set()
            if self.helper_identity() != self.helper_pin:
                raise LifecycleError('helper identity changed across launch; preserve')
            child.close()
            return self
        except BaseException as exc:
            exc.transport = self  # even identity/socket/configuration/close failures
            raise  # no guessed PID cleanup, signalling, retry, or handle disposal

    def socket_identity(self):
        fd = self.channel.fileno()
        info = os.fstat(fd)
        if (not stat.S_ISSOCK(info.st_mode)
                or self.channel.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) != socket.SOCK_SEQPACKET
                or fcntl.fcntl(fd, fcntl.F_GETFD) != fcntl.FD_CLOEXEC):
            raise LifecycleError('original helper channel differs')
        return fd, info.st_dev, info.st_ino, info.st_mode

    def pipe_identity(self, stream):
        fd = stream.fileno()
        info = os.fstat(fd)
        if not stat.S_ISFIFO(info.st_mode) or fcntl.fcntl(fd, fcntl.F_GETFD) != fcntl.FD_CLOEXEC:
            raise LifecycleError("original output pipe descriptor required")
        return fd, info.st_dev, info.st_ino, info.st_mode

    def _retained_streams(self):
        if (self.output is not self.launch_pin["output"] or self.errors is not self.launch_pin["errors"]
                or self.output_budget is not self.launch_pin["capture"]):
            raise LifecycleError("original output buffers/capture lost")
        expected = {self.launch_pin["stdout"]: (self.launch_pin["output"], "stdout"),
                    self.launch_pin["stderr"]: (self.launch_pin["errors"], "stderr")}
        if (set(self.stream_pins) != set(expected) or not self.stream_eof <= set(expected)
                or set(self.streams) != set(expected) - self.stream_eof
                or self.stream_roles != {stream: role for stream, (_, role) in expected.items()}):
            raise LifecycleError("original output pipe collection lost")
        for stream, (buffer, role) in expected.items():
            if (stream.fileno() != self.stream_pins[stream][0]
                    or self.pipe_identity(stream) != self.stream_pins[stream]
                    or stream in self.streams and self.streams[stream] is not buffer):
                raise LifecycleError("original output pipe identity lost")

    def _retained_launch(self):
        self._retained_streams()
        p = self.launch_pin
        if (self.helper_fd != p['helper_fd'] or self.root_fd != p['root_fd'] or self.runtime_fd != p['runtime_fd']
                or self.channel is not p['channel'] or self.channel.fileno() != p['channel_fd']
                or self.process is not p['process'] or self.process.pid != p['pid']
                or self.process.stdout is not p['stdout'] or self.process.stderr is not p['stderr']
                or self.output is not p['output'] or self.errors is not p['errors']
                or self.output_budget is not p['capture'] or self.socket_identity() != self.channel_pin):
            raise LifecycleError('original transport/process/channel/capture custody lost')

    def pidfs_type(self):
        if struct.calcsize('P') != 8:
            raise LifecycleError('64-bit pidfs identity required')
        buffer = ctypes.create_string_buffer(256)
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.fstatfs(self.pidfd, ctypes.byref(buffer)) != 0:
            raise OSError(ctypes.get_errno(), 'pidfd fstatfs')
        return ctypes.c_long.from_buffer(buffer).value & 0xFFFFFFFF

    def pidfd_identity(self):
        before = os.fstat(self.pidfd)
        if self.pidfs_type() != 0x50494446 or before.st_ino <= 0:
            raise LifecycleError('original pidfd requires distinct pidfs inode identity')
        after = os.fstat(self.pidfd)
        identity = lambda info: (info.st_dev, info.st_ino, info.st_mode)
        if identity(before) != identity(after):
            raise LifecycleError('pidfd changed during identity observation')
        return identity(after)

    def helper_identity(self):
        info = os.fstat(self.helper_fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_mode & 0o6022 or not info.st_mode & 0o100
                or info.st_nlink != 1 or info.st_size <= 0 or info.st_size > 4 * 1024 * 1024
                or os.listxattr(self.helper_fd)
                or fcntl.fcntl(self.helper_fd, fcntl.F_GETFD) != fcntl.FD_CLOEXEC):
            raise LifecycleError('unreviewed helper type/owner/mode/links/attributes/descriptor')
        data = os.pread(self.helper_fd, info.st_size + 1, 0)
        if len(data) != info.st_size or hashlib.sha256(data).hexdigest() != self.digest:
            raise LifecycleError('helper binary digest differs; no source or launcher-only trust')
        after = os.fstat(self.helper_fd)
        fields = ('st_dev', 'st_ino', 'st_uid', 'st_gid', 'st_mode', 'st_nlink', 'st_size', 'st_ctime_ns', 'st_mtime_ns')
        pin = tuple(getattr(info, name) for name in fields)
        if tuple(getattr(after, name) for name in fields) != pin:
            raise LifecycleError('helper changed while hashing')
        return pin

    def receive(self, timeout):
        end = time.monotonic() + timeout
        while True:
            left = end - time.monotonic()
            if left <= 0:
                raise LifecycleError('helper protocol deadline; preserve')
            try:
                readable, _, _ = select.select([self.channel, *self.streams], [], [], left)
            except InterruptedError:
                continue
            if not readable:
                raise LifecycleError('helper protocol timeout; preserve')
            self.capture(readable)
            if self.channel not in readable:
                continue
            # Per-message SCM_CREDENTIALS identifies the actual sender; initial
            # socketpair SO_PEERCRED would identify its creator, not exec'd peer.
            raw, ancillary, flags, _ = self.channel.recvmsg(
                33280, socket.CMSG_SPACE(8) + socket.CMSG_SPACE(12), socket.MSG_CMSG_CLOEXEC)
            received, credentials, unexpected = [], [], False
            for level, kind, payload in ancillary:
                if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
                    items = array.array('i')
                    items.frombytes(payload[:len(payload) - len(payload) % items.itemsize])
                    received.extend(items)
            # Keep even unexpected descriptors; an error is not a cleanup grant.
            self.rights.extend(received)
            for level, kind, payload in ancillary:
                if level == socket.SOL_SOCKET and kind == socket.SCM_CREDENTIALS:
                    credentials.append(struct.unpack('3i', payload))
                elif not (level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS):
                    unexpected = True
            if unexpected:
                raise LifecycleError('unexpected helper ancillary data')
            if (flags & (socket.MSG_TRUNC | socket.MSG_CTRUNC) or not raw or len(raw) >= 33280
                    or credentials != [(self.process.pid, os.geteuid(), os.getegid())]
                    or self.process.returncode is not None):
                raise LifecycleError('lost helper peer/truncated packet; preserve')
            if self.birth is None:
                if len(self.rights) != 2:
                    raise LifecycleError('atomic birth needs exactly pidfd and namespace descriptor')
            elif received:
                raise LifecycleError('unexpected descriptor after birth')
            return raw.decode('ascii', errors='strict')

    def capture(self, readable):
        self._retained_streams()
        for stream in list(self.streams):
            if stream not in readable:
                continue
            buffer = self.streams[stream]
            bound = min(65536, 1048577 - len(buffer))
            budget = getattr(self, 'output_budget', None)
            if budget is not None:
                role = self.stream_roles[stream]
                bound = min(bound, budget.remaining(role) + 1)
            raw = os.read(stream.fileno(), bound)
            buffer.extend(raw)  # retain overflow evidence before charging/refusing
            if budget is not None:
                budget.charge(role, raw)
            if len(buffer) > 1048576:
                raise LifecycleError('bounded helper/worker output exceeded; preserve')
            if not raw:
                self.stream_eof.add(stream)
                del self.streams[stream]

    def bind_birth(self, pid, namespace):
        if self.birth is not None or len(self.rights) != 2:
            raise LifecycleError('birth descriptor transfer missing/duplicate')
        self.pidfd, self.nsfd = self.rights
        if type(self.pidfd) is not int or type(self.nsfd) is not int or self.pidfd == self.nsfd:
            raise LifecycleError('distinct original birth descriptors required')
        self.birth_handles = (self.pidfd, self.nsfd)
        self.pid_pin = self.pidfd_identity()
        info = os.fstat(self.nsfd)
        if info.st_ino != namespace or fcntl.ioctl(self.nsfd, self.NS_GET_NSTYPE) != self.CLONE_NEWPID:
            raise LifecycleError('namespace descriptor differs from atomic birth')
        self.ns_pin = (info.st_dev, info.st_ino)
        self.birth = {'pid': pid, 'namespace': namespace, 'pidfd': self.pidfd, 'nsfd': self.nsfd}
        self.birth_pin = dict(self.birth)
        self.check()
        return dict(self.birth)

    def check(self):
        self._retained_launch()
        if self.helper_identity() != self.helper_pin:
            raise LifecycleError('retained helper changed')
        if self.birth is None:
            raise LifecycleError('no bound birth')
        if ((self.pidfd, self.nsfd) != self.birth_handles or self.rights != list(self.birth_handles)
                or self.birth != self.birth_pin or self.pidfd_identity() != self.pid_pin):
            raise LifecycleError('original pidfd/birth descriptor identity differs')
        info = os.fstat(self.nsfd)
        if (info.st_dev, info.st_ino) != self.ns_pin or fcntl.ioctl(self.nsfd, self.NS_GET_NSTYPE) != self.CLONE_NEWPID:
            raise LifecycleError('retained namespace lost/replaced')
        for fd in (self.nsfd, self.pidfd):
            if fcntl.fcntl(fd, fcntl.F_GETFD) != fcntl.FD_CLOEXEC:
                raise LifecycleError('birth descriptor lifetime flags changed')
        with open(f'/proc/self/fdinfo/{self.pidfd}', encoding='ascii') as stream:
            fields = dict(line.split(':', 1) for line in stream if ':' in line)
        expected = (str(self.birth['pid']), '-1') if self.stopping else (str(self.birth['pid']),)
        if fields.get('Pid', '').strip() not in expected:
            raise LifecycleError('pidfd kernel identity differs')

    def send(self, text):
        self.check()
        raw = text.encode('ascii')
        if self.channel.send(raw, socket.MSG_NOSIGNAL | socket.MSG_DONTWAIT) != len(raw):
            raise LifecycleError('short helper command; preserve')
        if text.startswith('STOP '):
            self.stopping = True

    def _pidfd_exited(self):
        poller = select.poll()
        poller.register(self.pidfd, select.POLLIN)
        observed = poller.poll(0)
        if (len(observed) != 1 or observed[0][0] != self.pidfd
                or not observed[0][1] & select.POLLIN
                or observed[0][1] & (select.POLLNVAL | select.POLLERR)):
            raise LifecycleError('original init pidfd not verifiably exited')

    def _output_witness(self):
        return {'helper_status': self.process.returncode, 'init_pidfd_exited': True, 'namespace_retained': True,
                'stdout_bytes': len(self.output), 'stderr_bytes': len(self.errors),
                'stdout_sha256': hashlib.sha256(self.output).hexdigest(),
                'stderr_sha256': hashlib.sha256(self.errors).hexdigest()}

    def wait_closed(self):
        if self.closed_proof is not None or not self.stopping:
            raise LifecycleError('missing STOP or repeated namespace closure')
        self.check()
        # Native CLOSED follows P_PIDFD wait; require own helper clean exit+EOF.
        if self.process.wait(timeout=2) != 0:
            raise LifecycleError('helper failed after alleged closure')
        end = time.monotonic() + 2
        while self.streams:
            left = end - time.monotonic()
            if left <= 0:
                raise LifecycleError('output EOF incomplete after closure; preserve')
            ready, _, _ = select.select(list(self.streams), [], [], left)
            self.capture(ready)
        self.check()
        self._pidfd_exited()
        witness = self._output_witness()
        if witness['helper_status'] != 0:
            raise LifecycleError('helper exit status not retained')
        self.closed_proof = dict(witness)
        return dict(witness)

    def check_closed(self):
        # No wait/signal/STOP/root metadata observation or historical PID lookup.
        self.check()
        if (self.closed_proof is None or not self.stopping or self.streams
                or self._output_witness() != self.closed_proof or self.process.returncode != 0):
            raise LifecycleError('original closed transport/output proof changed')
        self._pidfd_exited()
        if self.output_budget is not None and self.output_budget.witness() != {
                key: self.closed_proof[key] for key in ('stdout_bytes', 'stderr_bytes', 'stdout_sha256', 'stderr_sha256')}:
            raise LifecycleError('closed output/capture identity differs')


class NativeLifecycle:
    """Session-bound protocol; no accepted boolean/callback closure interface."""
    @classmethod
    def start(cls, kernel, ledger, helper_fd, digest, argv, session, root_fd, root_pin, *, _mediation=None, _capture=None, _factory=None):
        if (not isinstance(session, str) or not re.fullmatch('[0-9a-f]{32}', session)
                or not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest)
                or not isinstance(argv, (list, tuple)) or not argv or len(argv) > 128
                or any(not isinstance(arg, str) or not arg or len(arg) > 4096 or
                       any(ord(c) < 32 or ord(c) == 127 for c in arg) for arg in argv)
                or not argv[0].startswith('/') or '..' in argv[0].split('/')):
            raise LifecycleError('invalid reviewed helper/worker/session scope')
        self = cls()
        self.k, self.ledger, self.session = kernel, ledger, session
        self.root_fd, self.root_pin = root_fd, dict(root_pin)
        self.preserved = self.ran = self.closed = False
        self.birth = self._closure_witness = self._closed_sequence = None
        self._mediation = _mediation
        self._policy_ready = self._exec_ready = False
        if kernel.snapshot(root_fd) != self.root_pin:
            raise LifecycleError('root differs before helper start')
        ledger.append({'kind': 'namespace-intent', 'helper_sha256': digest,
                       'worker_sha256': hashlib.sha256(canonical(list(argv))).hexdigest(),
                       'profile': 'broker-v1' if _mediation else 'legacy-unmediated'})
        factory = getattr(kernel, 'process_transport', LinuxTransport.spawn) if _factory is None else _factory
        try:
            try:
                args = (helper_fd, digest, list(argv), session, root_fd)
                if _capture is not None:
                    self.transport = factory(*args, _mediation[0].fd, output_budget=_capture)
                else:
                    self.transport = factory(*args, _mediation[0].fd) if _mediation else factory(*args)
            except BaseException as exc:
                self.transport = getattr(exc, 'transport', None)
                raise
            packet = self.transport.receive(30)
            match = re.fullmatch(r'BIRTH ([0-9a-f]{32}) ([1-9][0-9]{0,9}) ([1-9][0-9]{0,19}) ([0-9]{1,20}) ([1-9][0-9]{0,19})', packet)
            if (not match or match[1] != session or
                    (int(match[4]), int(match[5])) != (root_pin['dev'], root_pin['ino'])):
                raise LifecycleError('invalid atomic namespace birth packet')
            birth = self.transport.bind_birth(int(match[2]), int(match[3]))
            self.birth = dict(birth)
            self.check()
            ledger.append({'kind': 'namespace-born', 'birth': birth})
            return self
        except BaseException as exc:
            self.preserved = True
            exc.lifecycle = self
            raise

    @classmethod
    def start_mediated(cls, kernel, ledger, helper_fd, digest, session, root_fd, root_pin, *, runtime, store, plan):
        """External-controller entry. Does not authorize execution on this host.

        One epoch only; process-crash recovery/restart remains unsupported. The
        worker uses the existing pure transaction engine through fixed-role RPC.
        JSON or a callback never selects this profile or grants teardown.
        """
        if type(runtime) is not RuntimeGrant or runtime.k is not kernel:
            raise LifecycleError('original typed runtime grant required')
        runtime.check()
        receipt = store.root_receipt()
        if (receipt['fd'] != root_fd or receipt['pin'] != root_pin or receipt['session_id'] != session
                or store.s.k is not kernel or runtime.file('/app/host_canary.py') != store.program.data):
            raise LifecycleError('broker/runtime/session source authority differs')
        for path in ('/app/host_canary_rpc.py','/app/host_canary_mediated.py'):
            if not runtime.file(path): raise LifecycleError('approved worker module absent')
        runtime.file('/bin/python3')
        if not runtime.objects['bin/python3']['pin']['mode'] & 0o100:
            raise LifecycleError('approved interpreter must be owner executable')
        if type(plan) is not list or not 1 <= len(plan) <= 32:
            raise LifecycleError('bounded explicit worker plan required')
        encoded = canonical(plan).decode('ascii')
        if len(encoded) > 4096: raise LifecycleError('worker plan exceeds argument bound')
        store.restrict_plan(plan)  # controller-only, one-way; never worker RPC
        path = Path(__file__).with_name('host_canary_rpc.py')
        if not path.is_file(): path = Path(__file__).resolve().parents[1] / 'theme/panda/common/host_canary_rpc.py'
        spec = importlib.util.spec_from_file_location('_panda_controller_rpc', path)
        rpc_api = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rpc_api)
        rpc = rpc_api.Server(store, ledger, session, 1)
        argv = ['/bin/python3','-B','-I','-S','/app/host_canary_mediated.py',
                '--rpc-fd','3','--session',session,'--epoch','1','--plan',encoded]
        return cls.start(kernel, ledger, helper_fd, digest, argv, session, root_fd, root_pin,
                         _mediation=(runtime, store, rpc, receipt['birth']))

    @property
    def mediated_profile(self):
        return bool(self._mediation and self._policy_ready and self._exec_ready and not self.preserved)

    def _refresh_root(self):
        runtime, store, rpc, birth = self._mediation
        receipt = store.root_receipt()  # original broker HeldObject; complete graph checked
        if receipt['fd'] != self.root_fd or receipt['birth'] != birth or receipt['session_id'] != self.session:
            raise LifecycleError('broker root birth/descriptor changed')
        if self.k.snapshot(self.root_fd) != receipt['pin']:
            raise LifecycleError('broker root transition not current')
        if receipt['pin'] != self.root_pin:
            self.ledger.append({'kind':'broker-root-transition','birth':birth,'pin':receipt['pin']})
            self.root_pin = dict(receipt['pin'])

    def _quiescent(self):
        if self._mediation:
            runtime, store, rpc, birth = self._mediation
            runtime.check()
            if not rpc.quiescent or store.lease is not None or store.views or store.programs:
                raise LifecycleError('incomplete RPC/view/program/lock evidence; preserve')
            store.root_receipt()

    def check(self):
        if self.preserved or self.closed or self.k.snapshot(self.root_fd) != self.root_pin:
            raise LifecycleError('root/lifecycle custody lost; preserve')
        self.transport.check()

    def run(self):
        try:
            self.check()
            if self.ran:
                raise LifecycleError('worker run already consumed')
            self.ledger.append({'kind': 'worker-intent'})
            self.transport.send('START ' + self.session)
            end = time.monotonic() + 30
            sequence, active, root, root_status = 0, set(), None, None
            generation = None
            while True:
                left = end - time.monotonic()
                if left <= 0:
                    raise LifecycleError('worker deadline; preserve')
                packet = self.transport.receive(left)
                self.check()
                if self._mediation and packet.startswith('POLICY '):
                    runtime = self._mediation[0]
                    expected = f'POLICY {self.session} {generation} {root} {runtime.root_pin["dev"]} {runtime.root_pin["ino"]} broker-v1'
                    if packet != expected or self._policy_ready or root not in active:
                        raise LifecycleError('unregistered or duplicate kernel policy receipt')
                    runtime.check()
                    self.ledger.append({'kind':'worker-policy','profile':'broker-v1','generation':generation,'pid':root,
                                        'runtime_sha256':runtime.digest})
                    self._policy_ready = True
                    self.transport.send(f'ACK {self.session} 0')
                    continue
                if self._mediation and packet.startswith('RPC '):
                    prefix = f'RPC {self.session} {generation} {root} '
                    if not self.mediated_profile or root not in active or not packet.startswith(prefix):
                        raise LifecycleError('RPC lacks acknowledged original worker/generation/policy/exec')
                    raw = packet[len(prefix):].encode('ascii')
                    reply = self._mediation[2].accept(raw)
                    self._refresh_root()
                    self.transport.send(f'RPC_REPLY {self.session} {generation} {root} ' + reply.decode('ascii'))
                    continue
                done = re.fullmatch(r'DONE ([0-9a-f]{32}) ([0-9]{1,3})', packet)
                if done:
                    if done[1] != self.session or active or root is None or int(done[2]) != root_status:
                        raise LifecycleError('incomplete descendant registration/termination')
                    if self._mediation:
                        if not self.mediated_profile: raise LifecycleError('missing enforced worker policy/exec evidence')
                        if root_status != 0: raise LifecycleError('worker failure or stopped plan; preserve transaction evidence')
                        self._quiescent()
                    self.ledger.append({'kind': 'worker-complete', 'status': root_status, 'events': sequence})
                    self.ran = True
                    return root_status
                event = re.fullmatch(r'TASK ([0-9a-f]{32}) ([1-9][0-9]{0,5}) (BIRTH|EXIT|EXEC) ([1-9][0-9]{0,9}) ([0-9]{1,10})', packet)
                if not event or event[1] != self.session or int(event[2]) != sequence + 1 or sequence >= 100000:
                    raise LifecycleError('unknown/gapped lifecycle record')
                sequence += 1
                kind, pid, value = event[3], int(event[4]), int(event[5])
                if pid <= 1:
                    raise LifecycleError('namespace-init cannot be a worker task')
                if kind == 'BIRTH':
                    if self._mediation and root is not None:
                        raise LifecycleError('unexpected descendant in no-fork mediated profile')
                    if pid in active or len(active) >= 4096 or (root is None and value != 1) or (root is not None and value not in active):
                        raise LifecycleError('unregistered creator/duplicate task')
                    active.add(pid)
                    if root is None:
                        root, generation = pid, sequence
                elif kind == 'EXEC':
                    if (not self._mediation or not self._policy_ready or self._exec_ready
                            or pid != root or pid not in active or value != generation):
                        raise LifecycleError('unexpected exec/generation or missing kernel policy')
                    self._exec_ready = True
                else:
                    if pid not in active or value > 255:
                        raise LifecycleError('unknown task exit')
                    active.remove(pid)
                    if pid == root and root_status is None: root_status = value
                self.ledger.append({'kind': 'task', 'sequence': sequence, 'event': kind,
                                    'pid': pid, 'creator_or_status': value})
                self.transport.send(f'ACK {self.session} {sequence}')
        except BaseException:
            self.preserved = True
            if self._mediation: self._mediation[2].abort('native worker custody lost')
            raise

    def finish(self):
        if not self.ran:
            raise LifecycleError('no completed registered descendant run')
        try:
            self.check()
            self._quiescent()
            self.ledger.append({'kind': 'namespace-stop-intent'})
            self.transport.send('STOP ' + self.session)
            if self.transport.receive(30) != 'CLOSED ' + self.session:
                raise LifecycleError('missing authenticated namespace closure')
            witness = self.transport.wait_closed()
            self.check()
            self.ledger.append({'kind': 'namespace-closed', 'witness': witness})
            self._closure_witness = dict(witness)
            self._closed_sequence = getattr(self.ledger, 'sequence', None)
            self.closed = True
        except BaseException:
            self.preserved = True
            raise
