"""D2b inert Media Controller intent and synthetic capability projection.

No MPRIS discovery, control dispatch, image loading, native code or config writes.
The exact upstream contract is not an installed/running release attestation.
"""
import copy
import hashlib
import json

from desktop_layout import digest, fields, string, validate_config, validate_fixture
from palette import resolve_slug

VERSION = '6.8.2'
PLUGIN = 'org.kde.plasma.mediacontroller'
CONTRACT_SHA256 = '6c0104340b7b4e448ea0cb0228f15ce2fb9aedc60ccbf367784cd0a125cb45a7'
CAPABILITIES = ('can_control','can_play','can_pause','can_go_previous','can_go_next','can_seek')


def validate_media_settings(settings, *, plasma_version, contract_bytes):
    """No per-instance XML/config UI exists in this reviewed media package."""
    if plasma_version != VERSION:
        raise ValueError('media candidate requires exact upstream Plasma 6.8.2')
    if type(contract_bytes) is not bytes or hashlib.sha256(contract_bytes).hexdigest()!=CONTRACT_SHA256:
        raise ValueError('media source contract differs from reviewed Plasma 6.8.2')
    if type(settings) is not dict or settings:
        raise ValueError('media native settings are unsupported; preserve global settings')
    return json.loads(contract_bytes)


def validate_media_fixture(scene):
    """Strict synthetic readings, not MPRIS wire input or actual player health."""
    fields(scene, ('schema_version','scope','state','players','title','artist','artwork',
                   'duration_us','position_us','capabilities'), 'media fixture')
    if type(scene['schema_version']) is not int or scene['schema_version']!=1 or scene['scope']!='panda-media-synthetic':
        raise ValueError('explicit synthetic media schema required')
    if scene['state'] not in ('playing','paused','stopped','no-player','unavailable'):
        raise ValueError('unknown media state')
    if type(scene['players']) is not int or not 0<=scene['players']<=16:
        raise ValueError('bounded synthetic player count required')
    for key in ('title','artist'):
        if scene[key]!='':
            string(scene[key], 'media.'+key)
    if scene['artwork'] not in ('sample','none','unavailable'):
        raise ValueError('synthetic artwork state required; no URI inputs')
    caps=scene['capabilities']
    fields(caps, CAPABILITIES, 'media capabilities')
    if any(type(value) is not bool for value in caps.values()):
        raise ValueError('media capabilities must be boolean')
    duration,position=scene['duration_us'],scene['position_us']
    for value,minimum in ((duration,1),(position,0)):
        if value is not None and (type(value) is not int or not minimum<=value<=86_400_000_000):
            raise ValueError('bounded integer microseconds or null required')
    if duration is not None and position is not None and position>duration:
        raise ValueError('synthetic position exceeds duration')
    if scene['state'] in ('no-player','unavailable'):
        if (scene['players'] or any(caps.values()) or duration is not None or position is not None
                or scene['title'] or scene['artist'] or scene['artwork']!='none'):
            raise ValueError('absent/unavailable state cannot claim healthy readings or controls')
    elif not scene['players']:
        raise ValueError('playback state requires a synthetic player')
    return scene


def _media_projection(scene):
    validate_media_fixture(scene)
    active=scene['state'] in ('playing','paused','stopped')
    caps=scene['capabilities']
    controllable=active and caps['can_control']
    duration,position=scene['duration_us'],scene['position_us']
    return dict(state=scene['state'], title=scene['title'], artist=scene['artist'], players=scene['players'],
                controls=dict(play=controllable and scene['state']!='playing' and caps['can_play'],
                              pause=controllable and scene['state']=='playing' and caps['can_pause'],
                              previous=controllable and caps['can_go_previous'],
                              next=controllable and caps['can_go_next']),
                primary_action='pause' if scene['state']=='playing' else 'play',
                seek_possible=controllable and caps['can_seek'] and duration is not None,
                duration_seconds=None if duration is None else duration/1_000_000,
                position_seconds=None if position is None else position/1_000_000,
                progress_fraction=None if duration is None or position is None else position/duration,
                artwork=scene['artwork'], artwork_uri=None,
                compact_content_hint='icon-when-track-empty' if not scene['title'] else 'adaptive-row-or-icon',
                native_control_visibility_verified=False)


def build_media_candidate(config, fixture, scene, *, plasma_version, contract_bytes, flavor='hybrid'):
    """One additive desktop proposal; no tray reuse, allocated ID or operations."""
    validate_config(config)
    validate_fixture(fixture)
    contract=validate_media_settings({},plasma_version=plasma_version,contract_bytes=contract_bytes)
    projection=_media_projection(scene)
    flavor=resolve_slug(flavor)
    instances=[a for a in fixture['applets'] if a['containment_id']==fixture['desktop_id'] and a['plugin']==PLUGIN]
    if instances or fixture['bindings']['media'] is not None:
        raise ValueError('existing or ambiguous desktop media instance; separate decision required')
    sizes={name:[profile['width'],profile['heights'][1]] for name,profile in config['profiles'].items()}
    if sizes!={'compact':[288,120],'expanded':[352,168]}:
        raise ValueError('media size preferences differ from reviewed Panda design targets')
    return dict(schema_version=1,scope='offline-media-only-candidate',plasma_version=plasma_version,
                source_contract_sha256=CONTRACT_SHA256,plugin=PLUGIN,desktop_id=fixture['desktop_id'],
                instance_id=None,intent='propose-one-additive-desktop-instance',settings={},
                global_settings='preserve-without-reading',background_request='stock-current-style-default',
                preview_flavor=flavor,size_preferences=sizes,native_geometry=copy.deepcopy(contract['native_geometry']),
                geometry_method='future-operator-edit-mode-only',media=projection,
                native_verified=False,native_size_verified=False,ready_for_native_test=False,operations=[],
                fixture_sha256=digest(fixture),preserved_fixture=copy.deepcopy(fixture),
                media_fixture_sha256=digest(scene),preserved_media_fixture=copy.deepcopy(scene),
                stop_conditions=['separate-native-scope-and-gate-review-required',
                                 'installed-and-running-release-revalidation-required',
                                 'fresh-target-and-preservation-baseline-required',
                                 'mpris-player-artwork-network-and-action-scope-unapproved',
                                 'native-representation-fit-and-opacity-unverified',
                                 'new-instance-identity-and-scoped-recovery-unresolved'])


def validate_media_candidate(value, config, *, contract_bytes):
    """Reject widened settings/actions/claims; validating data grants no authority."""
    if not isinstance(value,dict):
        raise ValueError('media candidate must be an object')
    try:
        expected=build_media_candidate(config,value['preserved_fixture'],value['preserved_media_fixture'],
            plasma_version=value['plasma_version'],contract_bytes=contract_bytes,flavor=value['preview_flavor'])
        if digest(value)!=digest(expected):
            raise ValueError('media candidate differs from reviewed inert intent')
    except (KeyError,TypeError,RecursionError) as error:
        raise ValueError('malformed media candidate') from error
    return value
