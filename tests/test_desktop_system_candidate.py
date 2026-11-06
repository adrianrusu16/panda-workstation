"""Synthetic monitor contracts only: never import Qt, sensors, or a session bus."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'theme/panda/common'))
CONTRACT = ROOT / 'theme/panda/common/desktop/system-6.8.2.json'
FIXTURE = ROOT / 'tests/fixtures/desktop/assessment/sanitized-shape.json'
SAMPLES = ROOT / 'tests/fixtures/desktop/system'


def reading(value, unit, *, state='valid', at=60000):
    return dict(state=state, value=value, unit=unit, sampled_at_ms=at)


def scene():
    return dict(schema_version=1, scope='panda-system-synthetic', now_ms=60000,
                sample_interval_ms=1000, stale_after_ms=3000,
                cpu=dict(usage=reading(25.0, 'percent'),
                         history=[dict(at_ms=57000, value=10.0), dict(at_ms=58000, value=None),
                                  dict(at_ms=60000, value=25.0)]),
                ram=dict(used=reading(4294967296, 'byte'),
                         available=reading(12884901888, 'byte'),
                         total=reading(17179869184, 'byte')))


class SystemTests(unittest.TestCase):
    def setUp(self):
        from desktop_layout import load_config
        self.config = load_config(ROOT / 'theme/panda/common/desktop/layout.toml')
        self.fixture = json.loads(FIXTURE.read_text())
        self.scene = scene()

    def plan(self, **kwargs):
        from desktop_system_candidate import build_system_candidate
        return build_system_candidate(self.config, self.fixture, self.scene,
            plasma_version='6.8.2', contract_bytes=CONTRACT.read_bytes(), **kwargs)

    def test_official_native_faces_have_additive_null_identities_and_no_actions(self):
        plan = self.plan()
        self.assertEqual(plan['scope'], 'offline-system-only-candidate')
        self.assertEqual([(w['role'], w['plugin'], w['instance_id']) for w in plan['widgets']],
                         [('cpu', 'org.kde.plasma.systemmonitor.cpu', None),
                          ('ram', 'org.kde.plasma.systemmonitor.memory', None)])
        cpu, ram = plan['widgets']
        self.assertEqual(cpu['settings']['Appearance/chartFace'], 'org.kde.ksysguard.linechart')
        self.assertEqual(cpu['settings']['Sensors/highPrioritySensorIds'], ['cpu/all/usage'])
        self.assertEqual(cpu['settings']['org.kde.ksysguard.linechart/General/historyAmount'], 60)
        self.assertEqual(ram['settings']['Appearance/chartFace'], 'org.kde.ksysguard.horizontalbars')
        self.assertEqual(ram['settings']['Sensors/lowPrioritySensorIds'],
                         ['memory/physical/free', 'memory/physical/total'])
        self.assertEqual(plan['operations'], [])
        self.assertFalse(plan['native_verified'])
        self.assertFalse(plan['ready_for_native_test'])

    def test_cpu_is_percent_without_core_count_division_and_gaps_break_history(self):
        cpu = self.plan()['readings']['cpu']
        self.assertEqual(cpu['usage']['value'], 25.0)
        self.assertEqual(cpu['fill_fraction'], .25)
        self.assertEqual(cpu['history'], [dict(at_ms=57000,value=10.0),
                         dict(at_ms=58000,value=None), dict(at_ms=59000,value=None),
                         dict(at_ms=60000,value=25.0)])
        self.assertEqual(cpu['history_segments'], [[dict(at_ms=57000,value=10.0)],
                                                   [dict(at_ms=60000,value=25.0)]])
        self.scene['cpu']['usage'] = reading(0, 'percent')
        self.assertEqual(self.plan()['readings']['cpu']['fill_fraction'], 0)
        self.scene['cpu']['usage'] = reading(100, 'percent')
        self.assertEqual(self.plan()['readings']['cpu']['fill_fraction'], 1)

    def test_stale_missing_unknown_values_never_become_healthy_zeroes(self):
        for state, value, at in [('stale',25.0,57000),('missing',None,None),('unknown',None,None),
                                 ('valid',25.0,56999)]:
            self.scene['cpu']['usage'] = reading(value, 'percent', state=state, at=at)
            cpu = self.plan()['readings']['cpu']
            self.assertIsNone(cpu['usage']['value'])
            self.assertIsNone(cpu['fill_fraction'])
            self.assertNotEqual(cpu['usage']['state'], 'valid')
        self.scene['cpu']['usage'] = reading(25.0, 'percent', at=57000)
        self.assertEqual(self.plan()['readings']['cpu']['usage']['state'], 'valid')
        self.scene['cpu']['usage'] = reading(25.0, None)
        self.assertEqual(self.plan()['readings']['cpu']['usage']['state'], 'unknown-unit')
        self.assertIsNone(self.plan()['readings']['cpu']['fill_fraction'])

    def test_ram_available_is_not_raw_free_and_only_valid_total_is_denominator(self):
        ram = self.plan()['readings']['ram']
        self.assertEqual(ram['used']['value'], 4294967296)
        self.assertEqual(ram['available']['value'], 12884901888)
        self.assertEqual(ram['used_percent'], 25.0)
        self.assertEqual(ram['available_percent'], 75.0)
        self.assertEqual(ram['fill_fraction'], .25)
        for total in [reading(None,'byte',state='missing',at=None), reading(0,'byte'),
                      reading(17179869184,None), reading(17179869184,'byte',at=50000)]:
            self.scene['ram']['total'] = total
            ram = self.plan()['readings']['ram']
            self.assertIsNone(ram['used_percent'])
            self.assertIsNone(ram['available_percent'])
            self.assertIsNone(ram['fill_fraction'])
            self.assertEqual(ram['used']['value'], 4294967296)

    def test_ram_missing_values_are_not_inferred_and_unsynchronised_values_do_not_fill(self):
        self.scene['ram']['available'] = reading(None,'byte',state='unknown',at=None)
        ram=self.plan()['readings']['ram']
        self.assertIsNone(ram['available']['value'])
        self.assertIsNone(ram['available_percent'])
        self.assertEqual(ram['used_percent'],25)
        self.scene['ram']['used']['sampled_at_ms'] = 59000
        self.assertIsNone(self.plan()['readings']['ram']['used_percent'])

    def test_strict_fixture_rejects_bad_types_ranges_units_time_and_unknown_fields(self):
        from desktop_system_candidate import validate_system_fixture
        mutations = [lambda s:s.update(extra=True), lambda s:s.update(schema_version=True),
                     lambda s:s.update(now_ms=True), lambda s:s.update(sample_interval_ms=0),
                     lambda s:s['cpu']['usage'].update(value=True),
                     lambda s:s['cpu']['usage'].update(value=float('nan')),
                     lambda s:s['cpu']['usage'].update(value=10**400),
                     lambda s:s['cpu']['history'][0].update(value=10**400),
                     lambda s:s['cpu']['usage'].update(value=101),
                     lambda s:s['cpu']['usage'].update(unit='MHz'),
                     lambda s:s['cpu']['usage'].update(sampled_at_ms=60001),
                     lambda s:s['cpu']['usage'].update(state='missing'),
                     lambda s:s['cpu']['history'].append(dict(at_ms=60000,value=20)),
                     lambda s:s['cpu']['history'][0].update(at_ms=57500),
                     lambda s:s['ram']['used'].update(value=-1),
                     lambda s:s['ram']['total'].update(value=4294967295),
                     lambda s:s['ram']['available'].update(value=1),
                     lambda s:s['ram']['used'].update(value=1.5)]
        for index, mutate in enumerate(mutations):
            wrong=scene();mutate(wrong)
            with self.subTest(index=index), self.assertRaises(ValueError):validate_system_fixture(wrong)

    def test_empty_history_is_unknown_and_stale_history_does_not_extend_current_value(self):
        self.scene['cpu']['history']=[]
        self.assertEqual(self.plan()['readings']['cpu']['history_segments'],[])
        self.scene['cpu']['history']=[dict(at_ms=50000,value=50)]
        history=self.plan()['readings']['cpu']['history']
        self.assertEqual(history[-1],dict(at_ms=60000,value=None))
        self.assertEqual(len(history),11)

    def test_existing_instances_are_refused_panel_and_tray_instances_remain_untouched(self):
        before=copy.deepcopy(self.fixture)
        for role,plugin in [('cpu','org.kde.plasma.systemmonitor.cpu'),
                            ('ram','org.kde.plasma.systemmonitor.memory')]:
            for count in (1,2):
                self.fixture=copy.deepcopy(before)
                for ident in range(40,40+count):
                    self.fixture['applets'].append(dict(id=ident,containment_id=10,
                        plugin=plugin,geometry=None,config={'opaque':'preserve'}))
                self.fixture['bindings'][role]=40
                with self.subTest(role=role,count=count),self.assertRaises(ValueError):self.plan()
        self.fixture=copy.deepcopy(before)
        self.fixture['applets'][4]['config']['nested_applets'].append(
            dict(id=32,plugin='org.kde.plasma.systemmonitor.cpu'))
        self.fixture['applets'].append(dict(id=40,containment_id=20,
            plugin='org.kde.plasma.systemmonitor.memory',geometry=None,config={'opaque':'preserve'}))
        self.fixture['panels'][0]['applet_ids'].append(40)
        before=copy.deepcopy(self.fixture); original=copy.deepcopy(self.scene)
        plan=self.plan()
        self.assertEqual(plan['preserved_fixture'],before)
        plan['preserved_fixture']['applets'].clear()
        self.assertEqual(self.fixture,before)
        self.assertEqual(self.scene,original)

    def test_geometry_scaling_and_flavors_reuse_layout_without_dispatching_other_widgets(self):
        geometry=None
        for flavor in ('minimal','cyber','gothic','hybrid','wave'):
            plan=self.plan(flavor=flavor,resolution='qhd',scale=1.5,presentation='expanded')
            rects=[w['rect'] for w in plan['widgets']]
            self.assertEqual([r[2:] for r in rects],[[352,120],[352,120]])
            self.assertEqual(plan['output']['logical_size'],[2560/1.5,1440/1.5])
            if geometry is None:geometry=rects
            self.assertEqual(rects,geometry)
            self.assertEqual(plan['preserved_fixture'],self.fixture)
            self.assertEqual([w['role'] for w in plan['widgets']],['cpu','ram'])
        with self.assertRaises(ValueError):self.plan(resolution='fhd',scale=1.5,presentation='expanded')

    def test_exact_source_settings_and_roundtrip_validation_reject_widened_claims(self):
        from desktop_system_candidate import build_system_candidate, validate_system_candidate, validate_system_settings
        plan=self.plan()
        validate_system_candidate(plan,self.config,contract_bytes=CONTRACT.read_bytes())
        for version in ('6.8.1','6.8.2-1','6.9.0',None):
            with self.assertRaises(ValueError):build_system_candidate(self.config,self.fixture,self.scene,
                plasma_version=version,contract_bytes=CONTRACT.read_bytes())
        for raw in (b'',CONTRACT.read_bytes()+b' '):
            with self.assertRaises(ValueError):validate_system_candidate(plan,self.config,contract_bytes=raw)
        for key,value in [('extra',1),('native_verified',True),('ready_for_native_test',True),
                          ('operations',['subscribe']),('schema_version',True),('readings',{})]:
            wrong=copy.deepcopy(plan);wrong[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):
                validate_system_candidate(wrong,self.config,contract_bytes=CONTRACT.read_bytes())
        for key,value in [('Appearance/chartFace','org.kde.ksysguard.piechart'),
                          ('Appearance/updateRateLimit',True),('Sensors/totalSensor','cpu/all/usage')]:
            wrong=copy.deepcopy(plan['widgets'][0]['settings']);wrong[key]=value
            with self.assertRaises(ValueError):validate_system_settings('cpu',wrong,
                plasma_version='6.8.2',contract_bytes=CONTRACT.read_bytes())


class SystemCLI(unittest.TestCase):
    def test_huge_cpu_integers_are_cleanly_refused_without_stdout_or_traceback(self):
        with tempfile.TemporaryDirectory() as td:
            home=Path(td)
            env={**os.environ,'HOME':td,'PYTHONDONTWRITEBYTECODE':'1',
                 'DBUS_SESSION_BUS_ADDRESS':'disabled-for-offline-test','DISPLAY':'','WAYLAND_DISPLAY':''}
            for key in ('CONFIG','DATA','CACHE','STATE'):env['XDG_'+key+'_HOME']=str(home/key.lower())
            for target in ('usage','history'):
                wrong=scene()
                if target=='usage':wrong['cpu']['usage']['value']=10**400
                else:wrong['cpu']['history'][0]['value']=10**400
                sample=home/'huge.json';sample.write_text(json.dumps(wrong))
                result=subprocess.run([sys.executable,'-B',str(ROOT/'theme/panda/common/desktop_cli.py'),
                    'system-candidate','--fixture',str(FIXTURE),'--system-fixture',str(sample),
                    '--system-contract',str(CONTRACT),'--plasma-version','6.8.2'],
                    env=env,capture_output=True,text=True,timeout=5)
                self.assertNotEqual(result.returncode,0)
                self.assertEqual(result.stdout,'')
                self.assertIn('desktop: refused:',result.stderr)
                self.assertNotIn('Traceback',result.stderr)

    def test_stdout_only_cli_is_deterministic_and_refuses_mixed_or_missing_inputs(self):
        with tempfile.TemporaryDirectory() as td:
            home=Path(td);(home/'sentinel').write_bytes(b'preserve')
            env={**os.environ,'HOME':td,'PYTHONDONTWRITEBYTECODE':'1',
                 'DBUS_SESSION_BUS_ADDRESS':'disabled-for-offline-test','DISPLAY':'','WAYLAND_DISPLAY':''}
            for key in ('CONFIG','DATA','CACHE','STATE'):env['XDG_'+key+'_HOME']=str(home/key.lower())
            def snapshot():
                return {str(p.relative_to(home)):(p.stat().st_mode,p.stat().st_mtime_ns,
                    hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None) for p in home.rglob('*')}
            before=snapshot()
            cmd=[sys.executable,'-B',str(ROOT/'theme/panda/common/desktop_cli.py'),
                 'system-candidate','--fixture',str(FIXTURE)]
            args=['--plasma-version','6.8.2','--system-contract',str(CONTRACT),
                  '--system-fixture',str(SAMPLES/'valid.json')]
            first=subprocess.run(cmd+args,env=env,capture_output=True,text=True,timeout=10)
            self.assertEqual(first.returncode,0,first.stderr)
            second=subprocess.run(cmd+args,env=env,capture_output=True,text=True,timeout=10)
            self.assertEqual(second.returncode,0,second.stderr)
            self.assertEqual(first.stdout,second.stdout)
            self.assertEqual(json.loads(first.stdout)['readings']['ram']['used_percent'],25)
            for extra in ([],args[:2],args[:-2],args+['--apply'],args+['--clock-schema',str(CONTRACT)],
                          args+['--media-fixture',str(SAMPLES/'valid.json')]):
                bad=subprocess.run(cmd+extra,env=env,capture_output=True,text=True,timeout=5)
                self.assertNotEqual(bad.returncode,0)
                self.assertEqual(bad.stdout,'')
                self.assertNotIn('Traceback',bad.stderr)
            self.assertEqual(snapshot(),before)


if __name__ == '__main__':
    unittest.main()
