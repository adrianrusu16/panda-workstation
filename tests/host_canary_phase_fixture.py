"""Synthetic native packets + in-memory engine task; no OS worker/namespace.

The Python thread is a cooperative test task, not a native custody witness.
All kernel proof is deliberately fake and the controller refuses live adapters.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import queue
import stat
import sys
import threading
from unittest.mock import patch

HERE = Path(__file__).parent
REPO = HERE.parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    api = importlib.util.module_from_spec(spec); sys.modules[name] = api; spec.loader.exec_module(api)
    return api


class Fixture:
    def __init__(self, real_program=False):
        tests = load('phase_broker_fixture', HERE / 'test_host_canary_broker.py')
        self.case = tests.BrokerTests(); self.case.setUp(); self.case.call('close')
        self.k, self.s, self.store = self.case.k, self.case.s, self.case.store
        self.api = self.s.phases_module()
        self.mediated = load('host_canary_mediated', REPO / 'theme/panda/common/host_canary_mediated.py')
        self.store.baseline = (REPO / 'home/dot_config/ghostty/config.ghostty').read_bytes()
        if real_program:
            data = (REPO / 'theme/panda/common/host_canary.py').read_bytes()
            fd = self.file(data)
            self.store.program = self.case.api.ApprovedProgramGrant(self.k, fd, hashlib.sha256(data).hexdigest())
        source = self.store.program.data
        self.helper_fd = self.file(b'approved synthetic helper', 0o700)
        self.helper_digest = hashlib.sha256(self.k.journals[self.helper_fd]).hexdigest()
        root = self.k.node(True)
        app, binary = self.k.node(True), self.k.node(True)
        self.k.names[root, 'app'], self.k.names[root, 'bin'] = app, binary
        files = {'host_canary.py': source, 'host_canary_rpc.py': b'# synthetic rpc',
                 'host_canary_mediated.py': b'# synthetic worker'}
        for name, raw in files.items(): self.k.names[app, name] = self.file(raw)
        self.k.names[binary, 'python3'] = self.file(b'synthetic interpreter', 0o755)
        self.k.runtime_open = lambda parent, name: self.k.names[parent, name]
        rows = []
        def manifest(fd, path):
            pin = self.k.snapshot(fd); directory = stat.S_ISDIR(pin['mode'])
            row = dict(path=path, mode=stat.S_IMODE(pin['mode']), directory=directory)
            if not directory:
                raw = self.k.read(fd, pin['size'] + 1, 0)
                row.update(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
            rows.append(row)
            if directory:
                for name in self.k.entries(fd): manifest(self.k.names[fd, name], path + '/' + name if path else name)
        manifest(root, '')
        self.runtime = self.api.life.RuntimeGrant(self.k, root, hashlib.sha256(self.api.life.canonical(rows)).hexdigest())
        self.transports, self.hook, self.spawn_count = [], lambda point, transport: None, 0
        self.wire_hook = lambda direction, transport, raw: raw
        self.k.process_transport = self.spawn
        self.guards = []
        for owner in (self.case.api.runtime.LinuxKernel,):
            for name, value in vars(owner).items():
                if callable(value):
                    guard = patch.object(owner, name, side_effect=AssertionError('real Linux adapter forbidden'))
                    guard.start(); self.guards.append(guard)
        guard = patch.object(self.api.life.LinuxTransport, 'spawn', side_effect=AssertionError('real native spawn forbidden'))
        guard.start(); self.guards.append(guard)

    def file(self, raw, mode=0o644):
        fd = self.k.node(False, mode); self.k.journals[fd] = raw
        self.k.nodes[fd].update(size=len(raw), flags=262144)
        return fd

    def controller(self):
        return self.s.offline_phases(self.helper_fd, self.helper_digest, self.runtime, self.store)

    def spawn(self, helper, digest, argv, nonce, root, runtime, *, output_budget):
        self.spawn_count += 1
        transport = Transport(self, helper, argv, nonce, root, output_budget)
        self.transports.append(transport)
        try:
            self.hook('spawn', transport)
            return transport
        except BaseException as exc:
            exc.transport = transport  # same partial-retention contract as LinuxTransport.spawn
            raise

    def close(self):
        for transport in self.transports: transport.abort_task()
        for guard in reversed(self.guards): guard.stop()


class Transport:
    def __init__(self, fixture, helper, argv, nonce, root, capture):
        self.f, self.helper, self.nonce, self.root, self.capture = fixture, helper, nonce, root, capture
        self.epoch = int(argv[argv.index('--epoch') + 1])
        self.session = argv[argv.index('--session') + 1]
        self.plan = json.loads(argv[argv.index('--plan') + 1])
        self.original_helper = fixture.k.snapshot(helper)
        self.events, self.replies = queue.Queue(), queue.Queue()
        self.birth = None; self.closed = self.bad = self.aborted = False
        self.thread = None; self.results = []; self.worker_error = None; self.waits = 0
        self.stdout, self.stderr, self.commands = bytearray(), bytearray(), []
        self.last_command = None
        self.frames_tx = self.frames_rx = self.bytes_tx = self.bytes_rx = 0
        pin = fixture.k.snapshot(root)
        self.events.put(f'BIRTH {nonce} {100 + self.epoch} {500 + self.epoch} {pin["dev"]} {pin["ino"]}')

    def check(self):
        if self.bad or self.f.k.snapshot(self.helper) != self.original_helper:
            raise OSError('lost original fake helper/namespace/pidfd custody')

    def bind_birth(self, pid, namespace):
        if self.birth is not None or pid != 100 + self.epoch or namespace != 500 + self.epoch:
            raise ValueError('invalid fake original birth')
        self.birth = dict(pid=pid, namespace=namespace, pidfd=10000 + 2 * self.epoch, nsfd=10001 + 2 * self.epoch)
        return dict(self.birth)

    def receive(self, timeout):
        self.f.hook('receive', self)
        try: return self.events.get(timeout=timeout)
        except queue.Empty: raise TimeoutError('missing synthetic lifecycle event')

    def send(self, packet):
        self.check(); self.last_command = packet; self.f.hook('send', self)
        prefix = f'RPC_REPLY {self.nonce} 1 2 '
        if packet.startswith(prefix):
            raw = packet[len(prefix):].encode('ascii')
            self.frames_rx += 1; self.bytes_rx += len(raw); self.replies.put(self.f.wire_hook('reply', self, raw)); return
        self.commands.append(packet)
        if packet == 'START ' + self.nonce: self.events.put(f'TASK {self.nonce} 1 BIRTH 2 1')
        elif packet == f'ACK {self.nonce} 1':
            pin = self.f.runtime.root_pin
            self.events.put(f'POLICY {self.nonce} 1 2 {pin["dev"]} {pin["ino"]} broker-v1')
        elif packet == f'ACK {self.nonce} 0': self.events.put(f'TASK {self.nonce} 2 EXEC 2 1')
        elif packet == f'ACK {self.nonce} 2':
            self.f.hook('before-task', self)
            self.thread = threading.Thread(target=self.worker, name='in-memory-canary-test', daemon=True)
            self.thread.start()
        elif packet == f'ACK {self.nonce} 3': self.events.put(f'DONE {self.nonce} {self.status}')
        elif packet == 'STOP ' + self.nonce:
            self.f.hook('stop', self); self.closed = True; self.events.put('CLOSED ' + self.nonce)
        else: raise ValueError('unexpected controller acknowledgement')

    def worker(self):
        transport = self
        class IO:
            def write(self, fd, raw):
                if transport.aborted: raise OSError(5, 'aborted synthetic wire')
                transport.frames_tx += 1; transport.bytes_tx += len(raw)
                changed = transport.f.wire_hook('request', transport, raw)
                transport.events.put(f'RPC {transport.nonce} 1 2 ' + changed.decode('ascii')); return len(raw)
            def read(self, fd, count):
                try: answer = transport.replies.get(timeout=30)
                except queue.Empty: raise OSError(5, 'synthetic reply timeout')
                if isinstance(answer, BaseException): raise answer
                return answer
        self.status = 1
        try:
            client = self.f.api.rpc.Client(3, self.session, self.epoch, io=IO())
            self.results = self.f.mediated.execute_plan(client, self.f.store.root, self.plan)
            raw = json.dumps(self.results, sort_keys=True).encode() + b'\n'
            self.stdout.extend(raw); self.capture.charge('stdout', raw)
            self.status = 0 if all(r['result']['status'] not in ('incomplete', 'manual-inspection-required',
                    'provisioning-stopped', 'cleanup-stopped') for r in self.results) else 1
        except BaseException as exc:
            self.worker_error = exc
        finally:
            self.events.put(f'TASK {self.nonce} 3 EXIT 2 {self.status}')

    def wait_closed(self):
        self.f.hook('wait-closed', self); self.check(); self.waits += 1
        if not self.closed or self.waits != 1: raise ValueError('missing or repeated synthetic kernel closure')
        if self.thread is not None:
            self.thread.join(timeout=2)
            if self.thread.is_alive(): raise ValueError('synthetic task still active')
        return dict(helper_status=0, init_pidfd_exited=True, namespace_retained=True,
                    stdout_bytes=len(self.stdout), stderr_bytes=len(self.stderr),
                    stdout_sha256=hashlib.sha256(self.stdout).hexdigest(), stderr_sha256=hashlib.sha256(self.stderr).hexdigest())

    def abort_task(self):
        self.aborted = True
        self.replies.put(OSError(5, 'test ended'))
        self.events.put('ABORTED')
        if self.thread is not None:
            self.thread.join(timeout=2)
            if self.thread.is_alive(): raise AssertionError('in-memory task did not terminate')
