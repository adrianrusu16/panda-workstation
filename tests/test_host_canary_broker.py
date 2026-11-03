"""Refusal-first broker tests; fake kernel only, no real fixture or adapter."""
import base64
import hashlib
import importlib.util
from pathlib import Path
import stat
import sys
import unittest

HERE = Path(__file__).parent

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class BrokerTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue((HERE / 'host_canary_broker.py').exists(), 'mediated broker missing')
        self.api = load('host_canary_broker', HERE / 'host_canary_broker.py')
        runtime = self.api.runtime
        fixtures = load('broker_fake_kernel', HERE / 'test_host_canary_runtime.py')
        class Fake(fixtures.FakeKernel):
            def fixed_tmp(self, fd):
                self.call('fixed-tmp', fd)
                pin = self.snapshot(fd)
                if pin['uid'] != 0 or pin['gid'] != 0 or pin['mode'] != stat.S_IFDIR | 0o1777:
                    raise runtime.CustodyError('unsafe canonical parent')
                return pin
            def approved_source_binding(self, fd):
                self.call('source-binding', fd)
                return self.snapshot(fd)
            def timestamps_exact(self, fd, atime, mtime):
                self.call('timestamps-exact', fd, atime, mtime)
                self.touch(fd)
                self.nodes[fd].update(atime=atime, mtime=mtime)
            def unlock(self, fd): self.call('unlock', fd)
        self.k = Fake()
        self.k.nodes[self.k.parent].update(uid=0, gid=0, mode=stat.S_IFDIR | 0o1777)
        grant = runtime.CanonicalTmpGrant(self.k, self.k.parent)
        self.boot = runtime.TrustedBootstrap.canonical(self.k, grant, self.k.anchor, 'd' * 32)
        self.s = self.boot.session()
        self.s.create('')
        self.engine = load('host_engine_broker_tests', HERE.parent / 'theme/panda/common/host_canary.py')
        program_fd = self.k.node(False, 0o644)
        raw = b'# approved synthetic source\n'
        self.k.journals[program_fd] = raw
        self.k.nodes[program_fd].update(size=len(raw), flags=262144)
        program = self.api.ApprovedProgramGrant(self.k, program_fd, hashlib.sha256(raw).hexdigest())
        self.store = self.api.BrokerStore(self.s, self.engine, program)
        self.root = '/tmp/' + self.s.root_name
        self.view = self.store.dispatch('open', {'root': self.root, 'pins': None})

    def call(self, op, **args):
        return self.store.dispatch(op, dict(view=self.view, **args))

    def scaffold(self):
        for role in self.engine.FIXED_DIRS:
            self.call('operator_mkdir', path=role)

    def test_default_private_parent_policy_not_relaxed(self):
        with self.assertRaises(self.api.runtime.CustodyError):
            self.api.runtime.TrustedBootstrap(self.k, self.k.parent, self.k.anchor, 'e' * 32)

    def test_explicit_canonical_binding_and_no_json_authority(self):
        self.assertEqual(self.root, '/tmp/panda-theme-b3b1-' + 'd' * 32)
        with self.assertRaises(self.api.runtime.CustodyError):
            self.api.runtime.TrustedBootstrap.canonical(self.k, {'fd': self.k.parent}, self.k.anchor, 'e' * 32)
        context = self.call('context')
        self.assertEqual(context['root'], self.root)
        self.assertEqual(context['tmp_pin'][2:5], [0, 0, 0o1777])
        self.assertNotIn('fd', str(context))

    def test_bad_view_unknown_operation_and_unapproved_output_fail_before_allocation(self):
        for op, args in [('unknown', {}), ('operator_mkdir', {'path': 'config/panda'})]:
            with self.assertRaises(Exception): self.call(op, **args)
        self.assertNotIn('config/panda', self.s.objects)

    def test_exact_nonzero_source_image_empty_lock_read_and_pin_projection(self):
        self.scaffold()
        baseline = (HERE.parent / 'home/dot_config/ghostty/config.ghostty').read_bytes()
        img = self.engine.image(baseline, 0o644, 1700000000000000000, 1700000001000000000)
        created = self.call('create', path=self.engine.SOURCE, image=img)
        self.assertEqual(created['image'], img)
        self.assertEqual(created['pin']['mode'], 0o644)
        self.assertEqual(self.call('read', path=self.engine.SOURCE, authority=False), created)
        lock = self.call('create', path=self.engine.LOCK, image=self.engine.image(b''))
        self.assertEqual(lock['image']['data'], '')
        self.assertIn('ctime_ns', self.call('read', path=self.engine.LOCK, authority=True))

    def test_wrong_baseline_timestamp_or_role_bytes_refuse_without_birth(self):
        self.scaffold()
        before = len(self.k.calls)
        bad = self.engine.image(b'wrong', 0o644, 1, 2)
        with self.assertRaises(Exception): self.call('create', path=self.engine.SOURCE, image=bad)
        self.assertNotIn(self.engine.SOURCE, self.s.objects)
        self.assertFalse(any(c[0] == 'create' for c in self.k.calls[before:]))

    def test_read_only_view_does_not_write_sync_or_lock(self):
        self.scaffold()
        before = len(self.k.calls)
        self.call('context')
        self.call('directory_pin', path='config')
        self.call('absent', path=self.engine.SOURCE)
        self.assertIsNone(self.call('read', path=self.engine.SOURCE, authority=False))
        self.assertFalse(any(c[0] in ('write', 'sync', 'lock') for c in self.k.calls[before:]))

    def test_program_grant_is_typed_and_final_binding_rechecked(self):
        result = self.call('program_begin')
        self.assertEqual(base64.b64decode(result['data']), b'# approved synthetic source\n')
        self.call('program_check', grant=result['grant'])
        self.k.nodes[self.store.program.fd]['ctime'] += 1
        with self.assertRaises(Exception): self.call('program_check', grant=result['grant'])

    def test_shared_parent_churn_preserves_session(self):
        self.k.touch(self.k.parent)
        with self.assertRaises(Exception): self.call('context')
        self.assertTrue(self.s.preserved)

    def test_program_end_is_view_bound_and_close_refuses_active_grant(self):
        grant = self.call('program_begin')['grant']
        other = self.store.dispatch('open', {'root': self.root})
        with self.assertRaises(Exception):
            self.store.dispatch('program_end', {'view': other, 'grant': grant})
        self.call('program_end', grant=grant)
        with self.assertRaises(Exception): self.call('program_check', grant=grant)
        self.call('close')
        with self.assertRaises(Exception): self.call('context')

    def test_active_source_close_preserves_without_deletion(self):
        self.call('program_begin')
        with self.assertRaises(Exception): self.call('close')
        self.assertTrue(self.s.preserved)
        self.assertFalse(any(c[0] == 'remove' for c in self.k.calls))

    def test_arbitrary_target_and_noncanonical_record_refuse_before_birth(self):
        self.scaffold()
        for path in (self.engine.JOURNAL,):
            before = len(self.k.calls)
            with self.assertRaises(Exception):
                self.call('create', path=path, image=self.engine.image(b'arbitrary'))
            self.assertNotIn(path, self.s.objects)
            self.assertFalse(any(c[0] == 'create' for c in self.k.calls[before:]))

    def test_missing_lock_cannot_lease_absence(self):
        self.scaffold()
        before = len(self.k.calls)
        with self.assertRaises(Exception): self.call('lock', expected=None)
        self.assertFalse(any(c[0] == 'lock' for c in self.k.calls[before:]))

    def test_lock_lease_is_view_bound_nonreentrant_and_release_exact(self):
        self.scaffold()
        expected = self.call('create', path=self.engine.LOCK, image=self.engine.image(b''))
        lease = self.call('lock', expected=expected)
        other = self.store.dispatch('open', {'root': self.root})
        for op, args in [('lock', {'expected': expected}), ('unlock', {'lease': 'stale'})]:
            with self.assertRaises(Exception): self.call(op, **args)
        with self.assertRaises(Exception):
            self.store.dispatch('unlock', {'view': other, 'lease': lease})
        self.call('unlock', lease=lease)
        self.assertIsNone(self.store.lease)

    def test_lock_client_loss_preserves_no_cleanup(self):
        self.scaffold()
        expected = self.call('create', path=self.engine.LOCK, image=self.engine.image(b''))
        self.call('lock', expected=expected)
        with self.assertRaises(Exception): self.call('close')
        self.assertTrue(self.s.preserved)
        self.assertFalse(any(c[0] == 'remove' for c in self.k.calls))

    def test_sync_failure_preserves_original_graph(self):
        self.scaffold()
        objects = dict(self.s.objects)
        self.k.fail_at = 'sync'
        with self.assertRaises(Exception): self.call('sync')
        self.assertTrue(self.s.preserved)
        self.assertEqual(self.s.objects, objects)
        self.assertFalse(any(c[0] == 'remove' for c in self.k.calls))

    def test_registration_failure_retains_birth_without_returning_authority(self):
        original = self.s.ledger.append
        def fail(event):
            if event['kind'] == 'registered': raise OSError('registration result lost')
            return original(event)
        self.s.ledger.append = fail
        with self.assertRaises(Exception): self.call('operator_mkdir', path='home')
        self.assertTrue(self.s.preserved)
        self.assertNotIn('home', self.s.objects)
        self.assertIn((self.s.objects[''].fd, 'home'), self.k.names)
        self.assertGreater(len(self.s._birth_fds), 1)

    def test_replacement_foreign_child_and_lost_custody_revoke_before_mutation(self):
        for fault in ('replacement', 'foreign', 'descriptor'):
            with self.subTest(fault=fault):
                self.setUp()
                root = self.s.objects['']
                if fault == 'replacement':
                    self.k.names[root.parent, root.name] = self.k.node(True)
                elif fault == 'foreign':
                    self.k.names[root.fd, 'foreign'] = self.k.node(False)
                else:
                    self.k.nodes[root.fd]['ino'] += 1
                before = len(self.k.calls)
                with self.assertRaises(Exception): self.call('operator_mkdir', path='home')
                self.assertTrue(self.s.preserved)
                self.assertFalse(any(c[0] in ('create', 'remove') for c in self.k.calls[before:]))

    def test_output_without_durable_intent_never_creates_or_removes(self):
        self.scaffold()
        before = len(self.k.calls)
        for op in ('operator_mkdir', 'operator_remove_output'):
            with self.assertRaises(Exception):
                self.call(op, path=self.engine.OUTPUT_DIRS[0],
                          **({'expected': {}} if op == 'operator_remove_output' else {}))
        self.assertFalse(any(c[0] in ('create', 'remove') for c in self.k.calls[before:]))

    def test_generic_lifecycle_cannot_start_or_teardown_canonical_session(self):
        with self.assertRaises(Exception): self.s.start_worker(8, 'f' * 64, ['python'])
        class Generic:
            def finish(inner): self.fail('generic lifecycle invoked')
        lifecycle = Generic()
        self.s._lifecycle = lifecycle
        with self.assertRaises(Exception): self.s.teardown(lifecycle)
        self.assertFalse(any(c[0] == 'remove' for c in self.k.calls))

    def test_root_receipt_rechecks_approved_source_authority(self):
        self.k.nodes[self.store.program.fd]['ctime'] += 1
        with self.assertRaises(Exception): self.store.root_receipt()
        self.assertTrue(self.s.preserved)

    def restored_operator(self):
        self.call('close')
        mediated = load('host_canary_mediated', HERE.parent / 'theme/panda/common/host_canary_mediated.py')
        self.store.baseline = (HERE.parent / 'home/dot_config/ghostty/config.ghostty').read_bytes()
        store = self.store
        class Endpoint:
            def call(inner, op, args): return store.dispatch(op, args)
        operator = mediated.MediatedOperator(mediated.BrokerStorage(Endpoint()), self.root)
        operator.initialize()
        operator.provision()
        self.assertEqual(mediated.api.install_minimal(self.root, storage=operator.storage)['status'], 'installed')
        self.assertEqual(mediated.api.recover(self.root, storage=operator.storage)['status'], mediated.api.RESTORED)
        return mediated, operator

    def test_restored_cleanup_uses_journal_reachable_identities(self):
        mediated, operator = self.restored_operator()
        operator.cleanup_outputs()
        self.assertEqual(self.store.removed_outputs, list(reversed(self.engine.OUTPUT_DIRS)))
        self.assertEqual(mediated.api.recover(self.root, storage=operator.storage)['status'], mediated.api.CLOSED)
        operator.close()
        self.assertEqual(self.store.programs, {})
        self.assertEqual(self.store.views, {})
        self.assertIsNone(self.store.lease)
        self.assertTrue(all(o.pin['nlink'] == 0 for o in self.s.retired))

    def test_output_removal_post_sync_failure_retains_descriptors_without_second_remove(self):
        mediated, operator = self.restored_operator()
        receipt = mediated.api.CleanupProvider(self.root, storage=operator.storage)
        receipt.start()
        path = self.engine.OUTPUT_DIRS[1]
        receipt.directory_intent(path)
        original = self.k.remove
        def remove(parent, name, directory):
            original(parent, name, directory)
            self.k.fail_at = 'sync'
        self.k.remove = remove
        before = len(self.k.calls)
        with self.assertRaises(Exception):
            operator.fs._operator_remove_output(path, receipt.enrollment['dirs'][path])
        self.assertTrue(self.s.preserved)
        self.assertEqual(sum(c[0] == 'remove' for c in self.k.calls[before:]), 1)
        self.assertIn(self.engine.OUTPUT_DIRS[0], self.s.objects)
        self.assertIn(path, self.s.objects)  # uncertain result retained, never adopted as absence

    def test_managed_stage_requires_owned_lease_and_durable_journal_intent(self):
        self.scaffold()
        baseline = (HERE.parent / 'home/dot_config/ghostty/config.ghostty').read_bytes()
        source = self.call('create', path=self.engine.SOURCE,
                           image=self.engine.image(baseline, 0o644, 1700000000000000000, 1700000001000000000))
        before = len(self.k.calls)
        with self.assertRaises(Exception):
            self.call('create', path=self.engine.STAGES[self.engine.SOURCE],
                      image=self.engine.image(baseline + self.engine.HOOK, 0o644,
                                              1700000000000000000, 1700000001000000000))
        self.assertEqual(self.call('read', path=self.engine.SOURCE), source)
        self.assertFalse(any(c[0] in ('create', 'replace', 'remove') for c in self.k.calls[before:]))

    def test_minimal_forged_provisioning_record_cannot_authorize_output(self):
        self.scaffold()
        value = dict(schema=2, scope=self.engine.SCOPE, enrollment_id='a' * 32,
                     root=self.root, state='provisioning', pending=self.engine.OUTPUT_DIRS[0], done=[])
        before = len(self.k.calls)
        with self.assertRaises(Exception):
            self.call('create', path=self.engine.PROVISION, image=self.engine.image(self.engine.pack(value)))
        self.assertNotIn(self.engine.PROVISION, self.s.objects)
        self.assertFalse(any(c[0] == 'create' for c in self.k.calls[before:]))

    def test_restored_journal_cannot_rewind_or_grant_out_of_order_managed_stage(self):
        mediated, operator = self.restored_operator()
        self.view = self.store.dispatch('open', {'root': self.root})
        enrollment, baseline = self.store._record(self.engine.BASELINE)
        lock = enrollment['support'][self.engine.LOCK]
        lease = self.call('lock', expected=lock)
        before = len(self.k.calls)
        with self.assertRaises(Exception):
            self.call('create', path=self.engine.STAGES[self.engine.JOURNAL],
                      image=self.engine.image(self.engine.pack(self.engine.new_journal(
                          baseline, self.engine.proposals(enrollment)))))
        source = enrollment['before'][self.engine.SOURCE]['image']
        with self.assertRaises(Exception):
            self.call('create', path=self.engine.STAGES[self.engine.SOURCE], image=source)
        other = self.store.dispatch('open', {'root': self.root})
        with self.assertRaises(Exception):
            self.store.dispatch('create', {'view': other, 'path': self.engine.STAGES[self.engine.SOURCE],
                                            'image': source})
        with self.assertRaises(Exception):
            self.call('create', path=self.engine.TARGET, image=self.engine.image(self.engine.MINIMAL))
        self.assertFalse(any(c[0] in ('create', 'replace', 'remove') for c in self.k.calls[before:]))
        self.call('unlock', lease=lease)
        self.store.dispatch('close', {'view': other})
        self.call('close')
        operator.close()

    def test_publish_and_unlink_require_intent_even_for_original_registered_objects(self):
        self.scaffold()
        raw = (HERE.parent / 'home/dot_config/ghostty/config.ghostty').read_bytes()
        source = self.call('create', path=self.engine.SOURCE,
                           image=self.engine.image(raw, 0o644, 1700000000000000000, 1700000001000000000))
        # Controller-side fault injection registers a stage; worker still has no journal authority.
        path = self.engine.STAGES[self.engine.SOURCE]
        obj = self.s.create(path)
        self.s.write(obj, raw + self.engine.HOOK)
        self.s.freeze_metadata(obj, (1700000000000000000, 1700000001000000000))
        staged = self.store.read(path)
        before = len(self.k.calls)
        with self.assertRaises(Exception):
            self.call('publish', path=self.engine.SOURCE, staged=staged, expected=source)
        with self.assertRaises(Exception):
            self.call('unlink', path=self.engine.TARGET, expected=None)
        self.assertFalse(any(c[0] in ('replace', 'remove') for c in self.k.calls[before:]))

    def test_readonly_plan_refuses_all_mutating_operations_before_kernel_calls(self):
        self.store.restrict_plan([{'action': 'status'}, {'action': 'preview'}])
        operations = [('create', dict(path=self.engine.LOCK, image=self.engine.image(b''))),
                      ('publish', dict(path=self.engine.SOURCE, staged=None, expected=None)),
                      ('unlink', dict(path=self.engine.TARGET, expected=None)), ('sync', {}),
                      ('sync_directory', dict(path='')), ('lock', dict(expected=None)),
                      ('unlock', dict(lease='stale')), ('operator_mkdir', dict(path='home')),
                      ('operator_remove_output', dict(path=self.engine.OUTPUT_DIRS[0], expected={}))]
        before = list(self.k.calls)
        for operation, arguments in operations:
            with self.subTest(operation=operation), self.assertRaises(Exception):
                self.call(operation, **arguments)
        self.assertEqual(self.k.calls, before)
        with self.assertRaises(Exception): self.store.restrict_plan([{'action': 'install'}])

    def test_controller_plan_rejects_unreviewed_fields_actions_and_stops(self):
        for plan in ([{'action': 'exec'}], [{'action': 'status', 'path': '/elsewhere'}],
                     [{'action': 'initialize', 'source': 'arbitrary'}],
                     [{'action': 'cleanup_outputs', 'stop': 'arbitrary'}],
                     [{'action': 'provision'}], []):
            with self.subTest(plan=plan), self.assertRaises(Exception):
                self.store.restrict_plan(plan)
        self.store.restrict_plan([{'action': 'initialize'}, {'action': 'provision', 'stop': 'support'}])
        self.assertFalse(self.store.readonly)

    def test_full_transaction_over_rpc_with_real_durable_ledger_stays_within_budgets(self):
        self.call('close')
        common = HERE.parent / 'theme/panda/common'
        mediated = load('host_canary_mediated', common / 'host_canary_mediated.py')
        rpc = load('broker_budget_rpc', common / 'host_canary_rpc.py')
        program_data = (common / 'host_canary.py').read_bytes()
        fd = self.k.node(False, 0o644)
        self.k.journals[fd] = program_data
        self.k.nodes[fd].update(size=len(program_data), flags=262144)
        self.store.program = self.api.ApprovedProgramGrant(self.k, fd, hashlib.sha256(program_data).hexdigest())
        self.store.baseline = (HERE.parent / 'home/dot_config/ghostty/config.ghostty').read_bytes()
        plan = [{'action': action} for action in
                ('initialize', 'provision', 'install', 'recover', 'cleanup_outputs', 'recover')]
        self.store.restrict_plan(plan)
        server = rpc.Server(self.store, self.s.ledger, self.boot.session_id, 1)
        class LoopIO:
            def write(inner, fd, raw):
                inner.reply = server.accept(raw)
                return len(raw)
            def read(inner, fd, bound): return inner.reply
        client = rpc.Client(3, self.boot.session_id, 1, io=LoopIO())
        answers = mediated.execute_plan(client, self.root, plan)
        self.assertEqual([entry['result']['status'] for entry in answers],
                         ['initialized', 'enrolled', 'installed', mediated.api.RESTORED,
                          'output-directories-removed', mediated.api.CLOSED])
        self.assertTrue(server.quiescent)
        self.assertFalse(self.s.preserved)
        self.assertEqual(self.store.views, {})
        self.assertEqual(self.store.programs, {})
        self.assertEqual(self.store.record_stages, {})
        self.assertIsNone(self.store.lease)
        history = self.s.ledger.history
        largest = max(len(line) for line in history.splitlines(keepends=True))
        self.rpc_budget_evidence = dict(requests=client.seq - 1, records=self.s.ledger.sequence,
                                       bytes=len(history), largest_record=largest)
        self.assertLessEqual(self.s.ledger.sequence, self.api.runtime.MAX_EVENTS)
        self.assertLessEqual(len(history), self.api.runtime.MAX_BYTES)
        self.assertLessEqual(largest, self.api.runtime.MAX_RECORD)


if __name__ == '__main__': unittest.main(verbosity=2)
