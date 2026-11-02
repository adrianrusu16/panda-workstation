"""Unexecuted Linux native-custodian binding; fake transports in offline tests.

No PATH lookup, inherited environment, PGID, JSON closure or journal replay.
Only an already trusted controller may call this API with its held descriptors.
Native code must be independently built/reviewed and its exact binary approved.
The original Host operator deliberately has no integration with these adapters.
"""
import array
import fcntl
import hashlib
import os
import re
import select
import signal
import socket
import stat
import struct
import subprocess
import time


class LifecycleError(ValueError):
    """Retain all filesystem/process evidence. No teardown or retry grant."""


class LinuxTransport:
    """Owns authenticated helper socket, original pidfd/nsfd and helper child.

    This concrete path is never invoked by the offline test suite. The helper
    requires existing PID-namespace privilege; no privilege/userns/policy setup
    or alternate backend is attempted. Descriptor ownership is exclusive and
    external writers/reapers are unsupported. All errors retain the transport.
    """
    NS_GET_NSTYPE = 0xb703
    CLONE_NEWPID = 0x20000000

    @classmethod
    def spawn(cls, helper_fd, digest, argv, session, root_fd):
        self = cls()
        self.helper_fd, self.digest, self.root_fd = helper_fd, digest, root_fd
        self.birth = None
        self.rights = []
        self.stopping = False
        self.output, self.errors = bytearray(), bytearray()
        self.helper_pin = self.helper_identity()
        parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET | socket.SOCK_CLOEXEC)
        self.channel = parent
        parent.setsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED, 1)
        parent.setblocking(False)
        try:
            # Root/worker argument scope was checked by the prospective broker.
            # Keep helper itself a direct unreaped child until CLOSED is checked.
            self.process = subprocess.Popen(
                [f'/proc/self/fd/{helper_fd}', '--control-fd', str(child.fileno()),
                 session, '--root-fd', str(root_fd), '--', *argv],
                pass_fds=(helper_fd, child.fileno(), root_fd), close_fds=True,
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env={'PATH': '/usr/bin:/bin', 'LANG': 'C'})
            self.streams = {self.process.stdout: self.output, self.process.stderr: self.errors}
            if self.helper_identity() != self.helper_pin:
                raise LifecycleError('helper identity changed across launch; preserve')
            return self
        except BaseException as exc:
            exc.transport = self  # retain partial launch evidence; never signal a guessed PID
            raise
        finally:
            child.close()

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
                192, socket.CMSG_SPACE(8) + socket.CMSG_SPACE(12), socket.MSG_CMSG_CLOEXEC)
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
            if (flags & (socket.MSG_TRUNC | socket.MSG_CTRUNC) or not raw or len(raw) >= 192
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
        for stream in list(self.streams):
            if stream not in readable:
                continue
            buffer = self.streams[stream]
            raw = os.read(stream.fileno(), min(65536, 1048577 - len(buffer)))
            buffer.extend(raw)
            if len(buffer) > 1048576:
                raise LifecycleError('bounded helper/worker output exceeded; preserve')
            if not raw:
                del self.streams[stream]

    def bind_birth(self, pid, namespace):
        if self.birth is not None or len(self.rights) != 2:
            raise LifecycleError('birth descriptor transfer missing/duplicate')
        self.pidfd, self.nsfd = self.rights
        info = os.fstat(self.nsfd)
        if info.st_ino != namespace or fcntl.ioctl(self.nsfd, self.NS_GET_NSTYPE) != self.CLONE_NEWPID:
            raise LifecycleError('namespace descriptor differs from atomic birth')
        self.ns_pin = (info.st_dev, info.st_ino)
        self.birth = {'pid': pid, 'namespace': namespace, 'pidfd': self.pidfd, 'nsfd': self.nsfd}
        self.check()
        return dict(self.birth)

    def check(self):
        if self.helper_identity() != self.helper_pin:
            raise LifecycleError('retained helper changed')
        if self.birth is None:
            raise LifecycleError('no bound birth')
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

    def wait_closed(self):
        self.check()
        # Authenticated CLOSED is emitted only after helper's real P_PIDFD wait
        # on its namespace-init child; require the helper's own clean exit too.
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
        poller = select.poll()
        poller.register(self.pidfd, select.POLLIN)
        observed = poller.poll(0)
        if not observed or any(fd != self.pidfd or not events & select.POLLIN or
                               events & (select.POLLNVAL | select.POLLERR) for fd, events in observed):
            raise LifecycleError('init pidfd not exited after closure witness')
        return {'helper_status': 0, 'init_pidfd_exited': True, 'namespace_retained': True,
                'stdout_bytes': len(self.output), 'stderr_bytes': len(self.errors),
                'stdout_sha256': hashlib.sha256(self.output).hexdigest(),
                'stderr_sha256': hashlib.sha256(self.errors).hexdigest()}


class NativeLifecycle:
    """Session-bound protocol; no accepted boolean/callback closure interface."""
    @classmethod
    def start(cls, kernel, ledger, helper_fd, digest, argv, session, root_fd, root_pin):
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
        if kernel.snapshot(root_fd) != self.root_pin:
            raise LifecycleError('root differs before helper start')
        ledger.append({'kind': 'namespace-intent', 'helper_sha256': digest, 'worker': list(argv)})
        factory = getattr(kernel, 'process_transport', LinuxTransport.spawn)
        try:
            try:
                self.transport = factory(helper_fd, digest, list(argv), session, root_fd)
            except BaseException as exc:
                self.transport = getattr(exc, 'transport', None)
                raise
            packet = self.transport.receive(30)
            match = re.fullmatch(r'BIRTH ([0-9a-f]{32}) ([1-9][0-9]{0,9}) ([1-9][0-9]{0,19}) ([0-9]{1,20}) ([1-9][0-9]{0,19})', packet)
            if (not match or match[1] != session or
                    (int(match[4]), int(match[5])) != (root_pin['dev'], root_pin['ino'])):
                raise LifecycleError('invalid atomic namespace birth packet')
            birth = self.transport.bind_birth(int(match[2]), int(match[3]))
            self.check()
            ledger.append({'kind': 'namespace-born', 'birth': birth})
            return self
        except BaseException as exc:
            self.preserved = True
            exc.lifecycle = self
            raise

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
            while True:
                left = end - time.monotonic()
                if left <= 0:
                    raise LifecycleError('worker deadline; preserve')
                packet = self.transport.receive(left)
                self.check()
                done = re.fullmatch(r'DONE ([0-9a-f]{32}) ([0-9]{1,3})', packet)
                if done:
                    if done[1] != self.session or active or root is None or int(done[2]) != root_status:
                        raise LifecycleError('incomplete descendant registration/termination')
                    self.ledger.append({'kind': 'worker-complete', 'status': root_status, 'events': sequence})
                    self.ran = True
                    return root_status
                event = re.fullmatch(r'TASK ([0-9a-f]{32}) ([1-9][0-9]{0,5}) (BIRTH|EXIT) ([1-9][0-9]{0,9}) ([0-9]{1,10})', packet)
                if not event or event[1] != self.session or int(event[2]) != sequence + 1 or sequence >= 100000:
                    raise LifecycleError('unknown/gapped lifecycle record')
                sequence += 1
                kind, pid, value = event[3], int(event[4]), int(event[5])
                if pid <= 1:
                    raise LifecycleError('namespace-init cannot be a worker task')
                if kind == 'BIRTH':
                    if pid in active or len(active) >= 4096 or (root is None and value != 1) or (root is not None and value not in active):
                        raise LifecycleError('unregistered creator/duplicate task')
                    active.add(pid)
                    if root is None: root = pid
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
            raise

    def finish(self):
        if not self.ran:
            raise LifecycleError('no completed registered descendant run')
        try:
            self.check()
            self.ledger.append({'kind': 'namespace-stop-intent'})
            self.transport.send('STOP ' + self.session)
            if self.transport.receive(30) != 'CLOSED ' + self.session:
                raise LifecycleError('missing authenticated namespace closure')
            witness = self.transport.wait_closed()
            self.check()
            self.ledger.append({'kind': 'namespace-closed', 'witness': witness})
            self.closed = True
        except BaseException:
            self.preserved = True
            raise
