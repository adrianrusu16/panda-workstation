"""Weather boundary tests: explicit synthetic inputs; no Qt, provider or host queries."""
import copy
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'theme/panda/common'))
CONTRACT = ROOT/'theme/panda/common/desktop/weather-6.8.2.json'
FIXTURE = ROOT/'tests/fixtures/desktop/assessment/sanitized-shape.json'
SAMPLES = ROOT/'tests/fixtures/desktop/weather'


class WeatherTests(unittest.TestCase):
    def setUp(self):
        from desktop_layout import load_config
        self.config = load_config(ROOT/'theme/panda/common/desktop/layout.toml')
        self.fixture = json.loads(FIXTURE.read_text())
        self.scene = dict(schema_version=1, scope='panda-weather-synthetic', state='unconfigured',
                          location='', condition='unknown', temperature=None, low=None, high=None,
                          temperature_unit=None, age_seconds=None)

    def plan(self, **kwargs):
        from desktop_weather_candidate import build_weather_candidate
        return build_weather_candidate(self.config, self.fixture, self.scene,
            plasma_version='6.8.2', contract_bytes=CONTRACT.read_bytes(), **kwargs)

    def test_unconfigured_official_candidate_cannot_select_provider_or_write(self):
        result = self.plan()
        self.assertEqual(result['plugin'], 'org.kde.plasma.weather')
        self.assertEqual(result['scope'], 'offline-weather-only-candidate')
        self.assertEqual(result['settings'], {})
        self.assertIsNone(result['instance_id'])
        self.assertEqual(result['operations'], [])
        self.assertEqual(result['network_requests'], [])
        self.assertIsNone(result['selected_provider'])
        self.assertIsNone(result['selected_location'])
        self.assertEqual(result['global_settings'], 'preserve-without-reading')
        self.assertFalse(result['native_verified'])
        self.assertFalse(result['ready_for_native_test'])
        self.assertEqual(result['weather']['temperature_text'], '—')

    def test_five_states_are_truthful_and_demo_never_configures_a_provider(self):
        for state in ('unconfigured','offline','missing','stale','available-demo'):
            self.scene = json.loads((SAMPLES/(state+'.json')).read_text())
            with self.subTest(state=state):
                result = self.plan()
                self.assertEqual(result['weather']['state'], state)
                self.assertEqual(result['weather']['data_origin'], 'synthetic-example-only')
                self.assertIsNone(result['selected_provider'])
                self.assertIsNone(result['selected_location'])
                self.assertEqual(result['weather']['is_stale'], state=='stale')
                self.assertEqual(result['weather']['temperature_text'],
                                 '0 °C' if state=='available-demo' else '12 °C' if state=='stale' else '—')

    def test_explicit_units_zero_and_partial_forecasts_do_not_invent_values(self):
        self.scene.update(state='available-demo',location='Synthetic station',condition='cloudy',
                          temperature=32,temperature_unit='F',age_seconds=0,low=None,high=40)
        result = self.plan()['weather']
        self.assertEqual(result['temperature_text'], '32 °F')
        self.assertEqual(result['low_text'], '—')
        self.assertEqual(result['high_text'], '40 °F')
        self.scene['temperature'] = None
        self.assertEqual(self.plan()['weather']['temperature_text'], '—')
        self.scene.update(temperature=0,temperature_unit='C',high=4)
        self.assertEqual(self.plan()['weather']['temperature_text'], '0 °C')

    def test_malformed_live_location_network_and_false_freshness_inputs_are_refused(self):
        from desktop_weather_candidate import validate_weather_fixture
        self.scene = dict(schema_version=1,scope='panda-weather-synthetic',state='available-demo',
                          location='Synthetic station',condition='cloudy',temperature=0,low=None,
                          high=None,temperature_unit='C',age_seconds=0)
        for key,value in (('schema_version',True),('state','available'),('location','Bucharest'),
                ('condition','https://example.invalid/icon'),('provider','noaa'),('url','https://api.weather.gov'),
                ('latitude',44),('temperature',True),('temperature',float('nan')),
                ('temperature',float('inf')),('temperature',-101),('temperature_unit',None),
                ('temperature_unit','Kelvin'),('age_seconds',True),('age_seconds',-1),
                ('age_seconds',1800),('high',-101)):
            bad=copy.deepcopy(self.scene);bad[key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):
                validate_weather_fixture(bad)
        for state in ('unconfigured','offline','missing'):
            bad=copy.deepcopy(self.scene);bad['state']=state
            with self.subTest(state=state),self.assertRaises(ValueError):validate_weather_fixture(bad)
        self.scene.update(state='stale',age_seconds=1799)
        with self.assertRaises(ValueError):self.plan()

    def test_reviewed_release_bytes_and_no_native_overrides_are_required(self):
        from desktop_weather_candidate import build_weather_candidate,validate_weather_settings
        for version in ('6.8.1','6.8.2-1','6.9.0',None):
            with self.subTest(version=version),self.assertRaises(ValueError):
                build_weather_candidate(self.config,self.fixture,self.scene,
                    plasma_version=version,contract_bytes=CONTRACT.read_bytes())
        for raw in (b'',CONTRACT.read_bytes()+b' '):
            with self.assertRaises(ValueError):
                validate_weather_settings({},plasma_version='6.8.2',contract_bytes=raw)
        for settings in ({'WeatherStation/provider':'noaa'},{'WeatherStation/placeInfo':'private'},
                         {'WeatherStation/updateInterval':0},{'Units/temperatureUnit':1},[]):
            with self.subTest(settings=settings),self.assertRaises(ValueError):
                validate_weather_settings(settings,plasma_version='6.8.2',contract_bytes=CONTRACT.read_bytes())

    def test_invalid_numeric_readings_raise_value_error_for_every_temperature_field(self):
        from desktop_weather_candidate import validate_weather_fixture
        self.scene = json.loads((SAMPLES/'available-demo.json').read_text())
        for key in ('temperature','low','high'):
            for value in (10**400,-10**400,True,False,float('nan'),float('inf'),-float('inf')):
                bad=copy.deepcopy(self.scene);bad[key]=value
                with self.subTest(key=key,value=value),self.assertRaises(ValueError):
                    validate_weather_fixture(bad)

    def test_existing_desktop_weather_is_preserved_and_refuses_addition(self):
        for count in (1,2):
            fixture=copy.deepcopy(self.fixture)
            for ident in range(40,40+count):
                fixture['applets'].append(dict(id=ident,containment_id=10,plugin='org.kde.plasma.weather',
                    geometry=None,config={'WeatherStation':{'provider':'private','placeInfo':'private'}}))
            fixture['bindings']['weather']=40
            before=copy.deepcopy(fixture)
            from desktop_weather_candidate import build_weather_candidate
            with self.subTest(count=count),self.assertRaises(ValueError):
                build_weather_candidate(self.config,fixture,self.scene,plasma_version='6.8.2',contract_bytes=CONTRACT.read_bytes())
            self.assertEqual(fixture,before)

    def test_panel_tray_locations_and_all_unrelated_fixture_state_remain_opaque(self):
        self.fixture['applets'][4]['config']['nested_applets'][0]['config']={'WeatherStation':{'placeInfo':'opaque sentinel'}}
        self.fixture['panels'][0]['applet_ids'].append(28)
        self.fixture['applets'].append(dict(id=28,containment_id=20,plugin='org.kde.plasma.weather',geometry=None,
                                          config={'Units':{'temperatureUnit':'opaque'}}))
        before,scene=copy.deepcopy(self.fixture),copy.deepcopy(self.scene)
        with patch.object(socket,'socket',side_effect=AssertionError('network forbidden')):
            result=self.plan()
        self.assertEqual(result['preserved_fixture'],before)
        self.assertEqual(result['preserved_weather_fixture'],scene)
        result['preserved_fixture']['applets'][4]['config'].clear()
        self.assertEqual(self.fixture,before)
        self.assertEqual(self.scene,scene)

    def test_five_flavors_and_supported_scales_reuse_compact_layout_geometry(self):
        for flavor in ('minimal','cyber','gothic','hybrid','pandawave','wave'):
            for width,height in ((1920,1080),(2560,1440)):
                for scale in (1,1.25,1.5):
                    self.fixture['output'].update(width=width,height=height,scale=scale)
                    result=self.plan(flavor=flavor)
                    with self.subTest(flavor=flavor,width=width,scale=scale):
                        self.assertEqual(result['compact_rect'],[width/scale-312,304,288,112])
                        self.assertEqual(result['size_preferences'],{'compact':[288,112],'expanded':[352,144]})
                        self.assertEqual(result['geometry_method'],'future-operator-edit-mode-only')
                        self.assertFalse(result['native_size_verified'])
                        self.assertEqual(result,self.plan(flavor=flavor))
        self.config['profiles']['compact']['heights'][2]=113
        with self.assertRaises(ValueError):self.plan()

    def test_validation_rejects_widened_authority_and_forged_health(self):
        from desktop_weather_candidate import validate_weather_candidate
        result=self.plan();validate_weather_candidate(result,self.config,contract_bytes=CONTRACT.read_bytes())
        for key,value in (('selected_provider','noaa'),('selected_location','private'),('network_requests',['fetch']),
                         ('native_verified',True),('ready_for_native_test',True),('instance_id',40),
                         ('settings',{'provider':'noaa'}),('operations',['configure']),('schema_version',True),
                         ('extra',1),('compact_rect',[0,0,1,1]),('weather',{})):
            bad=copy.deepcopy(result);bad[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):
                validate_weather_candidate(bad,self.config,contract_bytes=CONTRACT.read_bytes())


class WeatherCLI(unittest.TestCase):
    def test_invalid_numeric_readings_are_clean_cli_refusals(self):
        with tempfile.TemporaryDirectory(prefix='panda-weather-numeric-') as td:
            home=Path(td)
            env={**os.environ,'HOME':td,'PYTHONDONTWRITEBYTECODE':'1','DISPLAY':'','WAYLAND_DISPLAY':'',
                 'DBUS_SESSION_BUS_ADDRESS':'disabled-for-offline-test','DBUS_SYSTEM_BUS_ADDRESS':'disabled-for-offline-test',
                 'XDG_RUNTIME_DIR':str(home/'runtime')}
            for key in ('CONFIG','DATA','CACHE','STATE'):env['XDG_'+key+'_HOME']=str(home/key.lower())
            scene=json.loads((SAMPLES/'available-demo.json').read_text())
            sample=home/'sample.json'
            cmd=[sys.executable,'-B',str(ROOT/'theme/panda/common/desktop_cli.py'),'weather-candidate',
                 '--fixture',str(FIXTURE),'--plasma-version','6.8.2','--weather-contract',str(CONTRACT),
                 '--weather-fixture',str(sample)]
            for key in ('temperature','low','high'):
                for value in (10**400,-10**400,True,False,float('nan'),float('inf'),-float('inf')):
                    bad=copy.deepcopy(scene);bad[key]=value;sample.write_text(json.dumps(bad))
                    result=subprocess.run(cmd,env=env,capture_output=True,text=True,timeout=5)
                    with self.subTest(key=key,value=value):
                        self.assertEqual(result.returncode,1)
                        self.assertEqual(result.stdout,'')
                        self.assertTrue(result.stderr.startswith('desktop: refused:'),result.stderr)
                        self.assertNotIn('Traceback',result.stderr)

    def test_cli_requires_explicit_inputs_is_deterministic_and_never_writes_home(self):
        with tempfile.TemporaryDirectory(prefix='panda-weather-cli-') as td:
            home=Path(td);(home/'sentinel').write_bytes(b'preserve')
            env={**os.environ,'HOME':td,'PYTHONDONTWRITEBYTECODE':'1','DISPLAY':'', 'WAYLAND_DISPLAY':'',
                 'DBUS_SESSION_BUS_ADDRESS':'disabled-for-offline-test','DBUS_SYSTEM_BUS_ADDRESS':'disabled-for-offline-test'}
            for key in ('CONFIG','DATA','CACHE','STATE','RUNTIME'):env['XDG_'+key+('_DIR' if key=='RUNTIME' else '_HOME')]=str(home/key.lower())
            def snapshot():
                return {str(p.relative_to(home)):(p.stat().st_mode,p.stat().st_mtime_ns,
                    hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None) for p in home.rglob('*')}
            before=snapshot()
            cmd=[sys.executable,'-B',str(ROOT/'theme/panda/common/desktop_cli.py'),'weather-candidate','--fixture',str(FIXTURE)]
            args=['--plasma-version','6.8.2','--weather-contract',str(CONTRACT),'--weather-fixture',str(SAMPLES/'unconfigured.json')]
            first=subprocess.run(cmd+args,env=env,capture_output=True,text=True,timeout=5)
            self.assertEqual(first.returncode,0,first.stderr)
            second=subprocess.run(cmd+args,env=env,capture_output=True,text=True,timeout=5)
            self.assertEqual(second.returncode,0,second.stderr)
            self.assertEqual(first.stdout,second.stdout)
            self.assertIsNone(json.loads(first.stdout)['selected_provider'])
            for extra in ([],args[:2],args[:-2],args+['--apply'],args+['--provider','noaa'],
                          args+['--scale','1.5'],args+['--presentation','expanded'],
                          args+['--media-contract',str(CONTRACT)],args+['--clock-schema',str(CONTRACT)]):
                bad=subprocess.run(cmd+extra,env=env,capture_output=True,text=True,timeout=5)
                self.assertNotEqual(bad.returncode,0)
                self.assertEqual(bad.stdout,'')
                self.assertNotIn('Traceback',bad.stderr)
            for command in ('dry-run','media-candidate','clock-candidate'):
                bad=subprocess.run([*cmd[:3],command,*cmd[4:],*args],env=env,capture_output=True,text=True,timeout=5)
                self.assertNotEqual(bad.returncode,0)
            self.assertEqual(snapshot(),before)

    def test_weather_and_system_inputs_cannot_cross_candidate_boundaries(self):
        with tempfile.TemporaryDirectory(prefix='panda-weather-system-cli-') as td:
            home=Path(td);(home/'sentinel').write_bytes(b'preserve')
            env={**os.environ,'HOME':td,'PYTHONDONTWRITEBYTECODE':'1','DISPLAY':'','WAYLAND_DISPLAY':'',
                 'DBUS_SESSION_BUS_ADDRESS':'disabled-for-offline-test','DBUS_SYSTEM_BUS_ADDRESS':'disabled-for-offline-test'}
            for key in ('CONFIG','DATA','CACHE','STATE','RUNTIME'):
                env['XDG_'+key+('_DIR' if key=='RUNTIME' else '_HOME')]=str(home/key.lower())
            def snapshot():
                return {str(p.relative_to(home)):(p.stat().st_mode,p.stat().st_mtime_ns,
                    hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None) for p in home.rglob('*')}
            before=snapshot()
            common=['--fixture',str(FIXTURE),'--plasma-version','6.8.2']
            system_contract=ROOT/'theme/panda/common/desktop/system-6.8.2.json'
            system_fixture=ROOT/'tests/fixtures/desktop/system/valid.json'
            weather=['weather-candidate',*common,'--weather-contract',str(CONTRACT),
                     '--weather-fixture',str(SAMPLES/'unconfigured.json')]
            system=['system-candidate',*common,'--system-contract',str(system_contract),
                    '--system-fixture',str(system_fixture)]
            prefix=[sys.executable,'-B',str(ROOT/'theme/panda/common/desktop_cli.py')]
            for args in (weather,system):
                good=subprocess.run(prefix+args,env=env,capture_output=True,text=True,timeout=5)
                self.assertEqual(good.returncode,0,good.stderr)
                self.assertEqual(json.loads(good.stdout)['operations'],[])
            for args,foreign in ((system,['--weather-contract',str(CONTRACT)]),
                    (system,['--weather-fixture',str(SAMPLES/'unconfigured.json')]),
                    (weather,['--system-contract',str(system_contract)]),
                    (weather,['--system-fixture',str(system_fixture)])):
                with self.subTest(command=args[0],foreign=foreign[0]):
                    bad=subprocess.run(prefix+args+foreign,env=env,capture_output=True,text=True,timeout=5)
                    self.assertEqual(bad.returncode,2,bad.stderr)
                    self.assertEqual(bad.stdout,'')
                    self.assertNotIn('Traceback',bad.stderr)
            self.assertEqual(snapshot(),before)
