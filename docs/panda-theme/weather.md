# Official Weather offline candidate

The `weather-candidate` command prepares an inert proposal for one additive
`org.kde.plasma.weather` desktop instance. It implements strict sample-state
validation, temperature labels, preservation and geometry using the existing
desktop fixture/layout APIs. It does not load KDE, discover a location, start a
provider, fetch weather, create an applet or write configuration. Its null
instance ID is deliberately unallocated. There is no custom weather backend.

The approved Panda specification requires stock weather infrastructure and a
shared layout across flavors. This candidate follows that direction within the
authorized offline scope. It does not complete the specification's live weather
or visual-verification criteria.

## Reviewed release and source contract

The baseline is upstream Plasma **6.8.2**, KDE `kdeplasma-addons` tag `v6.8.2`,
commit `d858e942d3bfd4b1478cec829373cf89a3625cb7`.
[The pinned contract](../../theme/panda/common/desktop/weather-6.8.2.json) records
source paths, Git blobs, byte counts and SHA-256 values for the applet's config,
presentation, controller and NOAA adapter. The candidate validates the exact
contract bytes and rejects every other version claim and native override.
These bytes identify the reviewed source, not a verified installed package.

In this release, Weather uses native `ForecastControl`, shared `ForecastData`
and ions under `plasma/weather_ions`. It is not the historical weather
dataengine. [KDE's applet build definition](https://github.com/KDE/kdeplasma-addons/blob/d858e942d3bfd4b1478cec829373cf89a3625cb7/applets/weather/CMakeLists.txt)
and [NOAA plugin definition](https://github.com/KDE/kdeplasma-addons/blob/d858e942d3bfd4b1478cec829373cf89a3625cb7/applets/weather/ions/noaa/CMakeLists.txt)
establish those identities. `kdeplasma-addons` is already in the desktop package
catalog; this command does not inspect or install packages.

The [native schema](https://github.com/KDE/kdeplasma-addons/blob/d858e942d3bfd4b1478cec829373cf89a3625cb7/applets/weather/main.xml)
has `WeatherStation` provider, placeInfo, placeDisplayName, legacy source and
updateInterval entries; `Appearance` toggles; and `Units` selectors. Provider,
placeInfo and source default to empty, and the interval defaults to 30 minutes.
Unit entries have no explicit XML default; QML falls back to KDE's default unit
models. The candidate supplies **no overrides** (`settings: {}`), so it cannot
copy private settings or silently choose a unit, provider or station. This is
an intent for a future fresh unconfigured instance, never a reset recipe for an
existing one.

## Provider, location and network policy

The default is **unconfigured, no selected provider, no selected location and no
network**. The proposal has empty `network_requests` and `operations` even when
its presentation sample says `available-demo`. Provider selection is a separate
future owner decision. Never infer the owner's location from timezone, host,
IP address, saved weather, locale or these synthetic examples.

Only KDE's official **NOAA / National Weather Service** adapter (`noaa`) has been
statically reviewed here. It is a possible future choice for a station and
forecast grid supported by the US NWS, not a worldwide provider or an assumed
fit for this owner. Station matching uses the bundled
`plasma/weather/noaa_station_list.xml`. A station's presence alone does not
establish forecast coverage, freshness or service availability. No key is used
by the reviewed adapter. [NWS documentation](https://www.weather.gov/documentation/services-web-api)
currently requires an application User-Agent and mentions possible future API
key authentication. Recheck authentication, terms, limits and coverage before
any future use; no credentials belong in this repository.

The [reviewed NOAA implementation](https://github.com/KDE/kdeplasma-addons/blob/d858e942d3bfd4b1478cec829373cf89a3625cb7/applets/weather/ions/noaa/ion_noaa.cpp)
would use these request families after a configured station is selected:

| Purpose | Static request template |
| --- | --- |
| Current observation | `https://api.weather.gov/stations/{stationID}/observations/latest` |
| Grid lookup | `https://api.weather.gov/points/{stationLatitude},{stationLongitude}` |
| Forecast | URL returned by the points response, normally `https://api.weather.gov/gridpoints/{office}/{x},{y}/forecast` |
| County alerts | `https://api.weather.gov/alerts/active?zone={countyID}` |

These are documentation, never executable candidate requests. Station ID,
station coordinates and county zone reveal the chosen area; the provider and
network infrastructure also receive ordinary connection metadata such as the
public IP and headers. Debug output in KDE can include station names, queries,
coordinates and URLs. Treat future config, backups and logs as location-private;
retain them locally with restricted access, and redact before sharing.

Two limits prevent treating this review as network approval:

- KDE's general location search creates eligible providers and fans the search
  string out to them. The NOAA-only source review does not authorize typing a
  real location into that generic UI or activating other adapters.
- NOAA's adapter uses KIO transfers, follows a response-provided forecast URL
  and does not impose a hostname allowlist in the reviewed code. Redirects,
  response URLs, KIO behavior and the actual request headers require a separate
  future review before claiming a restricted endpoint boundary.

Selecting a configured location initiates a fetch. Setting updateInterval to
zero only stops the repeating timer; it is **not** a no-network switch. Do not
use this schema as an activation script. No provider action is supplied now.

## Cache, attribution and truthful sample states

Panda creates no weather cache, persisted data, background worker or retry loop.
KDE shares in-memory forecast objects by provider/place and uses their update
time for refresh decisions; NOAA requests use `KIO::Reload`. This source review
does not attest KIO's disk-cache retention, redirects, system proxy or native
error handling. Future activation must review those settings and a scoped
cleanup/backup policy without deleting unrelated user caches.

The NOAA adapter supplies Fahrenheit observations and a NOAA/NWS credit line;
KDE converts through its unit models and presents provider credit in its full
representation. Preserve that credit and any applicable provider attribution
when actual data is eventually used. The offline candidate labels its output
`Synthetic example; no provider data acquired`, so it does not imply that NOAA
supplied the samples. It accepts no remote icon or attribution URL and opens
no external link.

The explicit schema scope is `panda-weather-synthetic`. It accepts only the
fixed label `Synthetic station` (empty for unconfigured), an enumerated
condition, finite bounded C/F temperatures or null, and integer age in seconds.
It accepts no real place, coordinate, provider ID, request URL, acquisition
timestamp or API response. Zero is a valid temperature. Missing current/low/
high values each remain null and display `—`; no values or conversions are
invented. Daily low/high need not bound a current observation, but low cannot
exceed high when both are known.

| Sample | Readings and freshness |
| --- | --- |
| `unconfigured` | No location, unit, readings or age |
| `offline` | Fixed demo label; no readings, unit or age |
| `missing` | Fixed demo label; unknown readings, unit and age |
| `stale` | Explicit synthetic age at least 1800 seconds; any retained values remain visibly stale |
| `available-demo` | Explicit synthetic age below 1800 seconds; partial readings allowed |

The 1800-second boundary is a deterministic offline presentation rule, not a
claim about KDE status or a provider service guarantee. In particular, KDE's
reviewed `ForecastControl::onWeatherDataUpdated` sets `Normal` after its error
branch; synthetic states do not prove native timeout/stale behavior. Native
zero-value tooltip visibility and missing-unit handling also require visual
validation against the eventual installed release.

## Offline use and preservation

From the repository root, this Fish-compatible command prints JSON only:

```fish
python -B theme/panda/common/desktop_cli.py weather-candidate \
    --fixture tests/fixtures/desktop/assessment/sanitized-shape.json \
    --plasma-version 6.8.2 \
    --weather-contract theme/panda/common/desktop/weather-6.8.2.json \
    --weather-fixture tests/fixtures/desktop/weather/unconfigured.json \
    --flavor hybrid
```

Use explicit synthetic desktop fixtures only. The output deep-copies their
entire preserved state; do not supply real private configuration and publish
the resulting JSON. Unknown/duplicate JSON fields, nonfinite numbers, symlink
or nonregular file inputs and mixed candidate inputs are refused. No `--apply`,
provider selection, layout override or live acquisition option exists.

An existing bound or ambiguous desktop Weather instance refuses addition;
the command does not reset or reconcile it. Panel Weather, nested tray Weather,
their opaque private settings, panels, pins, other widgets, desktop count and
all fixture state are preserved. No global config is read. New instance
identity and scoped recovery remain unresolved until a separately approved
fresh target baseline exists.

All five canonical flavors use the same compact geometry from `build_plan`,
including its FHD/QHD and 1/1.25/1.5 scale checks. Compact/expanded logical size
preferences are 288×112 / 352×144. They are **not verified native minima**:
KDE's full width depends on implicit content within 10–25 grid units and its
minimum height is at least 10 grid units. Compact dimensions depend on icon/
text representation. No native size or anchoring setter is emitted. A future
operator must verify fit, opaque styling, attribution, units, keyboard/focus
behavior and all five flavors in Edit Mode. The candidate does not generate a
new preview framework or claim live-rendered results.

Before any AMD-host trial, revalidate the actual installed/running Plasma and
addons versions, source/config/provider contracts, plugin availability, native
state behavior, provider choice and location/network/cache policy. A future
release, patched package or changed provider must be reviewed afresh. This
work does not grant activation authority or alter the Helios safety contract.
