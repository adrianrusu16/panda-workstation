# Panda Desktop D4A — offline layout implementation

D4A supplies declarative desktop intent, a strict validator, deterministic
dry-runs and synthetic SVG previews. It does not apply a Plasma layout, install
packages, instantiate widgets, contact DBus, read live Plasma configuration or
activate sensors. There is deliberately no apply or restoration command.

The R3 directory-enumeration issue remains unresolved. Neither D4A tests nor
its fresh fixtures establish successful D3B1A recovery.

## Run from the repository

Python 3.11+ and Fish are already used by Panda Workstation. No new Python
dependencies are needed. The fixture must be explicit; HOME and XDG locations
are never used as desktop inputs.

    python3 -B theme/panda/common/desktop_cli.py validate --fixture tests/fixtures/desktop/fhd.json
    fish --no-config theme/panda/common/scripts/panda-desktop.fish dry-run --fixture tests/fixtures/desktop/fhd.json
    python3 -B theme/panda/common/desktop_cli.py preview --fixture tests/fixtures/desktop/fhd.json --resolution qhd --scale 1.25 --presentation expanded --flavor wave
    python3 -B theme/panda/common/desktop_cli.py packages --fixture tests/fixtures/desktop/fhd.json
    fish --no-config bootstrap/install-desktop.fish --dry-run

JSON and SVG are emitted only to stdout. Redirecting stdout is an explicit
artifact export, not native application. The installer dry-run uses one read-only, validated
pacman -Qq inventory; the desktop CLI instead uses a synthetic installed
inventory and never launches a process. The installer rejects unknown options.

The five flavors use the existing canonical TOML palettes, including wave's
canonical pandawave slug. Layout structures and their SHA-256 fingerprints are
identical across flavors. No new colors or theme-switching behavior are added.

## Configuration contract

The source is theme/panda/common/desktop/layout.toml. Schema version is integer
1. The validator rejects unknown/missing fields, booleans as numbers, invalid
numeric ranges and unreviewed plugin/face mappings. All geometry is in logical
pixels; physical output dimensions are divided by scale before placement.

| Element | Intent |
| --- | --- |
| Top bar | Full available width, 48 logical pixels, opaque; launcher, workspaces, system tray and clock/status roles |
| Application dock | Floating intent, centered and content-sized, 56 logical pixels, with 8 logical pixels of model bottom clearance; applications only |
| Desktop cards | Clock, media, weather, CPU, RAM, in that order, right-column placement preference |
| Compact | Width 288; heights 88, 120, 112, 96, 96 |
| Expanded | Width 352; heights 104, 168, 144, 120, 120 |
| Margins / gaps | 24 / 12 logical pixels |

The dock's floating flag and bottom_clearance are explicit offline intent;
bottom_clearance is configurable from 1 to 32 logical pixels, default 8.
The widget column reserves the dock rectangle, that clearance and the regular
24-pixel separation. The top-bar clock role is separate from the independent
desktop-clock binding; the system-tray role supplies status intent. No new
native instance is allocated.

Dock width is 2*padding + visible application slots*icon size + inter-slot
spacing. The explicit fixture applications list represents distinct visible
pinned/running application slots, not a live task observation. More slots change
the model width; overflow is refused.

FHD is 1920x1080; QHD is 2560x1440. Supported model scales are 1, 1.25 and 1.5.
Compact fits all six combinations. Expanded fits all except FHD at 150%, which
fails explicitly. There is no automatic fallback, shrinking, widget parking,
hotplug handling, reparenting or scale change. Select another explicit preference.

These card sizes are planning preferences, not measurements of stock Plasma
minimum/preferred sizes. Compact/expanded do not promise universal native
presentations. Right-edge coordinates are calculated for this one input output;
automatic native anchoring is unverified.

## Fixture and identity contract

tests/fixtures/desktop/fhd.json is synthetic. Its explicit scope is
panda-desktop-offline-fixture and schema_version is integer 1.

- output: name, physical width/height, scale.
- desktop_id and desktop_count: preserved, never changed to the older
  specification's three-desktop target.
- panels: unique IDs and complete applet-ID membership lists.
- applets: unique ID, containment_id, plugin, optional geometry rectangle and
  opaque JSON config. Unknown user applets and their config are preserved.
- bindings: exactly clock/media/weather/cpu/ram, with null or an explicit existing
  desktop instance ID of the correct official plugin.
- applications: distinct visible application identifiers for dock modeling.
- installed_packages: distinct synthetic package names.
- providers: five explicit synthetic labels; unavailable/unconfigured are valid.

A panel ID cannot collide with a desktop or applet ID; dangling memberships,
duplicate bindings and wrong-plugin/containment bindings fail. An existing
unbound matching desktop widget fails instead of silently creating a duplicate.
The planner does not select among ambiguous instances.

A null binding requests future creation without inventing a Plasma instance ID.
An explicitly bound widget already at the requested rectangle yields keep;
another rectangle yields move_requested. Replanning the same fixture is
deterministic. The input is never mutated. The complete preserved_fixture is
included in JSON, together with canonical fixture/layout/structure hashes, so
pins, tray configuration, weather setup, workspace count and unrelated instances
remain reviewable. Use sanitized fixtures only: do not put credentials or private
player data into fixtures or publish plans containing them.

Inputs must be regular files, at most 1 MiB, with no final symlink. Reads use
O_NOATIME and fail if unsupported/denied; there is no timestamp-reset fallback.
Descriptor and final path identity/metadata are rechecked using exact nanoseconds.
Duplicate JSON keys, non-finite numbers and malformed documents are refused.
No host discovery or enrollment is performed.

## Official KDE requirements

The default desktop package manifest now explicitly declares:

| Package | Purpose |
| --- | --- |
| plasma-desktop | Desktop containment, application launcher/task manager and workspace integration |
| plasma-workspace | Clock, media controller, CPU/RAM monitor applets and shared workspace components |
| kdeplasma-addons | Official weather applet and providers |
| libksysguard | Native sensor faces, including preferred CPU line chart and RAM horizontal bars |
| ksystemstats | Sensor backend dependency, with activation still separately gated |

The standalone plasma-systemmonitor application is not required to instantiate
these workspace applets and is not added. Installing the backend in a later
authorized package operation would not constitute approval to start it or probe
hardware.

Package contents are documented by the official Arch inventories for
[plasma-workspace](https://archlinux.org/packages/extra/x86_64/plasma-workspace/files/),
[kdeplasma-addons](https://archlinux.org/packages/extra/x86_64/kdeplasma-addons/files/)
and [libksysguard](https://archlinux.org/packages/extra/x86_64/libksysguard/files/).
Current inventories include compiled clock/media/weather applet plugins; do not
assume each applet has a standalone installed metadata.json file.

[KDE's scripting API](https://develop.kde.org/docs/plasma/scripting/api/) documents
panel height, edge location, center alignment and fit/fill length modes. JSON native_properties
records that intended vocabulary. It is not executable scripting and does not
select or mutate a live panel. Exact screen mapping, logical sizing and opacity
configuration must be verified on the pinned native release. Floating margin
behavior is deliberately deferred; bottom_clearance is a model preference,
not a claimed native scripting property or a measured native margin.

The offline package check rejects invalid names and duplicate entries across
all packages/*.txt files, and requires each KDE requirement to appear once.
bootstrap/validate.fish also checks duplicates globally. The package installer
helper rejects duplicates/invalid entries in its supplied manifest before any
pacman query. It obtains one validated installed-name inventory with pacman -Qq. Every
nonzero inventory status (including 1, 2 and 127) is a retrieval failure, never
package absence. Unavailable executables, empty inventories, malformed names
and duplicate names fail closed before any successful plan or sudo. Confirmed
absence means a requested package is absent from a successful inventory.
It submits only missing packages with --needed, preserves pacman output and
propagates installation failure. After an installation it retrieves a fresh
validated inventory and verifies all requested names; an idempotent run reuses
the already-validated inventory. --dry-run returns before sudo or installation.

Normal desktop package installation also requires an explicit plasma target:
--profile plasma or an exported PANDA_DESKTOP_PROFILE=plasma. No session probing
or inference is used. Missing/unsupported selection fails before package queries.
An unselected --dry-run remains available as read-only planning; it does not
establish eligibility for installation. The workstation orchestrator inherits
PANDA_DESKTOP_PROFILE, so an operator must select it before a later authorized
normal setup run. This correction does not run that installer.

CPU/RAM face values are independently configurable through the small reviewed
allowlist org.kde.ksysguard.linechart and org.kde.ksysguard.horizontalbars, both
supplied by the required libksysguard package. CPU linechart and RAM horizontal
bars remain defaults. Plugin/package identities stay fixed. Other widgets
still require the empty face field; arbitrary plugin and unknown face IDs fail.
Accepted alternatives are design intent only, not native presentation evidence.

Optional third-party widgets are excluded. Adding one requires review of source,
license, permissions and dependencies, an immutable version/content lock and a
separate installer opt-in. No Get New Widgets fetch/install path exists here.

## Verification and remaining native requirements

    python3 -B -m unittest discover -s tests -q
    fish -n bootstrap/lib/packages.fish bootstrap/install-desktop.fish theme/panda/common/scripts/panda-desktop.fish
    fish --no-config bootstrap/validate.fish
    git diff --check

Tests cover the resolution/scale/preference matrix, flavor invariance, strict
schemas, fixture identity/binding/pin preservation, deterministic keep/move intent,
SVG parsing/escaping, malformed/oversized/nonregular/stale inputs, package
duplicates, idempotence and dry-run/failure behavior through disposable command
stand-ins. No test uses live KDE, sensor streams or a real package installation.

Still unverified: stock minimum/card extents, compact/expanded widget behavior,
native font clipping, zero/one/multiple MPRIS players, weather provider behavior,
CPU/RAM sensor IDs and CPU history face configuration, automatic anchoring,
actual panel opacity/sizing, and host GPU/QHD behavior.

## Recovery design and first controlled deployment proposal

No recovery is executed or claimed. Before any live layout change:

1. Capture a fresh trusted version/plugin/output inventory, all applet/containment
   IDs, task pins, panel order, desktop count and the six configuration files'
   exact bytes and supported metadata. Store new evidence in a separately approved
   location; D4A does not access or reuse the retained D3B1A tree.
2. Demonstrate a logged-out/stopped-Plasma recovery route under separate scoped
   authorization. Refuse stale source/destination snapshots, unexpected identities
   or permission drift. Restore only a reviewed affected-file set while Plasma
   is stopped, verify bytes/metadata, then let the operator resume the session.
   Do not restore active configuration or promise preservation of inode/ctime.
3. Review an explicit mapping from desired roles to existing native instances.
   New IDs must come from Plasma, followed by a fresh inventory. Preserve all
   unrelated IDs, pins and providers. No default-layout replacement script.
4. First proposal: operator-controlled addition of one official clock and one
   media widget on the existing desktop, with before/after crops and instance
   inventory. Keep current panels, pins, workspace count, wallpaper and weather.
   Observe native size/clipping and MPRIS no-player/one-player behavior. No CPU/RAM
   widget or backend activation, package installation, restart or automatic
   application is included.
5. Stop for review. Top-bar/dock migration, all five cards, weather networking and
   CPU/RAM activation each need a subsequent measured plan and explicit scope.

This proposal is not deployment authorization. The current canary branch and
untracked files are preserved. D4A is finalized as an offline milestone; native
deployment and recovery remain separately gated.

## D4A-Fix observation disposition

- Desktop-profile eligibility: confirmed missing gate, corrected before normal
  package queries/installation. Host hardware identity is not a desktop profile.
- Dock centering/content sizing: already satisfied. Floating intent and bottom
  clearance: confirmed declaration gaps, corrected with floating=true and an
  8-logical-pixel default clearance. Actual native margin behavior is deferred.
- Top-bar status: already satisfied by system_tray. Its separate clock role was
  missing and is now explicit alongside the desktop clock.
- The two P2 findings are covered by regression tests. No native widgets,
  alternate sensor faces, desktop migration or recovery were exercised.
