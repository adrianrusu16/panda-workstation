# D4C2 proposal — revalidate the installed native stack

Status: **approved static compatibility proposal; no native observation or implementation authorized**.
Prepared 2026-10-27. D4C1 commit: 6133292d753ba8369106a951e193f09098b6a53f.
D4C1 PR: [#9](https://github.com/adrianrusu16/panda-workstation/pull/9).
This proposal and its source-reference JSON were reviewed outside that PR and
are published separately as the D4C2 documentation milestone. Runtime observation
still requires its own exact procedure and authorization.

## Goal and boundary

Compare the accepted Plasma 6.7.5 static findings against the declared installed
Plasma 6.8.1 / Qt 6.12.0 stack, with Kirigami 6.31.0 as recorded by D4C1.
An installed package version is not a loaded-process version. Distribution
patches and loaded QML/library combinations have not been verified.

No packages, applets, providers, services, theme changes, configuration writers,
layout applicators, debugging attachments, custom plasmoids or native tests are
introduced. No new host configuration, process, hardware or session-bus observation
was performed. D3B1A was not accessed; its unresolved recovery status remains
independent of this proposal.

Recommended approach: compare immutable upstream source first, then authorize
only a bounded observation of already-running objects whose getter path has
been audited. A stock-default reconstruction cannot establish runtime pins or
font resolution. An automatic layout application is outside this phase and
cannot solve the disabled geometry setter.

## Evidence and classification rules

[Source references](d4c2/source-references.json) contain immutable commits/trees,
lengths, Git blob IDs and SHA256 hashes for **60 official source blobs**.
All 20 D4C1 source files were paired with 6.8.1 versions: 13 are byte-identical;
seven changed. A changed file does not mean every property in it changed.

| Repository | Tag | Immutable commit |
| --- | --- | --- |
| plasma-workspace | v6.8.1 | fb9b679a99078e68164b05b9cb3f5aaa6020222f |
| plasma-desktop | v6.8.1 | bb989636959f9edc7263f2f75dc2630835305b95 |
| kdeplasma-addons | v6.8.1 | 087c60377b1a1b05ab2564fc72fc49ed6b662a86 |
| libplasma | v6.8.1 | f46c05f2174e8cf35c8d46f4e8cd8fe7d595874e |
| libksysguard | v6.8.1 | 40faaf3284b370dd7b15574f379914cbe0af8245 |
| libksysguard, additional comparison | v6.7.5 | 1eb66dee405a7436d31b731a78634501497199db |
| kirigami | v6.31.0 | eecf183a956fdbfbf331c0ef61fd6e35220d4275 |
| qtbase | v6.12.0 | 025bdad181de241e81bf853c8a2d7bf3d19261a9 |
| qtdeclarative | v6.12.0 | 4332fbbb4c340463dc8cee36dda0c85d932122d8 |

**Unchanged** means the inspected behavior is retained, not native-tested.
**Changed**, **removed** and **newly supported** describe the inspected source
delta. **Unverified** means the baseline comparison, runtime effect or safe
observation route is not established. Unverified properties are not granted a
default value.

The KDE scripting documentation is rolling guidance; pinned implementation
controls version-specific claims. Qt 6.12 documentation is supplemented by
v6.12.0 source. Initial guessed paths were resolved through immutable trees:
task manager files are under plasma-desktop/applets/taskmanager, PlasmaShell XML
under shell/dbus, and QFontInfo implementation in qfont.cpp. A missing guessed
path was never classified as a removed API.

## Property comparison

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

## Proposed separately authorized observation — not executed

Recommend one short, operator-attended observation of already-running Plasma,
with a private new evidence root, a fixed allowlist and no polling loop.
This is a proposal for an authorization scope, not a ready-to-run collector.

### R0: offline approval prerequisites

Before any session access, review the exact command/message payloads, all getter
call paths and startup/teardown effects. Explicitly authorize selected process
metadata, existing-owner D-Bus messages, selected configuration receipts and
private evidence writes. Do not inherit D4C1 permission as approval for these.

The D-Bus transport must resolve existing unique owners through the bus daemon,
set NO_AUTO_START, disable interactive authorization and target the unique owner.
Recheck owner/PID/start-time identity around observations. An absent/replaced
owner, unsupported getter, timeout or permission error ends that portion.
Do not instantiate a default auto-activating proxy.

### Requested outputs and safe-route requirements

| Output | Proposed minimum observation | Required limitation / stop |
| --- | --- | --- |
| Loaded Plasma version | A single source-reviewed getter-only Plasma script may read applicationVersion; implementation returns the running qApp version. Bind to the existing Plasma owner. | evaluateScript is a general mutation-capable API, not inherently read-only. The exact fixed payload and engine/theme-construction path need separate approval. No arbitrary scripts, actions, ConfigFile constructors, theme assignment or widget enumeration/loaders. |
| Loaded Qt/KF identities | If separately authorized, inspect only the same process's selected Qt/KF mapped-library identity records, matched to package evidence; accept a process-specific already-available diagnostic when it identifies runtime versions. | No environment, command line, full memory maps, debugger, injection, process restart or reading unrelated processes. A newly launched --version program proves only the on-disk build. Mapping identity alone is not qVersion(); deleted/replaced/ambiguous modules leave exact versions unverified. |
| Active target output and activity | Obtain operator-selected connector/desktop binding, then use verified getters such as screenForConnector and screenGeometry; correlate with a separately approved read-only existing-output endpoint and existing activity owner. | Source shows currentActivity() creates a KActivities::Consumer: do not call it until its no-activation path is audited. Exact activity and fractional-scale endpoints are not established by this proposal. No ordinal screen assumptions, supportInformation GPU dump, KScreen activation or output setters. |
| Ordered task pins | Read the existing identified task model's launcherList, retaining raw order, preferred:// identities and activity metadata privately; compare with its current configuration. | Source proves the in-process property, not a public D-Bus export. Scripting readConfig is not established as the effective model value. No model recreation, setters, serialization, app launching or pin normalization. If no audited existing-object accessor exists, stop with pins unknown. |
| Native font metrics | Required values: actual QFontInfo family/style/size, QFontMetricsF ascent/descent/height/advance/ink bounds, QScreen logical DPI/DPR, and effective Kirigami Units for the relevant existing object. | These are C++/QML APIs, not demonstrated Plasma scripting exports. No QML loader, debug server/attach, GPU/rendering window or helper is authorized here. Without a separately reviewed safe accessor, exact native metrics remain unknown. Scripting gridUnit is only its own font-derived surrogate. |

The source does not establish a single supported command that safely provides
all requested fields. A partial owner-bound pass may establish running Plasma
version and screen mapping; it must not be reported as completing pins, exact
loaded Qt identity, activity, fractional scale or native font metrics.
Missing accessors are explicit D4C2 design prerequisites, not permission to
install tooling or weaken the boundary.

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

## Acceptance and handoff

This proposal can be accepted as a static comparison without approving R0/R1
session access. A future session pass is complete only when every required field
has a safe reviewed accessor and all preservation checks pass; otherwise report
the missing fields and remain blocked from native writes.

Current proposal verification: official source lengths/SHA256/Git blobs/tree
membership checked; 20 baseline pairs compared; no native measurements performed.
The D4C1 PR independently passed 314 local tests, Fish/package validation and CI.
The two proposal artifacts are documentation/evidence only and are published
separately from the D4C1 PR.

A fresh read-only reviewer checked the original 50 source receipts and the full
comparison/observation proposal, with no important findings. The final ten
metadata/install-name/header sources were then checked separately by the author.
All 60 final blobs are length/hash/tree verified. Exact plugin IDs come from
pinned install declarations where metadata omits Id. No additional code or
session access was needed for these checks.
