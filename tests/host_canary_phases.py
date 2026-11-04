"""Four-phase controller; live custody is not established by its offline tests.

The existing NativeLifecycle protocol is exercised without changing its timers.
The default entry refuses LinuxKernel and implicit native transports.
The explicit LinuxPhaseGrant entry is separate from the injected default.
No import, receipt, matching path or saved PID can recreate this controller.
"""
import hashlib
import importlib.util
from pathlib import Path
import secrets
import stat
import sys
import time


def load(name, path):
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            del sys.modules[name]
            raise
    return sys.modules[name]


HERE = Path(__file__).parent
life = load('_panda_host_native_lifecycle', HERE / 'host_canary_lifecycle.py')
RPC_PATH = HERE.parent / 'theme/panda/common/host_canary_rpc.py'
if not RPC_PATH.is_file():
    RPC_PATH = HERE / 'host_canary_rpc.py'
rpc = load('_panda_phase_rpc', RPC_PATH)
PHASES = (('A', ('initialize', 'provision')), ('B', ('install',)),
          ('C', ('recover',)), ('D', ('cleanup_outputs', 'recover')))
OUTPUT_LIMIT = 1024 * 1024


class PhaseError(ValueError):
    pass


class BirthGrant:
    """Object identity held only by the original controller; never serialized."""
    def __init__(self, owner, epoch, nonce, plan):
        self.owner, self.epoch, self.nonce, self.plan = owner, epoch, nonce, plan


class Capture:
    """Injected transport retains bytes first, then charges this exact lifetime."""
    def __init__(self, owner, grant):
        self.owner, self.grant = owner, grant
        self.used = {'stdout': 0, 'stderr': 0}
        self.hashes = {s: hashlib.sha256() for s in self.used}

    def _active(self, stream):
        owner = self.owner
        if (owner._grant is not self.grant or owner.state not in ('starting', 'running', 'closing')
                or stream not in self.used):
            owner.refuse('stale or invalid output capture')

    def remaining(self, stream):
        self._active(stream)
        return max(0, min(OUTPUT_LIMIT - self.used[stream], OUTPUT_LIMIT - self.owner.output[stream]))

    def charge(self, stream, raw):
        self._active(stream)
        if type(raw) is not bytes:
            self.owner.refuse('invalid output capture bytes')
        self.used[stream] += len(raw)
        self.owner.output[stream] += len(raw)
        self.hashes[stream].update(raw)
        if self.used[stream] > OUTPUT_LIMIT or self.owner.output[stream] > OUTPUT_LIMIT:
            self.owner.refuse('cumulative output ceiling exceeded')

    def witness(self):
        return {**{s + '_bytes': n for s, n in self.used.items()},
                **{s + '_sha256': h.hexdigest() for s, h in self.hashes.items()}}


class PhaseLifecycle(life.NativeLifecycle):
    @classmethod
    def create(cls, owner, grant):
        if owner._grant is not grant or owner.state != 'starting' or owner._birth_consumed:
            owner.refuse('stale or consumed birth grant')
        owner._birth_consumed = True
        owner.continuity()
        runtime, store = owner.runtime, owner.store
        if runtime.file('/app/host_canary.py') != store.program.data:
            owner.refuse('runtime engine differs from original approved source')
        for path in ('/app/host_canary_rpc.py', '/app/host_canary_mediated.py', '/bin/python3'):
            if not runtime.file(path):
                owner.refuse('approved runtime entry absent')
        if not runtime.objects['bin/python3']['pin']['mode'] & 0o100:
            owner.refuse('approved interpreter not executable')
        server = rpc.Server(store, owner.ledger, owner.session_id, grant.epoch, budget=owner.requests)
        owner._pending_server = server
        argv = ['/bin/python3', '-B', '-I', '-S', '/app/host_canary_mediated.py',
                '--rpc-fd', '3', '--session', owner.session_id, '--epoch', str(grant.epoch),
                '--plan', life.canonical(grant.plan).decode('ascii')]
        capture = Capture(owner, grant)
        scope = cls.start(owner.k, owner.ledger, owner.helper_fd, owner.digest, argv,
                          grant.nonce, owner.root.fd, owner.root.pin,
                          _mediation=(runtime, store, server, owner.root_birth), _capture=capture, _factory=owner._factory)
        scope.owner, scope.grant, scope.capture = owner, grant, capture
        scope.server, scope._closed_proof = server, None
        try:
            if owner.native is not None:
                owner.native.bind_transport(scope.transport)
        except BaseException as exc:
            exc.lifecycle = scope  # retain full birth/server/capture custody on binding failure
            raise
        return scope

    def _refresh_root(self):
        receipt = self.owner.store.root_receipt()
        if (receipt['fd'] != self.root_fd or receipt['birth'] != self.owner.root_birth
                or receipt['session_id'] != self.owner.session_id
                or self.k.snapshot(self.root_fd) != receipt['pin']):
            raise PhaseError('original root birth/descriptor changed')
        if receipt['pin'] != self.root_pin:
            self.ledger.append({'kind': 'broker-root-transition', 'birth': receipt['birth'], 'pin': receipt['pin']})
            self.root_pin = dict(receipt['pin'])

    def _quiescent(self):
        super()._quiescent()
        self.owner.store.quiescent()

    def seal_closed(self):
        witness = self._closure_witness
        if (not self.closed or not self.ran or self.preserved or not self.server.retired
                or not self.server.quiescent or type(self._closed_sequence) is not int
                or not isinstance(witness, dict) or witness.get('helper_status') != 0
                or witness.get('init_pidfd_exited') is not True or witness.get('namespace_retained') is not True):
            raise PhaseError('incomplete original namespace closure')
        if any(witness.get(key) != value for key, value in self.capture.witness().items()):
            raise PhaseError('capture/closure output evidence differs')
        self._closed_proof = (self.transport, dict(self.birth), dict(witness), self._closed_sequence)
        self.verify_closed()

    def verify_closed(self):
        proof = self._closed_proof
        if (proof is None or not self.closed or not self.ran or self.preserved
                or self.transport is not proof[0] or self.birth != proof[1]
                or self._closure_witness != proof[2] or self._closed_sequence != proof[3]
                or self.root_fd != self.owner.root.fd or self._mediation[3] != self.owner.root_birth
                or not self.server.retired or not self.server.quiescent):
            raise PhaseError('closed lifetime identity/proof changed')
        # Never call check()/finish()/wait_closed() here: root metadata may have
        # legitimately advanced, and an old namespace must never be reaped again.
        if self.owner.native is not None:
            self.owner.native.check_closed(self.transport)
        else:
            self.transport.check()


class PhaseController:
    def __init__(self, session, helper_fd, digest, runtime, store, *, _native=None):
        broker_module = sys.modules.get(type(store).__module__)
        if (broker_module is None or type(store) is not getattr(broker_module, 'BrokerStore', None)
                or Path(broker_module.__file__).resolve() != (HERE / 'host_canary_broker.py').resolve()):
            raise PhaseError('original broker implementation required')
        self.s, self.k, self.ledger = session, session.k, session.ledger
        self.store, self.runtime, self.helper_fd, self.digest = store, runtime, helper_fd, digest
        self.state, self._grant, self._birth_consumed = 'constructing', None, False
        self.native, self._native_removal, self._removal = _native, None, None
        self._active = self._pending_server = None
        self.scopes, self.receipts, self.output = [], [], {'stdout': 0, 'stderr': 0}
        self._original = (session.bootstrap, session.k, session.ledger, store, store.program, runtime)
        self._factory = getattr(self.k, 'process_transport', None)
        if _native is not None:
            if type(_native) is not session.linux_module().LinuxPhaseGrant or _native.s is not session:
                raise PhaseError('original explicit Linux phase grant required')
            self._factory = _native.spawn
        elif any(base.__name__ == 'LinuxKernel' for base in type(self.k).__mro__) or not callable(self._factory):
            raise PhaseError('offline phases require explicit injected boundaries; live execution unsupported')
        if (session._lifecycle is not None or session._phase_controller is not None
                or store.s is not session or not session.requires_mediation
                or session.registered() != ('',) or session.retired
                or type(runtime) is not life.RuntimeGrant or runtime.k is not self.k
                or store._plan_bound):
            raise PhaseError('fresh original typed session/store/runtime required')
        self.root = session.objects['']
        self.root_birth = dict(self.root.birth)
        self.root_fd = self.root.fd
        self._descriptor_fds = (helper_fd, runtime.fd, store.program.fd)
        self.session_id = session.bootstrap.session_id
        self._helper_pin = self.k.snapshot(helper_fd)
        self._helper_bytes = self.k.read(helper_fd, self._helper_pin['size'] + 1, 0)
        if (not stat.S_ISREG(self._helper_pin['mode']) or not self._helper_pin['mode'] & 0o100
                or self._helper_pin['mode'] & 0o6022
                or self._helper_pin['uid'] != session.bootstrap.uid or self._helper_pin['fdflags'] != 1
                or self._helper_pin['nlink'] != 1 or self._helper_pin['xattrs']
                or not 0 < len(self._helper_bytes) <= 4 * 1024 * 1024 or len(self._helper_bytes) != self._helper_pin['size']
                or hashlib.sha256(self._helper_bytes).hexdigest() != digest):
            raise PhaseError('original reviewed helper descriptor differs')
        self.plan_digest = hashlib.sha256(life.canonical(PHASES)).hexdigest()
        self.requests = rpc.RequestBudget(store, self.ledger, self.session_id)
        self._requests_original = self.requests
        try:
            if self.native is not None:
                self.native.claim(self)
            session.check(); runtime.check(); store.quiescent()
            self.ledger.append({'kind': 'phases-intent', 'plan_sha256': self.plan_digest,
                                'root_birth': self.root_birth, 'root_fd': self.root_fd, 'helper_sha256': digest, 'runtime_sha256': runtime.digest})
            session._phase_controller = self
            store.bind_phases(self)
            self.state = 'ready'
        except BaseException as exc:
            self.refuse('partial phase-controller initialization', exc)

    def refuse(self, reason, error=None):
        self.state = 'preserved'
        self._original[3].preserve(reason)
        server = self._pending_server
        if server is not None:
            server.abort(reason)
        if error is not None:
            error.phase_controller = self
            raise error
        raise PhaseError(reason)

    def continuity(self):
        original = self._original
        if (self.state in ('preserved', 'complete') or self.s._phase_controller is not self
                or self.s.bootstrap is not original[0] or self.s.k is not original[1]
                or self.s.ledger is not original[2] or self.store is not original[3]
                or self.store.program is not original[4] or self.runtime is not original[5]
                or self.s._lifecycle is not None or self.store._phase_owner is not self
                or self.requests is not self._requests_original
                or self.s.objects.get('') is not self.root or self.root.birth != self.root_birth
                or self.root.fd != self.root_fd
                or (self.helper_fd, self.runtime.fd, self.store.program.fd) != self._descriptor_fds
                or self.native is None and getattr(self.k, 'process_transport', None) != self._factory):
            raise PhaseError('original controller/descriptor/approval continuity lost')
        if self.native is not None:
            self.native.verify()
        self.s.check(); self.runtime.check(); self.store.program.check()
        if self.k.snapshot(self.helper_fd) != self._helper_pin or self.k.read(self.helper_fd, len(self._helper_bytes) + 1, 0) != self._helper_bytes:
            raise PhaseError('held helper changed')
        for scope in self.scopes:
            if scope is not self._active:
                scope.verify_closed()

    def require_dispatch(self):
        if (self.s._phase_controller is not self or self.state != 'running'
                or self._grant is None or self._grant.epoch != len(self.receipts) + 1):
            self.refuse('no current phase mutation/read grant')

    def run_phase(self, phase):
        start, cpu = time.perf_counter(), time.process_time()
        try:
            self.continuity()
            index = len(self.receipts)
            if self.state != 'ready' or index >= 4 or phase != PHASES[index][0] or len(self.scopes) != index:
                self.refuse('missing, repeated or reordered phase')
            if index and self.store.phase_checkpoint(PHASES[index - 1][0]) != self.receipts[-1]['checkpoint']:
                self.refuse('previous checkpoint changed after closure')
            self.store.quiescent()
            epoch = index + 1
            plan = [{'action': action} for action in PHASES[index][1]]
            nonce = secrets.token_hex(16)
            if nonce == self.session_id or any(scope.session == nonce for scope in self.scopes):
                self.refuse('native invocation identity repeated')
            self.ledger.append({'kind': 'phase-intent', 'phase': phase, 'epoch': epoch, 'invocation': nonce,
                                'plan': plan, 'plan_sha256': self.plan_digest, 'root_birth': self.root_birth, 'root_fd': self.root_fd,
                                'predecessor': None if not index else self.receipts[-1]['closure_sequence'],
                                'checkpoint': None if not index else self.receipts[-1]['checkpoint'],
                                'requests': self.requests.total, 'output': dict(self.output),
                                'cache_bytes': self.requests.cache_bytes, 'cache_entries': self.requests.cache_entries})
            self.state, self._grant, self._birth_consumed = 'starting', BirthGrant(self, epoch, nonce, plan), False
            self.requests.open_epoch(epoch)
            scope = PhaseLifecycle.create(self, self._grant)
            self._active = scope
            self.scopes.append(scope)
            self.ledger.append({'kind': 'phase-born', 'phase': phase, 'epoch': epoch, 'birth': scope.birth})
            self.state = 'running'
            worker_start = time.perf_counter()
            if scope.run() != 0:
                self.refuse('phase worker failed')
            worker_seconds = time.perf_counter() - worker_start
            self.state = 'closing'
            checkpoint = self.store.phase_checkpoint(phase)
            self.ledger.append({'kind': 'phase-checkpoint', 'phase': phase, 'epoch': epoch, 'checkpoint': checkpoint})
            scope.server.retire()
            scope.finish()
            scope.seal_closed()
            self.continuity()
            if self.store.phase_checkpoint(phase) != checkpoint:
                self.refuse('checkpoint changed during closure')
            self.requests.close_epoch(epoch)
            receipt = dict(phase=phase, epoch=epoch, checkpoint=checkpoint,
                           closure_sequence=scope._closed_sequence, requests=self.requests.total, output=dict(self.output),
                           cache_bytes=self.requests.cache_bytes, cache_entries=self.requests.cache_entries)
            self.ledger.append({'kind': 'phase-complete', **receipt})
            self.receipts.append(receipt)
            self._active = self._pending_server = self._grant = None
            self.state = 'ready'
            return dict(receipt, seconds=time.perf_counter() - start, cpu_seconds=time.process_time() - cpu,
                        worker_seconds=worker_seconds)
        except BaseException as exc:
            partial = getattr(exc, 'lifecycle', None)
            if partial is not None:
                self._active = partial
            self.refuse('ambiguous phase transition', exc)

    def authorize_removal(self, session):
        """One-way final evidence barrier at the actual typed deletion entry."""
        try:
            if self.native is not None:
                if type(self._removal) is not self.s.linux_module().LinuxRemovalGrant:
                    self.refuse('separate original native removal authorization required')
                self._removal.check(self)
            if session is not self.s or session._phase_controller is not self:
                self.refuse('foreign removal session')
            self.continuity()
            if self.state != 'ready' or len(self.receipts) != 4 or len(self.scopes) != 4 or self.requests.active:
                self.refuse('all four closed phases required for removal')
            if self.store.phase_checkpoint('D') != self.receipts[-1]['checkpoint']:
                self.refuse('final checkpoint changed before removal')
            self.ledger.append({'kind': 'phases-final', 'closures': [s._closed_sequence for s in self.scopes],
                                'requests': self.requests.total, 'output': dict(self.output),
                                'cache_bytes': self.requests.cache_bytes, 'cache_entries': self.requests.cache_entries})
            self.state = 'removing'  # synchronized evidence before a single removal attempt
        except BaseException as exc:
            self.refuse('incomplete final collection authorization', exc)

    def teardown(self, *, removal=None):
        try:
            if self.native is not None:
                if type(removal) is not self.s.linux_module().LinuxRemovalGrant:
                    self.refuse('separate original native removal authorization required')
                removal.claim(self)
                self._removal = removal
            elif removal is not None:
                self.refuse('native removal grant cannot authorize injected teardown')
            self.continuity()
            if self.state != 'ready' or len(self.receipts) != 4 or len(self.scopes) != 4 or self.requests.active:
                self.refuse('all four closed phases required')
            for scope in self.scopes:
                scope.verify_closed()
            if self.store.phase_checkpoint('D') != self.receipts[-1]['checkpoint']:
                self.refuse('final checkpoint changed')
            self.s._remove_registered(self)
            self.state = 'complete'
        except BaseException as exc:
            self.refuse('incomplete phase collection teardown', exc)
