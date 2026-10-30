"""Recovery-only probes: no fixture allocation or filesystem access in tests."""
import ast
from contextlib import ExitStack
import errno
import hashlib
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

repo = Path(__file__).resolve().parents[1]
names = ('theme/panda/common/host_canary.py', 'tests/host_canary_operator.py',
         'tests/test_theme_host_canary.py')
sources = {name: (repo / name).read_bytes() for name in names}
trees = {name: ast.parse(raw, filename=name) for name, raw in sources.items()}
api = types.ModuleType('recovered_host_canary')
api.__file__ = str(repo / names[0])
exec(compile(trees[names[0]], names[0], 'exec'), api.__dict__)
operator = types.ModuleType('recovered_operator')
exec(compile(trees[names[1]], names[1], 'exec'), operator.__dict__)
baseline = (repo / 'home/dot_config/ghostty/config.ghostty').read_bytes()

def blocked(*args, **kwargs):
    raise AssertionError('offline probe attempted filesystem access')

class OfflineChecks(unittest.TestCase):
    def setUp(self):
        guards = ExitStack()
        self.addCleanup(guards.close)
        guards.enter_context(patch("builtins.open", blocked))
        for name in ("open", "mkdir", "makedirs", "rmdir", "unlink", "remove",
                     "rename", "replace", "fsync", "stat", "lstat", "fstat",
                     "listdir", "scandir", "readlink", "listxattr", "utime", "chmod"):
            guards.enter_context(patch.object(os, name, blocked))
        guards.enter_context(patch.object(operator.tempfile, "mkdtemp", blocked))

    def test_sources_parse_and_engine_imports_are_stdlib(self):
        self.assertEqual(len(trees), 3)
        for node in ast.walk(trees[names[0]]):
            if isinstance(node, ast.Import):
                self.assertTrue(all(a.name.split('.')[0] in sys.stdlib_module_names for a in node.names))
            elif isinstance(node, ast.ImportFrom):
                self.assertIn(node.module.split('.')[0], sys.stdlib_module_names)
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                self.assertNotIn(node.func.attr, ('mkdir', 'makedirs', 'rmdir', 'rmtree',
                                                'system', 'Popen', 'spawn', 'execv'))

    def test_fixed_manifest_and_image_contract(self):
        self.assertEqual(len(api.ROLES), 24)
        self.assertEqual(len(set(api.ROLES)), 24)
        self.assertEqual(len(api.MINIMAL), 516)
        self.assertEqual(hashlib.sha256(api.MINIMAL).hexdigest(), api.MINIMAL_HASH)
        self.assertEqual(len(baseline), 1376)
        self.assertEqual(hashlib.sha256(baseline).hexdigest(), api.BASE_HASH)
        self.assertEqual(len(baseline + api.HOOK), 1423)
        self.assertEqual(hashlib.sha256(baseline + api.HOOK).hexdigest(), api.HOOK_HASH)

    def test_canonical_record_refusals(self):
        value = {'schema': 2, 'scope': api.SCOPE}
        raw = api.pack(value)
        self.assertEqual(api.unpack(raw), value)
        for invalid in (raw + b' ', raw.replace(b'"schema":2', b'"schema":1'),
                        b'{"payload":{},"payload":{},"sha256":"x"}\n',
                        api.canonical({'payload': value, 'sha256': 'x', 'extra': 1}),
                        b'x' * (api.LIMIT + 1), b'[' * 10000):
            with self.subTest(length=len(invalid)), self.assertRaises(ValueError):
                api.unpack(invalid)

    def test_image_and_id_refusals(self):
        image = api.image(b'fixture-only')
        self.assertEqual(api.decode(image), b'fixture-only')
        for change in ({'mode': 0o777}, {'sha256': 'x'}, {'data': '%%%'},
                       {'uid': os.getuid() + 1}, {'atime': True}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                api.decode({**image, **change})
        api.validate_id('0' * 32)
        for invalid in ('A' * 32, '0' * 31, None, 42):
            with self.assertRaises(ValueError):
                api.validate_id(invalid)

    def test_invalid_roots_refuse_before_any_filesystem_access(self):
        roots = ('/home/panda-fixture-user', str(repo), '/tmp/random',
                 '/tmp/panda-theme-b3b-other', '/tmp/panda-theme-b3b1-',
                 '/tmp/panda-theme-b3b1-test/../test', '/tmp/panda-theme-b3b1-a\x00',
                 '', b'/tmp/panda-theme-b3b1-bytes', None)
        for root in roots:
            for operation in (api.status, api.preview, api.install_minimal, api.recover):
                with self.subTest(root=root, operation=operation.__name__):
                    self.assertEqual(operation(root)['status'], 'manual-inspection-required')

    def test_missing_supervisor_refuses_before_runner_or_fixture_access(self):
        self.assertIsNone(operator.fixture_cleanup)
        with patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(ValueError, 'prospective'):
            operator.Operator(api, baseline, blocked)

    def test_missing_or_malformed_runner_capability_refuses_before_access(self):
        for capability in (None, 'not-json', '[]', '{}', '{"root":"/tmp/random"}'):
            env = {} if capability is None else {'PANDA_TEST_RUNNER': capability,
                                                  'XDG_RUNTIME_DIR': '/run/user/fixture'}
            with self.subTest(capability=capability), patch.dict(os.environ, env, clear=True):
                with self.assertRaises(ValueError), operator.runner_registry():
                    self.fail('runner capability accepted')

    def test_error_status_classification(self):
        for code in (errno.EIO, errno.ENOSPC, errno.EDQUOT, errno.EAGAIN, errno.EBUSY):
            self.assertEqual(api.failure(OSError(code, 'injected'))['status'], 'incomplete')
        self.assertEqual(api.failure(ValueError('unsupported'))['status'], 'manual-inspection-required')


if __name__ == "__main__":
    unittest.main(verbosity=2)
