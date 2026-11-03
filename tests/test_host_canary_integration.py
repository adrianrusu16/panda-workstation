"""Real engine algorithms over an in-memory broker; no Host adapter invocation."""
import base64
from contextlib import ExitStack
import copy
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

COMMON = Path(__file__).resolve().parents[1] / 'theme/panda/common'


def load(name):
    spec = importlib.util.spec_from_file_location(name, COMMON / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class MemoryEndpoint:
    """A semantic data model, never a filesystem/descriptor/lifecycle adapter."""
    def __init__(self, api, program):
        self.api, self.program = api, program
        self.root = '/tmp/panda-theme-b3b1-' + 'a' * 32
        self.ns = {'mnt': 'mnt:[21]', 'user': 'user:[22]'}
        self.tmp_pin = [7, 99, 0, 0, 0o1777, 9]
        self.next = 100
        self.dirs = {'': self.pin(0o700)}
        self.files, self.views, self.leases, self.calls = {}, {}, {}, []
        self.retired_dirs, self.grants = {}, {}
        self.baseline = None
        self.fail = None
        self.source_grant = 'reviewed-program'

    def pin(self, mode):
        self.next += 1
        return dict(dev=7, ino=self.next, uid=self.api.os.getuid(), gid=self.api.os.getgid(), mode=mode, mount=9)

    def call(self, op, args):
        self.calls.append((op, copy.deepcopy(args)))
        if op == self.fail:
            raise OSError(5, 'injected broker ' + op)
        if op == 'open':
            if args['root'] != self.root:
                raise ValueError('foreign root')
            for path, pin in (args.get('pins') or {}).items():
                if self.dirs.get(path, self.retired_dirs.get(path)) != pin:
                    raise ValueError('foreign witness')
            view = str(len(self.views) + 1)
            self.views[view] = True
            return view
        view = args.get('view')
        if view not in self.views:
            raise ValueError('foreign/closed view')
        path = args.get('path')
        if op == 'context':
            return copy.deepcopy(dict(root=self.root, ns=self.ns, tmp_pin=self.tmp_pin,
                                      root_pin=self.dirs[''], pins=self.dirs))
        if op == 'close':
            if view in self.grants.values():
                raise ValueError('active source grant')
            del self.views[view]
        elif op == 'directory_pin':
            return copy.deepcopy(self.dirs[path])
        elif op == 'bind':
            if self.dirs.get(path) != args['pin']:
                raise ValueError('directory binding differs')
        elif op == 'absent':
            return path not in self.dirs and path not in self.files
        elif op == 'entries':
            prefix = path + '/' if path else ''
            names = {p[len(prefix):] for p in (*self.dirs, *self.files)
                     if p.startswith(prefix) and p != path and '/' not in p[len(prefix):]}
            if names != set(args['expected']):
                raise ValueError('foreign child')
        elif op == 'operator_mkdir':
            if path in self.dirs or path in self.files:
                raise ValueError('occupied directory')
            parent = path.rpartition('/')[0]
            if parent not in self.dirs:
                raise ValueError('missing parent')
            self.dirs[path] = self.pin(0o700)
            return copy.deepcopy(self.dirs[path])
        elif op == 'read':
            obj = copy.deepcopy(self.files.get(path))
            if obj is not None and not args['authority']:
                obj.pop('ctime_ns')
            return obj
        elif op == 'create':
            if path in self.files or path in self.dirs or path.rpartition('/')[0] not in self.dirs:
                raise ValueError('occupied/missing image parent')
            image = args['image']
            self.api.decode(image)
            self.files[path] = dict(image=copy.deepcopy(image), pin=self.pin(image['mode']), ctime_ns=self.next)
            return {k: copy.deepcopy(self.files[path][k]) for k in ('image', 'pin')}
        elif op == 'publish':
            stage = self.api.STAGES[path]
            current = self.files.get(path)
            actual = None if current is None else {k: current[k] for k in args['expected']}
            if actual != args['expected'] or {k: self.files[stage][k] for k in ('image', 'pin')} != args['staged']:
                raise ValueError('publication mismatch')
            self.files[path] = self.files.pop(stage)
            return {k: copy.deepcopy(self.files[path][k]) for k in ('image', 'pin')}
        elif op == 'lock':
            if self.leases:
                raise ValueError('lock occupied')
            token = 'lease'
            self.leases[token] = view
            return token
        elif op == 'unlock':
            if self.leases.get(args['lease']) != view:
                raise ValueError('foreign lease')
            del self.leases[args['lease']]
        elif op in ('sync', 'sync_directory'):
            pass
        elif op == 'unlink':
            obj = self.files[path]
            if {k: obj[k] for k in args['expected']} != args['expected']:
                raise ValueError('unlink mismatch')
            del self.files[path]
        elif op == 'operator_baseline':
            if self.baseline is None:
                raise ValueError('controller baseline missing')
            return dict(data=base64.b64encode(self.baseline).decode())
        elif op == 'program_begin':
            self.grants[self.source_grant] = view
            return dict(data=base64.b64encode(self.program).decode(), grant=self.source_grant)
        elif op == 'program_check':
            if self.grants.get(args['grant']) != view:
                raise ValueError('source grant changed')
        elif op == 'program_end':
            if self.grants.get(args['grant']) != view:
                raise ValueError('foreign source grant')
            del self.grants[args['grant']]
        elif op == 'operator_remove_output':
            if path not in self.api.OUTPUT_DIRS or self.dirs.get(path) != args['expected']:
                raise ValueError('directory removal mismatch')
            if any(p.startswith(path + '/') for p in (*self.dirs, *self.files)):
                raise ValueError('nonempty output')
            self.retired_dirs[path] = self.dirs.pop(path)
        else:
            raise AssertionError('unexpected operation ' + op)
        return None


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.api = load('host_canary')
        self.program = (COMMON / 'host_canary.py').read_bytes()
        self.baseline = (COMMON.parents[2] / 'home/dot_config/ghostty/config.ghostty').read_bytes()
        self.mediated = load('host_canary_mediated')
        self.endpoint = MemoryEndpoint(self.api, self.program)
        self.storage = self.mediated.BrokerStorage(self.endpoint)

    def test_missing_or_foreign_authority_refuses_before_any_filesystem_probe(self):
        with self.assertRaises((TypeError, ValueError)):
            self.mediated.BrokerStorage(None)
        with patch.object(self.api, 'FS', side_effect=AssertionError('native storage opened')):
            with self.assertRaises(ValueError):
                self.storage.open('/tmp/panda-theme-b3b1-foreign')
            answer = self.api.status(self.endpoint.root, storage=self.storage)
        self.assertEqual(answer['status'], 'manual-inspection-required')
        self.assertEqual(self.endpoint.files, {})

    def test_context_or_namespace_drift_refuses_without_mutation(self):
        original = self.endpoint.call
        def changed(op, args):
            result = original(op, args)
            if op == 'context': result['root'] += '-foreign'
            return result
        self.endpoint.call = changed
        with self.assertRaises(ValueError): self.storage.open(self.endpoint.root)
        self.assertEqual(self.endpoint.files, {})

    def test_driver_rejects_bad_plan_and_unreviewed_baseline(self):
        for plan in ([{'action': 'exec', 'code': 'arbitrary'}], [{'action': 'initialize', 'baseline': 'bad'}],
                     [{'action': 'recover', 'path': '/elsewhere'}], [{'action': 'provision', 'stop': 'unknown'}]):
            with self.subTest(plan=plan), self.assertRaises(ValueError):
                self.mediated.execute_plan(self.endpoint, self.endpoint.root, plan)
        self.assertEqual(self.endpoint.files, {})

    def test_normal_cycle_uses_real_engine_and_restores_independent_images(self):
        with patch.object(self.api, 'FS', side_effect=AssertionError('native storage opened')), \
                patch.object(self.api, 'namespace', side_effect=AssertionError('worker namespace probe')):
            operator = self.mediated.MediatedOperator(self.storage, self.endpoint.root)
            operator.initialize(self.baseline)
            operator.provision()
            before = {p: copy.deepcopy(self.endpoint.files[p]['image']) for p in (self.api.SOURCE, self.api.DEPLOYED)}
            self.assertEqual(self.api.install_minimal(operator.root, storage=self.storage)['status'], 'installed')
            self.assertEqual(self.api.recover(operator.root, storage=self.storage)['status'], self.api.RESTORED)
            operator.cleanup_outputs()
            self.assertEqual(self.api.recover(operator.root, storage=self.storage)['status'], self.api.CLOSED)
            for path, image in before.items(): self.assertEqual(self.endpoint.files[path]['image'], image)
            operator.close()
        self.assertEqual(self.endpoint.leases, {})
        self.assertNotEqual(before[self.api.SOURCE]['atime'], before[self.api.DEPLOYED]['atime'])
        self.assertFalse(any(p in self.endpoint.dirs for p in self.api.OUTPUT_DIRS))

    def test_broker_failure_stops_initialization_without_retry_or_cleanup(self):
        self.endpoint.fail = 'create'
        operator = self.mediated.MediatedOperator(self.storage, self.endpoint.root)
        with self.assertRaises(OSError): operator.initialize(self.baseline)
        self.assertFalse(any(op == 'operator_remove_output' for op, _ in self.endpoint.calls))
        self.assertEqual(sum(op == 'create' for op, _ in self.endpoint.calls), 1)

    def test_complete_explicit_plan_releases_views_and_source_grants(self):
        self.endpoint.baseline = self.baseline
        actions = ('initialize', 'provision', 'status', 'preview', 'install',
                   'status', 'recover', 'cleanup_outputs', 'recover')
        with patch.object(self.api, 'FS', side_effect=AssertionError('native storage opened')), \
                patch.object(self.api, 'namespace', side_effect=AssertionError('worker namespace probe')):
            results = self.mediated.execute_plan(self.endpoint, self.endpoint.root,
                                                [dict(action=action) for action in actions])
        self.assertEqual([row['action'] for row in results], list(actions))
        self.assertEqual(results[-1]['result']['status'], self.api.CLOSED)
        self.assertEqual(self.endpoint.grants, {})
        self.assertEqual(self.endpoint.views, {})
        self.assertEqual(self.endpoint.leases, {})
        self.assertEqual(self.api.unpack(self.api.decode(self.endpoint.files[self.api.BASELINE]['image']))['schema'], 2)

    def test_rpc_transport_runs_the_same_bounded_plan_without_worker_or_os_access(self):
        rpc = load('host_canary_rpc')
        endpoint = self.endpoint
        class Store:
            def dispatch(self, op, args):
                return endpoint.call(op, args)
            def preserve(self, reason):
                raise AssertionError('unexpected RPC preservation: ' + reason)
        class Ledger:
            def __init__(self):
                self.records = []
                self.bytes = 0
            def append(self, value):
                envelope = dict(schema=1,session='a'*32,seq=len(self.records)+1,previous='0'*64,event=value)
                size = len(rpc.pack(envelope)) + 1
                if size > 4096 or len(self.records) >= 100000 or self.bytes + size > 64*1024*1024:
                    raise AssertionError('real custody ledger budget exceeded')
                self.bytes += size
                self.records.append(copy.deepcopy(value))
        class LoopIO:
            def write(self, fd, raw):
                self.reply = server.accept(raw)
                return len(raw)
            def read(self, fd, bound):
                return self.reply
        ledger = Ledger()
        server = rpc.Server(Store(), ledger, 'a' * 32, 1)
        client = rpc.Client(3, 'a' * 32, 1, io=LoopIO())
        endpoint.baseline = self.baseline
        actions = ('initialize', 'provision', 'install', 'recover', 'cleanup_outputs', 'recover')
        with ExitStack() as stack:
            for name in ('open', 'stat', 'fstat', 'readlink', 'listxattr', 'listdir',
                         'utime', 'replace', 'unlink', 'fsync', 'close'):
                stack.enter_context(patch.object(self.api.os, name,
                    side_effect=AssertionError('worker OS access: ' + name)))
            results = self.mediated.execute_plan(client, endpoint.root,
                                                [dict(action=action) for action in actions])
        self.assertEqual(results[-1]['result']['status'], self.api.CLOSED)
        self.assertTrue(server.quiescent)
        self.assertFalse(client.failed)
        self.assertLess(client.seq, rpc.MAX_REQUESTS)
        protocol = [e for e in ledger.records if e['kind'] in ('rpc-intent','rpc-result','rpc-ack')]
        self.assertEqual(len(protocol), 3 * (client.seq - 1))
        self.assertTrue(any(e['kind']=='rpc-content' for e in ledger.records))
        self.assertTrue(any(e['kind']=='rpc-content-reference' for e in ledger.records))
        self.assertEqual(endpoint.grants, {})
        self.assertEqual(endpoint.views, {})

    def test_stopped_provision_plan_preserves_created_support_without_continuing(self):
        self.endpoint.baseline = self.baseline
        results = self.mediated.execute_plan(self.endpoint, self.endpoint.root,
            [dict(action='initialize'), dict(action='provision', stop='support'), dict(action='install')])
        self.assertEqual([row['action'] for row in results], ['initialize', 'provision'])
        self.assertEqual(results[-1]['result']['status'], 'provisioning-stopped')
        self.assertIn(self.api.PROVISION, self.endpoint.files)
        self.assertNotIn(self.api.BASELINE, self.endpoint.files)
        self.assertNotIn(self.api.OUTPUT_DIRS[0], self.endpoint.dirs)
        self.assertEqual(self.endpoint.views, {})

    def test_failed_program_check_preserves_grant_and_blocks_more_calls(self):
        view = self.storage.open(self.endpoint.root)
        self.endpoint.fail = 'program_check'
        with self.assertRaises(OSError):
            with view.program():
                self.fail('failed source check granted program')
        before = len(self.endpoint.calls)
        with self.assertRaises(ValueError):
            view.absent(self.api.SOURCE)
        self.assertEqual(len(self.endpoint.calls), before)
        self.assertTrue(view.failed)
        self.assertTrue(self.endpoint.grants)

    def test_storage_and_plan_expose_no_descriptor_or_general_mutation_method(self):
        view = self.storage.open(self.endpoint.root)
        for name in ('fd', 'fds', 'parent', 'pin', 'directory', 'chmod', 'rename', 'rmtree'):
            self.assertFalse(hasattr(view, name), name)
        view.close()


if __name__ == '__main__':
    unittest.main()
