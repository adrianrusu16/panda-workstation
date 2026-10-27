# D4C1 — first clock/media candidate

Status: **offline candidate; blocked for native execution**.
See [machine-readable synthetic candidate](d4c1/clock-media-candidate.json),
[compatibility](desktop-d4c1-compatibility.md) and
[host inventory](desktop-d4c1-inventory.md).

## Existing and proposed instances

The saved desktop has neither a desktop clock nor a media applet. Its existing
panel clock remains in place with the same plugin, ID, parent and settings.
The tray's weather applet, all seven panel slots, 16 nested tray applets,
virtual desktop count 1, task configuration and unrelated desktop settings
are outside the candidate's change set.

Both selected roles therefore have instance_id=null and
binding=new_instance_proposed. This is an explicit future addition request,
not a created instance, allocated ID or instruction to replace a panel applet.
The private candidate records the real saved desktop parent and panel-clock
identity. Public numeric IDs and ordered launcher samples are synthetic.
The current runtime pin order remains unknown and must not be inferred from
the fixture's two example pins or D4B's seven-slot dock.

If future inventory finds exactly one eligible desktop instance, the tested
builder reuses its ID without reparenting. The classifier reports multiple matching desktop instances as ambiguous and
requires explicit operator selection; panel and nested tray matches are never substituted.

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

## Stops and recovery gates

The JSON always sets ready_for_native_test=false and native_verified=false.
Stop before any mutation until all of these are separately resolved:

1. On-disk Plasma 6.8.1 differs from approved source baseline 6.7.5; loaded
   versions and schema compatibility require confirmation.
2. Active output/activity and actual runtime ordered pins are unobserved.
3. Two new applets need exact additive-instance authorization; the existing
   panel clock/tray must be preserved.
4. Geometry setter is unsupported at the baseline; operator placement/sizing
   needs an explicit bounded native test scope and measurement method.
5. Media minima/representation and Qt/font/frame behavior remain unmeasured.
6. A separately reviewed recovery route, source-freshness checks, managed-key
   boundary and failure-stop procedure are prerequisites to any native write.
   D4C1 receipts are not backups and do not prove restoration.

The final inventory check also found intervening mtime/ctime drift in the saved
output configuration despite identical bytes. Host collection stopped. The
private candidate reflects the earlier snapshot; neither it nor the synthetic
JSON is a fresh executable host plan. Require a new stable preservation baseline
under separate authorization before relying on output geometry.

Do not reopen or repair historical D3B1A evidence as part of these gates. No
Plasma restart, service activation, sensor/weather/network request, package
installation, graphics change, theme switch or live restoration is authorized.
D4C1 stops with this candidate for review; native implementation remains separate.
