"""Prospective Linux custody adapters; import and bare LinuxKernel are inert.

Only a trusted external controller may construct TrustedBootstrap. It must own
the supplied descriptors exclusively, provide quiescent private storage, and
retain them for this process lifetime. This API is not an untrusted-worker RPC.
There is no journal replay, environment bootstrap, operator injection or CLI.
TrustedBootstrap construction opens namespace descriptors and creates/syncs its
external ledger. That invocation is separately authorized and unvalidated.
"""
from dataclasses import dataclass
import ctypes
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys

MAX_RECORD = 4096
MAX_EVENTS = 100000
MAX_BYTES = 64 * 1024 * 1024
FILESYSTEMS = frozenset((0xEF53, 0x9123683E))  # ext4, btrfs; trial still required


class CustodyError(ValueError):
    """Preserve all retained objects and descriptors; never reopen/adopt/retry."""


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def safe_name(name):
    if (not isinstance(name, str) or not name or name in ('.', '..')
            or '/' in name or '\\' in name or any(ord(c) < 32 or ord(c) == 127 for c in name)):
        raise CustodyError('one safe basename required')
    return name


def invariant(pin):
    return {key: value for key, value in pin.items()
            if key not in ('nlink', 'size', 'ctime', 'mtime', 'flags')}


def valid(pin, directory, mode, uid, gid):
    expected = (stat.S_IFDIR if directory else stat.S_IFREG) | mode
    if (pin['mode'] != expected or pin['uid'] != uid or pin['gid'] != gid
            or pin['xattrs'] or pin['filesystem'] not in FILESYSTEMS
            or (directory and pin['filesystem'] == 0x9123683E and pin['ino'] == 256) or pin['nlink'] < 1
            or pin['fdflags'] != fcntl.FD_CLOEXEC
            or not pin['flags'] & os.O_NOATIME
            or (not directory and pin['flags'] & (os.O_ACCMODE | os.O_APPEND) != os.O_RDWR | os.O_APPEND)
            or not directory and pin['nlink'] != 1):
        raise CustodyError('unsupported ownership/type/mode/link/filesystem/ACL state')


class LinuxKernel:
    """Concrete Linux filesystem calls, always explicitly invoked by a controller.

    No fallback for missing /proc, fstatfs, no-follow/no-atime, xattr or fsync.
    Kernel namespace/mount evidence is read from the supervisor's own procfs.
    Linux x86_64/aarch64 and libc statfs ABI only; no remote/overlay/tmpfs storage.
    """
    def identity(self):
        return os.geteuid(), os.getegid()

    def bind_context(self):
        if hasattr(self, '_namespace_fds'):
            raise CustodyError('namespace context already bound')
        self._namespace_fds = []
        for kind in ('mnt', 'user'):
            self._namespace_fds.append(os.open('/proc/self/ns/' + kind, os.O_RDONLY | os.O_CLOEXEC))
        self._namespace_pin = tuple((os.fstat(fd).st_dev, os.fstat(fd).st_ino) for fd in self._namespace_fds)

    def snapshot(self, fd):
        if not hasattr(self, '_namespace_pin'):
            raise CustodyError('retained namespace context required before observation')
        info = os.fstat(fd)
        with open(f'/proc/self/fdinfo/{fd}', encoding='ascii') as stream:
            fields = dict(line.split(':', 1) for line in stream if ':' in line)
        if 'mnt_id' not in fields:
            raise CustodyError('kernel mount ID unavailable')
        if os.uname().machine not in ('x86_64', 'aarch64'):
            raise CustodyError('unsupported statfs ABI')
        buffer = ctypes.create_string_buffer(256)
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.fstatfs(fd, ctypes.byref(buffer)) != 0:
            raise OSError(ctypes.get_errno(), 'fstatfs')
        filesystem = ctypes.c_long.from_buffer(buffer).value & 0xFFFFFFFF
        namespace = tuple((os.stat('/proc/self/ns/' + kind).st_dev,
                           os.stat('/proc/self/ns/' + kind).st_ino) for kind in ('mnt', 'user'))
        held = tuple((os.fstat(nfd).st_dev, os.fstat(nfd).st_ino) for nfd in self._namespace_fds)
        if namespace != self._namespace_pin or held != self._namespace_pin:
            raise CustodyError('retained namespace descriptor/current membership changed')
        if any(fcntl.fcntl(nfd, fcntl.F_GETFD) != fcntl.FD_CLOEXEC for nfd in self._namespace_fds):
            raise CustodyError('namespace descriptor became inheritable')
        return dict(dev=info.st_dev, ino=info.st_ino, uid=info.st_uid, gid=info.st_gid,
                    mode=info.st_mode, nlink=info.st_nlink, size=info.st_size,
                    ctime=info.st_ctime_ns, mtime=info.st_mtime_ns, atime=info.st_atime_ns,
                    mount=int(fields['mnt_id']), filesystem=filesystem,
                    namespace=namespace, xattrs=tuple(sorted(os.listxattr(fd))),
                    flags=fcntl.fcntl(fd, fcntl.F_GETFL), fdflags=fcntl.fcntl(fd, fcntl.F_GETFD))

    def observe(self, parent, name):
        # Single basename and O_NOFOLLOW prevent ancestor traversal. Do not keep
        # this temporary descriptor or learn an identity from it after loss.
        safe_name(name)
        info = os.stat(name, dir_fd=parent, follow_symlinks=False)
        flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NOATIME | os.O_NONBLOCK
        if stat.S_ISDIR(info.st_mode):
            flags |= os.O_DIRECTORY
        elif not stat.S_ISREG(info.st_mode):
            raise CustodyError('nonregular parent/name entry')
        fd = os.open(name, flags, dir_fd=parent)
        try:
            answer = self.snapshot(fd)
            if (answer['dev'], answer['ino'], answer['mode']) != (info.st_dev, info.st_ino, info.st_mode):
                raise CustodyError('entry changed during binding observation')
            return answer
        finally:
            os.close(fd)

    def entries(self, fd):
        return sorted(os.listdir(fd))

    def create(self, parent, name, directory, mode):
        safe_name(name)
        flags = os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NOATIME
        if directory:
            os.mkdir(name, mode=mode, dir_fd=parent)
            # Failure here preserves the entry. No reopen/retry/adoption path.
            return os.open(name, flags | os.O_RDONLY | os.O_DIRECTORY, dir_fd=parent)
        return os.open(name, flags | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_EXCL,
                       mode, dir_fd=parent)

    def lock(self, fd):
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def read(self, fd, count, offset):
        return os.pread(fd, count, offset)

    def offset(self, fd):
        return os.lseek(fd, 0, os.SEEK_CUR)

    def write(self, fd, raw):
        return os.write(fd, raw)

    def sync(self, fd):
        os.fsync(fd)

    def remove(self, parent, name, directory):
        safe_name(name)
        (os.rmdir if directory else os.unlink)(name, dir_fd=parent)

    def chmod(self, fd, mode):
        os.fchmod(fd, mode)

    def timestamps(self, fd):
        os.utime(fd, ns=(0, 0))

    def timestamps_exact(self, fd, atime, mtime):
        os.utime(fd, ns=(atime, mtime))

    def unlock(self, fd):
        fcntl.flock(fd, fcntl.LOCK_UN)

    def fixed_tmp(self, fd):
        """Compare an explicitly supplied original FD to the fixed real /tmp."""
        actual = os.open('/tmp', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            pin, observed = self.snapshot(fd), self.snapshot(actual)
            if ({k: v for k, v in pin.items() if k != 'flags'} !=
                    {k: v for k, v in observed.items() if k != 'flags'}
                    or pin['uid'] != 0 or pin['gid'] != 0 or pin['mode'] != stat.S_IFDIR | 0o1777
                    or pin['xattrs'] or pin['fdflags'] != fcntl.FD_CLOEXEC):
                raise CustodyError('canonical /tmp descriptor/binding/policy differs')
            return pin
        finally:
            os.close(actual)

    def runtime_open(self, parent, name):
        return os.open(safe_name(name), os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW |
                       os.O_NOATIME | os.O_NONBLOCK, dir_fd=parent)

    def approved_source_binding(self, fd):
        path = Path(__file__).resolve().parents[1] / 'theme/panda/common/host_canary.py'
        expected = self.snapshot(fd)
        info = os.stat(path, follow_symlinks=False)
        fields = {'dev': 'st_dev', 'ino': 'st_ino', 'mode': 'st_mode', 'uid': 'st_uid', 'gid': 'st_gid',
                  'nlink': 'st_nlink', 'size': 'st_size', 'atime': 'st_atime_ns',
                  'mtime': 'st_mtime_ns', 'ctime': 'st_ctime_ns'}
        if any(expected[key] != getattr(info, field) for key, field in fields.items()):
            raise CustodyError('reviewed fixed source path no longer binds original descriptor')
        return expected

    def replace(self, source_parent, source_name, target_parent, target_name):
        safe_name(source_name)
        safe_name(target_name)
        os.rename(source_name, target_name, src_dir_fd=source_parent, dst_dir_fd=target_parent)


class DurableLedger:
    """Exclusively born external evidence; never deleted or replayed as authority."""
    def __init__(self, kernel, parent, name, session, uid, gid):
        self.k, self.parent, self.name, self.session = kernel, parent, safe_name(name), session
        self.uid, self.gid = uid, gid
        # Controller-owned expected bytes; append in place, but still reread and
        # compare the entire durable prefix on every check. Export bytes(history)
        # for a retained snapshot; never share this buffer or hold a memoryview.
        self.poisoned, self.history, self.sequence = False, bytearray(), 0
        self._last_digest = '0' * 64
        self.parent_pin = kernel.snapshot(parent)
        self.fd = kernel.create(parent, name, False, 0o600)
        self.pin = kernel.snapshot(self.fd)
        valid(self.pin, False, 0o600, uid, gid)
        # Creating the evidence file is an authorized bootstrap action. This
        # ledger never certifies or cleans its own birth/parent; retain forever.
        current = kernel.snapshot(parent)
        if invariant(current) != invariant(self.parent_pin) or current['nlink'] != self.parent_pin['nlink']:
            raise CustodyError('external journal parent changed at birth')
        self.parent_pin = current
        kernel.lock(self.fd)
        kernel.sync(self.fd)
        kernel.sync(parent)
        self.check()

    def check(self):
        if self.poisoned:
            raise CustodyError('ledger revoked; preserve resources')
        try:
            pin = self.k.snapshot(self.fd)
            if pin != self.pin or self.k.snapshot(self.parent) != self.parent_pin:
                raise CustodyError('external journal descriptor/parent changed')
            observed = self.k.observe(self.parent, self.name)
            if {k: v for k, v in observed.items() if k != 'flags'} != {k: v for k, v in pin.items() if k != 'flags'}:
                raise CustodyError('external journal name changed')
            if pin['flags'] & (os.O_ACCMODE | os.O_APPEND) != os.O_RDWR | os.O_APPEND:
                raise CustodyError('journal requires retained read/write append description')
            if self.k.offset(self.fd) != len(self.history) or pin['size'] != len(self.history):
                raise CustodyError('journal offset/size differs')
            # Read the complete bounded committed prefix, including one extra byte.
            if self.k.read(self.fd, len(self.history) + 1, 0) != self.history:
                raise CustodyError('journal history differs')
        except BaseException:
            self.poisoned = True
            raise

    def append(self, event):
        try:
            self.check()
            if type(event) is not dict or not event:
                raise CustodyError('invalid journal event')
            previous = self._last_digest
            raw = canonical(dict(schema=1, session=self.session, seq=self.sequence + 1,
                                 previous=previous, event=event)) + b'\n'
            if len(raw) > MAX_RECORD or self.sequence >= MAX_EVENTS or len(self.history) + len(raw) > MAX_BYTES:
                raise CustodyError('journal budget exceeded')
            if self.k.write(self.fd, raw) != len(raw):
                raise CustodyError('partial journal write')
            self.k.sync(self.fd)
            self.k.sync(self.parent)
            after = self.k.snapshot(self.fd)
            if (invariant(after) != invariant(self.pin) or after['nlink'] != 1
                    or after['size'] != len(self.history) + len(raw)
                    or after['flags'] != self.pin['flags']):
                raise CustodyError('post-sync journal identity differs')
            self.history += raw
            self.pin = after
            self.check()
            self.sequence += 1
            self._last_digest = hashlib.sha256(raw).hexdigest()
            return self.sequence
        except BaseException:
            self.poisoned = True
            raise


@dataclass(eq=False)
class HeldObject:
    fd: int
    path: str
    parent: int
    name: str
    directory: bool
    mode: int
    birth: dict
    pin: dict
    state: str = 'created'


SOURCE = 'source/home/dot_config/ghostty/config.ghostty'
DEPLOYED = 'config/ghostty/config.ghostty'
SUPPORT = 'state/panda-ghostty-b3b-canary'
DIRS = frozenset(('', 'home', 'data', 'cache', 'runtime', 'tmp', 'system-config', 'system-data', 'source', 'source/home',
                  'source/home/dot_config', 'source/home/dot_config/ghostty', 'config',
                  'config/ghostty', 'config/panda', 'config/panda/generated', 'state', SUPPORT))
FILE_MODES = {SOURCE: 0o644, DEPLOYED: 0o644, 'config/panda/generated/ghostty.conf': 0o600}
for _name in ('canary.py', 'source.before', 'deployed.before', 'lock', 'provisioning.json',
              'baseline.json', 'journal.json', 'cleanup.json', '.journal.json.panda-b3b-stage',
              '.provisioning.json.panda-b3b-stage', '.cleanup.json.panda-b3b-stage'):
    FILE_MODES[SUPPORT + '/' + _name] = 0o600
for _path in (SOURCE, DEPLOYED, 'config/panda/generated/ghostty.conf'):
    _parent, _, _name = _path.rpartition('/')
    FILE_MODES[_parent + '/.' + _name + '.panda-b3b-stage'] = FILE_MODES[_path]
PUBLISH = {path: path.rsplit('/', 1)[0] + '/.' + path.rsplit('/', 1)[1] + '.panda-b3b-stage'
           for path in (SOURCE, DEPLOYED, 'config/panda/generated/ghostty.conf',
                        SUPPORT + '/journal.json', SUPPORT + '/provisioning.json', SUPPORT + '/cleanup.json')}


class CanonicalTmpGrant:
    """Explicit trusted-controller selection of actual /tmp; never a worker claim."""
    def __init__(self, kernel, fd):
        kernel.bind_context()
        self.kernel, self.fd = kernel, fd
        self.pin = kernel.fixed_tmp(fd)

    def verify(self, expected):
        if self.kernel.fixed_tmp(self.fd) != expected:
            raise CustodyError('shared canonical parent changed; preserve')


class TrustedBootstrap:
    """Root-of-trust entry point, called by an independently approved controller.

    Supplied parent/anchor are already trusted *external* held directories, not
    fixture paths or claims. Both stay outside teardown. No environment or file
    can construct this authority on behalf of a worker. The Python interpreter,
    controller and cooperative exclusive FD ownership are trusted prerequisites.
    """
    def __init__(self, kernel, parent_fd, evidence_parent_fd, session_id):
        if not re.fullmatch('[0-9a-f]{32}', session_id) or parent_fd == evidence_parent_fd:
            raise CustodyError('distinct external parents and fresh session ID required')
        self.k, self.parent, self.session_id = kernel, parent_fd, session_id
        kernel.bind_context()
        self.uid, self.gid = kernel.identity()
        if self.uid == 0:
            raise CustodyError('privileged controller unsupported')
        self.parent_pin = kernel.snapshot(parent_fd)
        anchor = kernel.snapshot(evidence_parent_fd)
        for pin in (self.parent_pin, anchor):
            valid(pin, True, 0o700, self.uid, self.gid)
        if self.parent_pin['namespace'] != anchor['namespace']:
            raise CustodyError('external parents belong to different kernel context')
        if (self.parent_pin['dev'], self.parent_pin['ino']) == (anchor['dev'], anchor['ino']):
            raise CustodyError('external parents alias')
        self.ledger = DurableLedger(kernel, evidence_parent_fd, 'ledger-' + session_id,
                                    session_id, self.uid, self.gid)
        self._session = None

    def session(self):
        if self._session is not None:
            raise CustodyError('bootstrap consumed; no second session or replay')
        self._session = ProspectiveSession(self)
        return self._session

    @classmethod
    def canonical(cls, kernel, grant, evidence_parent_fd, session_id):
        if (type(grant) is not CanonicalTmpGrant or grant.kernel is not kernel
                or not isinstance(session_id, str) or not re.fullmatch('[0-9a-f]{32}', session_id)):
            raise CustodyError('explicit original canonical allocation-parent grant required')
        grant.verify(grant.pin)
        self = cls.__new__(cls)
        self.k, self.parent, self.session_id, self.canonical_grant = kernel, grant.fd, session_id, grant
        self.uid, self.gid = kernel.identity()
        if self.uid == 0 or evidence_parent_fd == grant.fd:
            raise CustodyError('nonroot controller and separate private evidence required')
        self.parent_pin = dict(grant.pin)
        anchor = kernel.snapshot(evidence_parent_fd)
        valid(anchor, True, 0o700, self.uid, self.gid)
        if anchor['namespace'] != self.parent_pin['namespace']:
            raise CustodyError('canonical/private kernel context differs')
        self.ledger = DurableLedger(kernel, evidence_parent_fd, 'ledger-' + session_id,
                                    session_id, self.uid, self.gid)
        self._session = None
        return self


class ProspectiveSession:
    """Fixed-role descriptor broker; direct worker filesystem writes unsupported."""
    def __init__(self, bootstrap):
        self.bootstrap, self.k, self.ledger = bootstrap, bootstrap.k, bootstrap.ledger
        self.root_name = ('panda-theme-b3b1-' if hasattr(bootstrap, 'canonical_grant') else 'panda-canary-') + bootstrap.session_id
        self.parent_pin = dict(bootstrap.parent_pin)
        self.objects, self.retired, self._birth_fds = {}, [], []
        self.preserved, self.closed, self._lifecycle = False, False, None
        self.requires_mediation = hasattr(bootstrap, 'canonical_grant')

    def ready(self):
        if self.preserved or self.closed or self.ledger.poisoned:
            raise CustodyError('session preserved/closed; no further operation')

    def registered(self):
        return tuple(sorted(self.objects))

    def _verify(self, obj):
        pin = self.k.snapshot(obj.fd)
        if pin != obj.pin:
            raise CustodyError('original descriptor metadata changed')
        observed = self.k.observe(obj.parent, obj.name)
        if {k: v for k, v in observed.items() if k != 'flags'} != {k: v for k, v in pin.items() if k != 'flags'}:
            raise CustodyError('original parent/name replaced')
        return pin

    def check(self):
        self.ready()
        try:
            self.ledger.check()
            if self.k.identity() != (self.bootstrap.uid, self.bootstrap.gid):
                raise CustodyError('controller identity changed')
            if self.k.snapshot(self.bootstrap.parent) != self.parent_pin:
                raise CustodyError('external allocation parent changed')
            if hasattr(self.bootstrap, 'canonical_grant'):
                self.bootstrap.canonical_grant.verify(self.parent_pin)
            for path, obj in self.objects.items():
                self._verify(obj)
                if obj.directory:
                    expected = sorted(item.name for item in self.objects.values() if item.parent == obj.fd)
                    if self.k.entries(obj.fd) != expected:
                        raise CustodyError('unregistered descendant; preserve entire session')
            for obj in self.retired:
                if self.k.snapshot(obj.fd) != obj.pin or obj.pin['nlink'] != 0:
                    raise CustodyError('superseded descriptor identity changed')
        except BaseException:
            self.preserved = True
            raise

    def _parent_transition(self, fd, before, links):
        after = self.k.snapshot(fd)
        if before['filesystem'] == 0x9123683E:
            links = 0  # btrfs directory i_nlink stays one, unlike ext4.
        if (invariant(after) != invariant(before) or after['flags'] != before['flags']
                or after['nlink'] != before['nlink'] + links):
            raise CustodyError('unsupported parent metadata transition')
        if fd == self.bootstrap.parent:
            self.parent_pin = after
        else:
            for obj in self.objects.values():
                if obj.fd == fd:
                    obj.pin = after
                    break
            else:
                raise CustodyError('mutation parent not registered')

    def create(self, path):
        self.ready()
        if path not in DIRS and path not in FILE_MODES:
            raise CustodyError('role not allowlisted')
        try:
            self.check()
            if path in self.objects:
                raise CustodyError('role already born; no reopen/adoption')
            directory, mode = path in DIRS, 0o700 if path in DIRS else FILE_MODES[path]
            if not path:
                parent, name = self.bootstrap.parent, self.root_name
                before = self.parent_pin
            else:
                parent_path, _, name = path.rpartition('/')
                owner = self.objects[parent_path]
                if not owner.directory:
                    raise CustodyError('parent is not directory')
                parent, before = owner.fd, owner.pin
            safe_name(name)
            self.ledger.append(dict(kind='create-intent', role=path, parent=parent,
                                    name=name, mode=mode, directory=directory))
            initial_mode = 0o700 if directory else 0o600
            fd = self.k.create(parent, name, directory, initial_mode)
            # Retain first descriptor even if every following step fails.
            self._birth_fds.append(fd)
            pin = self.k.snapshot(fd)
            valid(pin, directory, initial_mode, self.bootstrap.uid, self.bootstrap.gid)
            if directory and pin['nlink'] != (2 if pin['filesystem'] == 0xEF53 else 1):
                raise CustodyError('unsupported fresh directory link state')
            if (pin['namespace'] != before['namespace'] or pin['mount'] != before['mount']
                    or pin['dev'] != before['dev']):
                raise CustodyError('birth outside held parent kernel context')
            if any((o.birth['dev'], o.birth['ino']) == (pin['dev'], pin['ino']) for o in self.objects.values()):
                raise CustodyError('birth identity aliases another role')
            if directory and self.k.entries(fd):
                raise CustodyError('new directory not empty')
            obj = HeldObject(fd, path, parent, name, directory, mode, dict(pin), dict(pin))
            self._parent_transition(parent, before, 1 if directory else 0)
            self.k.sync(fd)
            self.k.sync(parent)
            self._verify(obj)
            self.ledger.append(dict(kind='registered', role=path, birth=pin))
            if mode != initial_mode:
                self.ledger.append(dict(kind='mode-intent', role=path, mode=mode))
                self.k.chmod(fd, mode)
                self.k.sync(fd)
                self.k.sync(parent)
                after = self.k.snapshot(fd)
                expected = dict(invariant(pin), mode=stat.S_IFREG | mode)
                if (invariant(after) != expected or after['nlink'] != 1
                        or after['size'] != pin['size'] or after['flags'] != pin['flags']):
                    raise CustodyError('mode transition changed other identity')
                obj.pin = after
                self._verify(obj)
                self.ledger.append(dict(kind='mode-complete', role=path, pin=after))
            self._verify(obj)
            self.objects[path] = obj
            self.check()
            return obj
        except BaseException:
            self.preserved = True
            raise

    def write(self, obj, data):
        """Append to one exact registered regular role; no path/offset/metadata API."""
        self.ready()
        try:
            self.check()
            if (self.objects.get(obj.path) is not obj or obj.directory or obj.state not in ('created', 'appended')
                    or type(data) is not bytes or not data or len(data) > MAX_BYTES):
                raise CustodyError('invalid role append')
            before = self._verify(obj)
            self.ledger.append(dict(kind='append-intent', role=obj.path, size=len(data),
                                    sha256=hashlib.sha256(data).hexdigest()))
            if self.k.write(obj.fd, data) != len(data):
                raise CustodyError('partial role write')
            self.k.sync(obj.fd)
            self.k.sync(obj.parent)
            after = self.k.snapshot(obj.fd)
            if (invariant(after) != invariant(before) or after['nlink'] != 1
                    or after['flags'] != before['flags'] or after['size'] != before['size'] + len(data)):
                raise CustodyError('unsupported append transition')
            if self.k.read(obj.fd, len(data) + 1, before['size']) != data:
                raise CustodyError('post-sync append content differs')
            obj.pin = after
            obj.state = 'appended'
            self._verify(obj)
            self.ledger.append(dict(kind='appended', role=obj.path, pin=after))
            self.check()
        except BaseException:
            self.preserved = True
            raise

    def freeze_metadata(self, obj, image_times=None):
        """Exact authorized metadata transition to zero timestamps, never chmod-any."""
        self.ready()
        try:
            self.check()
            if self.objects.get(obj.path) is not obj or obj.directory or obj.state not in ('created', 'appended'):
                raise CustodyError('invalid metadata-freeze transition')
            before = self._verify(obj)
            times = (0, 0) if image_times is None else tuple(image_times)
            allowed = (0, 0)
            for index, path in enumerate((SOURCE, DEPLOYED)):
                if obj.path in (path, PUBLISH[path]):
                    allowed = (1700000000000000000 + index, 1700000001000000000 + index)
            if times != (0, 0) and times != allowed:
                raise CustodyError('unapproved exact image timestamps')
            self.ledger.append(dict(kind='freeze-intent', role=obj.path, atime=times[0], mtime=times[1]))
            if times == (0, 0):
                self.k.timestamps(obj.fd)
            else:
                self.k.timestamps_exact(obj.fd, *times)
            self.k.sync(obj.fd)
            self.k.sync(obj.parent)
            after = self.k.snapshot(obj.fd)
            expected = dict(invariant(before), atime=times[0])
            if (invariant(after) != expected or after['nlink'] != 1 or after['mtime'] != times[1]
                    or after['size'] != before['size'] or after['flags'] != before['flags']):
                raise CustodyError('unsupported metadata-freeze transition')
            obj.pin, obj.state = after, 'frozen'
            self._verify(obj)
            self.ledger.append(dict(kind='frozen', role=obj.path, pin=after))
            self.check()
        except BaseException:
            self.preserved = True
            raise

    def publish(self, stage, target):
        """Move only one fixed staging role onto its paired target; keep old FD."""
        self.ready()
        if PUBLISH.get(target) != stage:
            raise CustodyError('publication endpoints not allowlisted')
        try:
            self.check()
            obj = self.objects[stage]
            old = self.objects.get(target)
            if obj.directory or obj.state != 'frozen' or old is not None and old.directory:
                raise CustodyError('publication needs frozen stage and regular target')
            parent_path, _, name = target.rpartition('/')
            parent = self.objects[parent_path]
            if parent.fd != obj.parent:
                raise CustodyError('publication parents differ')
            before, stage_pin = dict(parent.pin), dict(obj.pin)
            self.ledger.append(dict(kind='publish-intent', stage=stage, target=target,
                                    birth=obj.birth, replaced=old.birth if old else None))
            self._verify(obj)
            if old is not None:
                self._verify(old)
            self.k.replace(obj.parent, obj.name, parent.fd, name)
            self.k.sync(obj.fd)
            self.k.sync(parent.fd)
            after = self.k.snapshot(obj.fd)
            if (invariant(after) != invariant(stage_pin) or after['nlink'] != 1
                    or after['size'] != stage_pin['size'] or after['flags'] != stage_pin['flags']
                    or after['mtime'] != stage_pin['mtime']):
                raise CustodyError('unexpected publication identity transition')
            if old is not None:
                replaced = self.k.snapshot(old.fd)
                if (invariant(replaced) != invariant(old.pin) or replaced['nlink'] != 0
                        or replaced['size'] != old.pin['size'] or replaced['flags'] != old.pin['flags']):
                    raise CustodyError('replaced object custody differs')
                old.pin, old.state = replaced, 'retired'
                self.retired.append(old)
            self._parent_transition(parent.fd, before, 0)
            del self.objects[stage]
            obj.path, obj.name, obj.pin, obj.state = target, name, after, 'published'
            self.objects[target] = obj
            self._verify(obj)
            self.ledger.append(dict(kind='published', target=target, pin=after))
            self.check()
            return obj
        except BaseException:
            self.preserved = True
            raise

    def unlink_transient(self, obj):
        """Remove only fixed stages or the generated fragment; not support/baseline."""
        self.ready()
        if obj.path not in (*PUBLISH.values(), 'config/panda/generated/ghostty.conf'):
            raise CustodyError('role is not a removable transient')
        try:
            self.check()
            if self.objects.get(obj.path) is not obj or obj.directory:
                raise CustodyError('no registered transient')
            parent = next(o for o in self.objects.values() if o.fd == obj.parent)
            before = dict(parent.pin)
            self.ledger.append(dict(kind='unlink-intent', role=obj.path, birth=obj.birth))
            self._verify(obj)
            self.k.remove(obj.parent, obj.name, False)
            self.k.sync(obj.parent)
            after = self.k.snapshot(obj.fd)
            if (invariant(after) != invariant(obj.pin) or after['nlink'] != 0
                    or after['size'] != obj.pin['size'] or after['flags'] != obj.pin['flags']):
                raise CustodyError('unlink identity differs')
            self._parent_transition(parent.fd, before, 0)
            del self.objects[obj.path]
            obj.pin, obj.state = after, 'retired'
            self.retired.append(obj)
            self.ledger.append(dict(kind='unlinked', role=obj.path, pin=after))
            self.check()
        except BaseException:
            self.preserved = True
            raise

    def start_worker(self, helper_fd, digest, argv):
        """Register one native lifecycle after every private environment role exists.

        Invokes real process machinery with LinuxKernel; offline tests must fake
        the transport. No operator/dynamic-test hook. Run the returned lifecycle
        synchronously before teardown. Helper source/binary execution stays gated.
        """
        self.ready()
        if self.requires_mediation:
            raise CustodyError('canonical session requires enforced mediated lifecycle')
        try:
            self.check()
            required = ('', 'home', 'config', 'data', 'cache', 'state', 'runtime', 'tmp',
                        'system-config', 'system-data')
            if self._lifecycle is not None or any(path not in self.objects for path in required):
                raise CustodyError('single lifecycle and complete private environment required')
            path = Path(__file__).with_name('host_canary_lifecycle.py')
            spec = importlib.util.spec_from_file_location('_panda_host_native_lifecycle', path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            root = self.objects['']
            self._lifecycle = module.NativeLifecycle.start(self.k, self.ledger, helper_fd, digest, argv,
                                                            self.bootstrap.session_id, root.fd, root.pin)
            self.check()
            return self._lifecycle
        except BaseException:
            self.preserved = True
            raise

    @staticmethod
    def lifecycle_module():
        name = '_panda_host_native_lifecycle'
        if name not in sys.modules:
            path = Path(__file__).with_name('host_canary_lifecycle.py')
            spec = importlib.util.spec_from_file_location(name, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            try:
                spec.loader.exec_module(module)
            except BaseException:
                del sys.modules[name]
                raise
        return sys.modules[name]

    def start_mediated_worker(self, helper_fd, digest, runtime, store, plan):
        """One explicit canonical epoch; never resume/reconstruct lost custody."""
        self.ready()
        if not self.requires_mediation or self._lifecycle is not None or getattr(store, 's', None) is not self:
            raise CustodyError('one canonical mediated lifecycle bound to original store required')
        try:
            self.check()
            root = self.objects['']
            receipt = store.root_receipt()
            if receipt != dict(fd=root.fd, birth=dict(root.birth), pin=dict(root.pin),
                               session_id=self.bootstrap.session_id):
                raise CustodyError('broker root receipt differs from original registration')
            module = self.lifecycle_module()
            self._lifecycle = module.NativeLifecycle.start_mediated(
                self.k, self.ledger, helper_fd, digest, self.bootstrap.session_id,
                root.fd, root.pin, runtime=runtime, store=store, plan=plan)
            self.check()
            return self._lifecycle
        except BaseException as exc:
            # Keep partially born native custody even when start has no result.
            self._lifecycle = getattr(exc, 'lifecycle', self._lifecycle)
            self.preserved = True
            raise

    def teardown(self, lifecycle):
        self.ready()
        # A bool, JSON, arbitrary callback or another session's helper is not
        # lifecycle authority. Only this broker's registered native session is.
        if lifecycle is not self._lifecycle or lifecycle is None:
            raise CustodyError('no birth-bound lifecycle registered for this session')
        if self.requires_mediation and not getattr(lifecycle, 'mediated_profile', False):
            raise CustodyError('generic lifecycle cannot authorize canonical teardown')
        try:
            self.check()  # Full graph BEFORE first deletion, not late tree learning.
            lifecycle.finish()
            self.check()
            self.ledger.append(dict(kind='teardown-intent', roles=self.registered()))
            for path in sorted(self.objects, key=lambda p: (p.count('/'), len(p)), reverse=True):
                self.check()
                obj = self.objects[path]
                before = self.parent_pin if obj.parent == self.bootstrap.parent else next(
                    o.pin for o in self.objects.values() if o.fd == obj.parent)
                if not path:
                    self.ledger.append(dict(kind='final-evidence', remaining=[''],
                                            retired=[o.birth['ino'] for o in self.retired]))
                self.ledger.append(dict(kind='remove-intent', role=path, birth=obj.birth))
                self._verify(obj)
                if obj.directory and self.k.entries(obj.fd):
                    raise CustodyError('registered directory not empty')
                self.k.remove(obj.parent, obj.name, obj.directory)
                self.k.sync(obj.parent)
                after = self.k.snapshot(obj.fd)
                if invariant(after) != invariant(obj.pin) or after['nlink'] != 0:
                    raise CustodyError('removed object identity/link status differs')
                self._parent_transition(obj.parent, before, -1 if obj.directory else 0)
                self.ledger.append(dict(kind='removed', role=path, pin=after))
                obj.pin, obj.state = after, 'retired'
                self.retired.append(obj)
                del self.objects[path]
            self.ledger.append(dict(kind='teardown-complete', retained='external ledger and original descriptors'))
            self.closed = True
        except BaseException:
            self.preserved = True
            raise
