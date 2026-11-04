"""Native capability entry under an entirely fake LinuxKernel boundary."""
import contextlib
import hashlib
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location('native_grant_fixture', HERE / 'host_canary_phase_fixture.py')
fixture = importlib.util.module_from_spec(spec); sys.modules[spec.name] = fixture; spec.loader.exec_module(fixture)


class NativeGrantTests(unittest.TestCase):
    def setUp(self):
        self.f = fixture.Fixture(real_program=getattr(self, "real_program", False)); self.addCleanup(self.f.close)
        self.rt = self.f.case.api.runtime
        fake = self.f.k
        kernel = self.rt.LinuxKernel()  # inert; every method below is intercepted
        kernel.__dict__.update({k:v for k,v in vars(fake).items() if k!='process_transport'})
        self.boundaries = contextlib.ExitStack(); self.addCleanup(self.boundaries.close)
        for name, value in vars(self.rt.LinuxKernel).items():
            if callable(value):
                method = getattr(fake, name, Mock(side_effect=AssertionError('unmocked Linux call '+name)))
                def delegate(instance, *args, _method=method, **kwargs): return _method(*args, **kwargs)
                self.boundaries.enter_context(patch.object(self.rt.LinuxKernel, name, new=delegate))
        self.f.k = self.f.s.k = self.f.store.k = self.f.store.program.k = self.f.runtime.k = kernel
        self.f.s.bootstrap.k = self.f.s.bootstrap.canonical_grant.kernel = kernel
        self.api = self.f.s.linux_module()
        self.plan = hashlib.sha256(self.f.api.life.canonical(self.f.api.PHASES)).hexdigest()

    def grant(self, digest=None):
        return self.api.LinuxPhaseGrant(self.f.s, self.f.helper_fd, self.f.helper_digest,
            self.f.runtime, self.f.store, self.plan if digest is None else digest)

    def test_boolean_json_foreign_and_wrong_plan_cannot_enable_native(self):
        for value in (True, {}, {'session': 'd'*32}, object()):
            with self.assertRaises(ValueError): self.f.s.linux_phases(value)
        with self.assertRaises(ValueError): self.grant('0'*64)
        self.assertTrue(self.f.s.preserved)
        self.assertEqual(self.f.spawn_count, 0)

    def test_instance_factory_is_not_native_authority(self):
        fake = Mock(side_effect=AssertionError('injected factory used'))
        self.f.k.process_transport = fake
        with self.assertRaises(ValueError): self.grant()
        fake.assert_not_called()

    def test_original_grant_is_bound_and_consumed_once_before_birth(self):
        grant = self.grant()
        c = self.f.s.linux_phases(grant)
        self.assertIs(c.native, grant)
        self.assertIs(c.s, self.f.s); self.assertIs(c.ledger, self.f.s.ledger)
        self.assertIs(c.store, self.f.store)
        self.assertEqual(c.state, 'ready')
        with self.assertRaises(ValueError): self.f.s.linux_phases(grant)
        self.assertTrue(self.f.s.preserved)
        self.assertEqual(self.f.spawn_count, 0)

    def test_offline_entry_never_accepts_native_kernel_even_after_issue(self):
        self.grant()
        with self.assertRaises(ValueError): self.f.controller()
        self.assertEqual(self.f.spawn_count, 0)

    def test_native_start_failure_keeps_partial_transport_and_no_retry(self):
        error = OSError('mocked native launch interrupted')
        transport = self.f.api.life.LinuxTransport()
        error.transport = transport
        with patch.object(self.f.api.life.LinuxTransport, 'spawn', side_effect=error) as spawn:
            grant = self.grant(); c = self.f.s.linux_phases(grant)
            with self.assertRaises(OSError): c.run_phase('A')
            self.assertIs(c._active.transport, transport)
            self.assertIs(grant.transports[0], transport)
            self.assertEqual(spawn.call_count, 1)
            with self.assertRaises(ValueError): c.run_phase('A')
            self.assertEqual(spawn.call_count, 1)
        self.assertTrue(self.f.s.preserved)

    def test_controller_loss_refuses_even_direct_native_grant_reuse(self):
        grant = self.grant(); c = self.f.s.linux_phases(grant)
        self.f.s._phase_controller = None
        with self.assertRaises(ValueError): grant.verify()
        self.assertTrue(self.f.s.preserved)
        self.assertEqual(c.state, "preserved")

    def test_failed_durable_issue_and_consumption_preserve_original_authority(self):
        for point in ("issue", "consume"):
            with self.subTest(point=point):
                if point == "consume": grant = self.grant()
                with patch.object(self.f.s.ledger, "append", side_effect=OSError("sync interrupted")):
                    with self.assertRaises(OSError):
                        if point == "issue": self.grant()
                        else: self.f.s.linux_phases(grant)
                self.assertTrue(self.f.s.preserved)
                self.assertIsNotNone(self.f.s._linux_phase_grant)
                self.assertEqual(self.f.spawn_count, 0)
                if point == "issue":
                    # Separate synthetic session for the second failure boundary.
                    self.doCleanups(); self.setUp()

    def test_birth_binding_failure_retains_complete_partial_lifecycle(self):
        grant = self.grant(); c = self.f.s.linux_phases(grant)
        scope = SimpleNamespace(transport=object(), birth={"pid": 123})
        with patch.object(self.f.api.PhaseLifecycle, "start", return_value=scope), \
             patch.object(grant, "bind_transport", side_effect=ValueError("aliased birth")):
            with self.assertRaises(ValueError): c.run_phase("A")
        self.assertIs(c._active, scope)
        self.assertIs(scope.server, c._pending_server)
        self.assertIs(scope.owner, c)
        self.assertTrue(self.f.s.preserved)
        self.assertEqual(c.state, "preserved")

    def final_policy(self):
        # Isolate capability policy with explicitly synthetic closed records.
        # Actual transport closure is exercised separately with mocked syscalls.
        c = self.f.s.linux_phases(self.grant())
        checkpoint = {'state': 'closed', 'graph_sha256': '1'*64}
        c.receipts = [dict(checkpoint=checkpoint)] * 4
        c.scopes = [SimpleNamespace(_closed_sequence=i, verify_closed=lambda: None) for i in range(4)]
        c.continuity = lambda: None
        self.f.store.phase_checkpoint = lambda phase: checkpoint
        return c, checkpoint

    def test_execution_grant_does_not_authorize_final_fixture_removal(self):
        c, checkpoint = self.final_policy()
        before = len(self.f.k.calls)
        with self.assertRaises(ValueError): c.teardown()
        self.assertFalse(any(row[0]=='remove' for row in self.f.k.calls[before:]))
        self.assertTrue(self.f.s.preserved)

    def test_separate_original_removal_grant_is_one_use(self):
        c, checkpoint = self.final_policy()
        grant = self.api.LinuxRemovalGrant(c, checkpoint['graph_sha256'])
        c.teardown(removal=grant)
        self.assertTrue(self.f.s.closed)
        with self.assertRaises(ValueError): c.teardown(removal=grant)


if __name__ == '__main__': unittest.main(verbosity=2)
