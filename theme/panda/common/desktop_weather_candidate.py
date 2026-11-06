"""Pure offline intent for the official Weather applet; no Qt or acquisition.

Reviewed source is a compatibility baseline, never installed-release evidence.
Synthetic samples cannot configure a station, select an ion or grant network use.
"""
import copy
import hashlib
import json
import math

from desktop_layout import build_plan, digest, fields, validate_config, validate_fixture
from palette import resolve_slug

VERSION = '6.8.2'
PLUGIN = 'org.kde.plasma.weather'
CONTRACT_SHA256 = '349aaf7a44ab8573d35a42b674f108627d7603ad1454da2c6292bf7825ee5186'
STALE_SECONDS = 1800  # Synthetic presentation policy, not a KDE freshness guarantee.


def validate_weather_settings(settings, *, plasma_version, contract_bytes):
    """Only empty overrides: never serialize native provider/location/unit settings."""
    if plasma_version != VERSION:
        raise ValueError('weather candidate requires exact upstream Plasma 6.8.2')
    if type(contract_bytes) is not bytes or hashlib.sha256(contract_bytes).hexdigest() != CONTRACT_SHA256:
        raise ValueError('weather source contract differs from reviewed Plasma 6.8.2')
    if type(settings) is not dict or settings:
        raise ValueError('weather native overrides are unsupported; provider and location remain unset')
    return json.loads(contract_bytes)


def validate_weather_fixture(scene):
    """A deliberately non-wire schema with fixed demo identity and no URLs/coordinates."""
    fields(scene, ('schema_version','scope','state','location','condition','temperature',
                   'low','high','temperature_unit','age_seconds'), 'weather fixture')
    if type(scene['schema_version']) is not int or scene['schema_version'] != 1 or scene['scope'] != 'panda-weather-synthetic':
        raise ValueError('explicit synthetic weather schema required')
    state = scene['state']
    if state not in ('unconfigured','offline','missing','stale','available-demo'):
        raise ValueError('unknown synthetic weather state')
    if scene['location'] != ('' if state == 'unconfigured' else 'Synthetic station'):
        raise ValueError('only the fixed synthetic station label is supported; no private locations')
    if scene['condition'] not in ('unknown','clear','cloudy','rain','snow'):
        raise ValueError('synthetic condition enum required; no remote icons or prose')
    values = [scene[key] for key in ('temperature','low','high')]
    unit = scene['temperature_unit']
    if unit not in (None,'C','F') or (any(value is not None for value in values) and unit is None):
        raise ValueError('explicit C/F unit required for each known temperature')
    minimum, maximum = (-148,158) if unit == 'F' else (-100,70)
    for value in values:
        if value is not None and (type(value) not in (int,float) or not minimum <= value <= maximum or not math.isfinite(value)):
            raise ValueError('finite bounded temperature or null required')
    low,high = scene['low'],scene['high']
    if low is not None and high is not None and low > high:
        raise ValueError('weather low exceeds high')
    # Daily forecast extrema need not bound a current observation. They are independent values.
    age = scene['age_seconds']
    if state in ('unconfigured','offline','missing'):
        if any(value is not None for value in values) or age is not None or unit is not None or scene['condition'] != 'unknown':
            raise ValueError('absent/offline weather cannot claim readings or freshness')
    else:
        if type(age) is not int or not 0 <= age <= 604800:
            raise ValueError('bounded synthetic integer age required')
        if (state == 'stale') != (age >= STALE_SECONDS):
            raise ValueError('synthetic weather age disagrees with freshness state')
    return scene


def _weather_projection(scene):
    validate_weather_fixture(scene)
    def display(value):
        return '—' if value is None else f'{value:g} °{scene["temperature_unit"]}'
    return dict(state=scene['state'],data_origin='synthetic-example-only',location=scene['location'],
                condition=scene['condition'],temperature=scene['temperature'],low=scene['low'],high=scene['high'],
                temperature_unit=scene['temperature_unit'],age_seconds=scene['age_seconds'],
                temperature_text=display(scene['temperature']),low_text=display(scene['low']),high_text=display(scene['high']),
                is_stale=scene['state']=='stale',freshness_policy_seconds=STALE_SECONDS,
                attribution='Synthetic example; no provider data acquired',native_status_verified=False)


def build_weather_candidate(config, fixture, scene, *, plasma_version, contract_bytes, flavor='hybrid'):
    """One additive unconfigured applet intent; existing weather remains untouched."""
    validate_config(config)
    validate_fixture(fixture)
    contract = validate_weather_settings({},plasma_version=plasma_version,contract_bytes=contract_bytes)
    projection = _weather_projection(scene)
    flavor = resolve_slug(flavor)
    if fixture['bindings']['weather'] is not None or any(
            applet['containment_id'] == fixture['desktop_id'] and applet['plugin'] == PLUGIN for applet in fixture['applets']):
        raise ValueError('existing or ambiguous desktop weather instance; separate decision required')
    sizes = {name:[profile['width'],profile['heights'][2]] for name,profile in config['profiles'].items()}
    if sizes != {'compact':[288,112],'expanded':[352,144]}:
        raise ValueError('weather size preferences differ from reviewed Panda design targets')
    layout = build_plan(config,fixture,flavor=flavor)
    rect = next(widget['rect'] for widget in layout['widgets'] if widget['role']=='weather')
    return dict(schema_version=1,scope='offline-weather-only-candidate',plasma_version=plasma_version,
                source_contract_sha256=CONTRACT_SHA256,plugin=PLUGIN,desktop_id=fixture['desktop_id'],instance_id=None,
                intent='propose-one-additive-unconfigured-desktop-instance',settings={},selected_provider=None,
                selected_location=None,network_requests=[],operations=[],global_settings='preserve-without-reading',
                background_request='stock-current-style-default',preview_flavor=flavor,size_preferences=sizes,
                output=copy.deepcopy(layout['output']),compact_rect=copy.deepcopy(rect),
                native_geometry=copy.deepcopy(contract['native_geometry']),geometry_method='future-operator-edit-mode-only',
                weather=projection,native_verified=False,native_size_verified=False,ready_for_native_test=False,
                fixture_sha256=digest(fixture),preserved_fixture=copy.deepcopy(fixture),
                weather_fixture_sha256=digest(scene),preserved_weather_fixture=copy.deepcopy(scene),
                stop_conditions=['separate-native-scope-and-gate-review-required',
                                 'installed-and-running-release-revalidation-required',
                                 'fresh-target-and-preservation-baseline-required',
                                 'provider-location-privacy-network-and-cache-owner-approval-required',
                                 'generic-provider-search-and-redirect-scope-unapproved',
                                 'native-status-units-attribution-fit-and-opacity-unverified',
                                 'new-instance-identity-and-scoped-recovery-unresolved'])


def validate_weather_candidate(value, config, *, contract_bytes):
    """Canonical reconstruction rejects additional operations, settings and claims."""
    if not isinstance(value,dict):
        raise ValueError('weather candidate must be an object')
    try:
        expected = build_weather_candidate(config,value['preserved_fixture'],value['preserved_weather_fixture'],
            plasma_version=value['plasma_version'],contract_bytes=contract_bytes,flavor=value['preview_flavor'])
        if digest(value) != digest(expected):
            raise ValueError('weather candidate differs from reviewed inert intent')
    except (KeyError,TypeError,RecursionError) as error:
        raise ValueError('malformed weather candidate') from error
    return value
