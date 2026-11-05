"""D1 clock-only intent, never a native executor or runtime attestation.

Explicit synthetic inputs only. Historical D4C1 clock/media assessment is unchanged.
The schema pin is upstream source identity, not proof of a loaded host plugin.
"""
import copy
import hashlib

from desktop_layout import digest, validate_config, validate_fixture
from palette import resolve_slug

PLASMA_VERSION = "6.8.2"
SCHEMA_SHA256 = "06b085a2451b7197253c4c425c61f150ce89ef2f127c7186eb90039e5ddd7c21"
PLUGIN = "org.kde.plasma.digitalclock"


def _settings():
    # Checked against 6.8.2 main.xml, configAppearance.qml and DigitalClock.qml.
    # use24hFormat is UInt in XML; its three UI indices are 12h/locale/24h.
    return {"Appearance/showDate": True,
            "Appearance/dateFormat": "custom",
            "Appearance/customDateFormat": "dddd, d MMMM",
            "Appearance/use24hFormat": 2,
            "Appearance/dateDisplayFormat": 2,
            "Appearance/showSeconds": 0,
            "Appearance/autoFontAndSize": True}


def validate_clock_settings(settings, *, plasma_version, schema_xml):
    """Accept only this reviewed settings subset on the exact source schema."""
    if plasma_version != PLASMA_VERSION:
        raise ValueError("clock candidate requires exact upstream Plasma 6.8.2")
    if type(schema_xml) is not bytes or hashlib.sha256(schema_xml).hexdigest() != SCHEMA_SHA256:
        raise ValueError("clock schema differs from reviewed Plasma 6.8.2 source")
    expected = _settings()
    if (not isinstance(settings, dict) or set(settings) != set(expected)
            or any(type(settings[k]) is not type(v) or settings[k] != v for k, v in expected.items())):
        raise ValueError("unsupported clock settings, types or enum values")
    return {"Appearance/use24hFormat": "24-Hour",
            "Appearance/dateDisplayFormat": "BelowTime",
            "Appearance/showSeconds": "Never"}


def build_clock_candidate(config, fixture, *, plasma_version, schema_xml, flavor="hybrid"):
    """Propose one absent desktop clock, retaining all input state verbatim.

    Existing/ambiguous clocks require a separate decision, never reuse or allocate
    an ID. Size preferences do not dispatch the five-widget/panel/dock plan.
    """
    validate_config(config)
    validate_fixture(fixture)
    settings = _settings()
    meanings = validate_clock_settings(settings, plasma_version=plasma_version, schema_xml=schema_xml)
    flavor = resolve_slug(flavor)
    clocks = [a for a in fixture["applets"]
              if a["containment_id"] == fixture["desktop_id"] and a["plugin"] == PLUGIN]
    if len(clocks) > 1:
        raise ValueError("ambiguous existing desktop clocks; separate decision required")
    if clocks or fixture["bindings"]["clock"] is not None:
        raise ValueError("existing desktop clock; D1 is additive only")
    sizes = {name: [profile["width"], profile["heights"][0]]
             for name, profile in config["profiles"].items()}
    if sizes != {"compact": [288, 88], "expanded": [352, 104]}:
        raise ValueError("clock design size preferences differ from reviewed D1 targets")
    return dict(schema_version=1, scope="offline-clock-only-candidate",
                plasma_version=plasma_version, schema_sha256=SCHEMA_SHA256,
                native_verified=False, ready_for_native_test=False,
                preview_flavor=flavor, plugin=PLUGIN, desktop_id=fixture["desktop_id"],
                instance_id=None, intent="propose-one-additive-desktop-instance",
                settings=settings, setting_meanings=meanings,
                background_request="StandardBackground-current-style",
                size_preferences=sizes, native_size_verified=False,
                geometry_method="future-operator-edit-mode-only",
                operations=[], fixture_sha256=digest(fixture),
                preserved_fixture=copy.deepcopy(fixture),
                stop_conditions=["separate-native-authorization-required",
                                 "fresh-stable-desktop-baseline-required",
                                 "runtime-plugin-identity-and-output-unverified",
                                 "native-minima-font-metrics-and-opacity-unverified",
                                 "new-instance-id-must-be-observed-not-invented",
                                 "scoped-recovery-prerequisites-unresolved"])


def validate_clock_candidate(value, config, *, schema_xml):
    """Validate inert intent; this does not approve or authorize native writes."""
    if not isinstance(value, dict):
        raise ValueError("clock candidate must be an object")
    try:
        expected = build_clock_candidate(config, value["preserved_fixture"],
                    plasma_version=value["plasma_version"], schema_xml=schema_xml,
                    flavor=value["preview_flavor"])
        # Canonical JSON distinguishes bool/int and rejects non-finite payloads.
        if digest(value) != digest(expected):
            raise ValueError("clock candidate differs from reviewed inert intent")
    except (KeyError, TypeError, RecursionError) as error:
        raise ValueError("malformed clock candidate") from error
    return value
