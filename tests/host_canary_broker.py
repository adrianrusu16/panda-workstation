"""Fixed-role engine storage in the external custodian; no worker descriptors.

All objects come from one prospective session. JSON images/pins are comparison
inputs, never creation-custody, source-provenance or teardown authority.
"""
import base64
import hashlib
import importlib.util
from pathlib import Path
import stat
import sys
from types import SimpleNamespace

_spec = importlib.util.spec_from_file_location('_panda_broker_runtime', Path(__file__).with_name('host_canary_runtime.py'))
runtime = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = runtime
_spec.loader.exec_module(runtime)


class ApprovedProgramGrant:
    """Reviewed fixed source held outside the fixture, not a worker blob/path."""
    def __init__(self, kernel, fd, reviewed_digest):
        self.k, self.fd = kernel, fd
        self.pin = kernel.approved_source_binding(fd)
        uid, gid = kernel.identity()
        p = self.pin
        if (p['uid'] != uid or p['gid'] != gid or p['mode'] not in (stat.S_IFREG | 0o600, stat.S_IFREG | 0o644)
                or p['nlink'] != 1 or p['xattrs'] or p['fdflags'] != 1 or not p['flags'] & runtime.os.O_NOATIME
                or not 0 < p['size'] <= 1024 * 1024):
            raise runtime.CustodyError('reviewed program descriptor metadata differs')
        self.data = kernel.read(fd, p['size'] + 1, 0)
        if len(self.data) != p['size'] or hashlib.sha256(self.data).hexdigest() != reviewed_digest:
            raise runtime.CustodyError('reviewed program bytes/digest differ')
        compile(self.data, '<reviewed-host-canary>', 'exec')
        self.check()

    def check(self):
        if self.k.approved_source_binding(self.fd) != self.pin or self.k.read(self.fd, len(self.data) + 1, 0) != self.data:
            raise runtime.CustodyError('original reviewed program changed')


class BrokerStore:
    OPS = frozenset(('open', 'close', 'context', 'directory_pin', 'bind', 'absent', 'entries',
                     'read', 'create', 'publish', 'sync', 'sync_directory', 'unlink', 'lock', 'unlock',
                     'program_begin', 'program_check', 'program_end', 'operator_mkdir', 'operator_remove_output', 'operator_baseline'))
    FIELDS = {
        'open': ({'root'}, {'pins'}), 'close': (set(), set()), 'context': (set(), set()),
        'directory_pin': ({'path'}, set()), 'bind': ({'path', 'pin'}, set()),
        'absent': ({'path'}, set()), 'entries': ({'path', 'expected'}, set()),
        'read': ({'path'}, {'authority'}), 'create': ({'path', 'image'}, set()),
        'publish': ({'path', 'staged', 'expected'}, set()), 'sync': (set(), {'removed'}),
        'sync_directory': ({'path'}, {'parent'}), 'unlink': ({'path', 'expected'}, set()),
        'lock': ({'expected'}, set()), 'unlock': ({'lease'}, set()),
        'program_begin': (set(), set()), 'program_check': ({'grant'}, set()),
        'program_end': ({'grant'}, set()),
        'operator_mkdir': ({'path'}, set()), 'operator_remove_output': ({'path', 'expected'}, set()),
        'operator_baseline': (set(), set())}

    def __init__(self, session, engine_api, approved_program_grant, approved_baseline=None):
        if type(approved_program_grant) is not ApprovedProgramGrant or approved_program_grant.k is not session.k:
            raise runtime.CustodyError('typed external approved-source grant required')
        if not hasattr(session.bootstrap, 'canonical_grant'):
            raise runtime.CustodyError('schema2 broker requires explicit canonical allocation parent')
        self.s, self.k, self.e, self.program = session, session.k, engine_api, approved_program_grant
        self.root = '/tmp/' + session.root_name
        self.views, self.programs, self.lease = {}, {}, None
        self.record_stages = {}
        self.readonly, self._plan_bound = False, False
        self._phase_owner = None
        self.counter, self.removed_outputs = 0, []
        self.baseline = approved_baseline
        if approved_baseline is not None and (type(approved_baseline) is not bytes or len(approved_baseline) != 1376
                                              or self.e.digest(approved_baseline) != self.e.BASE_HASH):
            raise runtime.CustodyError('unapproved controller baseline')
        self.s.check()
        self.program.check()


    def restrict_plan(self, plan):
        """Bind one controller-reviewed plan; worker RPC cannot widen authority."""
        if self._plan_bound or type(plan) is not list or not 1 <= len(plan) <= 32:
            raise runtime.CustodyError('one bounded controller plan required')
        if len(runtime.canonical(plan)) > 65536:
            raise runtime.CustodyError('controller plan exceeds bound')
        initialized = False
        actions = ('initialize', 'provision', 'install', 'status', 'preview', 'recover', 'cleanup_outputs')
        for index, command in enumerate(plan):
            if type(command) is not dict or command.get('action') not in actions:
                raise runtime.CustodyError('unsupported controller plan command')
            action = command['action']
            fields = {'action', 'stop'} if action in ('provision', 'cleanup_outputs') else {'action'}
            if not set(command) <= fields:
                raise runtime.CustodyError('unexpected controller plan fields')
            if action in ('provision', 'cleanup_outputs'):
                phases = ('intent', 'created', 'attested') if action == 'provision' else ('intent', 'removed', 'attested')
                stops = {None, *(path + ':' + phase for path in self.e.OUTPUT_DIRS for phase in phases)}
                if action == 'provision': stops.add('support')
                if command.get('stop') not in stops:
                    raise runtime.CustodyError('unsupported controller stop')
            if action == 'initialize':
                if index != 0 or initialized: raise runtime.CustodyError('initialization must be first and single-use')
                initialized = True
            if action == 'provision' and not initialized:
                raise runtime.CustodyError('provision requires this plan initialization')
        self.readonly = all(command['action'] in ('status', 'preview') for command in plan)
        self._plan_bound = True

    def bind_phases(self, controller):
        if (self._plan_bound or self._phase_owner is not None
                or self.s._phase_controller is not controller
                or type(controller) is not self.s.phases_module().PhaseController):
            raise runtime.CustodyError('original typed phase controller required')
        self.quiescent()
        self._phase_owner, self._plan_bound = controller, True

    def quiescent(self):
        if self.views or self.programs or self.lease is not None or self.record_stages:
            raise runtime.CustodyError('incomplete view/source/lease/record-stage custody')
        self.root_receipt()

    def phase_checkpoint(self, phase):
        """Controller observation of original held objects, never journal adoption."""
        self.quiescent()
        enrollment, baseline, journal, journal_obj = self.e.observe(self._evidence_view())
        if phase == 'A':
            valid = journal is None and journal_obj is None and not self.removed_outputs
            state = 'enrolled'
        else:
            states = {'B': 'installed', 'C': 'restored', 'D': 'closed'}
            state = states.get(phase)
            valid = (state is not None and journal is not None and journal['phase'] == state
                     and journal['intent'] is None and len(journal['forward']) == 6
                     and len(journal['reverse']) == (0 if phase == 'B' else 5))
            if phase in ('B', 'C'):
                valid = valid and self.read(self.e.CLEANUP) is None and not self.removed_outputs
            elif phase == 'D':
                expected = list(reversed(self.e.OUTPUT_DIRS))
                valid = valid and self.removed_outputs == expected
                for path in expected:
                    held = [o for o in self.s.retired if o.path == path and o.directory]
                    valid = valid and len(held) == 1 and self.pin(held[0]) == enrollment['dirs'][path]
        if not valid:
            raise runtime.CustodyError('phase checkpoint does not match exact complete transaction')
        graph = [(p, o.birth, o.pin) for p, o in sorted(self.s.objects.items())]
        retired = [(o.path, o.birth, o.pin) for o in self.s.retired]
        self.quiescent()
        return dict(state=state, enrollment_id=enrollment['enrollment_id'],
                    baseline=self.e.digest(self.e.decode(baseline['image'])),
                    journal=None if journal_obj is None else self.e.digest(self.e.decode(journal_obj['image'])),
                    graph_sha256=hashlib.sha256(runtime.canonical([graph, retired])).hexdigest(),
                    removed=list(self.removed_outputs))

    def preserve(self, reason):
        self.s.preserved = True
        self.reason = str(reason)

    def root_receipt(self):
        self.s.check()
        try:
            self.program.check()
        except BaseException:
            self.preserve('approved source changed')
            raise
        obj = self.s.objects['']
        return dict(fd=obj.fd, birth=dict(obj.birth), pin=dict(obj.pin), session_id=self.s.bootstrap.session_id)

    def token(self, kind):
        self.counter += 1
        return kind + '-' + self.s.bootstrap.session_id + '-' + str(self.counter)

    def pin(self, obj):
        return {key: stat.S_IMODE(obj.pin[key]) if key == 'mode' else obj.pin[key]
                for key in ('dev', 'ino', 'uid', 'gid', 'mode', 'mount')}

    def obj(self, path, directory=False):
        if not isinstance(path, str) or path not in (self.e.FILES if not directory else ('', *self.e.FIXED_DIRS, *self.e.OUTPUT_DIRS)):
            raise runtime.CustodyError('engine role not allowlisted')
        obj = self.s.objects.get(path)
        if obj is None or obj.directory != directory:
            raise runtime.CustodyError('role has no continuously held registration')
        self.s._verify(obj)
        return obj

    def read(self, path, authority=False):
        if type(authority) is not bool or path not in self.e.FILES:
            raise runtime.CustodyError('invalid bounded image read')
        self.s.check()
        obj = self.s.objects.get(path)
        if obj is None:
            return None  # complete graph check already rejects foreign entries/lost known roles
        if obj.directory or obj.pin['size'] > self.e.LIMIT:
            raise runtime.CustodyError('invalid image size/type')
        before = dict(obj.pin)
        raw = self.k.read(obj.fd, self.e.LIMIT + 1, 0)
        self.s._verify(obj)
        if len(raw) != before['size'] or len(raw) > self.e.LIMIT:
            self.preserve('short/oversized stable read')
            raise runtime.CustodyError('incomplete bounded image')
        result = dict(image=dict(data=base64.b64encode(raw).decode(), sha256=self.e.digest(raw),
                                 mode=stat.S_IMODE(before['mode']), uid=before['uid'], gid=before['gid'],
                                 atime=before['atime'], mtime=before['mtime']), pin=self.pin(obj))
        if authority:
            result['ctime_ns'] = before['ctime']
        self.s.check()
        return result

    def expect(self, path, expected):
        if self.read(path, expected is not None and 'ctime_ns' in expected) != expected:
            raise runtime.CustodyError('engine expected image/pin differs: ' + path)

    def _record(self, path):
        value = self.read(path)
        if value is None:
            raise runtime.CustodyError('required current engine record absent')
        return self.e.unpack(self.e.decode(value['image'])), value

    def _scope(self, value):
        if (type(value.get('schema')) is not int or value['schema'] != 2 or value.get('scope') != self.e.SCOPE):
            raise runtime.CustodyError('wrong schema2 engine scope')
        self.e.validate_id(value.get('enrollment_id'))

    def _evidence_view(self):
        """Read-only engine validator projection of continuously held roles."""
        parent = self.s.parent_pin
        ns = self.s.objects[''].pin['namespace']
        def entries(path, expected):
            if self.k.entries(self.obj(path, True).fd) != sorted(expected):
                raise runtime.CustodyError('unexpected evidence directory entries')
            self.s.check()
        return SimpleNamespace(
            root=self.root,
            ns={name: name + ':[' + str(value[-1] if isinstance(value, (list, tuple)) else value) + ']'
                for name, value in zip(('mnt', 'user'), ns)},
            tmp_pin=[parent[k] for k in ('dev', 'ino', 'uid', 'gid')] +
                    [stat.S_IMODE(parent['mode']), parent['mount']],
            read=self.read, expect=self.expect, directory_pin=lambda path: self.pin(self.obj(path, True)),
            check_context=self.s.check, absent=lambda path: path not in self.s.objects, entries=entries)

    def _output_intent(self, path, removing=False):
        if path not in self.e.OUTPUT_DIRS:
            raise runtime.CustodyError('not an output directory')
        if not removing:
            value, _ = self._record(self.e.PROVISION)
            self._scope(value)
            done = value.get('done')
            if (value.get('root') != self.root or value.get('state') != 'provisioning'
                    or value.get('pending') != path or not isinstance(done, list)
                    or done not in ([], [self.e.OUTPUT_DIRS[0]]) or path != self.e.OUTPUT_DIRS[len(done)]):
                raise runtime.CustodyError('no exact durable output provisioning intent')
            return
        cleanup, _ = self._record(self.e.CLEANUP)
        evidence = self._evidence_view()
        enrollment, baseline = self.e.load(evidence)
        journal, journal_obj = self._record(self.e.JOURNAL)
        for value in (cleanup, enrollment, journal): self._scope(value)
        current, _ = self.e.model(journal, enrollment, baseline)
        self.e.verify(evidence, enrollment, baseline, journal, journal_obj)
        if (journal['phase'] != 'restored' or journal['intent'] is not None
                or enrollment.get('root') != self.root or cleanup.get('enrollment_id') != enrollment['enrollment_id']
                or cleanup.get('enrollment') != self.e.digest(self.e.decode(baseline['image']))
                or cleanup.get('checkpoint') != self.e.digest(self.e.decode(journal_obj['image']))
                or cleanup.get('done') != self.removed_outputs or cleanup.get('pending') != path
                or len(self.removed_outputs) >= 2 or path != tuple(reversed(self.e.OUTPUT_DIRS))[len(self.removed_outputs)]):
            raise runtime.CustodyError('no validated restored cleanup intent')
        for role in (self.e.SOURCE, self.e.DEPLOYED): self.expect(role, current[role])
        self.expect(self.e.TARGET, None)
        for role in self.e.STAGES.values():
            if role == self.e.STAGES[self.e.TARGET] and self.e.OUTPUT_DIRS[1] in self.removed_outputs:
                continue
            self.expect(role, None)


    def _lease(self, view):
        if self.lease is None or self.lease[1] != view:
            raise runtime.CustodyError('mutation requires this view original lock lease')
        self.expect(self.e.LOCK, self.lease[2])

    def _managed_intent(self, view, operation, target, image=None):
        self._lease(view)
        evidence = self._evidence_view()
        enrollment, baseline = self.e.load(evidence)
        journal, obj = self._record(self.e.JOURNAL)
        self.e.verify(evidence, enrollment, baseline, journal, obj)
        if self._phase_owner is not None:
            phase = self._phase_owner._grant.epoch
            if journal['phase'] != {2: 'applying', 3: 'recovering'}.get(phase):
                self._phase_owner.refuse('managed mutation outside current phase')
        if journal['intent'] != [operation, target]:
            raise runtime.CustodyError('no exact durable managed mutation intent')
        current, stages = self.e.model(journal, enrollment, baseline)
        wanted = (enrollment['before'].get(target, {}).get('image')
                  if journal['phase'] == 'recovering' else journal['proposed'][target])
        if operation == 'stage' and image != wanted:
            raise runtime.CustodyError('managed stage image differs from journal intent')
        if operation == 'publish' and stages[target] is None:
            raise runtime.CustodyError('no attested stage for publication')
        if operation == 'unlink' and (target != self.e.TARGET or current[target] is None):
            raise runtime.CustodyError('no journal-bound generated target removal')

    def _record_transition(self, view, target, value):
        self._scope(value)
        if self._phase_owner is not None and target == self.e.JOURNAL:
            phase = self._phase_owner._grant.epoch
            states = {2: ('applying', 'installed'), 3: ('recovering', 'restored'), 4: ('closed',)}
            if value.get('phase') not in states.get(phase, ()):
                self._phase_owner.refuse('journal transition outside current phase')
        old_obj = self.read(target)
        old = None if old_obj is None else self.e.unpack(self.e.decode(old_obj['image']))
        evidence = self._evidence_view()
        allowed = []
        if target == self.e.PROVISION:
            if old is None:
                dirs = {p: self.pin(self.obj(p, True)) for p in ('', *self.e.FIXED_DIRS)}
                before = {p: self.read(p) for p in (self.e.SOURCE, self.e.DEPLOYED)}
                support = {p: self.read(p, True) for p in
                           (self.e.PROGRAM, self.e.SOURCE_BEFORE, self.e.DEPLOYED_BEFORE, self.e.LOCK)}
                if any(v is None for v in (*before.values(), *support.values())):
                    raise runtime.CustodyError('provisioning requires original initialized support')
                for p, obj in before.items():
                    if obj['image']['sha256'] != self.e.BASE_HASH:
                        raise runtime.CustodyError('provisioning source is not baseline')
                allowed.append(dict(schema=2, scope=self.e.SCOPE, enrollment_id=value['enrollment_id'],
                                    root=self.root, ns=evidence.ns, tmp=evidence.tmp_pin, dirs=dirs,
                                    before=before, support=support, done=[], pending=None,
                                    state='provisioning', preseal=None))
            elif old['state'] == 'provisioning':
                if old['pending'] is None and len(old['done']) < 2:
                    path = self.e.OUTPUT_DIRS[len(old['done'])]
                    if path not in self.s.objects: allowed.append({**old, 'pending': path})
                elif old['pending'] is not None:
                    path = old['pending']
                    obj = self.obj(path, True)
                    if not self.k.entries(obj.fd):
                        allowed.append({**old, 'pending': None, 'done': [*old['done'], path],
                                        'dirs': {**old['dirs'], path: self.pin(obj)}})
                elif old['done'] == list(self.e.OUTPUT_DIRS):
                    allowed.append({**old, 'state': 'completed', 'preseal': self.read(target, True)})
        elif target == self.e.BASELINE:
            if old is None:
                provision, _ = self._record(self.e.PROVISION)
                if provision['state'] == 'completed':
                    allowed.append(dict(schema=2, scope=self.e.SCOPE, enrollment_id=provision['enrollment_id'],
                                        root=self.root, ns=evidence.ns, tmp=evidence.tmp_pin, roles=list(self.e.ROLES),
                                        dirs=provision['dirs'], before=provision['before'], support=provision['support'],
                                        preseal=provision['preseal'], completed_provisioning=self.read(self.e.PROVISION, True)))
        else:
            self._lease(view)
            enrollment, baseline = self.e.load(evidence)
            if target == self.e.CLEANUP:
                journal, journal_obj = self._record(self.e.JOURNAL)
                self.e.model(journal, enrollment, baseline)
                if journal['phase'] != 'restored' or journal['intent'] is not None:
                    raise runtime.CustodyError('cleanup record requires restored journal')
                if old is None:
                    self.e.verify(evidence, enrollment, baseline, journal, journal_obj)
                    allowed.append(dict(schema=2, scope=self.e.SCOPE, enrollment_id=enrollment['enrollment_id'],
                                        enrollment=self.e.digest(self.e.decode(baseline['image'])),
                                        checkpoint=self.e.digest(self.e.decode(journal_obj['image'])), done=[], pending=None))
                elif old['pending'] is None and len(old['done']) < 2:
                    path = list(reversed(self.e.OUTPUT_DIRS))[len(old['done'])]
                    self.e.verify(evidence, enrollment, baseline, journal, journal_obj)
                    allowed.append({**old, 'pending': path})
                elif old['pending'] is not None:
                    path = old['pending']
                    if self.removed_outputs == [*old['done'], path] and path not in self.s.objects:
                        self.e.verify(evidence, enrollment, baseline, journal, journal_obj, operator_absence=path)
                        allowed.append({**old, 'pending': None, 'done': [*old['done'], path]})
            elif target == self.e.JOURNAL:
                self.e.model(value, enrollment, baseline)
                if old is None:
                    allowed.append(self.e.new_journal(baseline, self.e.proposals(enrollment)))
                elif old['intent'] is None:
                    history = old['forward'] if old['phase'] == 'applying' else old['reverse']
                    operations = self.e.FORWARD if old['phase'] == 'applying' else self.e.REVERSE
                    if old['phase'] in ('applying', 'recovering') and len(history) < len(operations):
                        allowed.append({**old, 'intent': list(operations[len(history)])})
                    if old['phase'] == 'applying' and len(old['forward']) == 6:
                        allowed.append({**old, 'phase': 'installed'})
                    if old['phase'] in ('applying', 'installed') and all(
                            v is None for v in self.e.model(old, enrollment, baseline)[1].values()):
                        allowed.append({**old, 'phase': 'recovering'})
                    if old['phase'] == 'recovering' and len(old['reverse']) == 5:
                        allowed.append({**old, 'phase': 'restored'})
                    if old['phase'] == 'restored' and self.removed_outputs == list(reversed(self.e.OUTPUT_DIRS)):
                        cleanup, cleanup_obj = self._record(self.e.CLEANUP)
                        if cleanup['done'] == self.removed_outputs and cleanup['pending'] is None:
                            allowed.append({**old, 'phase': 'closed',
                                            'cleanup': self.e.digest(self.e.decode(cleanup_obj['image']))})
                else:
                    operation, path = old['intent']
                    current, stages = self.e.model(old, enrollment, baseline)
                    restoring = old['phase'] == 'recovering'
                    wanted = enrollment['before'].get(path, {}).get('image') if restoring else old['proposed'][path]
                    skip = restoring and (current[path] is None if wanted is None else
                                          current[path] is not None and current[path]['image'] == wanted)
                    history_name = 'reverse' if restoring else 'forward'
                    history = old[history_name]
                    if operation == 'publish': skip = history[-1]['skip']
                    stage_pin = None
                    if operation == 'stage' and not skip:
                        actual = self.read(self.e.STAGES[path])
                        if actual is None or actual['image'] != wanted:
                            raise runtime.CustodyError('journal stage result lacks original registered image')
                        stage_pin = actual['pin']
                    allowed.append({**old, 'intent': None, history_name: [*history,
                                    dict(op=operation, path=path, stage=stage_pin, skip=skip)]})
                    # Reconciliation may clear an unperformed intent only while the original graph still matches.
                    try:
                        self.e.verify(evidence, enrollment, baseline, old, old_obj)
                    except (ValueError, KeyError):
                        pass
                    else:
                        allowed.append({**old, 'intent': None})
                # Proposed checkpoint must describe the actual managed objects, never invented result pins.
                current, stages = self.e.model(value, enrollment, baseline)
                for path in self.e.MANAGED:
                    if path == self.e.TARGET and self.e.OUTPUT_DIRS[1] in self.removed_outputs:
                        if current[path] is not None or stages[path] is not None:
                            raise runtime.CustodyError('journal invents removed target')
                        continue
                    self.expect(path, current[path])
                    self.expect(self.e.STAGES[path], stages[path])
        if value not in allowed:
            raise runtime.CustodyError('record is not the exact next controller-validated transition')

    def _create(self, path, image, view):
        if path not in self.e.FILES:
            raise runtime.CustodyError('unapproved file role')
        raw = self.e.decode(image)
        if path == self.e.TARGET:
            raise runtime.CustodyError('generated target requires staged publication')
        if path in (self.e.SOURCE, self.e.DEPLOYED) and any(p in self.s.objects for p in (self.e.PROVISION, self.e.BASELINE, self.e.JOURNAL)):
            raise runtime.CustodyError('direct baseline creation is initialization-only')
        for target in self.e.MANAGED:
            if path == self.e.STAGES[target]: self._managed_intent(view, 'stage', target, image)
        index = next((i for i, target in enumerate((self.e.SOURCE, self.e.DEPLOYED))
                      if path in (target, self.e.STAGES[target])), None)
        times = (1700000000000000000 + index, 1700000001000000000 + index) if index is not None else (0, 0)
        if (image['mode'] != runtime.FILE_MODES[path] or (image['atime'], image['mtime']) != times
                or image['uid'] != self.s.bootstrap.uid or image['gid'] != self.s.bootstrap.gid):
            raise runtime.CustodyError('image mode/ownership/timestamps outside approved role')
        if index is not None and (self.e.digest(raw) not in (self.e.BASE_HASH, self.e.HOOK_HASH)
                                  or path in (self.e.SOURCE, self.e.DEPLOYED) and self.e.digest(raw) != self.e.BASE_HASH):
            raise runtime.CustodyError('unapproved baseline/proposal bytes')
        if path == self.e.LOCK and raw or path == self.e.PROGRAM and raw != self.program.data:
            raise runtime.CustodyError('lock/program bytes differ')
        if path in (self.e.SOURCE_BEFORE, self.e.DEPLOYED_BEFORE) and self.e.digest(raw) != self.e.BASE_HASH:
            raise runtime.CustodyError('backup not approved baseline')
        if path in (self.e.TARGET, self.e.STAGES[self.e.TARGET]) and raw != self.e.MINIMAL:
            raise runtime.CustodyError('unapproved generated fragment')
        target = None
        records = (self.e.PROVISION, self.e.BASELINE, self.e.JOURNAL, self.e.CLEANUP)
        if path in (*records, *(self.e.STAGES[p] for p in records if p in self.e.STAGES)):
            value = self.e.unpack(raw)
            if type(value) is not dict or self.e.pack(value) != raw:
                raise runtime.CustodyError('engine record must be bounded canonical object')
            target = next((p for p in records if path in (p, self.e.STAGES.get(p))), None)
            if path == target and target in (self.e.JOURNAL,):
                raise runtime.CustodyError('journal requires staged publication')
            self._record_transition(view, target, value)
        self.expect(path, None)
        obj = self.s.create(path)
        if raw: self.s.write(obj, raw)
        self.s.freeze_metadata(obj, times)
        result = self.read(path)
        if target is not None and path != target:
            self.record_stages[path] = (view, target, image, self.read(target, True))
        if result['image'] != image:
            self.preserve('post-create image mismatch')
            raise runtime.CustodyError('post-create image mismatch')
        return result

    def _phase_operation(self, op, args):
        """Restrict mutation roles before even parsing worker-supplied images."""
        owner = self._phase_owner
        if owner is None:
            return
        owner.require_dispatch()
        phase = owner._grant.epoch
        e, path = self.e, args.get('path')
        records = {1: (e.PROVISION, e.BASELINE), 2: (e.JOURNAL,),
                   3: (e.JOURNAL,), 4: (e.CLEANUP, e.JOURNAL)}[phase]
        create = {e.STAGES[p] for p in records if p in e.STAGES}
        if phase == 1:
            create.update((e.PROGRAM, e.LOCK, e.SOURCE, e.DEPLOYED, e.SOURCE_BEFORE,
                           e.DEPLOYED_BEFORE, e.PROVISION, e.BASELINE))
        if phase == 4:
            create.add(e.CLEANUP)
        if phase in (2, 3):
            create.update(e.STAGES[p] for p in e.MANAGED)
        allowed = True
        if op == 'create': allowed = path in create
        elif op == 'publish': allowed = path in records or phase in (2, 3) and path in e.MANAGED
        elif op == 'unlink': allowed = phase == 3 and path == e.TARGET
        elif op == 'operator_mkdir': allowed = phase == 1
        elif op == 'operator_remove_output': allowed = phase == 4
        elif op == 'operator_baseline': allowed = phase == 1
        if not allowed:
            owner.refuse('mutation outside current phase authority')

    def dispatch(self, op, args):
        if self._phase_owner is not None:
            self._phase_owner.require_dispatch()
        if not isinstance(op, str) or op not in self.OPS or type(args) is not dict:
            raise runtime.CustodyError('unknown broker operation')
        required, optional = self.FIELDS[op]
        supplied = set(args) - ({'view'} if op != 'open' else set())
        if not required <= supplied or supplied - required - optional:
            raise runtime.CustodyError('invalid broker argument fields')
        if self.readonly and op in ('create', 'publish', 'unlink', 'sync', 'sync_directory', 'lock', 'unlock',
                                     'operator_mkdir', 'operator_remove_output'):
            raise runtime.CustodyError('controller plan authorizes observation only')
        self._phase_operation(op, args)
        self.s.check()
        if op == 'open':
            if args['root'] != self.root:
                raise runtime.CustodyError('root selector is not current original session')
            pins = args.get('pins')
            if pins is not None:
                if type(pins) is not dict: raise runtime.CustodyError('invalid expected directory pins')
                for path, pin in pins.items():
                    if path in self.removed_outputs:
                        retired = [o for o in self.s.retired if o.path == path and o.directory]
                        if len(retired) != 1 or self.pin(retired[0]) != pin:
                            raise runtime.CustodyError('foreign removed directory witness')
                    elif self.pin(self.obj(path, True)) != pin:
                        raise runtime.CustodyError('foreign directory witnesses')
            token = self.token('view')
            self.views[token] = dict(pins or {})
            return token
        view = args.get('view')
        if not isinstance(view, str) or view not in self.views:
            raise runtime.CustodyError('unknown/closed broker view')
        if self.record_stages and op in ('create', 'unlink', 'operator_mkdir', 'operator_remove_output', 'lock', 'unlock'):
            raise runtime.CustodyError('record stage requires its exact next publication')
        if op == 'close':
            if any(item[0] == view for item in self.record_stages.values()):
                self.preserve('client closed with pending record stage')
                raise runtime.CustodyError('record publication custody lost')
            if view in self.programs.values():
                self.preserve('client closed with approved source grant')
                raise runtime.CustodyError('lost approved source grant')
            if self.lease is not None and self.lease[1] == view:
                self.preserve('client closed with engine lock')
                raise runtime.CustodyError('lost engine lock lease')
            del self.views[view]
            return None
        if op == 'context':
            parent = self.s.parent_pin
            ns = self.s.objects[''].pin['namespace']
            return dict(root=self.root, ns={name: name + ':[' + str(value[-1] if isinstance(value, (list, tuple)) else value) + ']'
                                           for name, value in zip(('mnt', 'user'), ns)},
                        tmp_pin=[parent[k] for k in ('dev', 'ino', 'uid', 'gid')] + [stat.S_IMODE(parent['mode']), parent['mount']],
                        pins=dict(self.views[view]), root_pin=self.pin(self.s.objects['']))
        if op in ('directory_pin', 'bind'):
            pin = self.pin(self.obj(args['path'], True))
            if op == 'bind':
                if pin != args['pin']: raise runtime.CustodyError('directory binding changed')
                return None
            return pin
        if op == 'absent':
            path = args['path']
            if path not in (*self.e.FILES, *self.e.FIXED_DIRS, *self.e.OUTPUT_DIRS):
                raise runtime.CustodyError('unapproved absence role')
            return path not in self.s.objects
        if op == 'entries':
            obj = self.obj(args['path'], True)
            if type(args['expected']) is not list or sorted(args['expected']) != self.k.entries(obj.fd):
                raise runtime.CustodyError('unexpected directory entries')
            self.s.check()
            return None
        if op == 'read': return self.read(args['path'], args.get('authority', False))
        if op == 'create': return self._create(args['path'], args['image'], view)
        if op == 'publish':
            path = args['path']
            if path not in self.e.STAGES: raise runtime.CustodyError('not paired target')
            if path in self.e.MANAGED:
                self._managed_intent(view, 'publish', path)
            else:
                stage = self.e.STAGES[path]
                slot = self.record_stages.get(stage)
                previous = slot[3] if slot else None
                if previous is not None and args['expected'] is not None and 'ctime_ns' not in args['expected']:
                    previous = {key: previous[key] for key in ('image', 'pin')}
                if slot is None or slot[:3] != (view, path, args['staged']['image']) or previous != args['expected']:
                    raise runtime.CustodyError('record publication lacks original validated transition')
            self.expect(path, args['expected'])
            self.expect(self.e.STAGES[path], args['staged'])
            self.s.publish(self.e.STAGES[path], path)
            self.record_stages.pop(self.e.STAGES[path], None)
            return self.read(path)
        if op == 'unlink':
            if args['path'] != self.e.TARGET:
                raise runtime.CustodyError('only journal-bound generated target unlink supported')
            self._managed_intent(view, 'unlink', self.e.TARGET)
            self.expect(args['path'], args['expected'])
            self.s.unlink_transient(self.obj(args['path']))
            return None
        if op in ('sync', 'sync_directory'):
            try:
                self.s.ledger.append(dict(kind='engine-sync-intent', operation=op))
                if op == 'sync_directory':
                    obj = self.obj(args['path'], True)
                    if type(args.get('parent', False)) is not bool: raise runtime.CustodyError('invalid parent sync flag')
                    fds = [obj.fd] + ([obj.parent] if args.get('parent', False) else [])
                else:
                    if args.get('removed', []) != self.removed_outputs: raise runtime.CustodyError('unregistered output removal')
                    fds = [o.fd for o in self.s.objects.values() if not o.directory]
                    fds += [o.fd for _, o in sorted(self.s.objects.items(), key=lambda item: len(item[0]), reverse=True) if o.directory]
                for fd in fds: self.k.sync(fd)
                self.s.check()
                self.s.ledger.append(dict(kind='engine-synced', operation=op))
                return None
            except BaseException:
                self.preserve('engine sync uncertainty')
                raise
        if op == 'lock':
            if self.lease is not None: raise runtime.CustodyError('engine lock already leased')
            self.expect(self.e.LOCK, args['expected'])
            obj = self.obj(self.e.LOCK)
            try:
                self.s.ledger.append(dict(kind='engine-lock-intent'))
                self.k.lock(obj.fd)
                self.s.check()
                token = self.token('lease')
                self.lease = (token, view, args['expected'])
                self.s.ledger.append(dict(kind='engine-locked', lease=token))
                return token
            except BaseException:
                self.preserve('engine lock uncertainty')
                raise
        if op == 'unlock':
            if self.lease is None or self.lease[:2] != (args['lease'], view): raise runtime.CustodyError('foreign engine lock lease')
            try:
                self.expect(self.e.LOCK, self.lease[2])
                self.s.ledger.append(dict(kind='engine-unlock-intent'))
                self.k.unlock(self.obj(self.e.LOCK).fd)
                self.s.check()
                self.s.ledger.append(dict(kind='engine-unlocked', lease=args['lease']))
                self.lease = None
                return None
            except BaseException:
                self.preserve('engine unlock uncertainty')
                raise
        if op == 'program_begin':
            self.program.check()
            token = self.token('source')
            self.programs[token] = view
            return dict(data=base64.b64encode(self.program.data).decode(), grant=token)
        if op in ('program_check', 'program_end'):
            if self.programs.get(args['grant']) != view: raise runtime.CustodyError('foreign source grant')
            try: self.program.check()
            except BaseException:
                self.preserve('approved source changed')
                raise
            if op == 'program_end': del self.programs[args['grant']]
            return None
        if op == 'operator_baseline':
            if self.baseline is None: raise runtime.CustodyError('controller baseline not supplied')
            return dict(data=base64.b64encode(self.baseline).decode())
        if op == 'operator_mkdir':
            path = args['path']
            if path not in self.e.FIXED_DIRS and path not in self.e.OUTPUT_DIRS: raise runtime.CustodyError('unapproved operator directory')
            if path in self.e.OUTPUT_DIRS: self._output_intent(path)
            return self.pin(self.s.create(path))
        if op == 'operator_remove_output':
            path = args['path']
            self._output_intent(path, True)
            obj = self.obj(path, True)
            if self.pin(obj) != args['expected'] or self.k.entries(obj.fd): raise runtime.CustodyError('output not original/empty')
            try:
                before = next(o.pin for o in self.s.objects.values() if o.fd == obj.parent)
                self.s.ledger.append(dict(kind='output-remove-intent', role=path, birth=obj.birth))
                self.s._verify(obj)
                self.k.remove(obj.parent, obj.name, True)
                self.k.sync(obj.parent)
                after = self.k.snapshot(obj.fd)
                if (runtime.invariant(after) != runtime.invariant(obj.pin) or after['nlink'] != 0
                        or after['size'] != obj.pin['size'] or after['flags'] != obj.pin['flags']):
                    raise runtime.CustodyError('removed output identity differs')
                self.s._parent_transition(obj.parent, before, -1)
                obj.pin, obj.state = after, 'retired'
                self.s.retired.append(obj)
                del self.s.objects[path]
                self.removed_outputs.append(path)
                self.s.ledger.append(dict(kind='output-removed', role=path, pin=after))
                self.s.check()
                return None
            except BaseException:
                self.preserve('output removal uncertainty')
                raise
        raise runtime.CustodyError('operation not implemented')
