# Panda Desktop: offline planning and visual contracts

Panda supplies a deterministic layout planner, synthetic SVG/PNG previews and
generated Plasma Style sources. There is no desktop apply command. These tools
do not discover host configuration, contact D-Bus or activate widgets/providers.
Native rendering, deployment and recovery remain separately gated.

Start here for layout and fixture usage; see [compatibility and preservation](desktop-compatibility.md),
[Plasma Style assets](plasma-style.md), and the [native worker safety boundary](../../tests/native/README.md).
The theme manager and transaction APIs are documented separately in [manager.md](manager.md),
[transactions.md](transactions.md) and [live-integration.md](live-integration.md).

Authority is the current user request, AGENTS.md, the approved local ignored
`docs/superpowers/specs/2026-10-06-panda-theme-system-design.md`, and canonical
flavor manifests. The approved specification's recorded SHA256 is
`5904eb5532d5fc66d70918f959b499f3906bd20b0098c1a8fba5896eaad22db0`.
The tracked Panda skill reference supplies design context; it does not replace
that local authority. Preserve the actual desktop count rather than applying
the specification's initial three-desktop target.

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

## Detailed visual previews

## Commands and dependencies

Keep the existing D4A schematic commands. Detailed visual output is explicit:

    python3 -B theme/panda/common/desktop_cli.py preview --fixture tests/fixtures/desktop/visual/dock-seven.json --visual-fixture tests/fixtures/desktop/visual/playing.json --resolution fhd --scale 1 --presentation compact --flavor cyber

Add `--composition` only for a Cyber visual preview. Preview remains stdout-only;
there is no apply/install command. Supplying visual inputs to another command,
composition without visual inputs, or composition for another flavor fails.

Explicit artifact export:

    python3 -B theme/panda/common/desktop_visual_export.py --output-dir docs/panda-theme/previews/d4b

The exporter preserves byte-identical existing files and refuses conflicting
files, symlinks and unsafe export directories. For another render environment,
export to a fresh directory; do not reset timestamps or overwrite operator content.
Partial newly created exports can remain after an I/O failure; no transactional
recovery guarantee is claimed. Native configuration names/paths are never generated.

Detailed visual export requires the already available PyGObject bindings for
Pango/PangoCairo/librsvg and pycairo. D4A planning, validation and its original
schematic do not import these modules. No dependency installation is performed,
and missing measurement tooling causes a clear refusal rather than a guessed export.

## Renderer and data contracts

`desktop/visual.toml` holds the reviewed 12-pixel radius, padding, type scale and
semantic token references. It cannot substitute arbitrary color literals or
alter plugins. The canonical palettes supply all UI colors.

`visual_svg` supplies bounded surfaces, controls, progress bars, disconnected
linechart runs and actual glyph/icon measurements. `visual_style` supplies
semantic style/contrast checks. `visual_text` supplies isolated font shaping.
These drawing components take explicit data and can be reused by a later Panda
Command Center; this phase implements no Command Center, navigation framework,
runtime data acquisition or background process.

`desktop_visual_fixture` validates a separate strict presentation schema:
clock/time labels; playing/paused/no-player/unavailable media; available/stale/
offline/unconfigured weather; available/missing CPU; available/unknown-total/
missing RAM; and exact application/icon/running/selected dock states.
The original D4A FHD fixture is unchanged. The independent seven-slot fixture
retains its containment/applet IDs, pins and unrelated configuration and changes
only the explicit visible application sample list.

No missing sensor becomes zero. Unknown RAM total has no utilization fill.
Gaps in CPU history create separate paths; no interpolation invents samples.
A RAM linechart override reports missing history rather than fabricating a series.
CPU linechart and RAM horizontal bars remain defaults, and the existing two-face
allowlist stays independent per card. No native alternate face is exercised.

Controls are synthetic illustrations. Their active/paused/running/selection
states come only from fixtures, not the current desktop. Sample artwork is a
licensed Breeze audio-player illustration; missing artwork uses a distinct
placeholder. No third-party album cover is fetched or inferred.

## Font, icon and wallpaper provenance

The source asset directory contains SHA-256 records, unmodified source SVG
strings, notices and licenses. Assets are read with the existing guarded regular-file
reader and checked against their receipt before rendering.

- Noto Sans Regular 2.015: copied unchanged from the available local font,
  SHA-256 `478c558ea716033cd60c03438f628dfa75694dcf6b5f6d505a2f05fd2b4f3823`.
  Its embedded metadata and upstream font-specific
  [OFL notice](https://raw.githubusercontent.com/notofonts/latin-greek-cyrillic/main/OFL.txt)
  agree. The installed package's generic Apache notice is not used for this font.
- Nineteen selected Breeze sources: local `breeze-icons 6.31.0-1.1`; source paths
  and individual hashes are recorded in `breeze-icons.json`.
  [COPYING-ICONS](https://github.com/KDE/breeze-icons/blob/master/COPYING-ICONS)
  supplies KDE's artwork-library notice; the full notice and GPL text are included.
  Exports retain attribution/source references. Editor metadata is removed,
  local gradient references are prefixed, and reviewed symbolic CSS is resolved
  per icon without globally recoloring application artwork.
- The installed Okular sample had genuine off-canvas paint even when rendered
  directly by librsvg. It was excluded; the dock uses the reviewed Ark source.
- `cyber-overlook.png`: exact member of the user-approved design library,
  SHA-256 `bc21387ebaf407beed04596b89809950722c692e23c6ded487dca9adb95f92b7`.
  The archive documents it as a generated clean Panda wallpaper and records the
  matching hash. It is a QHD resize of 1672×941 artwork, not native-QHD generation.
  No baked-in UI reference, commercial character image or unverified album art is embedded.

Vendored license notices remove only upstream trailing whitespace; their source and normalized hashes are recorded and their full wording is unchanged. Raw fetched notices remain in the local development review inputs.

The source archive/reference image remain unchanged. License notices were checked
during development; runtime rendering never retrieves remote assets or licenses.

## Measurement, contrast and reproducibility

Actual shaping uses the vendored font in a private Fontconfig/Pango map and
verifies the resolved file identity. System fallback is disabled. Exported text
is glyph outlines, avoiding viewer font substitution. Full original labels remain
in accessible SVG titles/ARIA metadata. Ellipsis is shaped by Pango at the
available width, not estimated from character count.

The recorded environment is Pango 1.58.2, Cairo 1.18.6 and Fontconfig 2.18.3,
96-DPI shaping, explicit English language, hint metrics disabled and tabular
number features. Actual painted glyph bounds, control bounds, card padding,
icon paint extents and text/icon collisions are checked. Icon paint is measured
with librsvg on a Cairo recording surface at 8× precision (conservative 1/8-pixel
extents). No card clip masks conceal overflow. Nominal Pango line-box height can
exceed the explicit preview row; the renderer validates the actual ink placed
inside that row. This does not establish equivalent Qt/native line-box behavior.

Used semantic pairs pass the 4.5:1 text and 3:1 essential boundary/indicator
targets across all five palettes. Unused Gothic primary/surface (1.7622:1) and
secondary/surface (2.5588:1) fail the indicator target and are recorded as
candidate failures. Graphs/readable emphasis use the existing `accent_text`;
canonical color values are untouched. The report does not claim contrast for
every pixel of licensed multicolor icons or the decorative wallpaper.

The committed-D4A baseline receipt records original fixture/layout/palette bytes
and all eleven accepted model structures. Matrix checks verify all 55
flavor/layout cases and five expected expanded-FHD-at-150% refusals. Tight-fit
tests include long text, normal, unavailable and paused states. Export manifests
record source visual fixtures/specification, geometry identity, font/asset hashes, renderer source hashes,
environment (including Python/librsvg) and output hashes. Repeated exports must match byte-for-byte under
those inputs. Different rendering-library versions can change rasterization;
cross-platform pixel identity and native fidelity are unverified. Unsupported
glyphs fail clearly, including absent emoji/CJK coverage; no universal localization
or pixel-perfect native-layout claim is made.

## Maintained reference outputs

- Original D4A schematics: [FHD compact Hybrid](previews/fhd-compact-hybrid.svg)
  and [QHD expanded PandaWave](previews/qhd-expanded-wave.svg).
- [Five-flavor layout comparison](previews/d4b/five-flavor-comparison.png) and
  [Cyber composition](previews/d4b/cyber-composition.png).
- [D4B output hashes](previews/d4b/manifest.json) and
  [verification contract](previews/d4b/verification.json).
- [Native frame source models](previews/d4c3-s1/five-flavor-gallery.png).

The dated directory names and D4A/D4B fixture labels are stable reproducibility
identities. Their manifests, baseline fixtures and generator inputs are required;
do not remove them as disposable milestone reports.

## Native preservation and deployment gates

Prefer official applets in place and supported Plasma styling, then measure gaps.
A Plasma Style cannot style arbitrary applet internals. Custom Panda QML or a
third-party widget requires a separate source/license/version/identity decision;
never swap a plugin under an existing ID, hide duplicates, reparent or park
widgets to match an image. Reuse canonical tokens/assets/state schemas for any
future Command Center; no such application or service is implemented here.

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

Before any desktop mutation, obtain a fresh explicitly authorized inventory of
instances, ordered task pins, output/activity bindings, actual desktop count,
loaded builds/fonts and the affected configuration bytes/metadata. Receipts are
not backups. Establish and review a stopped/logged-out Plasma recovery route;
restore only a reviewed affected-file set, verify bytes/metadata and let the
operator resume. Do not restore active configuration or promise inode/ctime
preservation. Refuse stale source/destination receipts and unexpected identities.

D3B1A/R3 recovery remains unresolved. Do not read, repair, reuse or delete its
retained evidence, or claim that synthetic fixtures prove recovery. R0 session
observation is separately authorized; source review grants no live access.

The first bounded native layout proposal is one official clock and one media
widget on the existing desktop, preserving the panel clock, tray weather, panel
order, task pins, wallpaper and desktop count. Missing roles require explicit
additive-instance authorization. Review managed keys, minima, native font/frame
metrics, MPRIS no-player/paused behavior, accessibility, contrast and before/after
preservation. Stop on any drift, clipping or unexpected activation.
CPU/RAM/KSystemStats activation, weather networking, toolbar/dock migration and
custom plugins each need separate authorization and measured acceptance.
No automatic anchoring, hotplug handling, shrinking, parking or scale changes.

MPRIS controls must honor CanControl/CanPlay/CanPause/CanGoNext/CanGoPrevious/
CanSeek; paused progress must not advance. Unknown duration is indeterminate;
missing artwork uses a local placeholder, and no player differs from stopped.
The official private MPRIS import is not a stable custom-widget API. A new adapter
needs bounded image/URL handling and service-disappearance review. Weather needs
preserved location/units, provider attribution/terms and truthful stale/offline/
unconfigured states. Network/audio icons must reflect actual backend states,
including disconnected/connecting/disabled/VPN, mute/no-output/unavailable states;
never toggle connections or devices just to manufacture a test.

Use [the repository guide](../../README.md#development-and-verification) for the complete
offline verification commands. No offline success establishes native fidelity,
provider availability, Plasma fallback or safe live rollback.
