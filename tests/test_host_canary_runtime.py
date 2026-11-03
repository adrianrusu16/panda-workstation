"""OS-adapter regression tests using fake descriptors only; no fixture allocation."""
import dataclasses
import hashlib
from contextlib import ExitStack
import importlib.util
import json
from pathlib import Path
import stat
import sys
import types
import unittest
from unittest.mock import Mock, patch

SOURCE = Path(__file__).with_name('host_canary_runtime.py')


class FakeKernel:
    def __init__(self):
        self.uid, self.gid = 1000, 1000
        self.nodes = {}
        self.names = {}
        self.calls = []
        self.nextfd = 10
        self.tick = 1
        self.fail_at = None
        self.hook = lambda operation: None
        self.parent = self.node(True)
        self.anchor = self.node(True)
        self.journals = {}

    def node(self, directory, mode=None):
        self.nextfd += 1
        fd = self.nextfd
        self.nodes[fd] = dict(dev=7, ino=fd + 100, uid=self.uid, gid=self.gid,
                              mode=(stat.S_IFDIR | 0o700) if directory else (stat.S_IFREG | (mode or 0o600)),
                              nlink=2 if directory else 1, size=0, ctime=self.tick, mtime=self.tick, atime=self.tick,
                              mount=9, filesystem=0xEF53, namespace=(21, 22), xattrs=(), flags=262144, fdflags=1)
        return fd

    def bind_context(self):
        self.call('bind-context')

    def identity(self):
        return self.uid, self.gid

    def call(self, name, *args):
        self.calls.append((name, *args))
        self.hook(name)
        if self.fail_at == name:
            raise OSError('injected ' + name)

    def snapshot(self, fd):
        self.call('snapshot', fd)
        return dict(self.nodes[fd])

    def observe(self, parent, name):
        self.call('observe', parent, name)
        return self.snapshot(self.names[parent, name])

    def entries(self, fd):
        self.call('entries', fd)
        return sorted(name for (parent, name) in self.names if parent == fd)

    def create(self, parent, name, directory, mode):
        self.call('create', parent, name, directory)
        if (parent, name) in self.names:
            raise FileExistsError(name)
        fd = self.node(directory, mode)
        if not directory:
            self.nodes[fd]['flags'] = 2 | 1024 | 262144
        self.names[parent, name] = fd
        self.touch(parent, 1 if directory else 0)
        return fd

    def touch(self, fd, links=0):
        self.tick += 1
        if self.nodes[fd]['filesystem'] == 0x9123683E:
            links = 0
        self.nodes[fd].update(ctime=self.tick, mtime=self.tick,
                              nlink=self.nodes[fd]['nlink'] + links)

    def lock(self, fd):
        self.call('lock', fd)

    def read(self, fd, count, offset):
        self.call('read', fd)
        return self.journals.get(fd, b'')[offset:offset + count]

    def offset(self, fd):
        return len(self.journals.get(fd, b''))

    def write(self, fd, raw):
        self.call('write', fd)
        self.journals[fd] = self.journals.get(fd, b'') + raw
        self.nodes[fd]['size'] = len(self.journals[fd])
        self.touch(fd)
        return len(raw)

    def sync(self, fd):
        self.call('sync', fd)

    def remove(self, parent, name, directory):
        self.call('remove', parent, name, directory)
        fd = self.names.pop((parent, name))
        if directory and self.entries(fd):
            raise OSError('not empty')
        self.nodes[fd]['nlink'] = 0
        self.touch(parent, -1 if directory else 0)

    def chmod(self, fd, mode):
        self.call('chmod', fd, mode)
        self.nodes[fd]['mode'] = stat.S_IFREG | mode
        self.touch(fd)

    def timestamps(self, fd):
        self.call('timestamps', fd)
        self.touch(fd)
        self.nodes[fd]['mtime'] = 0
        self.nodes[fd]['atime'] = 0

    def replace(self, source_parent, source_name, target_parent, target_name):
        self.call('replace', source_parent, source_name, target_parent, target_name)
        old = self.names.get((target_parent, target_name))
        if old is not None:
            self.nodes[old]['nlink'] = 0
            self.touch(old)
        fd = self.names.pop((source_parent, source_name))
        self.names[target_parent, target_name] = fd
        old_mtime = self.nodes[fd]['mtime']
        self.touch(fd)
        self.nodes[fd]['mtime'] = old_mtime
        self.touch(target_parent)


class ClosedLifecycleForFilesystemUnitTests:
    """Reaches FS algorithm only; not a production lifecycle acceptance receipt."""
    def __init__(self, kernel): self.k = kernel
    def finish(self): self.k.call('mock-lifecycle-closed')


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SOURCE.exists(), 'OS-backed supervisor module missing')
        spec = importlib.util.spec_from_file_location('canary_runtime_test', SOURCE)
        self.api = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = self.api
        self.addCleanup(sys.modules.pop, spec.name, None)
        spec.loader.exec_module(self.api)
        self.k = FakeKernel()
        self.authority = self.api.TrustedBootstrap(self.k, self.k.parent, self.k.anchor, 'a' * 32)
        self.session = self.authority.session()
        # Every actual adapter call must have its syscall explicitly replaced by
        # this test. Default guards prevent an accidental live invocation.
        guards = ExitStack()
        self.addCleanup(guards.close)
        def forbidden(*args, **kwargs):
            raise AssertionError('mock-only test attempted real Host adapter syscall')
        actual_os = self.api.os
        denied = frozenset(('open', 'stat', 'fstat', 'mkdir', 'listdir', 'read', 'pread', 'write', 'lseek',
                            'fsync', 'close', 'dup', 'rename', 'rmdir', 'unlink', 'fchmod', 'utime',
                            'listxattr', 'geteuid', 'getegid', 'uname'))
        class GuardedOS:
            def __getattr__(self, name):
                return forbidden if name in denied else getattr(actual_os, name)
        guards.enter_context(patch.object(self.api, 'os', GuardedOS()))
        guards.enter_context(patch.object(self.api.fcntl, 'fcntl', forbidden))
        guards.enter_context(patch.object(self.api.fcntl, 'flock', forbidden))
        guards.enter_context(patch.object(self.api.ctypes, 'CDLL', forbidden))


    def test_ledger_chain_uses_committed_digest_without_splitting_full_prefix(self):
        ledger = self.authority.ledger
        ledger.append({'kind': 'first'})
        class NoSplit(bytes):
            def splitlines(inner, *args, **kwargs):
                raise AssertionError('append rescanned complete history for previous digest')
        ledger.history = NoSplit(ledger.history)
        ledger.append({'kind': 'second'})
        ledger.append({'kind': 'third'})
        lines = bytes(ledger.history).splitlines(keepends=True)
        previous = '0' * 64
        for index, raw in enumerate(lines, 1):
            record = json.loads(raw)
            self.assertEqual(record['seq'], index)
            self.assertEqual(record['previous'], previous)
            previous = hashlib.sha256(raw).hexdigest()
        self.assertEqual(ledger._last_digest, previous)
        self.assertEqual(ledger.sequence, 3)

    def test_interrupted_ledger_append_never_advances_committed_digest(self):
        for failure in ('sync', 'final-read'):
            with self.subTest(failure=failure):
                kernel = FakeKernel()
                boot = self.api.TrustedBootstrap(kernel, kernel.parent, kernel.anchor, 'b' * 32)
                ledger = boot.ledger
                ledger.append({'kind': 'committed'})
                previous, sequence = ledger._last_digest, ledger.sequence
                if failure == 'sync':
                    kernel.fail_at = 'sync'
                else:
                    original_read = kernel.read
                    committed_size = len(ledger.history)
                    def read(fd, count, offset):
                        if fd == ledger.fd and kernel.offset(fd) > committed_size:
                            raise OSError('injected final full-prefix read failure')
                        return original_read(fd, count, offset)
                    kernel.read = read
                with self.assertRaises(OSError): ledger.append({'kind': 'interrupted'})
                self.assertTrue(ledger.poisoned)
                self.assertEqual(ledger._last_digest, previous)
                self.assertEqual(ledger.sequence, sequence)
                before = len(kernel.calls)
                with self.assertRaises(self.api.CustodyError): ledger.append({'kind': 'retry'})
                self.assertEqual(len(kernel.calls), before)

    def test_external_bootstrap_ledger_precedes_first_fixture_allocation(self):
        self.assertEqual(self.k.entries(self.k.parent), [])
        self.assertEqual(self.k.entries(self.k.anchor), ['ledger-' + 'a' * 32])
        self.session.create('')
        calls = [c[0] for c in self.k.calls]
        allocation = max(i for i, c in enumerate(self.k.calls) if c[0] == 'create')
        self.assertIn('write', calls[:allocation])
        self.assertIn('sync', calls[:allocation])
        self.assertEqual(self.session.registered(), ('',))

    def test_no_existing_root_adoption_and_no_retry_after_allocation_failure(self):
        self.k.names[self.k.parent, self.session.root_name] = self.k.node(True)
        with self.assertRaises(Exception):
            self.session.create('')
        self.assertTrue(self.session.preserved)
        before = len(self.k.calls)
        with self.assertRaises(self.api.CustodyError):
            self.session.create('')
        self.assertEqual(len(self.k.calls), before)

    def test_intent_sync_failure_allocates_nothing(self):
        self.k.fail_at = 'sync'
        before = sum(c[0] == 'create' for c in self.k.calls)
        with self.assertRaises(Exception):
            self.session.create('')
        self.assertEqual(sum(c[0] == 'create' for c in self.k.calls), before)
        self.assertTrue(self.session.preserved)

    def test_registered_roles_only_and_controlled_parent_link_transition(self):
        self.session.create('')
        self.session.create('home')
        self.assertEqual(self.session.registered(), ('', 'home'))
        self.session.check()
        before = len(self.k.calls)
        for path in ('../escape', '/tmp', 'home/unknown', 'cache/fish'):
            with self.assertRaises(self.api.CustodyError):
                self.session.create(path)
        self.assertEqual(len(self.k.calls), before)

    def test_unknown_child_revokes_before_any_mutation(self):
        self.session.create('')
        root = self.session.objects[''].fd
        self.k.names[root, 'unwitnessed'] = self.k.node(False)
        before = sum(c[0] == 'create' for c in self.k.calls)
        with self.assertRaises(self.api.CustodyError):
            self.session.create('home')
        self.assertEqual(sum(c[0] == 'create' for c in self.k.calls), before)
        self.assertTrue(self.session.preserved)

    def test_registry_history_same_size_edit_revokes(self):
        self.session.create('')
        fd = self.authority.ledger.fd
        original = self.k.journals[fd]
        self.k.journals[fd] = original.replace(b'create-intent', b'forged-intent', 1)
        with self.assertRaises(self.api.CustodyError):
            self.session.check()

    def test_short_write_and_post_sync_replacement_never_register(self):
        for kind in ('short', 'replace'):
            with self.subTest(kind=kind):
                k = FakeKernel()
                authority = self.api.TrustedBootstrap(k, k.parent, k.anchor, 'b' * 32)
                session = authority.session()
                if kind == 'short':
                    original = k.write
                    k.write = lambda fd, raw: original(fd, raw[:7])
                else:
                    fired = [False]
                    def replace(operation):
                        if operation == 'sync' and not fired[0]:
                            fired[0] = True
                            k.nodes[authority.ledger.fd]['ino'] += 1
                    k.hook = replace
                with self.assertRaises(Exception):
                    session.create('')
                self.assertTrue(session.preserved)
                self.assertEqual(session.registered(), ())

    def test_changed_descriptor_or_parent_binding_refuses(self):
        for kind in ('descriptor', 'name', 'namespace', 'xattr', 'links'):
            with self.subTest(kind=kind):
                k = FakeKernel()
                session = self.api.TrustedBootstrap(k, k.parent, k.anchor, 'c' * 32).session()
                session.create('')
                fd = session.objects[''].fd
                if kind == 'descriptor': k.nodes[fd]['ino'] += 1
                if kind == 'name': k.names[k.parent, session.root_name] = k.node(True)
                if kind == 'namespace': k.nodes[fd]['namespace'] = (99, 22)
                if kind == 'xattr': k.nodes[fd]['xattrs'] = ('user.unknown',)
                if kind == 'links': k.nodes[fd]['nlink'] += 1
                with self.assertRaises(self.api.CustodyError): session.check()
                self.assertTrue(session.preserved)

    def test_no_bool_or_callback_can_claim_process_closure(self):
        self.session.create('')
        for closure in (True, {'closed': True}, lambda: True, object()):
            with self.assertRaises(self.api.CustodyError):
                self.session.teardown(closure)
        self.assertFalse(any(c[0] == 'remove' for c in self.k.calls))

    def test_linux_adapter_has_no_implicit_startup_side_effects(self):
        # Construction holds no paths, descriptors, process or environment authority.
        adapter = self.api.LinuxKernel()
        self.assertIsNotNone(adapter)
        self.assertFalse(hasattr(adapter, 'fixture_cleanup'))

    def test_foreign_bootstrap_parent_refused_before_external_allocation(self):
        k = FakeKernel()
        k.nodes[k.parent]['uid'] = 2000
        k.nodes[k.anchor]['uid'] = 2000
        with self.assertRaises(self.api.CustodyError):
            self.api.TrustedBootstrap(k, k.parent, k.anchor, 'd' * 32)
        self.assertFalse(any(c[0] == 'create' for c in k.calls))

    def build_source_parents(self):
        for path in ('', 'source', 'source/home', 'source/home/dot_config', 'source/home/dot_config/ghostty'):
            self.session.create(path)

    def test_registry_flag_offset_history_limit_and_lock_faults_fail_closed(self):
        for kind in ('flags', 'offset', 'history', 'limit', 'lock'):
            with self.subTest(kind=kind):
                k = FakeKernel()
                if kind == 'lock':
                    k.fail_at = 'lock'
                    with self.assertRaises(Exception):
                        self.api.TrustedBootstrap(k, k.parent, k.anchor, 'f' * 32)
                    self.assertEqual(k.entries(k.parent), [])
                    continue
                a = self.api.TrustedBootstrap(k, k.parent, k.anchor, 'f' * 32)
                s = a.session()
                if kind == 'flags': k.nodes[a.ledger.fd]['flags'] = 2
                if kind == 'offset': k.offset = lambda fd: 99
                if kind == 'history': k.journals[a.ledger.fd] = b'foreign'
                if kind == 'limit': a.ledger.sequence = self.api.MAX_EVENTS
                with self.assertRaises(self.api.CustodyError): s.create('')
                self.assertTrue(s.preserved)
                self.assertEqual(k.entries(k.parent), [])

    def test_incomplete_first_open_keeps_unregistered_entry_and_forbids_retry(self):
        original = self.k.create
        def interrupted(parent, name, directory, mode):
            original(parent, name, directory, mode)
            raise OSError('first open failed after mkdir')
        self.k.create = interrupted
        with self.assertRaises(OSError): self.session.create('')
        self.assertEqual(self.k.entries(self.k.parent), [self.session.root_name])
        self.assertTrue(self.session.preserved)
        self.assertEqual(self.session.registered(), ())
        self.assertFalse(any(c[0] == 'remove' for c in self.k.calls))

    def test_btrfs_parent_links_stay_one_across_registered_directory_birth(self):
        k = FakeKernel()
        original = k.node
        def btrfs_node(directory, mode=None):
            fd = original(directory, mode)
            k.nodes[fd]['filesystem'] = 0x9123683E
            if directory: k.nodes[fd]['nlink'] = 1
            return fd
        k.node = btrfs_node
        for fd in (k.parent, k.anchor):
            k.nodes[fd].update(filesystem=0x9123683E, nlink=1)
        s = self.api.TrustedBootstrap(k, k.parent, k.anchor, 'd' * 32).session()
        s.create('')
        s.create('home')
        s.check()
        self.assertEqual(s.objects[''].pin['nlink'], 1)

    def test_fixed_mode_transition_and_freeze_then_publish_accounts_old_descriptor(self):
        self.build_source_parents()
        target = self.api.SOURCE
        old = self.session.create(target)
        self.assertEqual(old.birth['mode'], stat.S_IFREG | 0o600)
        self.assertEqual(old.pin['mode'], stat.S_IFREG | 0o644)
        self.session.write(old, b'original')
        self.session.freeze_metadata(old)
        stage = self.session.create(self.api.PUBLISH[target])
        self.session.write(stage, b'replacement')
        self.session.freeze_metadata(stage)
        new = self.session.publish(stage.path, target)
        self.assertIs(new, stage)
        self.assertEqual(old.pin['nlink'], 0)
        self.assertIn(old, self.session.retired)
        self.assertNotIn(self.api.PUBLISH[target], self.session.objects)
        self.session.check()
        self.k.nodes[old.fd]['ino'] += 1
        with self.assertRaises(self.api.CustodyError): self.session.check()

    def test_append_partial_write_and_metadata_faults_preserve_original_descriptors(self):
        self.build_source_parents()
        obj = self.session.create(self.api.SOURCE)
        original = self.k.write
        def partial(fd, raw):
            return original(fd, raw[:2] if fd == obj.fd else raw)
        self.k.write = partial
        with self.assertRaises(self.api.CustodyError): self.session.write(obj, b'original')
        self.assertEqual(self.k.journals[obj.fd], b'or')
        self.assertIn(obj.fd, self.session._birth_fds)
        self.assertTrue(self.session.preserved)

    def test_unknown_child_prevents_entire_teardown_before_first_removal(self):
        self.session.create('')
        self.session.create('home')
        self.session._lifecycle = ClosedLifecycleForFilesystemUnitTests(self.k)
        self.k.names[self.session.objects['home'].fd, 'unknown'] = self.k.node(False)
        with self.assertRaises(self.api.CustodyError): self.session.teardown(self.session._lifecycle)
        self.assertFalse(any(c[0] == 'remove' for c in self.k.calls))
        self.assertFalse(any(c[0] == 'mock-lifecycle-closed' for c in self.k.calls))

    def test_exact_teardown_retains_external_ledger_and_deleted_fds(self):
        self.session.create('')
        self.session.create('home')
        self.session._lifecycle = ClosedLifecycleForFilesystemUnitTests(self.k)
        self.session.teardown(self.session._lifecycle)
        self.assertTrue(self.session.closed)
        self.assertEqual(self.k.entries(self.k.parent), [])
        self.assertEqual(self.k.entries(self.k.anchor), [self.authority.ledger.name])
        self.assertEqual(len(self.session.retired), 2)
        self.assertTrue(all(self.k.nodes[o.fd]['nlink'] == 0 for o in self.session.retired))
        events = [json.loads(raw)['event']['kind'] for raw in self.k.journals[self.authority.ledger.fd].splitlines()]
        self.assertLess(events.index('final-evidence'), max(i for i, name in enumerate(events) if name == 'removed'))

    def test_partial_teardown_stops_and_does_not_remove_remaining_root(self):
        self.session.create('')
        self.session.create('home')
        self.session._lifecycle = ClosedLifecycleForFilesystemUnitTests(self.k)
        removed = [False]
        def fail_sync(operation):
            if operation == 'remove': removed[0] = True
            if operation == 'sync' and removed[0]: raise OSError('post-unlink sync failed')
        self.k.hook = fail_sync
        with self.assertRaises(OSError): self.session.teardown(self.session._lifecycle)
        self.assertTrue(self.session.preserved)
        self.assertEqual(sum(c[0] == 'remove' for c in self.k.calls), 1)
        self.assertIn(self.session.root_name, self.k.entries(self.k.parent))

    def test_post_sync_registry_parent_replacement_and_unexpected_link_delta_revoke(self):
        self.session.create('')
        root = self.session.objects[''].fd
        fired = [False]
        def drift(operation):
            if operation == 'create' and not fired[0]:
                fired[0] = True
                self.k.nodes[root]['nlink'] += 2
        self.k.hook = drift
        with self.assertRaises(self.api.CustodyError): self.session.create('home')
        self.assertTrue(self.session.preserved)

    def test_non_cloexec_bootstrap_descriptor_refused_before_allocation(self):
        k = FakeKernel()
        k.nodes[k.parent]['fdflags'] = 0
        with self.assertRaises(self.api.CustodyError):
            self.api.TrustedBootstrap(k, k.parent, k.anchor, 'e' * 32)
        self.assertFalse(any(c[0] == 'create' for c in k.calls))

    def test_freeze_rejects_unverified_atime_even_when_mtime_is_zero(self):
        self.build_source_parents()
        obj = self.session.create(self.api.SOURCE)
        self.session.write(obj, b'data')
        original = self.k.timestamps
        def partial(fd):
            previous = self.k.nodes[fd]['atime']
            original(fd)
            self.k.nodes[fd]['atime'] = previous
        self.k.timestamps = partial
        with self.assertRaises(self.api.CustodyError): self.session.freeze_metadata(obj)
        self.assertTrue(self.session.preserved)

    def test_linux_observation_is_parent_relative_nofollow_and_nonblocking(self):
        adapter = self.api.LinuxKernel()
        info = types.SimpleNamespace(st_dev=7, st_ino=91, st_mode=stat.S_IFREG | 0o600)
        adapter.snapshot = Mock(return_value=dict(dev=7, ino=91, mode=info.st_mode))
        with patch.object(self.api.os, 'stat', return_value=info) as observed, \
                patch.object(self.api.os, 'open', return_value=83) as opened, \
                patch.object(self.api.os, 'close') as closed:
            adapter.observe(51, 'registry')
        observed.assert_called_once_with('registry', dir_fd=51, follow_symlinks=False)
        self.assertEqual(opened.call_args.kwargs, dict(dir_fd=51))
        flags = opened.call_args.args[1]
        for flag in (self.api.os.O_NOFOLLOW, self.api.os.O_CLOEXEC, self.api.os.O_NOATIME, self.api.os.O_NONBLOCK):
            self.assertTrue(flags & flag)
        closed.assert_called_once_with(83)

    def test_linux_exclusive_creation_and_narrow_removal_syscalls(self):
        adapter = self.api.LinuxKernel()
        with patch.object(self.api.os, 'mkdir') as mkdir, \
                patch.object(self.api.os, 'open', return_value=83) as opened:
            self.assertEqual(adapter.create(51, 'runner', True, 0o700), 83)
            mkdir.assert_called_once_with('runner', mode=0o700, dir_fd=51)
            self.assertTrue(opened.call_args.args[1] & self.api.os.O_DIRECTORY)
            adapter.create(83, 'journal', False, 0o600)
            flags = opened.call_args.args[1]
            for flag in (self.api.os.O_EXCL, self.api.os.O_CREAT, self.api.os.O_APPEND, self.api.os.O_RDWR):
                self.assertTrue(flags & flag)
        with patch.object(self.api.os, 'unlink') as unlink, patch.object(self.api.os, 'rmdir') as rmdir:
            adapter.remove(83, 'journal', False)
            adapter.remove(51, 'runner', True)
        unlink.assert_called_once_with('journal', dir_fd=83)
        rmdir.assert_called_once_with('runner', dir_fd=51)

    def test_publication_partial_boundaries_preserve_both_original_fds(self):
        for phase in ('rename', 'parent-sync', 'result-write'):
            with self.subTest(phase=phase):
                k = FakeKernel()
                s = self.api.TrustedBootstrap(k, k.parent, k.anchor, 'f' * 32).session()
                for path in ('', 'source', 'source/home', 'source/home/dot_config', 'source/home/dot_config/ghostty'):
                    s.create(path)
                target = self.api.SOURCE
                old = s.create(target)
                s.write(old, b'old')
                s.freeze_metadata(old)
                stage = s.create(self.api.PUBLISH[target])
                s.write(stage, b'new')
                s.freeze_metadata(stage)
                if phase == 'rename':
                    k.fail_at = 'replace'
                elif phase == 'parent-sync':
                    renamed = [False]
                    def fault(operation):
                        if operation == 'replace': renamed[0] = True
                        if renamed[0] and operation == 'sync': raise OSError('sync after rename')
                    k.hook = fault
                else:
                    original = k.write
                    def fault(fd, raw):
                        if fd == s.ledger.fd and b'"kind":"published"' in raw:
                            return original(fd, raw[:7])
                        return original(fd, raw)
                    k.write = fault
                with self.assertRaises(Exception): s.publish(stage.path, target)
                self.assertTrue(s.preserved)
                self.assertIn(old.fd, s._birth_fds)
                self.assertIn(stage.fd, s._birth_fds)
                self.assertFalse(any(c[0] == 'remove' for c in k.calls))

    def test_generated_fragment_unlink_is_scoped_and_retains_removed_fd(self):
        for role in ('', 'config', 'config/panda', 'config/panda/generated'):
            self.session.create(role)
        path = 'config/panda/generated/ghostty.conf'
        obj = self.session.create(path)
        self.session.write(obj, b'fragment')
        self.session.freeze_metadata(obj)
        self.session.unlink_transient(obj)
        self.assertIn(obj, self.session.retired)
        self.assertEqual(obj.pin['nlink'], 0)
        self.assertNotIn(path, self.session.objects)
        self.session.check()
        before = len(self.k.calls)
        with self.assertRaises(self.api.CustodyError):
            self.session.unlink_transient(self.session.objects['config'])
        self.assertEqual(len(self.k.calls), before)

    def test_final_evidence_failure_preserves_last_runner_root(self):
        self.session.create('')
        self.session.create('home')
        self.session._lifecycle = ClosedLifecycleForFilesystemUnitTests(self.k)
        original = self.k.write
        def fault(fd, raw):
            if fd == self.authority.ledger.fd and b'"kind":"final-evidence"' in raw:
                raise OSError('final evidence unavailable')
            return original(fd, raw)
        self.k.write = fault
        with self.assertRaises(OSError): self.session.teardown(self.session._lifecycle)
        self.assertTrue(self.session.preserved)
        self.assertIn(self.session.root_name, self.k.entries(self.k.parent))
        self.assertEqual(sum(c[0] == 'remove' for c in self.k.calls), 1)

    def test_worker_start_refuses_incomplete_private_environment_before_process_boundary(self):
        self.session.create('')
        self.session.create('home')
        self.k.process_transport = Mock(side_effect=AssertionError('process started'))
        with self.assertRaises(self.api.CustodyError):
            self.session.start_worker(99, '0' * 64, ['/approved/worker'])
        self.k.process_transport.assert_not_called()
        self.assertTrue(self.session.preserved)

    def test_uncertain_process_completion_refuses_any_filesystem_removal(self):
        self.session.create('')
        lifecycle = ClosedLifecycleForFilesystemUnitTests(self.k)
        lifecycle.finish = Mock(side_effect=OSError('namespace completion unknown'))
        self.session._lifecycle = lifecycle
        with self.assertRaises(OSError): self.session.teardown(lifecycle)
        self.assertTrue(self.session.preserved)
        self.assertFalse(any(c[0] == 'remove' for c in self.k.calls))


if __name__ == '__main__':
    unittest.main(verbosity=2)
