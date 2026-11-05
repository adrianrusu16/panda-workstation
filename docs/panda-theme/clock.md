# Official desktop clock candidate and operator trial

D1 prepares one **additional official Digital Clock** for issue #34. It does not
create an instance, discover the live desktop, change configuration or establish
native functionality. The historical D4C1 clock/media candidate remains unchanged.
No custom PandaClock, theme switch, provider or Setup Manager work is included.

## Reproduce the offline proposal

From the repository, with explicit synthetic input:

    python3 -B theme/panda/common/desktop_cli.py clock-candidate --fixture tests/fixtures/desktop/assessment/sanitized-shape.json --plasma-version 6.8.2 --clock-schema tests/fixtures/desktop/clock-6.8.2.xml

The existing Fish wrapper accepts the same arguments. Output is stdout-only JSON:
one proposed plugin, target fixture containment, **null instance ID**, zero
executable operations, preserved fixture and required stop conditions. Existing
or ambiguous desktop clocks are refused; the panel clock is never reused.
Repeated planning allocates nothing. `--flavor` labels the preview comparison;
it does not select or activate a native style. Both size preferences are included;
layout overrides and `--apply` are refused. Existing preview/validate/package modes
retain their behavior. Pure Python APIs in `desktop_clock_candidate.py` also
validate settings and candidate payloads, without acquiring any native authority.

The version is an explicit input claim, **not runtime discovery**. The XML must
match SHA-256 `06b085a2451b7197253c4c425c61f150ce89ef2f127c7186eb90039e5ddd7c21`.
That pins upstream schema bytes, not a distro binary or running plugin. The
fixture is an unmodified KDE source resource; attribution and immutable URLs are
in [source references](clock-source-references.json). Tests use it offline.

## Plasma 6.8.2 compatibility

Review pins plasma-workspace commit
`30beb0095873364c6b34ebcfd292ecafd4db7f61` and libplasma commit
`6f6566e4ec44a432abdcdd4854cbed3582bcddd1`, both resolved from `v6.8.2`.
Blob identity and immutable tree membership were checked for the selected sources.
Local static metadata reports `plasma-workspace 6.8.2-1.1` and the root-owned
regular `org.kde.plasma.digitalclock.so`; no plugin was loaded. Distro patch or
loaded-process equivalence and the effective current style remain unestablished.

| Area | Verified static contract | Native limit |
| --- | --- | --- |
| Plugin | `plasma_add_applet(org.kde.plasma.digitalclock)` embeds clock QML and `main.xml` | Registration does not prove a working instance |
| Settings | Appearance group and types below match XML and configuration UI | Only the seven-key D1 subset is accepted |
| Time | UI indices 0/1/2 mean 12-Hour/region defaults/24-Hour; implementation uses Qt check-state values | Locale still controls separators/digits; no global locale change |
| Date | `custom` uses `Qt.locale().toString` with the requested format | Localized weekday/month length may wrap or shrink |
| Font | Automatic follows the system font and fits available space | No exact Noto Sans or 38/44 px guarantee; manual font size is in points |
| Background | Clock requests `ShadowBackground \| ConfigurableBackground`; libplasma `StandardBackground=1` requests the current theme's standard background | Standard does not guarantee opacity. Only the new widget may request it; no global style change |
| Clock view | Preferred representation is compact; desktop form-factor minimum is 3×3 Kirigami grid units | Native units, frame margins and font fit must be measured |
| Full view | Calendar: minimum width 22 units, or 45 with agenda/multiple clocks; maximum 80. Height 25–40 units | Panda “expanded” size preference does not mean full/calendar representation |
| Placement | `Widget.setGeometry` body is disabled/no-op | Operator edit mode only; no config geometry patch or scripting workaround |

The settings are revalidated from the pinned XML, `configAppearance.qml` and
`DigitalClock.qml`, not inferred from the historical 6.7.5 candidate. XML and UI
files happen to retain their older hashes; main/clock behavior was inspected at
the new commit separately.

| Exact proposed key under the new instance | Value | Meaning |
| --- | --- | --- |
| `Appearance/showDate` | `true` | Date visible |
| `Appearance/dateFormat` | `custom` | Explicit Qt date pattern |
| `Appearance/customDateFormat` | `dddd, d MMMM` | Localized weekday, day and month |
| `Appearance/use24hFormat` | integer `2` | 24-Hour; XML UInt, UI index 2 |
| `Appearance/dateDisplayFormat` | integer `2` | BelowTime; Adaptive=0, BesideTime=1 |
| `Appearance/showSeconds` | integer `0` | Never; ToolTip=1, Always=2 |
| `Appearance/autoFontAndSize` | `true` | Automatic typography |

No timezone, `timeFormat`, calendar provider, font family/size, pin or locale keys
are managed. A new instance starts with stock defaults (including Local timezone
and no enabled event plugins); it does not inherit private panel-clock settings.
Existing instance settings remain untouched. StandardBackground is a separate
new-instance background request, not an Appearance XML entry.

## Stock versus Panda visual gaps

Comparison is **source versus synthetic previews**, not a screenshot of a live
stock clock. Existing D4B previews use Noto Sans, 38/44 px time, 12/16 px padding
and a 12 px frame radius. Stock automatic layout follows native fonts, fitting,
Kirigami spacing and current style frames. Appearance exposes no D1-supported
per-widget radius, padding, accent or exact preview font-size controls.

| Flavor | Preview time (`accent_text`) / surface | Opaque time contrast | Muted date contrast | Stock baseline gap |
| --- | --- | --- | --- | --- |
| Minimal | `#DDE3E6` / `#14171A` | 13.88:1 | 5.85:1 | Neutral Panda frame/tokens unactivated |
| Cyber | `#20D7F2` / `#0E1620` | 10.45:1 | 6.93:1 | Cyan accents/frame unactivated |
| Gothic | `#DBA5B5` / `#151012` | 9.03:1 | 5.58:1 | Rose/charcoal frame unactivated |
| Hybrid | `#36C5E8` / `#151B23` | 8.50:1 | 5.72:1 | Blue/slate frame unactivated |
| PandaWave | `#FB2AA9` / `#101420` | 5.25:1 | 7.66:1 | Wave accents/frame unactivated |

Ratios are computed from canonical opaque sRGB palette tokens, not measured
native pixels or wallpaper contrast. Stock does not necessarily give time its
preview accent or the date its muted token. Effective native colors, small/shrunk date readability,
focus visibility, scaling and opacity remain trial observations. Compact 288×88
and expanded 352×104 **logical pixels** are shared design targets across all five
flavors, not guaranteed native sizes or a request to change representation.

The essential first requirements (24h, date, seconds hidden, automatic typography)
are supported. Exact frame/type parity is deferred to a separate appearance
slice. There is no demonstrated essential gap justifying a custom PandaClock.

## D2a authorization sheet — proposed, not executed

This sheet requires separate owner approval. D1 authorizes no native trial.
Approval must identify the reviewed source revision, attended session, target
output/activity/desktop containment **D**, and the fresh baseline below. Fixture
ID 10 is synthetic and must never be substituted for an observed native ID.

### Before any mutation

1. Establish the ordinary user, Wayland session, actual output/scale, running
   Plasma/plugin identity, target containment and absence of a standalone clock.
   Confirm panel clock, tray, wallpaper, current desktop count, ordered pins and
   existing widget identities using separately reviewed read-only observations.
   Saved config alone cannot establish live pins or loaded plugin identity.
2. Take private 0700/0600 recovery copies and preservation receipts for the seven
   existing config files below, with safe non-following, atime-preserving reads.
   Record bytes/hash, device/inode, owner/mode/link count, xattrs, size and all
   timestamps; record missing files as missing. Take two stable observations
   around a quiet interval, covering both file identity and relevant live state.
   An unsafe read, concurrent writer, unknown binding or any unexplained drift
   blocks the trial. Do not inject loaders/scripts to fill an observation gap.
3. D0 recorded unexplained mtime/ctime drift in `kwinoutputconfig.json`; final
   byte equality was not established. Do not repair, restore or normalize it.
   D0 receipts are historical context, not a mutation baseline. Require fresh
   stability; if drift recurs, stop and retain evidence without retry/repair.
4. Confirm the supported UI exposes background selection and settings below,
   and that scoped removal/recovery can target only the newly observed ID.
   Resolve native persistence keys for the new layout entry before approval;
   this sheet does not invent a raw geometry key or authorize unknown writes.

### Exact proposed operations

Through operator-attended Plasma UI only, enter edit mode on **D**, add exactly
one `org.kde.plasma.digitalclock`, and record the **allocated N** and its parent
before configuring it. Stop on existing/ambiguous clock, wrong plugin/parent,
duplicate creation or an inability to identify N. Never preassign N, touch the
panel clock, reparent a widget, use a layout template or run `evaluateScript`.

Configure **N only** with the seven Appearance keys above and request its
standard background using the supported widget UI (`userBackgroundHints=1`,
StandardBackground in the pinned API). If that UI or correspondence cannot be
verified, stop; do not patch config or substitute a native loader. This is the
current Plasma style, not a Panda style installation or global color change.

Use edit-mode handles to place N in an unoccupied operator-selected region and
try compact 288×88 logical pixels first. Record the actual accepted rectangle,
native minimum, margins and font fit. Expanded 352×104 is only an alternate
preference if separately selected in the approval; do not force calendar mode,
change scale or move another widget to obtain a fit. Exit edit mode.

Expected persistence is confined to N's subtree in
`plasma-org.kde.plasma.desktop-appletsrc`, its new desktop membership/layout entry
under D, and N's background preference. Existing entries in shared serialized
layout values must remain semantically identical. UI defaults may be serialized
for N; record them, and refuse nondefault timezone/calendar/network-provider
settings. No direct file editing is authorized by this sheet. Whole-file bytes
and timestamps of appletsrc necessarily change; unexplained serialization or
writes outside these exact additions require stopping, not normalization.

### Protected state and after checks

All other appletsrc groups/instances, panel IDs/order, tray and its nested
instances, launchers/pins, wallpaper, locale/timezones/calendar settings, output
bindings, virtual desktop count and geometry of existing items must remain
unchanged. These six config files must retain their baseline bytes and metadata:
`plasmashellrc`, `kwinrc`, `kdeglobals`, `plasmarc`, `kactivitymanagerdrc`,
`kwinoutputconfig.json`. Do not create missing files. No package, service, theme,
autostart, machine-policy or other config change is included.

Repeat protected-file receipts and live observations after save/settling. Diff
appletsrc structurally against its fresh copy, permitting only N and its exact
new membership/layout/background entries. Preserve raw private evidence and a
sanitized summary. Metadata-only change in a protected file still fails this
preservation gate even if bytes match; do not attribute it without evidence.

Observe at least two minute transitions against the session time without changing
the clock. Verify 24h, localized date/weekday, no seconds (including tooltip),
automatic type, readable unclipped text and an opaque stable background against
the current wallpaper. Check keyboard focus/activation, tooltip and opening and
closing the stock calendar; do not pin it, select another timezone, enable event
plugins, open external links or launch time/date settings. Calendar interaction
may serialize state; any write outside the approved additions stops acceptance.
No network action is needed for this trial. Preserve the panel clock/tray
behavior and layout. Record actual output/scale and only claim that tested case.

### Recovery and stop conditions

Stop on identity/version drift, unsafe baseline, unexpected writes, unreadable
time/date, translucency artifacts, inaccessible controls, fit failure or unclear
ownership. No automatic retry, restart, restore or broad rollback is permitted.
Recovery copies are evidence, not permission to overwrite live Plasma config.

A separate trial approval may allow the operator to remove **N only**, after
confirming its plugin and parent, then verify removal and preservation again.
This cannot promise byte-for-byte restoration, unchanged timestamps, global
rollback or recovery of concurrent changes. If scoped removal is uncertain or
preservation fails, retain the current state/evidence and request a recovery
decision; never reset/recreate the desktop or restore the whole appletsrc while
Plasma is running. Existing Host Canary recovery mechanisms remain out of scope.

Passing D1 tests means the candidate is reviewable. Native D2a acceptance remains
blocked on separate authorization and successful fresh baseline, identity,
appearance, interaction and preservation observations.
