"""In-memory descriptor/registry checks; no Host Canary fixture or OS adapter."""
import ast
from contextlib import ExitStack
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import types
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).with_name('host_canary_supervisor.py')
RAW = SOURCE.read_bytes() if SOURCE.exists() else None


def forbidden(*args, **kwargs):
    raise AssertionError('source-only test attempted real OS operation')


class MemoryOS:
    def __init__(self):
        self.nodes = {
            2: dict(st_dev=7, st_ino=20, st_uid=1000, st_gid=1000,
                    st_mode=stat.S_IFDIR | 0o700, st_nlink=2, st_size=0),
            3: dict(st_dev=7, st_ino=30, st_uid=1000, st_gid=1000,
                    st_mode=stat.S_IFREG | 0o600, st_nlink=1, st_size=0),
            4: dict(st_dev=7, st_ino=40, st_uid=1000, st_gid=1000,
                    st_mode=stat.S_IFDIR | 0o700, st_nlink=2, st_size=0),
        }
        self.names = {(2, 'registry'): 3, (2, 'child'): 4}
        self.calls, self.data = [], bytearray()
        self.ns = ('mount-a', 'user-a')
        self.mount = 9
        self.xattrs = []
        self.write_result = None
        self.sync_hook = lambda fd: None

    def fstat(self, fd):
        self.calls.append(('fstat', fd))
        return types.SimpleNamespace(**self.nodes[fd])

    def stat(self, name, *, dir_fd, follow_symlinks):
        self.calls.append(('stat', dir_fd, name, follow_symlinks))
        assert follow_symlinks is False
        return types.SimpleNamespace(**self.nodes[self.names[dir_fd, name]])

    def listxattr(self, fd):
        return list(self.xattrs)

    def mount_id(self, fd):
        return self.mount

    def namespace(self):
        return self.ns

    def write(self, fd, raw):
        self.calls.append(('write', fd))
        size = len(raw) if self.write_result is None else self.write_result
        self.data.extend(raw[:max(0, size)])
        self.nodes[fd]['st_size'] = len(self.data)
        return size

    def fsync(self, fd):
        self.calls.append(('fsync', fd))
        self.sync_hook(fd)


class SupervisorChecks(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(RAW, 'source-only supervisor verification component missing')
        self.api = types.ModuleType('host_supervisor_under_test')
        sys.modules[self.api.__name__] = self.api
        self.addCleanup(sys.modules.pop, self.api.__name__, None)
        exec(compile(RAW, str(SOURCE), 'exec'), self.api.__dict__)
        guards = ExitStack()
        self.addCleanup(guards.close)
        guards.enter_context(patch('builtins.open', forbidden))
        for name in ('open', 'stat', 'lstat', 'fstat', 'mkdir', 'makedirs', 'listdir',
                     'scandir', 'unlink', 'rmdir', 'rename', 'replace', 'write', 'fsync',
                     'close', 'dup', 'kill', 'killpg', 'listxattr'):
            guards.enter_context(patch.object(os, name, forbidden))
        guards.enter_context(patch.object(subprocess, 'Popen', forbidden))
        self.os = MemoryOS()
        self.verifier = self.api.DescriptorVerifier(self.os, 1000, 1000, self.os.ns)
        self.parent = self.verifier.parent(2)
        self.registry = self.verifier.child(3, self.parent, 'registry', directory=False)
        self.writer = self.api.RegistryWriter(self.verifier, self.registry, 'a' * 32)

    def test_binding_checks_descriptor_and_nonfollowing_parent_name(self):
        self.verifier.verify(self.registry)
        self.assertIn(('stat', 2, 'registry', False), self.os.calls)
        self.os.nodes[3]['st_ino'] = 31
        with self.assertRaises(self.api.SupervisorError):
            self.verifier.verify(self.registry)
        self.assertTrue(self.verifier.poisoned)

    def test_unsafe_basename_refuses_before_os_access(self):
        for name in ('', '.', '..', '/child', '../child', 'a/b', 'a\\b', 'a\x00', 'a\n', None):
            with self.subTest(name=name):
                verifier = self.api.DescriptorVerifier(self.os, 1000, 1000, self.os.ns)
                parent = verifier.parent(2)
                before = len(self.os.calls)
                with self.assertRaises(self.api.SupervisorError):
                    verifier.child(4, parent, name, directory=True)
                self.assertEqual(len(self.os.calls), before)

    def test_metadata_mount_namespace_and_xattrs_never_become_new_expectations(self):
        for field, value in (('st_uid', 2), ('st_gid', 2), ('st_mode', stat.S_IFREG | 0o666),
                             ('st_nlink', 2), ('st_dev', 8)):
            with self.subTest(field=field):
                boundary = MemoryOS()
                verifier = self.api.DescriptorVerifier(boundary, 1000, 1000, boundary.ns)
                parent = verifier.parent(2)
                binding = verifier.child(3, parent, 'registry', directory=False)
                boundary.nodes[3][field] = value
                with self.assertRaises(self.api.SupervisorError):
                    verifier.verify(binding)
                self.assertTrue(verifier.poisoned)
        for change in ('namespace', 'mount', 'xattr'):
            with self.subTest(change=change):
                boundary = MemoryOS()
                verifier = self.api.DescriptorVerifier(boundary, 1000, 1000, boundary.ns)
                parent = verifier.parent(2)
                binding = verifier.child(3, parent, 'registry', directory=False)
                if change == 'namespace': boundary.ns = ('other', 'user-a')
                if change == 'mount': boundary.mount = 10
                if change == 'xattr': boundary.xattrs = ['user.unknown']
                with self.assertRaises(self.api.SupervisorError): verifier.verify(binding)

    def test_parent_replacement_and_known_descriptor_loss_refuse(self):
        self.os.names[2, 'registry'] = 4
        with self.assertRaises(self.api.SupervisorError): self.verifier.verify(self.registry)
        boundary = MemoryOS()
        verifier = self.api.DescriptorVerifier(boundary, 1000, 1000, boundary.ns)
        parent = verifier.parent(2)
        verifier.lost(parent)
        with self.assertRaises(self.api.SupervisorError): verifier.verify(parent)
        with self.assertRaises(self.api.SupervisorError): verifier.parent(2)

    def test_forged_or_stale_binding_is_not_a_local_handle(self):
        forged = dataclasses.replace(self.registry, generation=self.registry.generation + 1)
        with self.assertRaises(self.api.SupervisorError): self.verifier.verify(forged)

    def test_registry_ack_follows_exact_write_sync_and_post_sync_binding(self):
        ack = self.writer.append({'kind': 'intent', 'name': 'child'})
        self.assertTrue(self.writer.owns(ack))
        first = json.loads(self.os.data)
        self.assertEqual(first['seq'], 1)
        self.assertEqual(first['previous'], '0' * 64)
        self.assertEqual(first['event'], {'kind': 'intent', 'name': 'child'})
        self.assertEqual([c for c in self.os.calls if c[0] in ('write', 'fsync')],
                         [('write', 3), ('fsync', 3), ('fsync', 2)])
        last_sync = max(i for i, c in enumerate(self.os.calls) if c[0] == 'fsync')
        self.assertIn(('stat', 2, 'registry', False), self.os.calls[last_sync + 1:])
        digest = hashlib.sha256(bytes(self.os.data)).hexdigest()
        self.writer.append({'kind': 'next'})
        second = json.loads(bytes(self.os.data).splitlines()[1])
        self.assertEqual(second['seq'], 2)
        self.assertEqual(second['previous'], digest)
        self.assertFalse(self.writer.owns(dataclasses.replace(ack)))

    def test_short_write_permanently_poisons_and_preserves_partial_bytes(self):
        self.os.write_result = 5
        with self.assertRaises(self.api.SupervisorError): self.writer.append({'kind': 'intent'})
        self.assertEqual(len(self.os.data), 5)
        before = list(self.os.calls)
        with self.assertRaises(self.api.SupervisorError): self.writer.append({'kind': 'retry'})
        self.assertEqual(self.os.calls, before)
        self.assertTrue(self.writer.poisoned)

    def test_sync_failures_or_post_sync_replacement_never_acknowledge(self):
        for phase in (3, 2):
            with self.subTest(phase=phase):
                for drift in ('error', 'registry', 'parent', 'permissions', 'size'):
                    boundary = MemoryOS()
                    verifier = self.api.DescriptorVerifier(boundary, 1000, 1000, boundary.ns)
                    parent = verifier.parent(2)
                    registry = verifier.child(3, parent, 'registry', directory=False)
                    writer = self.api.RegistryWriter(verifier, registry, 'b' * 32)
                    def change(fd):
                        if fd != phase: return
                        if drift == 'error': raise OSError('synthetic fsync failure')
                        if drift == 'registry': boundary.nodes[3]['st_ino'] += 1
                        if drift == 'parent': boundary.nodes[2]['st_ino'] += 1
                        if drift == 'permissions': boundary.nodes[3]['st_mode'] |= 0o020
                        if drift == 'size': boundary.nodes[3]['st_size'] += 1
                    boundary.sync_hook = change
                    with self.assertRaises(self.api.SupervisorError): writer.append({'kind': 'intent'})
                    self.assertTrue(writer.poisoned)
                    self.assertGreater(len(boundary.data), 0)

    def test_serialization_and_byte_record_count_limits_poison_before_write(self):
        for event, limit in (({'blob': 'x' * 4096}, None), ({'bad': float('nan')}, None),
                             ({'kind': 'intent'}, 'MAX_EVENTS'), ({'kind': 'intent'}, 'MAX_BYTES')):
            boundary = MemoryOS()
            verifier = self.api.DescriptorVerifier(boundary, 1000, 1000, boundary.ns)
            parent = verifier.parent(2)
            registry = verifier.child(3, parent, 'registry', directory=False)
            writer = self.api.RegistryWriter(verifier, registry, 'c' * 32)
            with ExitStack() as patches:
                if limit: patches.enter_context(patch.object(self.api, limit, 0))
                with self.assertRaises(self.api.SupervisorError): writer.append(event)
            self.assertEqual(boundary.data, b'')
            self.assertTrue(writer.poisoned)

    def test_use_requires_own_durable_intent_and_registration(self):
        session = self.api.SessionModel(self.writer)
        with self.assertRaises(self.api.SupervisorError): session.use('child')
        self.assertTrue(session.preserved)

    def test_model_registration_and_use_still_cannot_grant_live_cleanup(self):
        session = self.api.SessionModel(self.writer)
        session.intent('child', self.parent, 'child')
        child = self.verifier.child(4, self.parent, 'child', directory=True)
        session.created('child', child)
        self.assertEqual(session.use('child'), 'MODEL ONLY: child')
        for claim in (True, {'closed': True}, lambda: self.fail('closure callback invoked')):
            with self.assertRaisesRegex(self.api.SupervisorError, 'disabled'):
                session.cleanup_plan(claim)

    def test_missing_intent_poisons_session(self):
        session = self.api.SessionModel(self.writer)
        child = self.verifier.child(4, self.parent, 'child', directory=True)
        with self.assertRaises(self.api.SupervisorError): session.created('child', child)
        self.assertTrue(session.preserved)
        with self.assertRaises(self.api.SupervisorError): session.intent('child', self.parent, 'child')

    def test_unknown_descendant_and_partial_cleanup_never_resume(self):
        session = self.api.SessionModel(self.writer)
        session.preserve('unknown descendant or interrupted cleanup')
        self.assertTrue(session.preserved)
        with self.assertRaises(self.api.SupervisorError): session.intent('child', self.parent, 'child')
        with self.assertRaises(self.api.SupervisorError): session.cleanup_plan()

    def test_write_error_after_partial_effect_retains_bytes_and_revokes(self):
        def partial(fd, raw):
            self.os.data.extend(raw[:7])
            self.os.nodes[fd]['st_size'] = 7
            raise OSError('synthetic partial-write error')
        self.os.write = partial
        with self.assertRaises(self.api.SupervisorError): self.writer.append({'kind': 'intent'})
        self.assertEqual(len(self.os.data), 7)
        self.assertTrue(self.writer.poisoned)
        with self.assertRaises(self.api.SupervisorError): self.writer.append({'kind': 'retry'})
        self.assertEqual(len(self.os.data), 7)

    def test_duplicate_intent_revokes_without_second_registry_write(self):
        session = self.api.SessionModel(self.writer)
        session.intent('child', self.parent, 'child')
        previous = bytes(self.os.data)
        with self.assertRaises(self.api.SupervisorError): session.intent('child', self.parent, 'child')
        self.assertTrue(session.preserved)
        self.assertEqual(bytes(self.os.data), previous)

    def test_wrong_parent_registration_preserves_session(self):
        session = self.api.SessionModel(self.writer)
        session.intent('child', self.parent, 'child')
        other_parent = self.verifier.parent(4)
        self.os.nodes[5] = dict(self.os.nodes[4], st_ino=50)
        self.os.names[4, 'child'] = 5
        wrong = self.verifier.child(5, other_parent, 'child', directory=True)
        with self.assertRaises(self.api.SupervisorError): session.created('child', wrong)
        self.assertTrue(session.preserved)

    def test_registered_child_drift_revokes_model_use(self):
        session = self.api.SessionModel(self.writer)
        session.intent('child', self.parent, 'child')
        child = self.verifier.child(4, self.parent, 'child', directory=True)
        session.created('child', child)
        self.os.nodes[4]['st_ino'] += 1
        with self.assertRaises(self.api.SupervisorError): session.use('child')
        self.assertTrue(session.preserved)

    def test_source_has_no_allocation_process_or_cleanup_implementation(self):
        for node in ast.walk(ast.parse(RAW)):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                self.assertNotIn(node.func.attr, ('open', 'mkdir', 'mkdtemp', 'Popen', 'spawn',
                                                 'unlink', 'rmdir', 'rmtree', 'kill', 'killpg'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
