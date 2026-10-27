# D4C1 — native compatibility matrix

Status: **static evidence only; native behavior unverified**. Baseline: Plasma
6.7.5. Integrated base: 215522fb36d9f4f29922fed83bd568bf7aa6a442.
The fresh package database reports Plasma 6.8.1 and Qt 6.12.0; loaded session
versions were not queried. Baseline properties must be revalidated for that
installed build before any native trial.

Authority: AGENTS.md, the approved Panda Theme System specification and merged
[proposal](desktop-d4c-proposal.md). The specification is a local ignored file,
not present in integrated main; its SHA256 is recorded in the D4C1 plan.
No native layout applicator, QML widget, provider or service adapter is added.

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

## Classification and unresolved native evidence

Confirmed at the pinned baseline: official identities/schemas, clock date/time
choices, configurable background request, native MPRIS control model, monitor
face configuration, panel height/alignment/length/floating/opacity setters, and
the disabled widget geometry setter.

Fresh saved-file facts: see [inventory](desktop-d4c1-inventory.md).
Unresolved: loaded session versions; 6.8.1 source/API parity; current active
output/activity; runtime pins; actual font resolution; scene geometry/minima;
opaque frames, radius and semantic contrast; media capability/artwork behavior;
weather provider freshness; CPU/RAM sensor data and scale/rounding behavior.

No custom Panda QML is justified by D4C1 alone. If stock differences are
unacceptable, return to the approved proposal's explicit identity/migration
gate. Shared tokens/assets/state schemas remain reusable for a future Command
Center; this phase implements neither the Command Center nor native visuals.

## Source provenance check

The first tag-addressed tree API response carried the resolved commit identifier
in its top-level sha field. An initial check compared that with commit.tree.sha
and refused the mismatch. The original receipt was retained. A second lookup
using each immutable tree ID proved that **all tree entries and all 20 downloaded
source blobs match** the resolved v6.7.5 commits. This was a receipt-field
comparison error; no source-content drift was found. The public references
record both identifiers and their verification.
