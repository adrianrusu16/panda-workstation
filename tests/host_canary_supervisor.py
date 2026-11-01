"""Source-only custody consistency checks. No accepted runtime/cleanup adapter.

Supplied descriptors and OS boundaries are allegations, not exclusive-birth or
lifecycle authority. Models never allocate fixtures or issue live capabilities.
"""
from dataclasses import dataclass
import hashlib
import json
import re
import stat

MAX_RECORD = 4096
MAX_EVENTS = 100000
MAX_BYTES = 64 * 1024 * 1024


class SupervisorError(ValueError):
    pass


def basename(value):
    if (not isinstance(value, str) or not value or value in ('.', '..')
            or '/' in value or '\\' in value
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise SupervisorError('one safe basename required')
    return value


@dataclass(frozen=True)
class Binding:
    fd: int
    generation: int
    pin: tuple
    directory: bool
    parent: object = None
    name: str = ''


class DescriptorVerifier:
    """Consistency of alleged held FDs; counters are not kernel OFD identity.

    Exclusive descriptor ownership is required. Unknown close/reopen onto the
    same inode cannot be detected; known loss permanently revokes this verifier.
    No default OS boundary exists, and this component opens no paths.
    Mount/namespace values are injected unverified context, not kernel proof;
    binding those labels to kernel descriptors remains a future adapter gate.
    Directory link count is pinned too: even a legitimate new child directory
    may cause refusal. No metadata-transition backend is accepted in this stage.
    """
    def __init__(self, boundary, uid, gid, namespace):
        self.boundary, self.uid, self.gid, self.namespace = boundary, uid, gid, namespace
        self.poisoned = False
        self._active = {}
        self._generation = 0

    def fail(self, message):
        self.poisoned = True
        raise SupervisorError(message)

    def ready(self):
        if self.poisoned:
            raise SupervisorError('descriptor custody revoked; preserve resources')

    def _pin(self, info, fd, directory):
        expected_mode = (stat.S_IFDIR | 0o700) if directory else (stat.S_IFREG | 0o600)
        if (info.st_mode != expected_mode or info.st_uid != self.uid or info.st_gid != self.gid
                or info.st_nlink < 1 or not directory and info.st_nlink != 1
                or self.boundary.namespace() != self.namespace or self.boundary.listxattr(fd)):
            self.fail('descriptor metadata or namespace differs')
        return (info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode,
                info.st_nlink, self.boundary.mount_id(fd), self.namespace)

    def _bind(self, fd, directory, parent=None, name=''):
        self.ready()
        try:
            if parent is not None:
                basename(name)  # Reject before even parent verification calls the boundary.
                self.verify(parent)
                if not parent.directory:
                    self.fail('parent must be a held directory')
            if type(fd) is not int or fd < 0 or fd in self._active:
                self.fail('invalid or already held descriptor')
            pin = self._pin(self.boundary.fstat(fd), fd, directory)
            self._generation += 1
            binding = Binding(fd, self._generation, pin, directory, parent, name)
            self._active[fd] = binding
            self.verify(binding)
            return binding
        except BaseException:
            self.poisoned = True
            raise

    def parent(self, fd):
        return self._bind(fd, True)

    def child(self, fd, parent, name, *, directory):
        return self._bind(fd, directory, parent, name)

    def verify(self, binding):
        self.ready()
        try:
            if not isinstance(binding, Binding) or self._active.get(binding.fd) is not binding:
                self.fail('foreign, stale or lost descriptor binding')
            if binding.parent is not None:
                self.verify(binding.parent)
            info = self.boundary.fstat(binding.fd)
            if self._pin(info, binding.fd, binding.directory) != binding.pin:
                self.fail('held descriptor identity changed')
            if binding.parent is not None:
                observed = self.boundary.stat(binding.name, dir_fd=binding.parent.fd,
                                              follow_symlinks=False)
                if self._pin(observed, binding.fd, binding.directory) != binding.pin:
                    self.fail('parent/name binding changed')
            return info
        except BaseException:
            self.poisoned = True
            raise

    def lost(self, binding):
        self._active.pop(binding.fd, None)
        self.poisoned = True


@dataclass(frozen=True)
class Registration:
    sequence: int
    digest: str


class RegistryWriter:
    """Bounded writes to an alleged existing empty registry; no birth proof.

    Verifies fixed identity/owner/mode/link/mount/namespace and expected size,
    not ctime continuity or physical power-loss durability. It does not establish
    FD flags, current offset/O_APPEND, exclusive locking or whole-history content
    readback. Those require a future accepted adapter; this model grants no real
    append/durability authority. No replay/import API.
    """
    def __init__(self, verifier, registry, session_id):
        self.verifier, self.registry = verifier, registry
        self.poisoned = False
        self.sequence, self.bytes = 0, 0
        self.previous = '0' * 64
        self._acks = {}
        if not isinstance(session_id, str) or not re.fullmatch('[0-9a-f]{32}', session_id):
            self.poisoned = True
            raise SupervisorError('invalid session ID')
        self.session_id = session_id
        try:
            if registry.directory or registry.parent is None:
                raise SupervisorError('registry needs a held regular file and parent')
            self.check()
        except BaseException:
            self.poisoned = True
            raise

    def check(self):
        if self.poisoned:
            raise SupervisorError('registry poisoned; preserve partial effects')
        try:
            info = self.verifier.verify(self.registry)
            if info.st_size != self.bytes:
                raise SupervisorError('registry size changed')
        except BaseException:
            self.poisoned = True
            raise

    def append(self, event):
        if self.poisoned:
            raise SupervisorError('registry poisoned; preserve partial effects')
        try:
            if type(event) is not dict or not event:
                raise SupervisorError('nonempty event mapping required')
            event_raw = json.dumps(event, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
            record = dict(schema=1, session=self.session_id, seq=self.sequence + 1,
                          previous=self.previous, event=event,
                          event_sha256=hashlib.sha256(event_raw).hexdigest())
            raw = (json.dumps(record, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()
            if len(raw) > MAX_RECORD or self.sequence >= MAX_EVENTS or self.bytes + len(raw) > MAX_BYTES:
                raise SupervisorError('registry budget exceeded')
            self.check()
            count = self.verifier.boundary.write(self.registry.fd, raw)
            if type(count) is not int or count != len(raw):
                raise SupervisorError('short/invalid registry write; preserve partial bytes')
            self.verifier.boundary.fsync(self.registry.fd)
            self.verifier.boundary.fsync(self.registry.parent.fd)
            # Do not advance the committed sequence or issue an ack before checks.
            info = self.verifier.verify(self.registry)
            if info.st_size != self.bytes + len(raw):
                raise SupervisorError('post-sync registry size differs')
            digest = hashlib.sha256(raw).hexdigest()
            ack = Registration(self.sequence + 1, digest)
            self.sequence += 1
            self.bytes += len(raw)
            self.previous = digest
            self._acks[ack.sequence] = ack
            return ack
        except BaseException as exc:
            self.poisoned = True
            if isinstance(exc, SupervisorError):
                raise
            raise SupervisorError('registry failure; preserve partial effects') from exc

    def owns(self, ack):
        return (not self.poisoned and isinstance(ack, Registration)
                and self._acks.get(ack.sequence) is ack)


class SessionModel:
    """Diagnostic ordering only. No live capability or lifecycle acceptance API."""
    def __init__(self, writer):
        self.writer = writer
        self.preserved = False
        self.reason = ''
        self._objects = {}

    def preserve(self, reason):
        self.preserved, self.reason = True, str(reason)

    def _ready(self):
        if self.preserved or self.writer.poisoned or self.writer.verifier.poisoned:
            self.preserve('uncertain custody or durability')
            raise SupervisorError('session preserved; no further grants')

    def intent(self, object_id, parent, name):
        self._ready()
        try:
            basename(name)
            if not isinstance(object_id, str) or not re.fullmatch('[a-z][a-z0-9-]{0,63}', object_id) or object_id in self._objects:
                raise SupervisorError('invalid or duplicate object ID')
            self.writer.verifier.verify(parent)
            if not parent.directory:
                raise SupervisorError('intent parent is not a directory')
            ack = self.writer.append(dict(kind='create-intent', object_id=object_id,
                                          parent_generation=parent.generation, name=name))
            self._objects[object_id] = [parent, name, ack, None]
        except BaseException:
            self.preserve('intent failed')
            raise

    def created(self, object_id, binding):
        self._ready()
        try:
            parent, name, intent, current = self._objects[object_id]
            if current is not None or not self.writer.owns(intent) or binding.parent is not parent or binding.name != name:
                raise SupervisorError('creation lacks matching local durable intent')
            self.writer.verifier.verify(binding)
            self.writer.append(dict(kind='registered', object_id=object_id, generation=binding.generation))
            self.writer.verifier.verify(binding)
            self._objects[object_id][3] = binding
        except BaseException as exc:
            self.preserve('registration failed')
            raise SupervisorError('creation registration refused') from exc

    def use(self, object_id):
        self._ready()
        try:
            binding = self._objects[object_id][3]
            if binding is None:
                raise SupervisorError('object not durably registered')
            self.writer.verifier.verify(binding)
            self.writer.check()
            return 'MODEL ONLY: ' + object_id
        except BaseException as exc:
            self.preserve('use failed')
            raise SupervisorError('model use refused') from exc

    def cleanup_plan(self, *untrusted_claims):
        # No supplied record, bool, callback, environment or constructor flag can
        # accept an unimplemented runtime lifecycle/cleanup backend.
        raise SupervisorError('live lifecycle and cleanup disabled; preserve resources')
