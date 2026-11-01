# Desktop compatibility and preservation

These are pinned static contracts, not fresh host observations or native-test
approval. The baseline is Plasma 6.7.5; the source comparison covers Plasma 6.8.1,
Qt 6.12.0 and Kirigami/KSvg 6.31.0. Installed package versions do not prove loaded
session versions or distribution-patch parity.

Immutable source provenance is retained in [the 6.7.5 receipts](d4c1/kde-source-references.json)
and [the 6.8.1 comparison receipts](d4c2/source-references.json). They record
commits, trees, Git blobs, SHA256 and lengths. The latter covers 60 blobs and
20 baseline pairs (13 byte-identical, seven changed). Missing guessed source
paths do not establish removal of an API. Rolling documentation cannot override
the pinned implementation.

## Saved-file assessment limitations

The qualified 2026-10-26/27 saved-file inventory found one folder-view desktop,
desktop count 1 and one bottom panel, with seven ordered panel slots and 16
nested tray applets. No desktop clock/media/CPU/RAM instance was found; the
existing panel clock and nested tray weather are ineligible for repurposing.
Task launcher data was not serialized: runtime ordered pins are **unknown, not
zero**. Synthetic two-pin/seven-slot samples are not a host inventory.
Saved FHD/scale-1 output facts are provisional, not active topology.

All seven selected configuration files retained their bytes; only six retained
complete whole-assessment metadata receipts. `kwinoutputconfig.json` mtime/ctime
drifted between stable individual reads, with no established actor. Collection
stopped; identical bytes do not close the preservation/freshness failure.
The private earlier candidate and [public synthetic candidate](d4c1/clock-media-candidate.json)
are not executable host plans or recovery backups. Require a newly authorized
stable baseline; do not reopen historical D3B1A evidence.

`desktop_assessment.read_preserved()` requires bounded regular singly linked
files, safely owned non-symlink ancestors and O_NOATIME; there is no ordinary-read,
timestamp-reset or permission-workaround fallback. It checks parent bindings,
device/inode, owner/mode/link count, size, nanosecond times, SHA256 and supported
xattrs (including ACL xattrs when exposed). Filesystem flags, other ACL schemes
and unsaved in-memory state are not covered. The KConfig subset does not expand
expressions/flags/includes. Flagged/escaped identities refuse classification.

The prior selected file allowlist was plasma-org.kde.plasma.desktop-appletsrc,
plasmashellrc, kwinrc, kdeglobals, plasmarc, kactivitymanagerdrc and
kwinoutputconfig.json. That list does not authorize new reads. Raw configs were
not saved. Private IDs/order/output identifiers and receipts remain private;
inventory receipts cannot restore the configuration. Root-owned native-font
reading was refused by O_NOATIME; native font resolution remains unknown.

## Evidence and property map

Every upstream source below is pinned to an immutable commit and Git blob in
[d4c1/kde-source-references.json](d4c1/kde-source-references.json). Paths are
relative to the named KDE repository at v6.7.5. Raw source stays in private local
evidence. A source-supported property is not proof of native sizing or fidelity.

| Role / official package | Plugin | Exact baseline configuration surface | Representation and native questions |
| --- | --- | --- | --- |
| Clock / plasma-workspace | org.kde.plasma.digitalclock | Appearance: showDate, dateFormat, customDateFormat, autoFontAndSize, fontFamily, fontSize, boldText, italicText, fontWeight, fontStyleName, showSeconds, use24hFormat, dateDisplayFormat; preserve all timezone/calendar fields | main.qml prefers compact clock; full view is the calendar. “Expanded” Panda geometry must not force the calendar. Defaults request ShadowBackground with ConfigurableBackground. |
| Media / plasma-workspace | org.kde.plasma.mediacontroller | No per-instance main.xml in the inspected package. Native MPRIS model supplies track, artist, artwork, status and control capabilities. GlobalConfig reads General/VolumeStep in plasmaparc; **do not change this global audio setting** | Full minimum 14×10 Kirigami grid units; preferred 20×20. Compact view adapts to panel/desktop/tray and absent players. D4B 288×120 does not prove full controls fit. |
| Weather / kdeplasma-addons | org.kde.plasma.weather | WeatherStation: updateInterval, placeDisplayName, provider, placeInfo, source. Appearance: showTemperatureInCompactMode, showTemperatureInBadge, showTemperatureInTooltip, showWindInTooltip, showPressureInTooltip, showHumidityInTooltip. Units: temperatureUnit, pressureUnit, speedUnit, visibilityUnit | Default configurable background; panel icons can be symbolic. Forecast/provider state drives configuration/connection status. Provider updates may write station information; loading the widget is outside offline scope. |
| CPU / plasma-workspace, face from libksysguard | org.kde.plasma.systemmonitor.cpu | Generic monitor Appearance/title, chartFace; Sensors/totalSensor, sensorIds, sensorColors, textOnlySensorIds. CPU preset names cpu/all/usage, cpu/all/cpuCount, cpu/all/coreCount | Stock preset is piechart. Panda default remains org.kde.ksysguard.linechart. Sensor presence, units/history, supported minima and provider activation remain unobserved. |
| RAM / plasma-workspace, face from libksysguard | org.kde.plasma.systemmonitor.memory | Same monitor schema. Preset names memory/physical/used, memory/physical/usedPercent and memory/physical/total | Stock preset is piechart. Panda default remains org.kde.ksysguard.horizontalbars. Verify byte/percent semantics and unknown totals before trusting fills. |

Clock evidence: plasma-workspace/applets/digital-clock/{main.xml,main.qml,
configAppearance.qml}. Media evidence: applets/mediacontroller/{main.qml,
CompactRepresentation.qml,ExpandedRepresentation.qml,globalconfig.cpp,
globalconfig.h}. Weather evidence: kdeplasma-addons/applets/weather/{main.xml,
qml/main.qml}. Monitor evidence: plasma-workspace/applets/systemmonitor/
systemmonitor/package/contents/{config/main.xml,ui/main.qml,
ui/FullRepresentation.qml} and cpu/memory preset faceproperties.

The clock UI binds the 24-hour choice to index 2 and below-time date placement
to index 2. showSeconds index 0 is never. Font size is a point-valued UI setting;
do not copy D4B logical-pixel sizes directly. These are 6.7.5 facts, not a promise
about the currently installed or loaded version.

Both approved monitor faces remain independently selectable. The allowlist is
unchanged: org.kde.ksysguard.linechart and org.kde.ksysguard.horizontalbars.
No face is instantiated; no sensor object/backend is queried.

## Shared visuals and exact useful native properties

| Visual target | Supported mechanism / proposed property | Limit |
| --- | --- | --- |
| Opaque desktop clock frame | WorkspaceScripting Widget.userBackgroundHints = StandardBackground; libplasma stores Configuration/UserBackgroundHints and honors it only for configurable applets | Frame opacity, radius, margins and inheritance depend on the actual Plasma Style. No arbitrary CSS/card stylesheet. |
| Card colors | Inherited Plasma/Kirigami semantic theme colors; supported color-scheme/Plasma Style interfaces | No verified per-card independent color or exact 12-pixel radius setting for all five applets. No theme switching in D4C1 or first candidate. |
| Typography | Clock Appearance font controls; other widgets use native labels/fonts | Global changes would affect unrelated UI. Current active Qt font and line metrics remain unknown. |
| Icons | Native themed icon lookup and stock state models; media capability/status controls | Static D4B icon samples do not establish live network/audio states. No network/audio/backend calls were made. |
| Compact/expanded | Each applet's own representations and minima | Panda preferences are not universal Plasma modes. The media minimum may exceed either Panda target. |
| Desktop rectangles | Widget.geometry getter reads the scene item if present | **Widget.setGeometry is a no-op in inspected 6.7.5 source.** Do not implement an applicator around this setter or assume editing a geometry key works. Future assessment must use separately authorized operator edit mode and measurements. |

The geometry and background facts come from plasma-workspace/shell/scripting/
widget.cpp, especially geometry/setGeometry and userBackgroundHints setters,
and libplasma/src/plasma/applet.cpp. The latter stores background enum keys and
exposes Configuration as the ordinary applet config group. The clock's
configurable-background hint permits a standard-frame request; an actual
opaque result still needs visual evidence.

Media controls should retain official MPRIS capability checks and truthful
no-player/paused/missing-artwork states. Its private MPRIS import is not a stable
API commitment for a new Panda widget. No custom MPRIS implementation is proposed.

## Panel and dock properties

plasma-workspace/shell/scripting/panel.cpp implements these baseline properties:

| Target | Requested stock property values | What still needs measurement |
| --- | --- | --- |
| Toolbar | location=top; height=48; alignment=center; lengthMode=fill; opacity=opaque | Actual content/frame thickness, tray fit, text and output/scale behavior |
| Dock | location=bottom; height=56; alignment=center; lengthMode=fit; floating=true; opacity=opaque | Native floating clearance, frame versus reserved bounds, task growth and icon sizing |
| Applets | Preserve existing index/order and all instance IDs | Never recreate panels or replace existing contents to obtain the target |
| Output | Explicit preserved screen/activity mapping | Do not select desktopById or a screen solely by enumeration position |

Floating is a boolean independent of edge location. The location value
“floating” is not the bottom-dock instruction. No supported arbitrary
bottom_clearance=8 property was established. D4B icon_size=40, spacing=8,
padding=8 and the resulting content width remain design preferences until
native task-manager/style behavior is measured.

The first clock/media candidate makes **no panel, dock, task-manager, tray,
desktop-count or theme changes**. There is currently one saved bottom-panel
containment, not an established 48/56 two-panel layout.

## Plasma 6.8.1 source comparison

| Property | Classification | Evidence and consequence |
| --- | --- | --- |
| Official five plugin identities and CPU/RAM preset roles | Unchanged in inspected role sources | Pinned metadata and CMake install names retain org.kde.plasma.digitalclock, org.kde.plasma.mediacontroller, org.kde.plasma.weather, org.kde.plasma.systemmonitor.cpu and org.kde.plasma.systemmonitor.memory; no substitution or reparenting. |
| Clock Appearance schema | Unchanged | main.xml is byte-identical, as is configAppearance.qml. Preserve the proposed date/time keys, timezone/calendar settings and automatic typography. [Schema](https://github.com/KDE/plasma-workspace/blob/fb9b679a99078e68164b05b9cb3f5aaa6020222f/applets/digital-clock/main.xml). |
| Clock enum indices | Unchanged | use24hFormat=2, dateDisplayFormat=2 and showSeconds=0 retain their inspected UI meanings. These remain stock UI indices, not universal KDE enums. [UI](https://github.com/KDE/plasma-workspace/blob/fb9b679a99078e68164b05b9cb3f5aaa6020222f/applets/digital-clock/configAppearance.qml). |
| Clock compact clock / full calendar | Unchanged | Compact remains preferred and full representation remains calendar. Do not reinterpret Panda expanded geometry as a calendar request. [Main](https://github.com/KDE/plasma-workspace/blob/fb9b679a99078e68164b05b9cb3f5aaa6020222f/applets/digital-clock/main.qml). |
| Calendar expanded-change focus/reset | Changed | Full calendar now resets to today and focuses its configure button on expanded changes; observe that transition separately later. [Main](https://github.com/KDE/plasma-workspace/blob/fb9b679a99078e68164b05b9cb3f5aaa6020222f/applets/digital-clock/main.qml). |
| Clock background request | Unchanged | ShadowBackground plus ConfigurableBackground, Widget.userBackgroundHints and applet Configuration/UserBackgroundHints storage remain. StandardBackground is a request to the actual style, not an opacity/radius guarantee. [Widget](https://github.com/KDE/plasma-workspace/blob/fb9b679a99078e68164b05b9cb3f5aaa6020222f/shell/scripting/widget.cpp), [applet](https://github.com/KDE/libplasma/blob/f46c05f2174e8cf35c8d46f4e8cd8fe7d595874e/src/plasma/applet.cpp). |
| Media compact/full/artwork presentations | Unchanged | The three representation/artwork files are byte-identical. Full minimum remains 14×10 Kirigami grid units, preferred 20×20. Exact desktop fit is still unverified. [Expanded](https://github.com/KDE/plasma-workspace/blob/fb9b679a99078e68164b05b9cb3f5aaa6020222f/applets/mediacontroller/ExpandedRepresentation.qml). |
| Media MPRIS action dispatch | Changed | Previous/next/play/pause/toggle/stop/quit/raise now check that currentPlayer exists. Retain official capability checks; do not call actions during observation. No-player robustness is a source improvement, not a tested host result. [Main](https://github.com/KDE/plasma-workspace/blob/fb9b679a99078e68164b05b9cb3f5aaa6020222f/applets/mediacontroller/main.qml). |
| Media global VolumeStep / per-instance proposal | Unchanged inspected surface | globalconfig.cpp/h are identical. Keep the candidate's per-instance settings empty and do not change plasmaparc General/VolumeStep. |
| Widget geometry getter/setter | Unchanged limitation | Getter reads scene geometry; setGeometry remains commented out/no-op despite a read/write property declaration. No supported placement setter was newly established. [Implementation](https://github.com/KDE/plasma-workspace/blob/fb9b679a99078e68164b05b9cb3f5aaa6020222f/shell/scripting/widget.cpp). |
| Widget showConfigurationInterface | Newly supported implementation | The former no-op now triggers the enabled configure QAction. It is a UI action, not a read-only getter; exclude it from observation. |
| Applet globalConfig C++ surface | Removed from inspected implementation | libplasma Applet::globalConfig implementation and the Widget constructor's global-config initialization are gone. Do not base new work on this legacy route. This is separate from media's own unchanged GlobalConfig class. |
| Screen fallback in PlasmoidItem | Changed | Fallback now uses containment.screen rather than containment.lastScreen. Do not equate a saved lastScreen value or enumeration position with the active output. [Source](https://github.com/KDE/libplasma/blob/f46c05f2174e8cf35c8d46f4e8cd8fe7d595874e/src/plasmaquick/plasmoid/plasmoiditem.cpp). |
| Panel height, alignment, lengthMode, floating, opacity | Unchanged inspected setters | Retain toolbar height=48, location=top, lengthMode=fill and dock height=56, location=bottom, alignment=center, lengthMode=fit, floating=true, opacity=opaque as future preferences only. [Panel](https://github.com/KDE/plasma-workspace/blob/fb9b679a99078e68164b05b9cb3f5aaa6020222f/shell/scripting/panel.cpp). |
| Panel floatingApplets | Newly supported scripting property | New getter/setter and Q_PROPERTY are present. Independent from panel floating mode. Preserve its existing value; do not enable it to mimic card backgrounds without a later visual decision. [Header](https://github.com/KDE/plasma-workspace/blob/fb9b679a99078e68164b05b9cb3f5aaa6020222f/shell/scripting/panel.h). |
| Exact Fit Content width, floating clearance, opaque frame and icon bounds | Unverified native effect | Setter support does not establish 8-pixel clearance, 40-pixel icons or exact frame/content dimensions. No arbitrary bottom_clearance property was established. |
| Weather station/appearance/units schema | Unchanged | main.xml is byte-identical; preserve every station/provider field. No weather loader or request is allowed. [Schema](https://github.com/KDE/kdeplasma-addons/blob/087c60377b1a1b05ab2564fc72fc49ed6b662a86/applets/weather/main.xml). |
| Weather unavailable tooltip | Changed | Unknown-weather icon gains an explicit unable-to-load forecast message. Provider-driven configuration behavior remains; do not load it to check the tooltip. [Main](https://github.com/KDE/kdeplasma-addons/blob/087c60377b1a1b05ab2564fc72fc49ed6b662a86/applets/weather/qml/main.qml). |
| CPU/RAM schema and preset pie faces | Unchanged | Generic XML, main/full QML and both presets are identical. Panda linechart and horizontalbars remain independent approved choices, not stock preset defaults. |
| Effective monitor storage and activation boundary | Unchanged in the additional paired libksysguard files | Controller reads totalSensors, highPrioritySensorIds, lowPrioritySensorIds, SensorColors and SensorLabels; migration can write entries and resolution can contact sensors. The older generic XML alone is not a complete operational storage contract. Constructor/face loading is not an offline validator. [Controller](https://github.com/KDE/libksysguard/blob/40faaf3284b370dd7b15574f379914cbe0af8245/faces/SensorFaceController.cpp), [sensor interface](https://github.com/KDE/libksysguard/blob/40faaf3284b370dd7b15574f379914cbe0af8245/sensors/SensorDaemonInterface.cpp). |
| Official approved face package availability in source | Unverified baseline package/runtime parity | org.kde.ksysguard.linechart and org.kde.ksysguard.horizontalbars metadata exist at v6.8.1. No package loader, controller or sensor object was instantiated. |
| Kirigami unit and font semantics | Unverified runtime; source distinction established | Kirigami's base Units initializes gridUnit to 18 and permits overrides/platform implementations. Plasma scripting gridUnit() instead measures application-font M height and rounds it to even. They are different values and cannot substitute for each other. [Units](https://github.com/KDE/kirigami/blob/eecf183a956fdbfbf331c0ef61fd6e35220d4275/src/platform/units.cpp), [scripting](https://github.com/KDE/plasma-workspace/blob/fb9b679a99078e68164b05b9cb3f5aaa6020222f/shell/scripting/scriptengine_v1.cpp). |
| Qt text metrics and output scaling | Unverified native/baseline comparison | Qt 6.12.0 supports QFontInfo/QFontMetricsF, QQuick TextMetrics and QScreen geometry/DPI/DPR. The earlier milestone did not establish a pinned Qt baseline or loaded font, so no unchanged-rendering claim follows. [Metrics](https://doc.qt.io/qt-6.12/qfontmetricsf.html), [DPI](https://doc.qt.io/qt-6.12/highdpi.html). |

## Revisions required before a future candidate

Keep D4C1 immutable as the accepted qualified milestone. A future candidate needs
a new versioned evidence block and comparison gate; do not edit the D4C1 JSON to
silently bless 6.8.1.

- Retain clock key/value proposals: the inspected schema and enum UI are unchanged.
  Add a later calendar-focus/reset observation if full representation is opened.
- Retain empty media per-instance settings and stock MPRIS controls, including
  the new missing-player guards. Keep absent/paused/artwork states truthful.
- Keep both proposed new instance IDs null until explicit additive authorization.
  Preserve the panel clock, tray weather, every panel/tray identity, order,
  task pin and current desktop count. Source revalidation does not make the
  earlier saved inventory fresh.
- Keep operator-controlled future placement: geometry setter is still unusable.
  Do not turn a geometry getter into an invented write path.
- Replace any assumption that scripting gridUnit measures Kirigami gridUnit.
  With an illustrative Kirigami unit of 18, media minimum is 252×180 logical:
  both 288×120 compact and 352×168 expanded targets are shorter than that minimum.
  Measure the effective unit and native representation before proposing a layout
  exception; do not silently change D4A/D4B geometry or reduce native controls.
- Before adding CPU/RAM configuration, map effective controller keys and migration,
  not just generic XML. Preserve the reviewed face allowlist; no activation test.
- Treat floatingApplets as a new optional stock capability, with no proposed change.
  Do not call the now-functional configuration action during a read-only pass.
- Keep font family, resolved fallback, point/pixel size, weight, DPI, device ratio,
  Plasma Style and actual content/frame metrics unverified until measured.
- Keep timestamp drift, runtime pins and the recovery gate unresolved. Revalidating
  source cannot explain the old timestamps or establish restoration safety.

## Full HD / QHD measurement contract

These are offline coordinate expectations, not session observations:

| Mode / scale | Logical area | Toolbar / dock logical height | Ideal physical height |
| --- | --- | --- | --- |
| FHD / 100% | 1920×1080 | 48 / 56 | 48 / 56 |
| FHD / 125% | 1536×864 | 48 / 56 | 60 / 70 |
| FHD / 150% | 1280×720 | 48 / 56 | 72 / 84 |
| QHD / 125% | 2048×1152 | 48 / 56 | 60 / 70 |

Native available area excludes measured reservations. Use the actual output and
window DPR; do not apply the scale twice or infer active topology from this table.
Do not change output scaling for this phase. Existing geometry acceptance/refusal
rules, flavors and palettes remain unchanged.

## First clock and media candidate

## Exact future property proposal, not executed

Only after explicit authorization for the needed additions and version/schema
revalidation, propose the official plugins below:

| Role | Property / baseline config group | Proposed value |
| --- | --- | --- |
| Clock | Appearance/showDate | true |
| Clock | Appearance/dateFormat | custom |
| Clock | Appearance/customDateFormat | dddd, d MMMM |
| Clock | Appearance/use24hFormat | 2 (24-hour in inspected 6.7.5 UI) |
| Clock | Appearance/dateDisplayFormat | 2 (below time) |
| Clock | Appearance/showSeconds | 0 (never) |
| Clock | Appearance/autoFontAndSize | true |
| Clock | Widget.userBackgroundHints | StandardBackground |
| Media | Per-instance settings | none proposed; retain stock MPRIS behavior |
| Both | Scene rectangle | operator edit-mode measurement only, under a later native scope |

Clock plugin: org.kde.plasma.digitalclock. Media plugin:
org.kde.plasma.mediacontroller. The background property is stored by the
baseline implementation as Configuration/UserBackgroundHints; no filesystem
writer is supplied. Timezones, calendar plugins, locale and global typography
remain untouched. Media's global plasmaparc VolumeStep is not changed.

Automatic clock typography is intentional for the first compatibility
measurement: it does not promise D4B's 38-pixel clock text or alter the system
font. An exact per-card font override, frame style or palette is a separate
gap decision. The current Plasma Style/colors/icons are observed later, not
changed to force the offline image to match.

## Geometry and measurements

D4A compact FHD100 preferences:

| Card | Requested logical rectangle x,y,w,h |
| --- | --- |
| Clock | 1608,72,288,88 |
| Media | 1608,172,288,120 |

These are model preferences at 1920×1080/scale 1, not current scene geometry.
The saved output configuration is consistent with that mode; active output
binding remains unverified. No geometry key is invented. In the pinned baseline,
WorkspaceScripting Widget.setGeometry does nothing, so this candidate deliberately
contains no scripting-based geometry operation.

The media full view minimum is 14×10 Kirigami grid units and its preferred size
is 20×20. For illustration only, an 18-pixel grid would imply a minimum
252×180; **the actual grid unit was not measured**. Neither a 288×120 compact
card nor a 352×168 expanded preference can be assumed to provide the D4B
full-control layout. Record stock compact/full behavior; do not force a
representation, hide clipping or introduce QML to pass a screenshot comparison.

A later native assessment must capture:

- Loaded Plasma/Qt/KF builds, intended output/activity, actual logical available
  area, scale, selected font file and Kirigami grid unit.
- Allocated new IDs or explicitly chosen existing IDs and unchanged parent/order
  records. Record actual current pins without changing or normalizing them.
- Clock native minima, actual frame/content rectangles, time/date alignment,
  font point/pixel metrics, ellipsis and background result.
- Media native minima/default size, compact/full transition, control/artwork/seek
  bounds, no-player/paused states and keyboard/accessibility behavior.
- Frame opacity over contrasting wallpaper, radius/border/padding differences,
  semantic contrast and performance within the opaque-first Helios policy.

The candidate always has ready_for_native_test=false and native_verified=false.
Keep both proposed IDs null until exact additive authorization, or explicitly
reuse one eligible existing desktop instance. Multiple matches are ambiguous;
panel/tray children never substitute. Preserve timezone/calendar/locale/global
typography and media's global VolumeStep. Source parity does not establish fresh
pins, activity, output, font, geometry or recovery readiness.

## Blocked observation scope — not executed

A future observation would be short and operator-attended, using already-running
Plasma, a private new evidence root, a fixed allowlist and no polling loop.
The minimum useful set is the loaded Plasma version, selected output/desktop
containment binding and available geometry. No execution-cleared accessor set
covers these fields; no observation collector is ready to run.

The [runtime observation source receipts](runtime-observation-source-references.json)
retain the static R0 audit's 29 pinned KDE/systemd source identities. They are
design evidence, not fresh host observations or approval to execute commands.
The inspected KDE sources are Plasma 6.8.1; the bus client sources are systemd
v262. Applicability to an installed client or running session remains unverified.

### R0: offline approval prerequisites

Before any session access, review the exact command/message payloads, all getter
call paths and startup/teardown effects. Explicitly authorize selected process
metadata, existing-owner D-Bus messages, selected configuration receipts and
private evidence writes. Do not inherit D4C1 permission as approval for these.

The D-Bus transport must resolve existing unique owners through the bus daemon,
set NO_AUTO_START, disable interactive authorization and target the unique owner.
Recheck owner/PID/start-time identity around observations. An absent/replaced
owner, unsupported getter, timeout or permission error ends that portion.
Do not instantiate a default auto-activating proxy. A persistent client must
bind observations to the same bus lifetime and existing owner; separate busctl
invocations alone do not establish that binding. This client and the
provenance-checked private evidence writer remain unimplemented and unreviewed.

The pinned evaluateScript path constructs ScriptEngine and AppInterface before
evaluating the supplied expression. AppInterface constructs Plasma::Theme;
cold initialization can create shared theme state, a KSvg ImageSet, configuration
watchers and conditional Wayland effect objects. A getter-only expression does
not bound that startup/teardown path. The constructor's settingsChanged(false)
does not establish an unconditional settings write, but the unresolved cold/shared
state and configuration-read effects still withhold execution. Do not use
evaluateScript, widget wrappers or a substitute QML/debugger path for this scope.

### Requested outputs and safe-route requirements

| Output | Proposed minimum observation | Required limitation / stop |
| --- | --- | --- |
| Loaded Plasma version | AppInterface.applicationVersion returns the running qApp version through the withheld scripting path. No execution-cleared alternative exported getter is established. | No evaluateScript call: its engine/theme-construction path is not cleared. No arbitrary scripts, actions, ConfigFile constructors, theme assignment or widget enumeration/loaders. |
| Loaded Qt/KF identities | If separately authorized, inspect only the same process's selected Qt/KF mapped-library identity records, matched to package evidence; accept a process-specific already-available diagnostic when it identifies runtime versions. | No environment, command line, full memory maps, debugger, injection, process restart or reading unrelated processes. A newly launched --version program proves only the on-disk build. Mapping identity alone is not qVersion(); deleted/replaced/ambiguous modules leave exact versions unverified. |
| Active target output, containment binding and geometry | Require operator-selected connector/desktop binding and an approved existing-output endpoint. In-process screenForConnector, screenGeometry and availableScreenRect methods do not establish an exported D-Bus route. | The pinned PlasmaShell D-Bus interface does not export the geometry methods; invalid screen IDs can fall back to primary-screen geometry. currentActivity() creates a KActivities::Consumer whose no-activation path is not cleared. Exact activity and fractional-scale endpoints remain unestablished. No ordinal screen assumptions, supportInformation GPU dump, KScreen activation or output setters. |
| Ordered task pins | Read the existing identified task model's launcherList, retaining raw order, preferred:// identities and activity metadata privately; compare with its current configuration. | Source proves the in-process property, not a public D-Bus export. Scripting readConfig is not established as the effective model value. No model recreation, setters, serialization, app launching or pin normalization. If no audited existing-object accessor exists, stop with pins unknown. |
| Native font metrics | Required values: actual QFontInfo family/style/size, QFontMetricsF ascent/descent/height/advance/ink bounds, QScreen logical DPI/DPR, and effective Kirigami Units for the relevant existing object. | These are C++/QML APIs, not demonstrated Plasma scripting exports. No QML loader, debug server/attach, GPU/rendering window or helper is authorized here. Without a separately reviewed safe accessor, exact native metrics remain unknown. Scripting gridUnit is only its own font-derived surrogate. |

A broker/endpoint identity subset cannot establish the minimum useful runtime
set. The narrow exported PlasmaShell.shell property identifies a shell, not its
loaded version, selected output, containment binding or available geometry.
No broker-only pass or command catalog may be reported as completing those
fields, ordered pins, exact loaded Qt identity, activity, fractional scale or
native font metrics. Missing accessors remain blockers; they do not authorize
tool installation, service activation or a weaker preservation boundary.

A later offline CPU-only Qt metric helper could measure a supplied font at a
specified DPI without using the live desktop. It would need separate development
approval and isolated cache paths. Such results would be reference metrics,
not proof of the running widget's font, backend, DPR or layout. No helper is built.

### Preservation, privacy and stop conditions

Before/after reads of any reauthorized protected file must use the strict
non-mutating reader; no timestamp/ownership reset or fallback. Capture a new
baseline rather than overwriting D4C1 evidence. Stop on any identity, byte,
metadata or owner drift. Keep failed and partial receipts. The old output-config
timestamp drift remains unexplained even if a later baseline is stable.

Private evidence retains real IDs, activity/output identifiers, raw ordered
launcher identities and selected font paths; public reports use aliases and
redacted summaries. Do not collect weather locations, media titles, windows,
unrelated application data or full desktop screenshots. Read no D3B1A roots.

Stop on any path requiring a service/provider/model activation, package/tool
installation, widget/dialog configuration action, geometry/theme/config setter,
graphics probe, compositor change, session restart or recovery operation.
Do not use dumpCurrentLayoutJS as a blanket inventory or grabContainmentImage:
the latter is explicitly internal and creates an image file.

No placement/sizing test, new applet, provider activation or live restoration
follows automatically. A future operator-controlled clock/media test requires
its own exact instance IDs, managed-key boundary, measurements, preservation
receipts, fresh pins/output/activity evidence, reviewed recovery prerequisites
and explicit additive/native authorization.

A future session pass is complete only when each required field has a safe
reviewed accessor and preservation checks pass. Missing accessors remain blockers,
not permission to install tools, load QML, attach debuggers or weaken a boundary.
See the [layout guide](desktop.md#native-preservation-and-deployment-gates) for
later mutation and recovery requirements.
