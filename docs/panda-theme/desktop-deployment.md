# Offline desktop deployment review package

This package prepares Sprint 2 composition and Sprint 3 manual deployment for a
future AMD Wayland host. Hybrid is the first candidate; Minimal, Cyber, Gothic
and Wave use the same structure. It creates review files only. Nothing here
activates a style, creates a widget, starts a provider or installs a package.

## Generate and review

From the repository, use an existing Python 3.11+ interpreter and Fish:

```fish
set review_root (mktemp -d /tmp/panda-desktop-review.XXXXXXXX)
python3 -B theme/panda/common/desktop_cli.py deployment-export \
    --fixture tests/fixtures/desktop/visual/dock-seven.json \
    --inventory tests/fixtures/desktop/deployment-inventory.json \
    --output-dir "$review_root/package"
```

The parent directory must already exist, belong to the current user and have
mode 0700. The target must be fresh. Symlinks, traversal, unsafe ancestors,
native configuration roots, repository destinations and existing targets are
refused. Export is bounded to 128 files, 2 MiB per file and 16 MiB total.
Repeat into another fresh private parent to compare bytes. `manifest.json`
lists SHA256 for every other file; no timestamps or absolute source paths enter
the manifest. An interrupted package is incomplete: preserve it for inspection,
then generate into a different fresh directory. Never resume over existing files.

The explicit sample inventory contains synthetic package versions, plugin and
face claims. It is not a host probe or an installation lock. The generator
checks every required package/plugin/face independently; having a package does
not prove that a plugin is present or that a loaded session uses that release.
An incompatible/unknown release still produces a review package with failed
prerequisites and empty native write sets. It never grants activation readiness.

## Contents and supported configuration

- `plasma-styles/`: all 45 byte-checked generated style files, nine per canonical
  flavor. `panda-pandawave-s1` is the canonical Wave package name. Solid frame
  assets, adaptive transparency off, blur off and the Breeze Dark fallback reuse
  the existing Plasma Style generator. Fallback assets still need native review.
- `fragments/clock-appearance.json`: the exact reviewed Plasma 6.8.2 Appearance
  subset, with typed values, pinned XML hash and a symbolic new-instance target.
  It proposes 24-hour time, date below, no seconds and automatic font sizing.
  It omits timezone/calendar/locale/font overrides. Existing clocks have no
  proposed settings writes.
- `fragments/media.json`: reviewed empty per-instance settings; the global
  `plasmaparc/General/VolumeStep` remains unchanged.
- `fragments/cpu-controller.json` and `fragments/ram-controller.json`: exact
  source-reviewed relative controller groups and JSON-string sensor lists,
  intended only after stock preset initialization. They are data, not directly
  loadable applet configuration files. Real containment/applet IDs and config
  ancestry must be selected and reviewed privately before any native write.
- `plans/`: explicit inventory failures, per-role identity-preserving proposed
  write sets, all layout outcomes and independent data/provider plans.
- `sources/`: portable source contracts and canonical layout/visual tokens;
  `plans/layout-input.json` records the actual validated layout input.
- `previews/`: opaque SVG schematics for accepted cases. These are synthetic,
  with neutral provider labels and anonymous pin slots. No native screenshots,
  host pins, media titles, weather locations or opaque configs are exported.

No executable installation or activation script is included. Never source,
evaluate or execute fixture/package data as shell or JavaScript.

## Exact prerequisites and failure gates

Required Arch-family package names are `plasma-desktop`, `plasma-workspace`,
`kdeplasma-addons`, `libksysguard` and `ksystemstats`. No package manager runs.
Plasma 6.8.2 is the exact clock/media/controller source target; versioned sample
claims such as `6.8.2-1` are examples rather than claims about future repositories.
The future host must record exact installed package builds, loaded Plasma/Qt/KF
versions and distribution patches under a separately reviewed observation scope.
Do not downgrade or assume a different release is compatible. Revalidate the
source contracts against the installed release before adapting the fragments.

Required plugin IDs: `org.kde.plasma.digitalclock`,
`org.kde.plasma.mediacontroller`, `org.kde.plasma.weather`,
`org.kde.plasma.systemmonitor.cpu`, `org.kde.plasma.systemmonitor.memory` and
`org.kde.plasma.icontasks`. Required faces: `org.kde.ksysguard.linechart` and
`org.kde.ksysguard.horizontalbars`. Confirm availability from the exact target
package inventories without loading widgets or starting providers. Inspecting
one installed version does not attest to the already-running session.

Stop if release/plugin/face evidence is missing, a model layout refuses fit,
native identities are ambiguous, ordered pins are unknown, baseline bytes or
metadata drift, a backup is untested, or the approved write scope changes.
The earlier laptop's timestamp drift and recovery gate remain unresolved;
this package does not authorize another laptop collection pass.

## Preservation and proposed write boundary

All existing panels, IDs, applet order, settings, tray children and application
pins stay intact. The model's top 48-pixel header is visual intent, not an
instruction to convert/move an existing panel. Do not recreate or reparent
existing applets. The floating bottom dock is a proposed additional panel only.
Keep its application-only role: no duplicated clock/tray/system telemetry.
Its 56-pixel height, 40-pixel icon intent, 8-pixel spacing/padding and bottom
clearance are design values. Actual floating/fit/spacing serialization and
effective margins are unresolved; configure and measure with the native UI only
under separate authorization. No guessed geometry/config keys are generated.

Existing eligible desktop role bindings retain their identity, parent and
settings; changing their settings requires a separate exact key-diff review.
An absent role gets one additive proposal with an unknown new ID. Multiple
matches require explicit selection, not automatic reuse. Panel clock and nested
tray weather never substitute for desktop instances. Real IDs are observed
after approved addition, never preallocated from synthetic fixture numbers.

Keep current desktop count, wallpaper, activity/output bindings and scaling.
The design target of three desktops is deferred when the baseline differs.
Record private runtime ordered pins without normalization; the portable package
contains only pin-slot counts. New dock pins require separate per-item choices.
No wallpaper path, user path or opaque native config is copied into this package.

## Operator sequence after separate native approval

1. Review the package hashes, failed prerequisites, exact write set and all
   native gaps. Use Hybrid for the first trial. Plasma Style selection applies
   across the Plasma session. The first trial may use an isolated session with
   one output. Approve only the selected package copies, style selection and
   additive objects/config keys. Network, player controls, sensors and weather
   initialization need explicit scope.
2. Establish a fresh stable private baseline using the repository's preservation
   contract: bytes, ownership/mode, identities, timestamps and supported xattrs.
   Record real panel/applet IDs, parents/order, tray children, private ordered
   pins, desktop count, wallpaper, output/scale and previous style. Saved files
   alone do not establish current runtime pins or output topology.
3. Prepare and verify a scoped backup of every exact file/key group that the
   approved UI operation may change. Typical candidates include
   `plasma-org.kde.plasma.desktop-appletsrc`, `plasmashellrc` and `plasmarc`;
   include `kdeglobals` only if a separately approved color operation touches it.
   Treat this as a proposed allowlist, not permission to read every file.
   Rehearse recovery on an isolated clean profile. If affected files or native
   serialization cannot be bounded, stop before activation.
4. After approval, use the file manager to copy the selected nine-file Hybrid
   style directory to the user data `plasma/desktoptheme/` directory only if
   its destination is absent. Do not replace a locally modified style. In
   System Settings → Colors & Themes → Plasma Style (the module name may vary
   by release), select Panda Hybrid S1. Preserve wallpaper, global fonts/icons,
   task pins and layout. Record the exact setting/file changes and verify opaque
   surfaces over contrasting wallpaper before continuing.
5. Add one object at a time using the native desktop edit UI. Observe its new ID
   and parent; retain every existing object. For monitors, allow the reviewed
   stock preset initialization only within approved sensor activation scope,
   then select the reviewed face and settings through the UI. Initial creation
   writes `CurrentPreset` and loads the stock preset; prewriting fragments can
   be overwritten. Do not bulk merge a JSON fragment into appletsrc.
6. Measure native minima and actual logical rectangles before using the matrix
   positions. The media full minimum is 14×10 effective Kirigami units; an
   illustrative 18-pixel unit yields 252×180, taller than both Panda card heights.
   If the stock representation cannot fit, stop for an explicit design decision.
   Do not hide controls, force a calendar/representation or use a geometry setter.
7. Configure the new application-only dock manually and record its actual native
   storage and margins. Preserve every existing panel and pin. Leave Weather
   unconfigured and network off until provider/location/privacy approval.
8. Compare the fresh post-change baseline with the allowlist. Verify preservation
   and visible behavior; record failures/unverified states. Copy the other four
   styles only after Hybrid passes. Flavor changes must leave structure intact.

`panda-theme` already provides canonical palettes, deterministic selection and
transaction contracts for supported adapters. Its CLI still reports desktop
Tier 1 coverage as pending. This package reuses its style/palette sources and
does not add an automatic desktop adapter or claim a complete live transaction.

## Recovery

Stop immediately on drift, unexpected affected files, ambiguous IDs, clipping,
provider/network activity outside scope or loss of focus/navigation. Do not
retry against changed configuration. Preserve partial evidence privately.
After separate recovery approval, remove only newly added objects by their
recorded IDs using the UI, and reselect the previous style. Keep all preexisting
objects and pins. Remove a copied style directory only after switching away and
only when its hashes still match the package.

If UI recovery cannot restore the bounded state, use the previously rehearsed
scoped backup route with an approved logged-out/session-safe procedure. Never
overwrite a live whole appletsrc file, restart Plasma blindly or assume a backup
proves restoration. Confirm baseline bytes/metadata and runtime preservation
after recovery. No recovery script or compositor restart is supplied.

## Clean-host test matrix

| Dimension | Cases | Evidence required before success |
| --- | --- | --- |
| Release | 6.8.2 source target; actual future AMD release; missing/mismatched build | Exact installed/loaded versions, package/plugin/face inventory, reviewed patch/schema parity; mismatches stop |
| Output | FHD/QHD × 100/125/150%, compact/expanded | 55 accepted model cases and five FHD150 expanded refusals across flavors; native available area, DPR and content bounds measured |
| Structure | Hybrid then Minimal/Cyber/Gothic/Wave | All existing IDs/order/parents/tray/pins/count/wallpaper unchanged; only approved new objects |
| Data | Clock date; media no-player/paused/missing-artwork; CPU/RAM valid/missing/stale/gaps; Weather unconfigured/offline | Truthful unknown states and capability controls; no fake zero/percentage or interpolated gaps; stock missing-sensor zero fallbacks remain a native blocker |
| Visual | Opaque surfaces; compact/expanded cards; long text | Canonical surface/text/focus tokens, native fonts/icons, padding, contrast and clipping measured; no blur dependency |
| Input | Keyboard Tab/Shift+Tab, activation keys, visible focus, scaled pointer targets | Native accessibility names, focus order/visibility and control bounds verified; previews do not attest to keyboard behavior |
| Failure | Missing face/plugin; native minimum overflow; interrupted copy/addition; metadata drift | Stop without wider writes; exact partial evidence; rehearsed identity-scoped recovery restores preservation |

The visual source uses Noto Sans reference metrics, Breeze icon samples,
12/16-pixel card padding and the canonical focus token. These are offline design
values; no global font/icon changes are proposed. Stock widgets inherit the
active Plasma palette and native typography. Exact radius, spacing, focus,
screen-reader behavior, floating margins, provider initialization, missing/stale
monitor fidelity and live five-flavor switching still require the approved AMD
session test. CPU-only schematic/PNG output cannot close those gaps.
