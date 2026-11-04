"""Explicit Linux phase capabilities for a separately approved external controller.

Import is inert. No CLI, environment switch, discovery hook or receipt importer.
Constructing authority is not operator approval: the trusted caller must already
have separate permission for the exact effects. All runtime acceptance is pending.
"""
import hashlib
from pathlib import Path
import re
import sys


class NativeGrantError(ValueError):
    pass


class LinuxPhaseGrant:
    def __init__(self, session, helper_fd, digest, runtime, store, reviewed_plan_sha256):
        module = sys.modules.get(type(session).__module__)
        if (module is None or type(session) is not getattr(module, 'ProspectiveSession', None)
                or Path(module.__file__).resolve() != Path(__file__).with_name('host_canary_runtime.py').resolve()):
            raise NativeGrantError('original typed prospective session required')
        self.s, self.phases = session, session.phases_module()
        self.life = self.phases.life
        self.owner, self.claimed, self.transports, self.bound, self.invocations = None, False, [], [], set()
        self.helper_fd, self.digest, self.runtime, self.store = helper_fd, digest, runtime, store
        try:
            session.ready()
            plan = hashlib.sha256(self.life.canonical(self.phases.PHASES)).hexdigest()
            if (type(session.k) is not module.LinuxKernel or hasattr(session.k, 'process_transport')
                    or session._linux_phase_grant is not None or session._phase_controller is not None
                    or session._lifecycle is not None or not session.requires_mediation
                    or session.registered() != ('',) or session.retired or store.s is not session
                    or type(runtime) is not self.life.RuntimeGrant or runtime.k is not session.k
                    or store._plan_bound or reviewed_plan_sha256 != plan
                    or not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest)):
                raise NativeGrantError('fresh original Linux custody and externally reviewed fixed plan required')
            self.plan_sha256 = plan
            self.original = (session.k, session.bootstrap, session.ledger, store, store.program, runtime,
                             session.objects[''], session.bootstrap.parent, session.ledger.parent, session.ledger.fd,
                             session.objects[''].fd, helper_fd, runtime.fd, store.program.fd)
            self.factory = self.life.LinuxTransport.spawn  # never choose an instance-injected factory
            session._linux_phase_grant = self  # retain partial issuance; never reissue
            session.check(); runtime.check(); store.program.check(); store.quiescent()
            session.ledger.append(dict(kind='linux-phase-grant-issued', plan_sha256=plan,
                helper_sha256=digest, runtime_sha256=runtime.digest, root_birth=dict(session.objects[''].birth)))
        except BaseException as exc:
            session.preserved = True
            exc.native_grant = self
            raise

    def _refuse(self, reason):
        self.s.preserved = True
        if self.owner is not None:
            self.owner.refuse(reason)
        raise NativeGrantError(reason)

    def verify(self):
        s = self.s
        current = (s.k, s.bootstrap, s.ledger, self.store, self.store.program, self.runtime,
                   s.objects.get(''), s.bootstrap.parent, s.ledger.parent, s.ledger.fd,
                   s.objects.get('').fd if '' in s.objects else None, self.helper_fd,
                   self.runtime.fd, self.store.program.fd)
        if (current != self.original or s._linux_phase_grant is not self
                or hasattr(s.k, 'process_transport') or self.life.LinuxTransport.spawn != self.factory):
            self._refuse('original Linux grant/controller/descriptor/factory continuity lost')
        s.ready()
        if self.claimed and ((s._phase_controller is not self.owner
                and not (s._phase_controller is None and self.owner.state == "constructing"))
                or self.owner.native is not self or self.owner.plan_digest != self.plan_sha256):
            self._refuse('Linux grant owner/plan changed')

    def claim(self, owner):
        if self.claimed or self.owner is not None or owner.s is not self.s:
            self._refuse('Linux phase grant missing, foreign or already consumed')
        self.claimed, self.owner = True, owner  # consume before any launch or durable transition
        self.verify()
        self.s.ledger.append(dict(kind='linux-phase-grant-consumed', plan_sha256=self.plan_sha256))

    def spawn(self, helper_fd, digest, argv, nonce, root_fd, runtime_fd, *, output_budget):
        self.verify()
        c = self.owner
        if c is None or c.state != 'starting' or c._grant is None:
            self._refuse('no current original native birth grant')
        grant = c._grant
        expected = ['/bin/python3', '-B', '-I', '-S', '/app/host_canary_mediated.py',
                    '--rpc-fd', '3', '--session', c.session_id, '--epoch', str(grant.epoch),
                    '--plan', self.life.canonical(grant.plan).decode('ascii')]
        if (helper_fd != self.helper_fd or digest != self.digest or root_fd != c.root_fd
                or runtime_fd != self.runtime.fd or argv != expected or nonce != grant.nonce
                or nonce in self.invocations or len(self.invocations) >= 4
                or type(output_budget) is not self.phases.Capture or output_budget.owner is not c
                or output_budget.grant is not grant):
            self._refuse('native spawn differs from original approved lifetime')
        self.invocations.add(nonce)
        try:
            transport = self.factory(helper_fd, digest, argv, nonce, root_fd, runtime_fd,
                                     output_budget=output_budget)
            self.transports.append(transport)
            if type(transport) is not self.life.LinuxTransport:
                self._refuse('concrete Linux transport required')
            return transport
        except BaseException as exc:
            partial = getattr(exc, 'transport', None)
            if partial is not None and not any(t is partial for t in self.transports):
                self.transports.append(partial)
            raise

    def bind_transport(self, transport):
        if (type(transport) is not self.life.LinuxTransport
                or not any(t is transport for t in self.transports)
                or any(t is transport for t in self.bound)
                or any(t.pid_pin == transport.pid_pin or t.ns_pin == transport.ns_pin for t in self.bound)):
            self._refuse('new native birth aliases missing or already retained custody')
        transport.check()
        self.bound.append(transport)

    def check_closed(self, transport):
        self.verify()
        if not any(t is transport for t in self.bound):
            self._refuse('unregistered native closed lifetime')
        transport.check_closed()


class LinuxRemovalGrant:
    """Separate external-owner decision; cannot be inferred from a completed plan."""
    def __init__(self, controller, reviewed_graph_sha256):
        native = controller.native
        if type(native) is not LinuxPhaseGrant or native.owner is not controller:
            raise NativeGrantError('original native controller required for removal review')
        self.owner, self.claimed, self.graph = controller, False, reviewed_graph_sha256
        try:
            controller.continuity()
            if (controller.state != 'ready' or len(controller.receipts) != 4 or len(controller.scopes) != 4
                    or controller.requests.active or controller._native_removal is not None
                    or controller.store.phase_checkpoint('D') != controller.receipts[-1]['checkpoint']
                    or reviewed_graph_sha256 != controller.receipts[-1]['checkpoint']['graph_sha256']):
                raise NativeGrantError('reviewed exact final graph and complete closure collection required')
            controller._native_removal = self
            controller.ledger.append(dict(kind='linux-removal-grant-issued', graph_sha256=self.graph))
        except BaseException as exc:
            controller.refuse('partial native removal authorization', exc)

    def check(self, controller):
        if (controller is not self.owner or controller._native_removal is not self
                or not self.claimed or controller.receipts[-1]['checkpoint']['graph_sha256'] != self.graph):
            controller.refuse('original consumed native removal grant required')

    def claim(self, controller):
        if controller is not self.owner or self.claimed:
            controller.refuse('native removal grant foreign or already consumed')
        self.claimed = True
        self.check(controller)
        controller.ledger.append(dict(kind='linux-removal-grant-consumed', graph_sha256=self.graph))
