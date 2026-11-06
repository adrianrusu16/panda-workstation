"""D2b tests use explicit fixtures only; no MPRIS, Qt or native KDE processes."""
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
sys.path.insert(0, str(ROOT/'theme/panda/common'))
CONTRACT = ROOT/'theme/panda/common/desktop/media-6.8.2.json'
FIXTURE = ROOT/'tests/fixtures/desktop/assessment/sanitized-shape.json'
SAMPLES = ROOT/'tests/fixtures/desktop/media'


class MediaTests(unittest.TestCase):
    def setUp(self):
        from desktop_layout import load_config
        self.config = load_config(ROOT/'theme/panda/common/desktop/layout.toml')
        self.fixture = json.loads(FIXTURE.read_text())
        self.scene = json.loads((SAMPLES/'playing.json').read_text())

    def plan(self, **kwargs):
        from desktop_media_candidate import build_media_candidate
        return build_media_candidate(self.config, self.fixture, self.scene,
            plasma_version='6.8.2', contract_bytes=CONTRACT.read_bytes(), **kwargs)

    def test_one_official_additive_proposal_has_no_native_operations(self):
        plan = self.plan()
        self.assertEqual(plan['scope'], 'offline-media-only-candidate')
        self.assertEqual(plan['plugin'], 'org.kde.plasma.mediacontroller')
        self.assertIsNone(plan['instance_id'])
        self.assertEqual(plan['desktop_id'], 10)
        self.assertEqual(plan['settings'], {})
        self.assertEqual(plan['operations'], [])
        self.assertFalse(plan['native_verified'])
        self.assertFalse(plan['ready_for_native_test'])
        self.assertEqual(plan['global_settings'], 'preserve-without-reading')

    def test_requested_states_and_stopped_have_truthful_controls(self):
        for state, expected in (
                ('playing', {'play':False,'pause':True,'previous':False,'next':True}),
                ('paused', {'play':True,'pause':False,'previous':False,'next':True}),
                ('no-player', {'play':False,'pause':False,'previous':False,'next':False}),
                ('unavailable', {'play':False,'pause':False,'previous':False,'next':False})):
            self.scene = json.loads((SAMPLES/(state+'.json')).read_text())
            with self.subTest(state=state):
                self.assertEqual(self.plan()['media']['controls'], expected)
        self.scene = json.loads((SAMPLES/'playing.json').read_text())
        self.scene['state'] = 'stopped'
        self.assertTrue(self.plan()['media']['controls']['play'])
        self.assertFalse(self.plan()['media']['controls']['pause'])

    def test_capability_matrix_gates_every_control_including_can_control(self):
        keys = ('can_control','can_play','can_pause','can_go_previous','can_go_next','can_seek')
        for state in ('playing','paused'):
            self.scene['state'] = state
            for bits in range(64):
                caps = {key:bool(bits & (1<<index)) for index,key in enumerate(keys)}
                self.scene['capabilities'] = caps
                actual = self.plan()['media']['controls']
                with self.subTest(state=state,bits=bits):
                    self.assertEqual(actual['play'], state=='paused' and caps['can_control'] and caps['can_play'])
                    self.assertEqual(actual['pause'], state=='playing' and caps['can_control'] and caps['can_pause'])
                    self.assertEqual(actual['previous'], caps['can_control'] and caps['can_go_previous'])
                    self.assertEqual(actual['next'], caps['can_control'] and caps['can_go_next'])

    def test_duration_is_microseconds_and_unknown_art_is_not_fetched(self):
        media = self.plan()['media']
        self.assertEqual(media['duration_seconds'], 261)
        self.assertEqual(media['position_seconds'], 97)
        self.assertAlmostEqual(media['progress_fraction'], 97/261)
        self.scene.update(duration_us=None, artwork='unavailable')
        media = self.plan()['media']
        self.assertIsNone(media['duration_seconds'])
        self.assertIsNone(media['progress_fraction'])
        self.assertEqual(media['position_seconds'], 97)
        self.assertEqual(media['artwork'], 'unavailable')
        self.assertIsNone(media['artwork_uri'])
        self.assertFalse(media['seek_possible'])

    def test_invalid_unknown_and_inconsistent_media_data_is_refused(self):
        for key,value in (('unknown',1),('state','invented'),('players',True),('players',0),
                          ('artwork','https://example.invalid/image'),('duration_us',0),
                          ('duration_us',True),('position_us',float('nan')),('position_us',262000000)):
            wrong = copy.deepcopy(self.scene); wrong[key] = value
            from desktop_media_candidate import validate_media_fixture
            with self.subTest(key=key,value=value), self.assertRaises(ValueError):
                validate_media_fixture(wrong)
        self.scene['capabilities']['can_play'] = 1
        with self.assertRaises(ValueError):self.plan()
        self.scene = json.loads((SAMPLES/'no-player.json').read_text())
        self.scene['capabilities']['can_play'] = True
        with self.assertRaises(ValueError):self.plan()

    def test_empty_title_and_unknown_position_are_not_invented(self):
        self.scene.update(title='',artist='',duration_us=261000000,position_us=None)
        media = self.plan()['media']
        self.assertEqual(media['title'], '')
        self.assertIsNone(media['position_seconds'])
        self.assertIsNone(media['progress_fraction'])
        self.assertEqual(media['compact_content_hint'], 'icon-when-track-empty')

    def test_exact_source_version_and_empty_native_settings_are_enforced(self):
        from desktop_media_candidate import build_media_candidate, validate_media_settings
        for version in ('6.7.5','6.8.1','6.8.2-1.1','6.9.0',None):
            with self.subTest(version=version), self.assertRaises(ValueError):
                build_media_candidate(self.config,self.fixture,self.scene,plasma_version=version,contract_bytes=CONTRACT.read_bytes())
        for settings in ({'General/VolumeStep':10},{'Appearance/showDate':True},{'background':1},[]):
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                validate_media_settings(settings,plasma_version='6.8.2',contract_bytes=CONTRACT.read_bytes())
        for raw in (b'', CONTRACT.read_bytes().replace(b'"switch_grid_units"',b'"unreviewed"')):
            with self.assertRaises(ValueError):
                build_media_candidate(self.config,self.fixture,self.scene,plasma_version='6.8.2',contract_bytes=raw)

    def test_existing_and_ambiguous_desktop_instances_are_refused(self):
        for count in (1,2):
            self.fixture = json.loads(FIXTURE.read_text())
            for ident in range(40,40+count):
                self.fixture['applets'].append(dict(id=ident,containment_id=10,
                    plugin='org.kde.plasma.mediacontroller',geometry=None,config={'private':'preserve'}))
            self.fixture['bindings']['media'] = 40
            with self.subTest(count=count), self.assertRaises(ValueError):self.plan()

    def test_panel_tray_and_complete_settings_are_preserved_without_mutation(self):
        self.fixture['applets'][4]['config']['nested_applets'].append({'id':32,'plugin':'org.kde.plasma.mediacontroller'})
        self.fixture['applets'][5]['config'].update({'timezone':'opaque','calendar':['opaque'],'locale':'opaque'})
        before,scene = copy.deepcopy(self.fixture),copy.deepcopy(self.scene)
        plan = self.plan()
        self.assertEqual(plan['preserved_fixture'],before)
        self.assertEqual(plan['preserved_media_fixture'],scene)
        plan['preserved_fixture']['applets'][5]['config'].clear()
        self.assertEqual(self.fixture,before)
        self.assertEqual(self.scene,scene)
        self.assertEqual(self.plan(),self.plan())
        self.assertEqual(self.fixture['desktop_count'],1)
        self.assertIsNone(self.plan()['instance_id'])

    def test_geometry_preferences_are_shared_and_native_minima_are_explicit(self):
        for flavor in ('minimal','cyber','gothic','hybrid','pandawave','wave'):
            plan=self.plan(flavor=flavor)
            self.assertEqual(plan['size_preferences'],{'compact':[288,120],'expanded':[352,168]})
            self.assertEqual(plan['native_geometry']['full_minimum_grid_units'],[14,10])
            self.assertEqual(plan['native_geometry']['full_preferred_grid_units'],[20,20])
            self.assertIsNone(plan['native_geometry']['compact_minimum_grid_units'])
            self.assertFalse(plan['native_size_verified'])
            self.assertEqual(plan['geometry_method'],'future-operator-edit-mode-only')

    def test_candidate_validation_rejects_forged_claims_and_unknown_fields(self):
        from desktop_media_candidate import validate_media_candidate
        plan=self.plan();validate_media_candidate(plan,self.config,contract_bytes=CONTRACT.read_bytes())
        for key,value in (('instance_id',41),('native_verified',True),('ready_for_native_test',True),
                          ('operations',['play']),('settings',{'VolumeStep':10}),('extra',1),
                          ('media',{}),('schema_version',True)):
            wrong=copy.deepcopy(plan);wrong[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):
                validate_media_candidate(wrong,self.config,contract_bytes=CONTRACT.read_bytes())


class MediaCLI(unittest.TestCase):
    def test_cli_is_deterministic_inert_and_requires_reviewed_inputs(self):
        with tempfile.TemporaryDirectory() as td:
            home=Path(td);(home/'sentinel').write_bytes(b'preserve')
            env={**os.environ,'HOME':td,'PYTHONDONTWRITEBYTECODE':'1','DBUS_SESSION_BUS_ADDRESS':'disabled-for-offline-test'}
            for key in ('CONFIG','DATA','CACHE','STATE'):env['XDG_'+key+'_HOME']=str(home/key.lower())
            def snapshot():
                return {str(p.relative_to(home)):(p.stat().st_mode,p.stat().st_mtime_ns,
                    hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None) for p in home.rglob('*')}
            before=snapshot()
            cmd=[sys.executable,'-B',str(ROOT/'theme/panda/common/desktop_cli.py'),'media-candidate','--fixture',str(FIXTURE)]
            args=['--plasma-version','6.8.2','--media-contract',str(CONTRACT),'--media-fixture',str(SAMPLES/'playing.json')]
            first=subprocess.run(cmd+args,env=env,capture_output=True,text=True,timeout=5)
            self.assertEqual(first.returncode,0,first.stderr)
            second=subprocess.run(cmd+args,env=env,capture_output=True,text=True,timeout=5)
            self.assertEqual(second.returncode,0,second.stderr)
            self.assertEqual(first.stdout,second.stdout)
            self.assertEqual(json.loads(first.stdout)['media']['controls'],{'play':False,'pause':True,'previous':False,'next':True})
            for extra in ([],args[:2],args[:-2],args+['--apply'],args+['--scale','1.5'],args+['--presentation','expanded']):
                bad=subprocess.run(cmd+extra,env=env,capture_output=True,text=True,timeout=5)
                self.assertNotEqual(bad.returncode,0)
                self.assertEqual(bad.stdout,'')
                self.assertNotIn('Traceback',bad.stderr)
            self.assertEqual(snapshot(),before)
