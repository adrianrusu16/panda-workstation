# Offline CPU and RAM candidates

Sprint 1 adds a concrete, inert proposal for the official desktop CPU and Memory
applets. `desktop_system_candidate.py` uses the existing layout, fixture, palette,
package inventory and native-face contracts. It never reads `/proc`, `/sys`, a
sensor, Qt, D-Bus, package history or host Plasma configuration. It starts no
service, allocates no IDs, writes no configuration and installs no packages. Output is
JSON on stdout. This is source implementation and synthetic verification;
native functionality and visual fit remain unverified.

## Reproduce the proposal

From the repository root, with Python 3.11 or newer:

```fish
python -B theme/panda/common/desktop_cli.py system-candidate \
    --fixture tests/fixtures/desktop/assessment/sanitized-shape.json \
    --system-fixture tests/fixtures/desktop/system/valid.json \
    --system-contract theme/panda/common/desktop/system-6.8.2.json \
    --plasma-version 6.8.2 --flavor hybrid
```

Choose `missing.json`, `stale.json` or `unknown-total.json` for the other bundled
scenarios. `--resolution fhd|qhd`, `--scale 1|1.25|1.5`, and
`--presentation compact|expanded` use the established layout fit checks. FHD at
1.5 with expanded presentation is refused because the whole shared stack does
not fit. Preferences are 288×96 logical pixels per monitor in compact and
352×120 in expanded. Native planar mode uses the full face; “compact” here names
the Panda layout profile, not Plasma's panel representation.

The output contains only two additive desktop proposals, with null instance IDs,
typed proposed settings, CPU/RAM presentation readings, palette and geometry.
It preserves the complete original fixture and has an empty operations list.
The five canonical flavors share structure, IDs, settings, readings and geometry;
only palette/flavor changes. Panel/tray instances are neither reused nor altered.
Any existing desktop CPU/RAM instance, explicit binding or ambiguous identity
refuses the whole candidate. Existing widgets require a separate preservation
decision. The full-layout API is used for fitting; its clock/media/weather,
panel and dock proposals are discarded.

## Pinned official source contract

`theme/panda/common/desktop/system-6.8.2.json` is a required runtime/test contract
artifact. Its exact bytes are SHA-256 pinned in the module, including the reviewed
setting subset and source manifest. Wrong releases, unknown settings, enum/type
changes, extra candidate fields, modified claims and altered source contracts
are refused. This pin does not attest an installed or loaded plugin. A future
AMD host must revalidate its installed and running releases and provider
semantics; do not force 6.8.2 settings onto another version.

| Component | Exact reviewed release commit | Role |
| --- | --- | --- |
| plasma-workspace v6.8.2 | `30beb0095873364c6b34ebcfd292ecafd4db7f61` | Official CPU/Memory plugin install names, presets, applet initialization and representations |
| libksysguard v6.8.2 | `41f7f3cda360fff62c2d55d01427f2f5e0abc2e7` | Effective controller settings, native linechart/horizontalbars faces, metadata, units, percentage sensor and D-Bus interface |
| ksystemstats v6.8.2 | `3207406db3a0d73dd0b7917bb53763aece8f9e6e` | Linux CPU utilization and physical-memory provider meaning |

Each relevant file has a content hash and immutable source link in the contract.
The generic applet XML is insufficient: the
[controller](https://github.com/KDE/libksysguard/blob/41f7f3cda360fff62c2d55d01427f2f5e0abc2e7/faces/SensorFaceController.cpp)
reads `Appearance/chartFace`, `title`, `showTitle`, `updateRateLimit`, and
`Sensors/totalSensors`, `highPrioritySensorIds`, `lowPrioritySensorIds`.
The latter are compact JSON strings in KConfig; this inert proposal represents
them as typed arrays. `SensorColors`, `SensorLabels` and unrelated settings are
left to native defaults/theme inheritance. `updateRateLimit=1000` requests a
one-second throttle; it guarantees neither provider cadence nor freshness.

Face-specific XML entries are under `<face-ID>/General/<key>` relative to the
applet config group. The controller passes the face group to KConfigLoader,
whose XML group parser nests `General` below it. The supplemental
[KConfig v6.20.0 implementation](https://github.com/KDE/kconfig/blob/v6.20.0/src/gui/kconfigloader.cpp)
is separately content-pinned in the contract as evidence for nesting, not as an
installed-framework version assertion. Revalidate the installed loader before
any native write. The proposal is not a serialized configuration installer.

CPU selects `org.kde.ksysguard.linechart` with `cpu/all/usage`, fixed 0–100 Y
range, a 60-second history request and smoothing disabled. RAM selects
`org.kde.ksysguard.horizontalbars` with `memory/physical/used`, plus available
(`memory/physical/free`) and total as text-only sensors; the stock total sensor
is `memory/physical/usedPercent`. Both stock presets initially select piechart;
the Panda face selection is an explicit proposed customization.

[SystemMonitor::init](https://github.com/KDE/plasma-workspace/blob/30beb0095873364c6b34ebcfd292ecafd4db7f61/applets/systemmonitor/systemmonitor/systemmonitor.cpp)
writes `CurrentPreset` and loads the stock preset. Preseeding a new applet before
initialization can therefore be overwritten. Future native configuration must
occur after initialization, preferably through the reviewed settings UI; this
candidate never writes `CurrentPreset` or instantiates a controller. Controller
construction/resolution and sensor subscriptions can contact the
`org.kde.ksystemstats1` session-bus service at `/org/kde/ksystemstats1`.
They are outside offline scope. The standalone `plasma-systemmonitor` application
is not a widget prerequisite; its optional launch action is not exercised here.

## Synthetic reading rules

Inputs have exact fields and explicit synthetic milliseconds. The one-second
cadence and three-second freshness threshold are fixed Panda fixture policy,
not KDE timeout guarantees. A sample is stale when its age is **greater than**
3000 ms or its explicit state is `stale`. `missing` and `unknown` require null
value/time. A null unit yields `unknown-unit`; other unreviewed units are refused.
Stale or unavailable current readings have null displayed value/fill. Valid zero
remains zero. Booleans are not numbers; non-finite values, negative bytes,
future times and utilization outside 0–100 are refused.

The provider's
[aggregate CPU usage](https://github.com/KDE/ksystemstats/blob/3207406db3a0d73dd0b7917bb53763aece8f9e6e/plugins/cpu/usagecomputer.cpp)
is a percentage of total tick deltas using system+user as the busy numerator,
excluding iowait. It is already normalized to 0–100; never divide again by core
count, confuse it with load average or relabel it as MHz. Current utilization
fill is usage/100. Temperature/frequency and hardware-specific sensor discovery
are not part of this slice.

CPU history accepts at most 60 ordered, unique, cadence-aligned points within
the last 59 seconds. Explicit nulls, omitted intervals and trailing gaps remain
null. Separate segments never interpolate or repeat a previous sample across
a gap; empty history stays empty. History values do not manufacture a current
reading. A missing current sample can coexist with older valid history.

The Linux
[memory backend](https://github.com/KDE/ksystemstats/blob/3207406db3a0d73dd0b7917bb53763aece8f9e6e/plugins/memory/linuxbackend.cpp)
converts kernel kB counters to bytes with ×1024. `used = MemTotal - MemAvailable`;
the sensor named `free` exposes **MemAvailable**, not raw MemFree. Application,
cache and buffers are separate concepts, and swap is not physical memory. This
model accepts integer bytes for used/available/total, without reading counters.
For synchronized fresh positive totals it requires each numerator ≤ total and,
when all three are known, used+available=total. Unknown components are not derived
from other values. Percentages require fresh known byte units, a positive known
total and matching timestamps for numerator/denominator. Each percentage can be
independently unknown. Zero, stale or unknown totals never produce a fill or a
percentage; absolute valid byte values remain available for presentation.

## Native trial boundary and remaining gaps

No native trial is authorized by generating or validating this candidate.
`native_verified` and `ready_for_native_test` remain false. In a separately
approved manual trial:

1. Verify installed/running Plasma, libksysguard, ksystemstats and framework
   versions against the contract. Confirm plugin/face availability without
   silently starting providers. Stop on a different release or missing package.
2. Capture an exact target-output, containment, panel/tray, wallpaper, launcher,
   desktop-count and existing-widget identity baseline plus scoped recovery
   evidence. Preserve any existing CPU/RAM widgets rather than applying this
   additive-only candidate to them.
3. Obtain explicit provider/sensor activation and native creation/configuration
   authorization. Manually create one official CPU and one Memory desktop widget,
   observe their actual IDs after stock preset initialization, then select the
   reviewed native faces/settings. Do not invent IDs, reparent tray/panel widgets,
   write unrelated groups or call unsupported geometry setters.
4. Verify exact intended sensor IDs and units, current values, available-versus-
   raw-free meaning, zero/unknown denominator behavior, sampling/history and
   provider absence/restart behavior. Reconcile actual readings against trusted
   local reference values only within that later approved scope.
5. Check full-face fit, title/legend readability, scaling, opaque surfaces, theme
   inheritance and settings persistence across the five flavors. Use manual Edit
   Mode for geometry; source minima are eight grid units in width, a three-grid-
   unit minimum for the linechart plot, and dynamic whole-widget height/padding.
   Source constraints do not prove 96/120-pixel card fit.
6. Recheck every preservation baseline and recover only newly created/changed
   instances if verification fails. Recovery prerequisites and any recovery-gate
   review remain unresolved; this module does not weaken them.

Two source-level limits need particular attention. The stock
[RAM bar](https://github.com/KDE/libksysguard/blob/41f7f3cda360fff62c2d55d01427f2f5e0abc2e7/faces/facepackages/horizontalbars/contents/ui/Bar.qml)
uses a zero fallback for a null sensor value, and
[PercentageSensor](https://github.com/KDE/libksysguard/blob/41f7f3cda360fff62c2d55d01427f2f5e0abc2e7/systemstats/AggregateSensor.cpp)
returns zero for nonpositive maximum. These do not establish truthful native
unknown/fill behavior. The stock
[linechart](https://github.com/KDE/libksysguard/blob/41f7f3cda360fff62c2d55d01427f2f5e0abc2e7/faces/facepackages/linechart/contents/ui/LineChart.qml)
samples `HistoryProxySource` by interval with `FillFromEnd`; synthetic disconnected
segments do not demonstrate native missing/stale gap rendering. Do not claim
those requirements satisfied until a later native trial proves them or a
separately reviewed supported solution resolves them. No custom sensor backend
or extra monitoring service is introduced here.

This CPU/RAM slice intentionally leaves disk/kernel/GPU-profile dashboard
coverage for later work, and does not authorize weather, compositor, boot/GPU,
Android, Audit Lab, Host Canary or W2–W6 changes.
