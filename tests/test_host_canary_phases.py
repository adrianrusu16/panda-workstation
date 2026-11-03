"""Refusal-first phase tests: synthetic records/transports, never OS adapters."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import secrets

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location('phase_fixture_tests', HERE / 'host_canary_phase_fixture.py')
fixture = importlib.util.module_from_spec(spec); sys.modules[spec.name] = fixture; spec.loader.exec_module(fixture)


class PhaseTests(unittest.TestCase):
    def setUp(self):
        self.f = fixture.Fixture()
        self.addCleanup(self.f.close)

    def test_reordered_phase_preserves_before_birth(self):
        controller = self.f.controller()
        with self.assertRaises(ValueError): controller.run_phase('B')
        self.assertTrue(self.f.s.preserved)
        self.assertEqual(self.f.spawn_count, 0)

    def test_early_teardown_cannot_grant_removal(self):
        controller = self.f.controller()
        before = len(self.f.k.calls)
        with self.assertRaises(ValueError): controller.teardown()
        self.assertFalse(any(c[0] == 'remove' for c in self.f.k.calls[before:]))

    def test_direct_removal_without_closed_authority_is_refused(self):
        before = len(self.f.k.calls)
        with self.assertRaises(ValueError): self.f.s._remove_registered()
        self.assertFalse(any(c[0] == 'remove' for c in self.f.k.calls[before:]))

    def test_duplicate_descriptor_cannot_replace_original_before_first_birth(self):
        controller = self.f.controller()
        root = self.f.s.objects['']
        duplicate = max(self.f.k.nodes) + 1
        self.f.k.nodes[duplicate] = dict(self.f.k.nodes[root.fd])
        # Same kernel object metadata and child namespace, different held FD.
        for (parent, name), child in list(self.f.k.names.items()):
            if parent == root.fd: self.f.k.names[duplicate, name] = child
        root.fd = duplicate
        with self.assertRaises(ValueError): controller.run_phase('A')
        self.assertEqual(self.f.spawn_count, 0)
        self.assertTrue(self.f.s.preserved)

    def test_fresh_nonce_is_bound_before_birth(self):
        controller = self.f.controller()
        def stop(point, transport):
            if point == 'spawn': raise OSError('interrupted after creation')
        self.f.hook = stop
        with patch.object(secrets, 'token_hex', return_value='a' * 32) as entropy:
            with self.assertRaises(OSError): controller.run_phase('A')
        entropy.assert_called_once_with(16)
        self.assertEqual(self.f.transports[0].nonce, 'a' * 32)
        self.assertTrue(self.f.s.preserved)

    def test_later_phase_mutations_are_refused_before_broker_allocation(self):
        controller = self.f.controller()
        e = self.f.store.e
        cases = [('A', 'create', e.STAGES[e.JOURNAL]),
                 ('B', 'create', e.STAGES[e.CLEANUP]),
                 ('C', 'operator_remove_output', e.OUTPUT_DIRS[0]),
                 ('D', 'create', e.STAGES[e.TARGET])]
        for phase, op, path in cases:
            with self.subTest(phase=phase):
                controller.state = 'running'
                epoch = ord(phase) - ord('A') + 1
                controller.receipts = [{}] * (epoch - 1)
                controller._grant = self.f.api.BirthGrant(controller, epoch, 'a' * 32, [])
                before = len(self.f.k.calls)
                # The phase gate must run before image parsing or any mutation.
                args = {'path': path, 'view': 'invalid', 'image': None} if op == 'create' else {
                    'path': path, 'view': 'invalid', 'expected': None}
                with self.assertRaisesRegex(ValueError, 'phase'):
                    self.f.store.dispatch(op, args)
                self.assertFalse(any(c[0] in ('create', 'remove', 'write') for c in self.f.k.calls[before:]))
                # Restore only for independent cases; no failed controller is resumed.
                self.f.store._phase_owner = controller

    def assert_preserved(self, controller):
        self.assertEqual(controller.state, 'preserved')
        self.assertTrue(self.f.s.preserved)
        births = self.f.spawn_count
        before = len(self.f.k.calls)
        with self.assertRaises(ValueError): controller.run_phase('A')
        with self.assertRaises(ValueError): controller.teardown()
        self.assertEqual(self.f.spawn_count, births)
        self.assertFalse(any(c[0] == 'remove' for c in self.f.k.calls[before:]))

    def test_missing_injected_boundary_is_never_live_fallback(self):
        del self.f.k.process_transport
        with self.assertRaisesRegex(ValueError, 'injected'): self.f.controller()
        self.assertEqual(self.f.spawn_count, 0)

    def test_controller_loss_refuses_even_with_same_ledger_and_root(self):
        controller = self.f.controller()
        self.f.s._phase_controller = None
        with self.assertRaises(ValueError): controller.run_phase('A')
        self.assert_preserved(controller)
        self.assertEqual(self.f.spawn_count, 0)

    def test_unregistered_child_refuses_before_birth(self):
        controller = self.f.controller()
        root = self.f.s.objects['']
        self.f.k.names[root.fd, 'foreign'] = self.f.k.node(False)
        with self.assertRaises(ValueError): controller.run_phase('A')
        self.assert_preserved(controller)
        self.assertEqual(self.f.spawn_count, 0)

    def test_original_program_descriptor_cannot_be_rebound(self):
        controller = self.f.controller()
        old = self.f.store.program.fd
        duplicate = self.f.file(self.f.store.program.data)
        self.f.k.nodes[duplicate] = dict(self.f.k.nodes[old])
        self.f.store.program.fd = duplicate
        with self.assertRaises(ValueError): controller.run_phase('A')
        self.assertEqual(self.f.spawn_count, 0)
        self.assert_preserved(controller)

    def test_birth_interruptions_never_send_start(self):
        for point in ('spawn', 'receive'):
            with self.subTest(point=point):
                f = fixture.Fixture(); self.addCleanup(f.close)
                controller = f.controller()
                def fail(at, transport):
                    if at == point: raise OSError('interrupted worker creation')
                f.hook = fail
                with self.assertRaises(OSError): controller.run_phase('A')
                self.assertTrue(f.s.preserved)
                self.assertIs(controller._active.transport, f.transports[0])
                self.assertFalse(any(c.startswith('START') for t in f.transports for c in t.commands))
                with self.assertRaises(ValueError): controller.run_phase('A')
                self.assertEqual(f.spawn_count, 1)

    def test_stale_birth_wrong_root_and_reused_pid_namespace_packets_refuse(self):
        for mode in ('nonce', 'root', 'missing-descriptors'):
            with self.subTest(mode=mode):
                f = fixture.Fixture(); self.addCleanup(f.close)
                controller = f.controller()
                def alter(point, transport):
                    if point != 'spawn': return
                    original = transport.events.get_nowait().split()
                    if mode == 'nonce': original[1] = 'f' * 32
                    elif mode == 'root': original[-1] = '999999'
                    else:
                        transport.bind_birth = lambda *a: (_ for _ in ()).throw(ValueError('missing pidfd/nsfd'))
                    transport.events.put(' '.join(original))
                f.hook = alter
                with self.assertRaises(ValueError): controller.run_phase('A')
                self.assertTrue(f.s.preserved)
                self.assertFalse(any(c.startswith('START') for t in f.transports for c in t.commands))

    def test_missing_reordered_and_unexpected_descendant_events_refuse(self):
        for mode in ('gapped', 'descendant', 'done-active', 'pid-reuse'):
            with self.subTest(mode=mode):
                f = fixture.Fixture(); self.addCleanup(f.close)
                controller = f.controller()
                def alter(point, transport):
                    if point != 'send' or transport.last_command != 'ACK ' + transport.nonce + ' 2': return
                    def no_task(): pass
                    # Raise before a cooperative task can start; inject the next native event.
                    if mode == 'gapped': packet = f'TASK {transport.nonce} 4 EXIT 2 0'
                    elif mode == 'done-active': packet = f'DONE {transport.nonce} 0'
                    elif mode == 'descendant': packet = f'TASK {transport.nonce} 3 BIRTH 3 2'
                    else: packet = f'TASK {transport.nonce} 3 BIRTH 2 1'
                    transport.events.put(packet)
                    transport.f.hook = lambda *a: None
                    transport.worker = no_task
                f.hook = alter
                with self.assertRaises(ValueError): controller.run_phase('A')
                self.assertTrue(f.s.preserved)
                self.assertFalse(any(c.startswith('STOP') for t in f.transports for c in t.commands))

    def test_rpc_stale_epoch_missing_and_reordered_ack_preserve(self):
        for mode in ('epoch', 'sequence', 'ack', 'lost-result'):
            with self.subTest(mode=mode):
                f = fixture.Fixture(); self.addCleanup(f.close)
                controller = f.controller()
                def alter(direction, transport, raw):
                    value = f.api.rpc.unpack(raw)
                    if mode == 'epoch' and direction == 'request': value['epoch'] = 2
                    elif mode == 'sequence' and direction == 'request': value['seq'] = 2
                    elif mode == 'ack' and direction == 'request' and value['type'] == 'ack':
                        value['digest'] = '0' * 64
                    elif mode == 'lost-result' and direction == 'reply': return b''
                    return f.api.rpc.pack(value)
                f.wire_hook = alter
                with self.assertRaises(ValueError): controller.run_phase('A')
                self.assertTrue(f.s.preserved)
                self.assertEqual(f.s.registered(), ('',))
                self.assertFalse(any(c.startswith('STOP') for t in f.transports for c in t.commands))

    def test_durable_transition_failures_before_and_after_append_are_terminal(self):
        kinds = ('phases-intent', 'phase-intent', 'namespace-intent', 'namespace-born', 'phase-born',
                 'worker-intent', 'task', 'worker-policy', 'rpc-content', 'rpc-intent', 'rpc-result',
                 'rpc-ack', 'phase-checkpoint', 'namespace-stop-intent', 'namespace-closed', 'phase-complete')
        for kind in kinds:
            for after in (False, True):
                with self.subTest(kind=kind, after=after):
                    f = fixture.Fixture()
                    try:
                        append = f.s.ledger.append
                        def fail(event):
                            if event['kind'] == kind:
                                if after: append(event)
                                raise OSError('injected durable transition failure')
                            return append(event)
                        f.s.ledger.append = fail
                        controller = None
                        with self.assertRaises(OSError):
                            controller = f.controller()
                            controller.run_phase('A')
                        self.assertTrue(f.s.preserved)
                        births = f.spawn_count
                        if controller is not None:
                            with self.assertRaises(ValueError): controller.run_phase('B')
                        self.assertEqual(f.spawn_count, births)
                        self.assertFalse(f.s.closed)
                    finally: f.close()

    def test_closure_failures_and_output_mismatch_cannot_authorize_successor(self):
        for mode in ('stop', 'wait-closed', 'output-mismatch'):
            with self.subTest(mode=mode):
                f = fixture.Fixture(); self.addCleanup(f.close)
                controller = f.controller()
                def fail(point, transport):
                    if point == mode: raise OSError('incomplete namespace closure')
                    if point == 'wait-closed' and mode == 'output-mismatch': transport.stdout.extend(b'foreign')
                f.hook = fail
                with self.assertRaises((ValueError, OSError)): controller.run_phase('A')
                self.assertTrue(f.s.preserved)
                with self.assertRaises(ValueError): controller.run_phase('B')
                self.assertEqual(f.spawn_count, 1)

    def test_old_transport_pidfd_or_closure_loss_prevents_next_birth(self):
        controller = self.f.controller(); controller.run_phase('A')
        self.f.transports[0].bad = True
        with self.assertRaises(OSError): controller.run_phase('B')
        self.assert_preserved(controller)
        self.assertEqual(self.f.spawn_count, 1)

    def test_stale_grant_and_retired_rpc_cannot_be_reused(self):
        controller = self.f.controller(); controller.run_phase('A')
        scope = controller.scopes[0]
        cache = dict(scope.server.contents)
        with self.assertRaises(ValueError): self.f.api.PhaseLifecycle.create(controller, scope.grant)
        self.assert_preserved(controller)
        self.assertEqual(cache, scope.server.contents)
        self.assertEqual(self.f.spawn_count, 1)

    def test_cumulative_output_budget_is_charged_before_refusal(self):
        controller = self.f.controller()
        controller.output['stdout'] = self.f.api.OUTPUT_LIMIT
        def overflow(point, transport):
            if point == 'before-task':
                transport.stdout.extend(b'x')
                transport.capture.charge('stdout', b'x')
        self.f.hook = overflow
        with self.assertRaises(ValueError): controller.run_phase('A')
        self.assertEqual(controller.output['stdout'], self.f.api.OUTPUT_LIMIT + 1)
        self.assertEqual(self.f.transports[0].stdout, b'x')
        self.assert_preserved(controller)

    def test_shared_request_limit_cannot_be_reset_for_a_phase(self):
        controller = self.f.controller()
        controller.requests._total = self.f.api.rpc.MAX_REQUESTS
        with self.assertRaises(ValueError): controller.run_phase('A')
        self.assertEqual(self.f.s.registered(), ('',))
        self.assert_preserved(controller)

    def test_outstanding_record_stage_is_not_quiescence(self):
        controller = self.f.controller()
        self.f.store.record_stages['synthetic-stage'] = ('view', 'target', {}, None)
        with self.assertRaises(ValueError): controller.run_phase('A')
        self.assertEqual(self.f.spawn_count, 0)
        self.assert_preserved(controller)

    def test_incomplete_phase_collection_cannot_call_internal_removal(self):
        controller = self.f.controller()
        with self.assertRaises(ValueError): self.f.s._remove_registered(controller)
        self.assert_preserved(controller)

    def test_a_worker_cannot_install_before_next_grant(self):
        controller = self.f.controller()
        def later_action(point, transport):
            if point == 'spawn': transport.plan.append({'action': 'install'})
        self.f.hook = later_action
        with self.assertRaises(ValueError): controller.run_phase('A')
        e = self.f.store.e
        self.assertNotIn(e.JOURNAL, self.f.s.objects)
        self.assertNotIn(e.STAGES[e.JOURNAL], self.f.s.objects)
        for path in (e.SOURCE, e.DEPLOYED):
            self.assertEqual(self.f.k.journals[self.f.s.objects[path].fd], self.f.store.baseline)
        self.assert_preserved(controller)

    def test_partial_forward_checkpoint_is_rejected_after_validator_returns(self):
        controller = self.f.controller()
        # Inject only the pure validator result: checkpoint policy must independently
        # require the full six forward operations, never a legal partial rollback.
        observed = ({'enrollment_id': 'e' * 32}, {},
                    {'phase': 'restored', 'intent': None, 'forward': [None] * 4, 'reverse': [None] * 5}, {})
        with patch.object(self.f.store.e, 'observe', return_value=observed):
            with self.assertRaisesRegex(ValueError, 'exact complete'): self.f.store.phase_checkpoint('C')
        self.assertEqual(self.f.spawn_count, 0)

    def test_timeout_missing_policy_and_exec_never_grant_handoff(self):
        for mode in ('timeout', 'policy', 'exec'):
            with self.subTest(mode=mode):
                f = fixture.Fixture()
                try:
                    controller = f.controller()
                    def fail(point, transport):
                        if mode == 'timeout' and point == 'receive' and transport.birth is not None:
                            raise TimeoutError('absolute worker deadline reached')
                        if point != 'send': return
                        nonce = transport.nonce
                        if mode == 'policy' and transport.last_command == 'ACK ' + nonce + ' 1':
                            transport.events.put(f'TASK {nonce} 2 EXEC 2 1')
                        if mode == 'exec' and transport.last_command == 'ACK ' + nonce + ' 0':
                            transport.events.put(f'RPC {nonce} 1 2 invalid')
                    f.hook = fail
                    with self.assertRaises((ValueError, TimeoutError)): controller.run_phase('A')
                    self.assertTrue(f.s.preserved)
                    self.assertFalse(f.s.closed)
                    with self.assertRaises(ValueError): controller.run_phase('B')
                    self.assertEqual(f.spawn_count, 1)
                finally: f.close()

    def test_successor_reordering_nonce_replay_root_and_closed_proof_changes_refuse(self):
        for mode in ('repeat', 'skip', 'nonce', 'root', 'old-frame', 'birth-proof', 'byte-limit', 'event-limit'):
            with self.subTest(mode=mode):
                f = fixture.Fixture()
                try:
                    controller = f.controller(); controller.run_phase('A')
                    phase = 'A' if mode == 'repeat' else 'C' if mode == 'skip' else 'B'
                    if mode == 'root':
                        root = f.s.objects['']
                        f.k.names[root.parent, root.name] = f.k.node(True)
                    if mode == 'birth-proof': controller.scopes[0].birth['pidfd'] += 1
                    if mode == 'old-frame':
                        old = controller.scopes[0].server
                        with self.assertRaises(ValueError):
                            old.accept(f.api.rpc.request_frames(controller.session_id, 1, old.seq, 'open', {'root': f.store.root})[0])
                    if mode == 'byte-limit':
                        patcher = patch.object(f.case.api.runtime, 'MAX_BYTES', len(f.s.ledger.history)); patcher.start()
                    elif mode == 'event-limit':
                        patcher = patch.object(f.case.api.runtime, 'MAX_EVENTS', f.s.ledger.sequence); patcher.start()
                    else: patcher = None
                    try:
                        with patch.object(f.api.secrets, 'token_hex', return_value=controller.scopes[0].session if mode == 'nonce' else 'a' * 32):
                            with self.assertRaises(ValueError): controller.run_phase(phase)
                    finally:
                        if patcher is not None: patcher.stop()
                    self.assertTrue(f.s.preserved)
                    self.assertEqual(f.spawn_count, 1)
                finally: f.close()

    def test_final_evidence_and_partial_teardown_failures_preserve(self):
        # Synthetic closed records isolate the final barrier; the separate complete
        # cycle verifies these same methods over real engine/RPC checkpoints.
        from types import SimpleNamespace
        for kind in ('phases-final', 'teardown-intent', 'remove-intent', 'removed'):
            for after in (False, True):
                with self.subTest(kind=kind, after=after):
                    f = fixture.Fixture()
                    try:
                        controller = f.controller()
                        proof = {'state': 'closed'}
                        controller.receipts = [dict(checkpoint=proof)] * 4
                        controller.scopes = [SimpleNamespace(_closed_sequence=i, verify_closed=lambda: None) for i in range(4)]
                        f.store.phase_checkpoint = lambda phase: proof
                        append = f.s.ledger.append
                        def fail(event):
                            if event['kind'] == kind:
                                if after: append(event)
                                raise OSError('interrupted final evidence or removal')
                            return append(event)
                        f.s.ledger.append = fail
                        with self.assertRaises(OSError): controller.teardown()
                        self.assertTrue(f.s.preserved)
                        self.assertFalse(f.s.closed)
                        before = len(f.k.calls)
                        with self.assertRaises(ValueError): controller.teardown()
                        self.assertFalse(any(c[0] == 'remove' for c in f.k.calls[before:]))
                    finally: f.close()

    def test_direct_final_removal_requires_durable_collection_evidence(self):
        controller = self.f.controller()
        for phase in ('A', 'B', 'C', 'D'): controller.run_phase(phase)
        self.f.s._remove_registered(controller)
        import json
        kinds = [json.loads(line)['event']['kind'] for line in self.f.s.ledger.history.splitlines()]
        self.assertTrue('phases-final' in kinds, 'missing final collection durability event')
        self.assertLess(kinds.index('phases-final'), kinds.index('teardown-intent'))
        self.assertEqual(kinds.count('phases-final'), 1)

    def test_z_complete_four_phases_retains_all_original_proofs(self):
        controller = self.f.controller()
        original_root = self.f.s.objects['']
        records = [controller.run_phase(name) for name in ('A', 'B', 'C', 'D')]
        self.assertEqual([r['checkpoint']['state'] for r in records], ['enrolled', 'installed', 'restored', 'closed'])
        self.assertEqual(self.f.spawn_count, 4)
        self.assertEqual([t.waits for t in self.f.transports], [1, 1, 1, 1])
        self.assertIs(self.f.s.objects[''], original_root)
        self.assertEqual(len({s.session for s in controller.scopes}), 4)
        self.assertTrue(all(s.server.retired and s.server.quiescent for s in controller.scopes))
        controller.teardown()
        self.assertTrue(self.f.s.closed)
        self.assertEqual([t.waits for t in self.f.transports], [1, 1, 1, 1])


if __name__ == '__main__': unittest.main(verbosity=2)
