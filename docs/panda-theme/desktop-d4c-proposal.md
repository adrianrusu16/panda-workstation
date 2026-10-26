# Panda Desktop D4C — native visual translation proposal

Status: **proposal for review; no D4C implementation or native tests authorized.**
Prepared 2026-10-23 for KDE Plasma **6.7.5**, Wayland, Panda Helios.

## 1. Approved baseline and outcome

D4B offline milestone: `a49e7482cc7ee2948cd28bfcb4ddb8acb64907e1`,
branch `codex/feat-panda-desktop-d4b`, parent D4A
`bdfa0bf58c8091b4899401bd8b42bfda12e82cb3`.
Its 60 reviewed files and 33 generated artifacts retain their reviewed hashes.
The fresh finalization suite passed 297 tests in 61.984 seconds; all generated
artifacts reproduced exactly. Fish/package/whitespace checks passed.

The [approved comparison](previews/d4b/five-flavor-comparison.png) is a synthetic
visual target, not proof of native widgets. The supplied Downloads comparison
is a review input. D4B's committed ledger and guide describe the earlier
uncommitted review stage; this proposal records the subsequent milestone commit.

D4C should translate the five separate clock, media, weather, CPU and RAM cards,
48-logical-pixel top toolbar and centered 56-logical-pixel floating application
dock into supported Plasma behavior. Preserve the canonical five palettes and
one shared structure. Stock-native differences must be documented and reviewed;
pixel equality with Pango/Cairo previews is not promised.

This document proposes future work only. No QML, layout applicator, data adapter,
package installation, theme activation or native experiment is created here.
D3B1A/R3 recovery remains unresolved and separately gated; its evidence is not
accessed or treated as successful.

## 2. Approach and classification

**Recommended: stock applets in place, supported styling, then measured gap review.**
Use official KDE plugins and their existing backends. Reuse reviewed palette
tokens and mature icon coverage. Accept a native variation only when visible,
measured and approved against the D4B target.

Alternatives considered:

- Bespoke Panda QML for every card would give more layout control, but creates
  plugin/identity migration and backend maintenance obligations. Defer until a
  specific stock limitation justifies it and its migration is separately approved.
- Arbitrary Store widgets, monkey-patched KDE QML and runtime panel injectors
  lack the current provenance/version contract. Exclude from the default path.
  No third-party customization is declared trusted by this proposal.

Classification numbers used below:

| Class | Meaning |
| --- | --- |
| **1** | Stock Plasma configuration or official applet functionality. Source-supported capability; host behavior still needs evidence. |
| **2** | Existing trusted Plasma customization mechanism: supported Plasma Style/color-scheme/icon-theme interfaces and reviewed Panda tokens/assets. This does not mean a complete native Panda Style already exists. |
| **3** | Custom Panda QML required for the specified exact visual behavior if stock differences are unacceptable. A conditional design path, not permission to implement or replace an existing applet. |
| **4** | Requires native evidence, or is not feasible under the present identity/safety contract. Do not silently approximate or claim support. |

KDE separates Plasma Styles from applets and other desktop components.
Styles can supply shared frames, but are not a general stylesheet for arbitrary
applet internals. [KDE customization model](https://develop.kde.org/docs/plasma/),
[Plasma Style structure](https://develop.kde.org/docs/plasma/theme/theme-details/).

## 3. Component mapping

| Approved component | Preferred native implementation | Classes and boundary |
| --- | --- | --- |
| Desktop clock | Keep/bind `org.kde.plasma.digitalclock` from `plasma-workspace`; use its time/date/font configuration. | **1** for time/date; **2** for inherited palette/frame. **4** for exact clock-card bounds, date alignment and font fit. **3** only if a measured mismatch requires custom composition. |
| Media card | Keep/bind `org.kde.plasma.mediacontroller` from `plasma-workspace`; use official MPRIS player selection and controls. | **1** for playback; **2** for supported inherited visuals. **4** for a permanent compact desktop card with all D4B controls/artwork. **3** if exact independent layout is required after stock evaluation. |
| Weather card | Keep/bind `org.kde.plasma.weather` from `kdeplasma-addons`; retain existing provider/location/units. | **1** for official weather infrastructure; **2** for frame/colors/icons. **4** for provider availability, stale/offline rendering and D4B-sized content. **3** for an exact Panda layout if justified. |
| CPU | Keep/bind `org.kde.plasma.systemmonitor.cpu`; explicitly prefer `org.kde.ksysguard.linechart`. | **1** for face selection/sensors; **2** for face-supported colors. **4** for sensor presence/history/minima and exact graph/label arrangement. **3** for an exact custom face only under a separately reviewed contract change. |
| RAM | Keep/bind `org.kde.plasma.systemmonitor.memory`; explicitly prefer `org.kde.ksysguard.horizontalbars`. | **1** for face selection/sensors; **2** for supported colors. **4** for units/range/unknown-total behavior and fit. **3** for exact custom face composition only if approved later. |
| Shared independent card frames | Standard desktop background where supported; Panda-derived Plasma Style frames, opaque fills and semantic borders. | **2** for the supported styling route; **4** for independent per-applet applicability and exact radius/margins. **3** for deterministic 12-pixel card geometry beyond style control. |
| Typography and semantic icons | Existing system font configuration where appropriate, stock clock font override, supported icon theme and reviewed Panda overrides. | **1/2** for available settings/assets; **4** for per-card type sizes, Qt metrics, symbolic coverage. **3** for exact scoped QML typography where stock has no control. |
| Top toolbar | Existing `org.kde.panel` containment, `org.kde.plasma.kickoff` launcher where already used, `org.kde.plasma.pager`, `org.kde.plasma.systemtray`, and separate digital clock. | **1** for stock functions and panel geometry; **2** for visuals. **4** for mapping existing IDs/order, fit and actual opacity. Existing compatible alternative launcher is preserved, not replaced by name. |
| Application dock | Existing panel plus `org.kde.plasma.icontasks`, centered fit-content length, bottom edge, floating and opaque intent. | **1** for panel/task functionality; **2** for style. **4** for exact 8-pixel gap, 40-pixel icons, 8-pixel spacing and behavior as tasks change. No custom dock engine proposed. |
| Network and audio status | Existing tray network-management and volume applets: `org.kde.plasma.networkmanagement` / `org.kde.plasma.volume`. | **1** for backend-driven status/icons; **2** for matching icon-theme variants. **4** for host states and complete fallback coverage. Never use the static D4B sample as live status. |
| Future Command Center visuals | Share a versioned semantic/style specification and licensed icons; later thin Panda QML presentation primitives with injected data. | **2** for common tokens/assets; **3** for reusable QML primitives; **4** for their later host integration. Command Center implementation remains out of scope. |
| Resolution/scale adaptation | Reuse D4A logical geometry and explicit compact/expanded preference. | **1** for supported manual/native geometry settings; **4** for minima, rounding, available area and representation switching. No automatic right anchoring, hotplug reparenting or parking. |

These rows distinguish backend capability from exact visual fidelity. No class
1 or 2 label asserts that the whole D4B card can be reproduced by settings alone.

### Clock

The 6.7.5 schema exposes date format, font family/size, 24-hour choice and
date placement. Values must be derived from that version's schema and UI,
not guessed enum integers. Preserve timezone/calendar settings unless explicitly
approved otherwise. The toolbar clock and independent desktop clock have
different roles; one must not be removed to create the other.

Its QML initially requests a configurable shadow background and prefers its
compact clock representation; its full representation is the calendar.
D4A “expanded” therefore cannot mean forcing that full representation.
Check whether the standard opaque desktop background override is supported
before considering custom QML.
[Clock configuration](https://raw.githubusercontent.com/KDE/plasma-workspace/v6.7.5/applets/digital-clock/main.xml),
[clock representation](https://raw.githubusercontent.com/KDE/plasma-workspace/v6.7.5/applets/digital-clock/main.qml).

### Media and MPRIS

The official controller already derives track/player/status and control
capabilities from its MPRIS model. Its 6.7.5 implementation uses
`org.kde.plasma.private.mpris`; this private import is not a stable API promise
for a future Panda widget. Prefer keeping the official controller instead of
copying its private internals.
[Media controller source](https://raw.githubusercontent.com/KDE/plasma-workspace/v6.7.5/applets/mediacontroller/main.qml).

Proposed acceptance rules: controls follow `CanControl`, `CanPlay`,
`CanPause`, `CanGoNext`, `CanGoPrevious` and `CanSeek`; paused progress
does not advance. Unknown duration is indeterminate, absent artwork has a local
placeholder, and no player is distinct from stopped playback. No fabricated
metadata. A future custom adapter would require separate API/security review,
including bounded image handling, URL policy and service disappearance.
[MPRIS player contract](https://specifications.freedesktop.org/mpris/latest/Player_Interface.html).

### Weather

The 6.7.5 implementation uses forecast/provider state, supports configurable
backgrounds and may update stored location information after provider results.
Instantiating/configuring it is therefore not an inert rendering operation.
Do not run it in an “offline test” with host settings.
[Weather implementation](https://raw.githubusercontent.com/KDE/kdeplasma-addons/v6.7.5/applets/weather/qml/main.qml),
[configuration](https://raw.githubusercontent.com/KDE/kdeplasma-addons/v6.7.5/applets/weather/main.xml).

D4C must first use synthetic available/stale/offline/unconfigured fixtures.
Native provider access needs separate authorization, preserved location/units,
provider attribution/terms review and explicit unavailable states. High/low or
current observation may be absent; never infer sunshine or healthy connectivity.
A proposed Panda weather view must not assume private forecast types are stable
or introduce a new weather backend or embedded API key.

### CPU, RAM and sensor faces

Keep D4A's independently selectable **two-face allowlist**, unchanged:
`org.kde.ksysguard.linechart` and `org.kde.ksysguard.horizontalbars`.
Defaults remain CPU linechart and RAM horizontal bars. Do not widen the allowlist
to custom/arbitrary face IDs merely to obtain matching visuals.

Static local files confirm both official faces are present. The stock CPU/RAM
preset files currently name piechart; selecting Panda's defaults would be an
explicit future instance configuration change, not an assertion about stock
defaults. Candidate sensor IDs from those presets include `cpu/all/usage`,
`memory/physical/used`, `memory/physical/usedPercent` and
`memory/physical/total`. Their presence in files is not observed sensor data.

Official faces have separate representations and controller configuration.
Both full views have font/grid-dependent minima; the horizontal-bars view uses
sensor/legend rows and linechart has optional axes/grid/legend. Treat these as
constraints to measure, not evidence that 288×96 is sufficient.
[Sensor-face architecture](https://develop.kde.org/docs/apps/sensor-faces/),
[linechart](https://raw.githubusercontent.com/KDE/libksysguard/v6.7.5/faces/facepackages/linechart/contents/ui/FullRepresentation.qml),
[horizontal bars](https://raw.githubusercontent.com/KDE/libksysguard/v6.7.5/faces/facepackages/horizontalbars/contents/ui/FullRepresentation.qml).

Future native acceptance must verify percentage versus byte units, CPU aggregate
meaning, RAM numerator/denominator and bar range, history cadence, gaps and
missing/unknown total handling. CPU missing is not zero; RAM without a valid
total cannot have a utilization fill. RAM linechart without history must remain
explicitly unavailable. Do not activate KSystemStats during offline development;
even constructing a sensor object is excluded from provider-free fixtures.

## 4. Shared visual translation

Retain the approved opaque `surface`/`surface2`, semantic `text`, `muted`,
`accent_text`, `border` and `focus` roles. Use canonical manifests rather
than five copied hardcoded QML palettes. One shared visual structure must render
all five flavors. No blur, translucency dependency or shader-heavy workaround.

A supported Plasma Style can provide standard frame assets such as
`widgets/background.svg` and `widgets/panel-background.svg`. Applicability,
margins and background overrides vary by applet/containment. The existence of an
`opaque/` style directory alone does not guarantee an opaque Wayland desktop.
All relevant surfaces must be visibly checked over contrasting wallpapers.
[Theme element contract](https://develop.kde.org/docs/plasma/theme/theme-elements/),
[background-hint contract](https://api.kde.org/qml-org-kde-plasma-plasmoid-plasmoid.html).

D4B radius 12, compact/expanded padding 12/16, label/body/title 13/14/16, clock
38/44 and numeric 24/28 are logical design targets. Do not copy pixel sizes into
point-valued native settings. Retain accessible native text, tabular numerals
where available, elision, tooltips, keyboard focus and labelled controls.
Noto Sans is the reviewed font; measure the resolved native file/version and
Qt shaping/fallback separately from the vendored preview font. Do not globally
change user typography merely to make one card match.

Reuse mature Breeze/Panda icon lookup and license receipts. Standard application
icons retain application identity. Required symbolic state variants need complete
fallback coverage; do not globally recolor every icon to the flavor accent.
D4B's used semantic contrast passes are useful baseline evidence; Gothic's
unused primary/surface 1.7622:1 and secondary/surface 2.5588:1 failures stay
recorded. They are not suitable essential indicators. Recheck actual native
surfaces/focus/disabled states without silently altering canonical colors.

If class 3 becomes justified, proposed shared QML primitives are a data-free card
frame, semantic label/value, icon/control, bar and history-gap view. Use Plasma 6
`PlasmoidItem` and current APIs, with small adapters at widget boundaries.
Python drawing code cannot simply be imported into QML; share tokens, asset
provenance, state schemas and test vectors across renderers.
[Plasma 6 widget API](https://develop.kde.org/docs/plasma/widget/porting_kf6/).
No future Command Center shell, navigation, service or provider is implemented now.

## 5. Top toolbar, dock and genuine status icons

Top: 48 logical pixels, full available width, opaque, launcher/workspaces left,
system indicators/tray and clock right. Keep existing extra applets and their
settings; if target placement conflicts, report it rather than deleting them.
The independent desktop clock remains. Do not duplicate network/audio indicators
outside an already functioning tray unless a later plan explicitly requires it.

Dock: 56 logical pixels, bottom edge, centered and content-sized. Preserve the
existing task-manager instance, grouping/filter settings, ordered launcher URLs
and running-task behavior. The seven-slot D4B fixture is illustrative: it is not
authorization to pin those applications. Its ideal width is
`2*8 + N*40 + max(0,N-1)*8`, or 344 for seven slots. Native margins/task labels
may differ and running tasks can expand the dock. Overflow needs a reviewed
native fallback; do not discard pins, shrink implicitly or park widgets.

The exact 6.7.5 panel implementation supports fill/fit length, center alignment,
height, edge location, a floating boolean and an opaque mode. **Bottom location
plus floating=true** is the proposed route; the location value “floating” is not
a synonym for a bottom floating dock. Do not execute a layout script here.
The 8-logical-pixel bottom gap is a design target, not a promised public
arbitrary-margin setting; visual frame bounds and reserved screen space may
differ.
[Version-pinned panel API implementation](https://raw.githubusercontent.com/KDE/plasma-workspace/v6.7.5/shell/scripting/panel.cpp),
[panel geometry/lifecycle](https://raw.githubusercontent.com/KDE/plasma-workspace/v6.7.5/shell/panelview.cpp).

The stock network applet derives its icon from a connection-state provider;
the volume applet derives it from preferred sink volume/mute state and handles
missing devices/services. Keep those native data paths.
[Network source](https://raw.githubusercontent.com/KDE/plasma-nm/v6.7.5/applet/main.qml),
[audio source](https://raw.githubusercontent.com/KDE/plasma-pa/v6.7.5/applet/main.qml).

Proposed state verification matrix:

| Area | Required distinctions | Offline versus native evidence |
| --- | --- | --- |
| Network | disconnected, connecting, Wi-Fi strength, wired, disabled/airplane, unknown; VPN overlay where provided | Mock icon-name/state fixtures offline. Native observation later must match current backend state; do not toggle radios or connections to manufacture a test. |
| Audio | muted, low/medium/high, no physical output, service unavailable; input activity where supplied | Mock states offline. Later verify icon plus accessible tooltip against existing backend state, not just icon color. Audio device/mute changes need an explicit test scope. |
| Tray | hidden/passive versus active items, overflow and notifications | Preserve existing tray nested IDs/visibility and third-party status items; do not reconstruct the tray from a short list. |

## 6. Full HD/QHD and scaling

Keep D4A's model: logical width/height = physical dimensions / scale. Native
Qt/Plasma screen geometry, rounding and available-area measurements remain the
authority for a proposed native plan. Do not multiply QML geometry by scale a
second time. Qt documents device-independent coordinates; its general docs do
not establish this host's fractional-scale results.
[Qt high-DPI coordinate model](https://doc.qt.io/qt-6/highdpi.html).

| Physical output | Scale | Logical model | Compact / expanded |
| --- | --- | --- | --- |
| 1920×1080 | 100% | 1920×1080 | accept / accept offline |
| 1920×1080 | 125% | 1536×864 | accept / accept offline; expanded is tight |
| 1920×1080 | 150% | 1280×720 | accept compact, tight / **refuse expanded** |
| 2560×1440 | 100% | 2560×1440 | accept / accept offline |
| 2560×1440 | 125% | 2048×1152 | accept / accept offline |
| 2560×1440 | 150% | 1706.667×960 | accept / accept offline |

Five flavors give 55 accepted model cases and five expected refusals. D4B tests
ink/control/icon bounds, but does not establish stock-widget minima.

| Preference | Card width | Clock / media / weather / CPU / RAM heights | Padding |
| --- | --- | --- | --- |
| Compact | 288 | 88 / 120 / 112 / 96 / 96 | 12 |
| Expanded | 352 | 104 / 168 / 144 / 120 / 120 | 16 |

All values are logical pixels. Card order is fixed; margin 24, inter-card gap 12,
first y=72, x=logicalWidth−24−cardWidth. Compact stack height is 560; expanded
704. Dock y=logicalHeight−56−8. At FHD125 expanded, the stack ends at 776 and
dock begins at 800, leaving exactly the required 24 gap. At FHD150 compact,
the stack ends at 632 and dock begins at 656, also 24. Additional native frame
margins can invalidate both cases.

At FHD150 expanded the stack cannot fit; refuse before mutation. Compact and
expanded remain Panda preferences, not universal Plasma representations.
No automatic anchoring/repositioning on scale or output changes. Future plans
must bind the intended output identity and refuse stale geometry. Do not change
display scaling or graphics settings to make a native trial pass.

## 7. Identity and preservation contract

A future candidate plan must carry a fresh, explicit inventory and compare:

- Containment/applet numeric IDs, plugin IDs, parent containment, screen/activity
  bindings, applet order and nested tray identities.
- Ordered task launcher URLs, filters/grouping and unrelated applet configuration.
- Virtual desktop count, IDs/names/order, activity settings, desktop containment
  type, icon positions, wallpaper configuration, shortcuts and unrelated settings.

Use the actual desktop count. The broader original design's three-desktop goal
and D4B fixture's one desktop are not permission to change the user's count.
Existing applet bindings must be explicit; ambiguous duplicates cause refusal.
Never remove and recreate a containment or applet to “preserve its appearance.”
Never rewrite a plugin identifier under an existing numeric ID. No global-theme
layout template may reset the desktop.

The new five-card design can have a missing role. A missing instance is a
proposed additive change, requiring an exact approved role/plugin/parent plan;
it is never filled automatically from sample fixtures. Moving an existing
applet also requires a scoped plan even if its numeric ID is retained.

**Identity conflict:** a new Panda plasmoid is a different plugin, not a skin
setting for a stock applet. Under the present preservation contract, class 3
cannot silently replace any existing applet. If exact fidelity requires that,
stop at a gap report. A later user-approved design must reconcile identities
and visible duplicates before implementation/deployment; no ID reassignment,
hidden parking or reparenting workaround is permitted.

## 8. Work packages and gates

| Proposed work | Can be developed/validated offline after separate approval | Requires an authorized native environment |
| --- | --- | --- |
| Compatibility specification | Pinned source/schema mapping, explicit unknowns, mock inventories, refusal policies | Confirm actual host Qt/KF/Plasma/package builds, resources and current settings |
| Visual translation | Palette-derived supported style assets, provenance, contrast/SVG checks; conditional data-free QML primitives | Applet background inheritance, actual opaque frames, Qt metrics, focus, representation behavior and runtime warnings |
| State adapters | Interface/state schemas and fixtures only; no bus/provider objects | Real MPRIS, weather, sensors, network/audio semantics and service disappearance |
| Layout planning | Identity-preserving candidate diff, scale matrix, overflow/staleness refusal, fixture dry run | Supported minima, reserved area, screen mapping, fractional rounding, fit/floating behavior |
| Recovery/deployment design | Reviewable operation list and failure-stop policy; no claim of proven restoration | A separately approved recovery route and explicit bounded mutation authorization |

No D4C work package is implemented in this task. Offline QML execution also needs
a separately approved isolated harness, temporary HOME/XDG and denied session
bus/provider/network access; simply selecting an offscreen platform is insufficient.
Never run stock widget loaders, plasmoidviewer, plasmawindowed, nested Plasma or
sensor objects in the daily session as “offline validation.”

Suggested sequence for later authorization:

1. **D4C source/fixture preparation:** version-pin interfaces; draft only the
   supported visual assets and deterministic candidate plan after proposal review.
   Test malformed/stale inventories, independent face selection, canonical palette
   invariance and all geometry failures. No native connections.
2. **Native evidence gate, read-only scope:** operator-approved inventory of
   existing instances, pins/count/settings, installed resource/plugin versions,
   outputs and fonts. Files alone cannot prove widget behavior. Any runtime loader,
   GUI instance, service or provider access needs its own explicit scope.
3. **Gap review:** compare measured native behavior with D4B and classify each
   difference as acceptable stock variation, supported styling correction or
   class-3 blocker. Do not broaden the allowlist or mutate identities to pass.
4. **Controlled visual trial, separate authorization:** only after a reviewed
   recovery route, propose one existing official clock and one media instance,
   exact managed keys/rectangles and before/after checks. No new panel migration,
   sensor activation or weather networking in that initial scope. If suitable
   instances are absent, require a separate additive-instance decision first.
5. **Further gates:** CPU/RAM/KSystemStats activation, weather provider use,
   toolbar/dock changes and any custom plugins each need distinct deployment
   proposals and authorization. Existing D3B1A evidence stays untouched.

A recovery prerequisite may be satisfied only by separately reviewed evidence.
This proposal does not authorize reopening D3B1A, live backup/restore execution,
a VM, package installation or desktop mutation.

## 9. Acceptance before any wider native rollout

- Each of five roles remains independent; existing IDs/pins/count/settings match
  the approved preservation record, with only expressly approved managed deltas.
- Native screenshots/measurements identify build, output, scale, font and active
  flavor; they are separate from synthetic D4B assets.
- Opaque frames remain legible over light/dark wallpapers without blur. Record
  actual radius, margins, typography, glyph fallback, controls, keyboard focus,
  semantic contrast and dock bounds. Do not hide overflow with clipping.
- CPU/RAM defaults and alternate allowed faces are checked independently only
  under sensor authorization; missing data never becomes a healthy zero.
- Media capability/no-player/artwork states, weather missing/stale states and
  actual network/audio status are evidenced within their approved scopes.
- Every supported layout/flavor passes measured minima; unsupported combinations
  refuse. No automatic hotplug behavior is claimed.
- Scope, dry run, idempotence, failure stop and recovery readiness receive review
  before each mutation phase. D4A/D4B remain reproducible offline milestones.

## 10. Evidence provenance and review decisions

Research used official KDE/Qt/freedesktop documentation and KDE upstream
`v6.7.5` sources. Eleven version-pinned source files and SHA-256 receipts are
retained in the worktree's ignored `.local-ai/d4c-sources/`; source text was
inspected as data, never executed. The tag is an upstream reference, not proof
that the installed distribution build is byte-identical. Missing unpacked widget
directories are not proof of missing plugins: native resources need inventory.

The user's earlier trusted-host evidence reported Plasma 6.7.5, KDE Wayland,
FHD eDP-1 at scale 1 and an activatable KSystemStats backend. It is historical,
not fresh native validation. No session bus calls, live Plasma file inspection,
backend activation, package changes or D3B1A access occurred for this proposal.

Review is requested for the stock-first route and the explicit class-3/identity
stop condition. No native fidelity exception or deployment permission is implied
by approving this proposal alone.
