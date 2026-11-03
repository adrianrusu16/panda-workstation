"""Explicit broker-backed file-only driver; no filesystem or cleanup authority.

The endpoint must already be bound by the native relay to a prospectively created
worker/session/epoch. A JSON root, inherited FD number or successful callback
does not establish that binding. This module never opens a fixture or transfers
a custody descriptor. The native legacy engine entry stays unchanged by default.
"""
import argparse
import base64
from contextlib import contextmanager
import importlib.util
import json
from pathlib import Path
import re
import sys


def _sibling(name):
    """Load only fixed reviewed modules in the curated read-only runtime."""
    if name not in ('host_canary', 'host_canary_rpc'):
        raise ValueError('unreviewed runtime module')
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


api = _sibling('host_canary')
ROOT_RE = re.compile(r'/tmp/panda-theme-b3b1-[0-9a-f]{32}')
MAX_PLAN = 65536
MAX_JSON = 2 * 1024 * 1024


def _json_copy(value):
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)
    api.require(len(raw.encode()) <= MAX_JSON, 'broker value exceeds bound')
    return json.loads(raw, object_pairs_hook=api._unique)


class BrokerStorage:
    """Explicit storage factory; no ambient discovery, global patch or fallback."""
    def __init__(self, endpoint):
        api.require(callable(getattr(endpoint, 'call', None)), 'bound broker endpoint required')
        self.endpoint = endpoint

    def open(self, root, pins=None):
        return BrokerView(self, root, pins)


class BrokerView:
    def __init__(self, storage, root, pins):
        api.require(isinstance(root, str) and ROOT_RE.fullmatch(root), 'canonical bound root required')
        self.storage, self.root = storage, root
        self.closed, self.failed = False, False
        self.pins = _json_copy(pins or {})
        api.require(set(self.pins) <= {'', *api.FIXED_DIRS, *api.OUTPUT_DIRS}, 'foreign directory witnesses')
        for pin in self.pins.values(): api.validate_pin(pin, 0o700)
        self.view = storage.endpoint.call('open', {'root': root, 'pins': _json_copy(pins)})
        api.require(isinstance(self.view, str) and 0 < len(self.view) <= 128, 'invalid broker view')
        try:
            context = self._ask('context')
            self._validate_context(context)
            self.ns, self.tmp_pin = context['ns'], context['tmp_pin']
        except BaseException:
            self.failed = True
            raise

    def _ask(self, operation, **arguments):
        api.require(not self.closed and not self.failed, 'broker view lost; no further grants')
        try:
            return _json_copy(self.storage.endpoint.call(operation, _json_copy({'view': self.view, **arguments})))
        except BaseException:
            self.failed = True
            raise

    def _validate_context(self, context):
        api.keys(context, {'root', 'ns', 'tmp_pin', 'pins', 'root_pin'})
        api.require(context['root'] == self.root, 'broker root binding differs')
        api.keys(context['ns'], {'mnt', 'user'})
        for key in ('mnt', 'user'):
            api.require(isinstance(context['ns'][key], str) and
                        re.fullmatch(key + r':\[[0-9]+\]', context['ns'][key]), 'invalid kernel namespace projection')
        api.require(isinstance(context['tmp_pin'], list) and len(context['tmp_pin']) == 6,
                    'invalid canonical tmp projection')
        for value in context['tmp_pin']: api.integer(value)
        api.require(context['tmp_pin'][2] in (0, 65534) and context['tmp_pin'][4] == 0o1777,
                    'unsafe canonical tmp projection')
        api.validate_pin(context['root_pin'], 0o700)
        return context

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        if not self.closed and not self.failed:
            self._ask('close')
            self.closed = True

    def check_context(self):
        context = self._validate_context(self._ask('context'))
        api.require(context['ns'] == self.ns and context['tmp_pin'] == self.tmp_pin, 'broker context changed')

    def directory_pin(self, path):
        api.require(path in ('', *api.FIXED_DIRS, *api.OUTPUT_DIRS), 'directory role not allowlisted')
        pin = self._ask('directory_pin', path=path)
        api.validate_pin(pin, 0o700)
        if path in self.pins:
            api.require(pin == self.pins[path], 'directory replacement')
        return pin

    def directory_witnesses(self, paths):
        return {path: self.directory_pin(path) for path in ('', *paths)}

    def absent(self, path):
        api.require(path in (*api.FIXED_DIRS, *api.OUTPUT_DIRS, *api.FILES), 'absence role not allowlisted')
        value = self._ask('absent', path=path)
        api.require(type(value) is bool, 'invalid absence result')
        return value

    def read(self, path, *, authority=False):
        api.require(path in api.FILES and type(authority) is bool, 'file read role not allowlisted')
        value = self._ask('read', path=path, authority=authority)
        if value is not None:
            mode = 0o644 if path in (api.SOURCE, api.DEPLOYED, api.STAGES[api.SOURCE], api.STAGES[api.DEPLOYED]) else 0o600
            api.validate_object(value, mode, authority=authority)
        return value

    def expect(self, path, expected):
        actual = self.read(path, authority=expected is not None and 'ctime_ns' in expected)
        if path == api.PROGRAM and actual is not None and expected is not None:
            actual['image']['atime'] = expected['image']['atime']
        api.require(actual == expected, 'unexpected object: ' + path)

    def capture(self, path, expected):
        actual = self.read(path, authority=True)
        api.require(actual is not None and {key: actual[key] for key in ('image', 'pin')} == expected,
                    'created object changed before authority capture: ' + path)
        return actual

    def entries(self, path, expected):
        self.directory_pin(path)
        self._ask('entries', path=path, expected=sorted(expected))

    def create(self, path, image):
        api.require(path in api.FILES, 'create role not allowlisted')
        api.decode(image)
        self.expect(path, None)
        api._checkpoint('before-create:' + path)
        value = self._ask('create', path=path, image=image)
        api.validate_object(value, image['mode'])
        api.require(value['image'] == image, 'created image differs')
        self.expect(path, value)
        api._checkpoint('created:' + path)
        return value

    def publish(self, path, staged, expected):
        api.require(path in api.STAGES, 'publication role not allowlisted')
        self.expect(path, expected)
        self.expect(api.STAGES[path], staged)
        api._checkpoint('before-publish:' + path)
        value = self._ask('publish', path=path, staged=staged, expected=expected)
        api.require(value == staged, 'publication result differs')
        self.expect(path, staged)
        self.expect(api.STAGES[path], None)
        api._checkpoint('published:' + path)

    def record(self, path, value, expected):
        staged = self.create(api.STAGES[path], api.image(api.pack(value)))
        self.publish(path, staged, expected)
        self.expect(path, staged)
        return staged

    def sync(self, removed=()):
        self._ask('sync', removed=list(removed))

    def sync_directory(self, path, *, parent=False):
        self.directory_pin(path)
        self._ask('sync_directory', path=path, parent=parent)

    def unlink(self, path, expected):
        api.require(path in (api.TARGET, *api.STAGES.values()), 'unlink role not allowlisted')
        self.expect(path, expected)
        api._checkpoint('before-unlink:' + path)
        self._ask('unlink', path=path, expected=expected)
        self.expect(path, None)
        api._checkpoint('unlinked:' + path)

    @contextmanager
    def lease(self, expected):
        token = self._ask('lock', expected=expected)
        api.require(isinstance(token, str) and 0 < len(token) <= 128, 'invalid broker lease')
        try:
            yield
        finally:
            self._ask('unlock', lease=token)

    @contextmanager
    def program(self):
        value = self._ask('program_begin')
        api.keys(value, {'data', 'grant'})
        api.require(isinstance(value['data'], str) and len(value['data']) <= 4 * api.LIMIT // 3 + 4
                    and isinstance(value['grant'], str) and 0 < len(value['grant']) <= 128,
                    'invalid approved source grant')
        raw = base64.b64decode(value['data'], validate=True)
        api.require(0 < len(raw) <= api.LIMIT and base64.b64encode(raw).decode() == value['data'],
                    'invalid approved source image')
        compile(raw, 'canary.py', 'exec')
        def bound():
            self._ask('program_check', grant=value['grant'])
        bound()
        yield raw, bound
        bound()
        self._ask('program_end', grant=value['grant'])

    def _operator_mkdir(self, path):
        api.require(path in (*api.FIXED_DIRS, *api.OUTPUT_DIRS), 'operator directory role not allowlisted')
        pin = self._ask('operator_mkdir', path=path)
        api.validate_pin(pin, 0o700)
        api.require(pin == self.directory_pin(path), 'created directory binding differs')
        return pin

    def _operator_remove_output(self, path, expected):
        api.require(path in api.OUTPUT_DIRS, 'output removal role not allowlisted')
        self._ask('operator_remove_output', path=path, expected=expected)


class MediatedOperator:
    """Normal operator algorithms over broker views; never allocates/tears down roots."""
    def __init__(self, storage, root):
        api.require(isinstance(storage, BrokerStorage), 'explicit broker storage required')
        self.storage, self.root = storage, root
        self.fs = storage.open(root)
        self.creation = {'': self.fs.directory_pin('')}
        self.provider, self.failed = None, False

    def initialize(self, baseline=None):
        api.require(not self.failed and self.provider is None, 'operator initialization consumed')
        try:
            if baseline is None:
                value = self.fs._ask('operator_baseline')
                api.keys(value, {'data'})
                baseline = base64.b64decode(value['data'], validate=True)
            api.require(type(baseline) is bytes and len(baseline) == 1376 and api.digest(baseline) == api.BASE_HASH,
                        'unreviewed baseline')
            for path in api.FIXED_DIRS:
                self.creation[path] = self.fs._operator_mkdir(path)
            for index, path in enumerate((api.SOURCE, api.DEPLOYED)):
                self.fs.create(path, api.image(baseline, 0o644, 1700000000000000000 + index,
                                               1700000001000000000 + index))
            self.provider = api.Provider(self.root, self.witnesses(), storage=self.storage)
            return {'status': 'initialized'}
        except BaseException:
            self.failed = True
            raise

    def witnesses(self):
        roles = ('', *api.FIXED_DIRS)
        api.require(all(path in self.creation for path in roles), 'missing creation witnesses')
        for path in roles:
            api.require(self.fs.directory_pin(path) == self.creation[path], 'original creation witness differs')
        return {path: dict(self.creation[path]) for path in roles}

    def provision(self, stop=None):
        api.require(not self.failed and self.provider is not None, 'operator not initialized')
        _stop('provision', stop)
        try:
            self.provider.start()
            if stop == 'support': return {'status': 'provisioning-stopped', 'stop': stop}
            for path in api.OUTPUT_DIRS:
                self.provider.directory_intent(path)
                if stop == path + ':intent': return {'status': 'provisioning-stopped', 'stop': stop}
                self.creation[path] = self.fs._operator_mkdir(path)
                if stop == path + ':created': return {'status': 'provisioning-stopped', 'stop': stop}
                self.provider.attest_directory(path, self.fs.directory_pin(path))
                if stop == path + ':attested': return {'status': 'provisioning-stopped', 'stop': stop}
            self.provider.seal()
            return {'status': 'enrolled'}
        except BaseException:
            self.failed = True
            raise

    def cleanup_outputs(self, stop=None):
        api.require(not self.failed, 'operator preserved after failure')
        _stop('cleanup_outputs', stop)
        receipt = api.CleanupProvider(self.root, storage=self.storage)
        receipt.start()
        for path in reversed(api.OUTPUT_DIRS):
            receipt.directory_intent(path)
            if stop == path + ':intent': return {'status': 'cleanup-stopped', 'stop': stop}
            expected = receipt.enrollment['dirs'][path]
            api.require(self.fs.directory_pin(path) == expected, 'output directory replaced')
            self.fs.entries(path, ())
            self.fs._operator_remove_output(path, expected)
            if stop == path + ':removed': return {'status': 'cleanup-stopped', 'stop': stop}
            receipt.attest_absence(path)
            if stop == path + ':attested': return {'status': 'cleanup-stopped', 'stop': stop}
        return {'status': 'output-directories-removed'}

    def close(self):
        if self.provider is not None:
            self.provider.close()
        self.fs.close()


def _stop(action, value):
    values = {None}
    if action == 'provision': values.add('support')
    for path in api.OUTPUT_DIRS:
        values.update(path + ':' + phase for phase in
                      (('intent', 'created', 'attested') if action == 'provision' else ('intent', 'removed', 'attested')))
    api.require(value in values, 'unsupported operator stop')


def execute_plan(endpoint, root, plan):
    """Execute only a bounded fixed normal-flow plan; no code, paths or teardown."""
    api.require(isinstance(plan, list) and 0 < len(plan) <= 32, 'bounded command plan required')
    api.require(len(json.dumps(plan, allow_nan=False).encode()) <= MAX_PLAN, 'plan exceeds bound')
    initialized = False
    for index, command in enumerate(plan):
        api.require(isinstance(command, dict), 'invalid plan command')
        action = command.get('action')
        api.require(action in ('initialize', 'provision', 'install', 'status', 'preview', 'recover', 'cleanup_outputs'),
                    'unsupported plan command')
        api.require(set(command) <= ({'action', 'stop'} if action in ('provision', 'cleanup_outputs') else {'action'}),
                    'unexpected plan fields')
        if action in ('provision', 'cleanup_outputs'): _stop(action, command.get('stop'))
        if action == 'initialize':
            api.require(index == 0 and not initialized, 'initialization must be first and single-use')
            initialized = True
        if action == 'provision': api.require(initialized, 'provision requires this plan initialization')
    storage, operator, results = BrokerStorage(endpoint), None, []
    try:
        for command in plan:
            action = command['action']
            if action in ('initialize', 'provision', 'cleanup_outputs'):
                if operator is None: operator = MediatedOperator(storage, root)
                answer = (operator.initialize() if action == 'initialize' else
                          getattr(operator, action)(command.get('stop')))
            else:
                answer = getattr(api, 'install_minimal' if action == 'install' else action)(root, storage=storage)
            results.append({'action': action, 'result': answer})
            if answer.get('status') in ('incomplete', 'manual-inspection-required', 'provisioning-stopped', 'cleanup-stopped'):
                break
        return results
    finally:
        if operator is not None: operator.close()


def worker_main(argv=None):
    parser = argparse.ArgumentParser(description='Bound Host Canary normal-flow worker; real execution remains gated')
    parser.add_argument('--rpc-fd', type=int, required=True)
    parser.add_argument('--session', required=True)
    parser.add_argument('--epoch', type=int, required=True)
    parser.add_argument('--plan', required=True)
    arguments = parser.parse_args(argv)
    api.require(3 <= arguments.rpc_fd <= 1048576 and arguments.epoch > 0 and
                re.fullmatch('[0-9a-f]{32}', arguments.session) and len(arguments.plan.encode()) <= MAX_PLAN,
                'invalid worker binding/plan')
    plan = json.loads(arguments.plan, object_pairs_hook=api._unique)
    # Only Client's authenticated native relay can turn this inherited FD into
    # an endpoint; argument/environment values alone establish no authority.
    endpoint = _sibling('host_canary_rpc').Client(arguments.rpc_fd, arguments.session, arguments.epoch)
    results = execute_plan(endpoint, '/tmp/panda-theme-b3b1-' + arguments.session, plan)
    print(json.dumps(results, sort_keys=True))
    return 1 if any(row['result'].get('status') in ('incomplete', 'manual-inspection-required',
                    'provisioning-stopped', 'cleanup-stopped') for row in results) else 0


if __name__ == '__main__':
    sys.exit(worker_main())
