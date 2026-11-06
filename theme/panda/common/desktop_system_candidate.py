"""Pure CPU/RAM candidate projection; never load KDE faces or query sensors.

The pinned release describes source semantics, not an installed host. Native
unknown/stale and history behavior remain explicit trial blockers.
"""
import copy
import hashlib
import json
import math

from desktop_layout import build_plan, digest, fields, integer, validate_config, validate_fixture

VERSION = '6.8.2'
CONTRACT_SHA256 = 'e9d842f6678a6231b202cc0facc44114abbf0f496ca4e884f0291d4c2d76a110'
MAX_TIME = 2**53 - 1


def _contract(plasma_version, contract_bytes):
    if plasma_version != VERSION:
        raise ValueError('system candidate requires exact upstream Plasma 6.8.2')
    if type(contract_bytes) is not bytes or hashlib.sha256(contract_bytes).hexdigest() != CONTRACT_SHA256:
        raise ValueError('system source contract differs from reviewed Plasma 6.8.2')
    return json.loads(contract_bytes)


def validate_system_settings(role, settings, *, plasma_version, contract_bytes):
    """Accept only this source-reviewed face/settings subset, with exact types."""
    contract = _contract(plasma_version, contract_bytes)
    if role not in ('cpu', 'ram') or type(settings) is not dict:
        raise ValueError('unsupported system monitor role or settings')
    if digest(settings) != digest(contract['settings'][role]):
        raise ValueError('unsupported system settings, fields, types or values')
    return settings


def _number(value, unit):
    if unit == 'byte':
        integer(value, 'memory bytes', 0, MAX_TIME)
    elif type(value) not in (int, float) or not 0 <= value <= 100 or not math.isfinite(value):
        raise ValueError('CPU utilization must be finite percent 0..100')


def _reading(value, unit, now):
    fields(value, ('state', 'value', 'unit', 'sampled_at_ms'), 'sensor reading')
    if value['state'] not in ('valid', 'stale', 'missing', 'unknown'):
        raise ValueError('unknown sensor state')
    if value['unit'] not in (unit, None):
        raise ValueError('unexpected sensor unit')
    if value['state'] in ('missing', 'unknown'):
        if value['value'] is not None or value['sampled_at_ms'] is not None:
            raise ValueError('absent sensor cannot claim a reading or sample time')
    else:
        _number(value['value'], unit)
        integer(value['sampled_at_ms'], 'sample time', 0, now)


def _project_reading(value, scene):
    state = value['state']
    age = None if value['sampled_at_ms'] is None else scene['now_ms'] - value['sampled_at_ms']
    if state == 'valid' and age > scene['stale_after_ms']:
        state = 'stale'
    if state == 'valid' and value['unit'] is None:
        state = 'unknown-unit'
    return dict(state=state, value=value['value'] if state == 'valid' else None,
                unit=value['unit'], sampled_at_ms=value['sampled_at_ms'], age_ms=age)


def validate_system_fixture(scene):
    """Strict typed synthetic readings; null means unknown, never zero.

    Time is explicit synthetic milliseconds, not wall clock. A fixed one-second
    fixture cadence and three-second freshness limit are Panda projection policy,
    not claims about ksystemstats scheduling or native face missing-data handling.
    """
    fields(scene, ('schema_version', 'scope', 'now_ms', 'sample_interval_ms',
                   'stale_after_ms', 'cpu', 'ram'), 'system fixture')
    if type(scene['schema_version']) is not int or scene['schema_version'] != 1 or scene['scope'] != 'panda-system-synthetic':
        raise ValueError('explicit synthetic system schema required')
    integer(scene['now_ms'], 'synthetic time', 0, MAX_TIME)
    integer(scene['sample_interval_ms'], 'fixture sample interval', 1000, 1000)
    integer(scene['stale_after_ms'], 'fixture freshness threshold', 3000, 3000)
    fields(scene['cpu'], ('usage', 'history'), 'CPU fixture')
    fields(scene['ram'], ('used', 'available', 'total'), 'RAM fixture')
    _reading(scene['cpu']['usage'], 'percent', scene['now_ms'])
    for value in scene['ram'].values():
        _reading(value, 'byte', scene['now_ms'])
    history = scene['cpu']['history']
    if type(history) is not list or len(history) > 60:
        raise ValueError('CPU history must have at most 60 synthetic slots')
    previous = -1
    for point in history:
        fields(point, ('at_ms', 'value'), 'CPU history point')
        integer(point['at_ms'], 'history time', max(0, scene['now_ms'] - 59000), scene['now_ms'])
        if point['at_ms'] <= previous or (scene['now_ms'] - point['at_ms']) % scene['sample_interval_ms']:
            raise ValueError('history must be ordered unique cadence-aligned samples')
        if point['value'] is not None:
            _number(point['value'], 'percent')
        previous = point['at_ms']
    ram = {key: _project_reading(value, scene) for key, value in scene['ram'].items()}
    total = ram['total']
    for key in ('used', 'available'):
        value = ram[key]
        if (value['value'] is not None and total['value'] is not None and total['value'] > 0
                and value['sampled_at_ms'] == total['sampled_at_ms'] and value['value'] > total['value']):
            raise ValueError('memory reading exceeds synchronized total')
    if (all(value['value'] is not None for value in ram.values()) and total['value'] > 0
            and len({value['sampled_at_ms'] for value in ram.values()}) == 1
            and ram['used']['value'] + ram['available']['value'] != total['value']):
        raise ValueError('Linux used + available must equal synchronized total')
    return scene


def project_system_fixture(scene):
    """Human-reviewable current values and disconnected CPU history segments."""
    validate_system_fixture(scene)
    cpu = _project_reading(scene['cpu']['usage'], scene)
    points = scene['cpu']['history']
    history = []
    if points:
        values = {point['at_ms']: point['value'] for point in points}
        # Omitted slots and trailing gaps stay null. Never interpolate or hold.
        history = [dict(at_ms=at, value=values.get(at) if scene['cpu']['usage']['unit'] == 'percent' else None)
                   for at in range(points[0]['at_ms'], scene['now_ms'] + 1, scene['sample_interval_ms'])]
    segments, current = [], []
    for point in history:
        if point['value'] is None:
            if current:
                segments.append(current)
                current = []
        else:
            current.append(copy.deepcopy(point))
    if current:
        segments.append(current)
    ram = {key: _project_reading(value, scene) for key, value in scene['ram'].items()}
    total = ram['total']
    def percent(key):
        value = ram[key]
        if (value['value'] is None or total['value'] is None or total['value'] <= 0
                or value['sampled_at_ms'] != total['sampled_at_ms']):
            return None
        return value['value'] / total['value'] * 100
    used_percent, available_percent = percent('used'), percent('available')
    return dict(cpu=dict(usage=cpu, fill_fraction=None if cpu['value'] is None else cpu['value'] / 100,
                         history=history, history_segments=segments),
                ram=dict(**ram, used_percent=used_percent, available_percent=available_percent,
                         fill_fraction=None if used_percent is None else used_percent / 100))


def build_system_candidate(config, fixture, scene, *, plasma_version, contract_bytes,
                           flavor='hybrid', resolution=None, scale=None, presentation='compact'):
    """Two absent desktop applets; shared geometry only, no panel/dock intents.

    Full layout fitting is delegated to the established API. Its unrelated
    widget/panel/dock action proposals are discarded, never dispatched.
    """
    validate_config(config)
    validate_fixture(fixture)
    contract = _contract(plasma_version, contract_bytes)
    readings = project_system_fixture(scene)
    for role, plugin in contract['plugins'].items():
        instances = [a for a in fixture['applets']
                     if a['containment_id'] == fixture['desktop_id'] and a['plugin'] == plugin]
        if instances or fixture['bindings'][role] is not None:
            raise ValueError('existing or ambiguous desktop ' + role + ' instance; additive candidate refused')
        if config['widgets'][role]['face'] != contract['settings'][role]['Appearance/chartFace']:
            raise ValueError('system candidate requires reviewed CPU linechart and RAM horizontalbars')
    sizes = {name: [[p['width'], p['heights'][3]], [p['width'], p['heights'][4]]]
             for name, p in config['profiles'].items()}
    if sizes != {'compact': [[288,96],[288,96]], 'expanded': [[352,120],[352,120]]}:
        raise ValueError('system size preferences differ from reviewed Panda targets')
    layout = build_plan(config, fixture, flavor=flavor, resolution=resolution, scale=scale, presentation=presentation)
    widgets = []
    for role in ('cpu', 'ram'):
        rect = next(w['rect'] for w in layout['widgets'] if w['role'] == role)
        settings = copy.deepcopy(contract['settings'][role])
        validate_system_settings(role, settings, plasma_version=plasma_version, contract_bytes=contract_bytes)
        widgets.append(dict(role=role, plugin=contract['plugins'][role], desktop_id=fixture['desktop_id'],
                            instance_id=None, intent='propose-one-additive-desktop-instance',
                            settings=settings, rect=copy.deepcopy(rect), native_size_verified=False))
    return dict(schema_version=1, scope='offline-system-only-candidate', plasma_version=plasma_version,
                source_contract_sha256=CONTRACT_SHA256, preview_flavor=layout['flavor'],
                palette=copy.deepcopy(layout['palette']), output=copy.deepcopy(layout['output']),
                presentation=presentation, widgets=widgets, readings=readings,
                background_request='stock-default-configurable-current-style',
                native_geometry=copy.deepcopy(contract['native_geometry']),
                geometry_method='future-operator-edit-mode-only',
                settings_semantics=copy.deepcopy(contract['storage']),
                requirements=copy.deepcopy(contract['packages']),
                package_presence='synthetic inventory only',
                missing_packages=sorted(set(contract['packages']) - set(fixture['installed_packages'])),
                native_verified=False, ready_for_native_test=False, operations=[],
                fixture_sha256=digest(fixture), preserved_fixture=copy.deepcopy(fixture),
                system_fixture_sha256=digest(scene), preserved_system_fixture=copy.deepcopy(scene),
                stop_conditions=['separate-native-scope-and-authorization-required',
                                 'installed-and-running-release-revalidation-required',
                                 'fresh-identity-and-preservation-baseline-required',
                                 'provider-activation-and-sensor-scope-unapproved',
                                 'native-unknown-stale-history-fidelity-unverified',
                                 'native-font-fit-and-opacity-unverified',
                                 'new-instance-identity-and-scoped-recovery-unresolved'])


def validate_system_candidate(value, config, *, contract_bytes):
    """Reject any widened or altered intent; validation grants no native authority."""
    if type(value) is not dict:
        raise ValueError('system candidate must be an object')
    try:
        expected = build_system_candidate(config, value['preserved_fixture'], value['preserved_system_fixture'],
            plasma_version=value['plasma_version'], contract_bytes=contract_bytes,
            flavor=value['preview_flavor'], scale=value['output']['scale'],
            resolution=next((name for name, size in (('fhd',[1920,1080]),('qhd',[2560,1440]))
                             if size == value['output']['physical_size']), None),
            presentation=value['presentation'])
        if digest(value) != digest(expected):
            raise ValueError('system candidate differs from reviewed inert intent')
    except (KeyError, TypeError, RecursionError) as error:
        raise ValueError('malformed system candidate') from error
    return value
