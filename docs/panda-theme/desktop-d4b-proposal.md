# Panda Desktop D4B — offline visual-design implementation proposal

Status: proposed for review, 2026-10-22. No D4B implementation has started.
Baseline: D4A commit `bdfa0bf58c8091b4899401bd8b42bfda12e82cb3`
on `codex/feat-panda-desktop-d4a`.

## Intended outcome and authority

Develop an offline visual specification and deterministic fixture previews for
five independent desktop cards, a top toolbar and a floating application dock.
The visual language should recall the original Cyber Wildcard reference while
remaining recognizably Panda in every approved flavor. Preserve D4A's geometry,
identity model, official plugin/package mappings and explicit failure behavior.

The user requested a proposal before implementation. This document is the
review artifact; its proposed files, assets and verification work are future
work. It grants no authority to apply a layout, install anything, start a service,
deploy widgets or perform recovery. D3B1A/R3 remains unresolved and separate.

Authority: current request, repository AGENTS.md, approved Panda Theme System
specification, canonical flavor manifests, then visual inspiration. The broader
specification's dashboard and workspace targets do not expand this five-card
scope or authorize changing the existing workspace count.

## Reference and source provenance

The original image was located and visually inspected at:
[panda-cyber-wildcard-desktop-qhd-2560x1440.png](/home/adrian/Downloads/panda-cyber-wildcard-desktop-qhd-2560x1440.png).

- Image dimensions: 2560 × 1440.
- SHA-256: `72ba7d7fed06dc49a30b98d91e44808be821ddc6d9c82b19cfb08885ee6c22f3`.
- It is a visual reference, not evidence of a running Plasma configuration or
  supported plugin features. Its visible versions, readings and date are artwork.
- Do not redistribute the image, wallpaper or album art without establishing
  their reuse rights. Keep this source image unchanged.

Canonical palettes are the five tracked `theme.toml` files under
`theme/panda/{minimal,cyber,gothic,hybrid,pandawave}`.
`wave` resolves to `pandawave`; it is not a sixth palette.
The approved specification is
`docs/superpowers/specs/2026-10-06-panda-theme-system-design.md`;
the Panda skill's design-spec reference supplies the corresponding design context.

| Reference observation | Proposed D4B treatment |
| --- | --- |
| Separate rounded clock, media and weather frames in a right column | Retain independent framed cards and clear spacing |
| A combined system dashboard and a workspace card | Use separate CPU and RAM cards; workspace navigation stays in the toolbar |
| Bright time, clear media hierarchy, outlined weather/status icons | Preserve hierarchy and consistent symbolic icon treatment |
| Dark chrome, cyan/violet edges and luminous scenery | Use opaque canonical surfaces and semantic accents; no sampled purple added to Cyber |
| Wide top toolbar and centered floating application dock | Retain D4A's 48/56 logical-pixel geometry and content-sized dock |
| Dolphin/terminal windows, decorative folder art and four workspace thumbnails | Outside D4B; preserve actual workspace count and unrelated applications |
| Media waveform and decorative neon effects | Use truthful progress/state presentation; no fabricated live spectrum or required glow |

## Approach decision

| Approach | Benefit | Limitation |
| --- | --- | --- |
| **Recommended: independent offline card renderer over D4A plans** | Makes typography, states and all five palettes reviewable without desktop effects; preserves tested geometry | Native fidelity remains a later, measured compatibility task |
| Palette-only treatment of the existing schematic | Smallest change and direct token inheritance | Insufficient visual detail for card, toolbar and dock review |
| Custom native plasmoids or a new global Plasma style | Could offer more styling control | Adds deployment, compatibility and maintenance scope before native evidence; defer |

Extend the current stdlib SVG preview pipeline. Do not introduce an external
design service, new frontend framework, QML runtime or alternative layout engine.
Keep styling separate from the pure layout/identity planner.

## Shared visual system

All measurements below are proposed logical-pixel targets for synthetic previews,
not claims about stock applet minimum sizes or available native controls.

- Five separate opaque `surface` cards over `background`; no full-column slab.
- Shared radius 12, inside border 1 in `border`, and spacing from D4A's 12-pixel gap.
- Card padding 12 in compact and 16 in expanded. Borders, icons and decorative
  lines must remain within each planned rectangle.
- Use `surface2` for bounded control areas, progress tracks and chart tracks.
  Avoid blur, transparency, animated glow and shadow-dependent separation.
- Use `text` for content, `muted` for secondary labels and units,
  `accent_text` for readable emphasis, `focus` for focus indication,
  and `selection`/`on_selection` for selected controls.
- Brand fills use `primary`/`on_primary` or `secondary`/`on_secondary`.
  Warning/error/success retain their semantic roles. Missing data uses a label
  and symbol; it must not look like zero load, clear weather or successful playback.
- Color changes must not change dimensions, control placement, card order,
  icon identity, data meaning or content density between flavors.

Representative canonical values, for review only; implementation must read the
manifests rather than duplicate these literals:

| Flavor | Background | Surface | Text | Primary | Secondary | Accent text |
| --- | --- | --- | --- | --- | --- | --- |
| Minimal | #0B0D0F | #14171A | #F1F3F4 | #DDE3E6 | #6FCF97 | #DDE3E6 |
| Cyber | #070B10 | #0E1620 | #E6F7FA | #20D7F2 | #52E397 | #20D7F2 |
| Gothic | #090708 | #151012 | #F0EAEC | #741D32 | #992E4D | #DBA5B5 |
| Hybrid | #0D1117 | #151B23 | #E7EDF2 | #36C5E8 | #55D98B | #36C5E8 |
| PandaWave Pulse | #060A13 | #101420 | #FFFDFF | #FB2AA9 | #FA26A3 | #FB2AA9 |

Gothic's dark brand fills must keep their paired foregrounds and a visible
boundary; do not use `primary` as small text. The same semantic rules apply to
every flavor. Project acceptance targets: at least 4.5:1 for ordinary text and
3:1 for essential control boundaries and graphical indicators against their
adjacent surfaces. Check actual token pairings; report failures rather than
silently rewriting approved colors.

### Typography and icons

Use one UI sans-serif family across all components and flavors. Prefer the
existing Plasma UI family for eventual native presentation; propose Noto Sans
for offline review if an approved local copy is available. Resolve the actual
font file/version and record its hash before producing final visual exports.
No font installation or silent fallback is part of D4B. Missing approved fonts
must produce a clear export limitation, not a claim of reproducible typography.

Proposed type scale: secondary labels 13/16, body 14/20, card titles 16/20,
sensor values 24/28 compact and 28/32 expanded. Clock time is 38/42 compact and
44/48 expanded, with a 13/16 date line. Use tabular numerals where supported.
Reserve tracking/uppercase for short labels; keep media titles and condition
text in normal case. Test glyph coverage, long dates, long titles and mixed
scripts with the resolved font.

Use a small reviewed set of Breeze symbolic SVG assets for controls and
clock/media/weather/CPU/RAM semantics, sourced from an available local copy.
Record source/version, license and hashes; embed sanitized, self-contained
symbols in exported previews. If an asset is unavailable, report the missing
prerequisite rather than fetching/installing it. Do not use emoji as UI icons.
Use 16-pixel label/status icons, 20-pixel media glyphs and 40-pixel dock icons.
Application identity icons retain recognizable artwork rather than being
recolored indiscriminately. New Panda launcher artwork is separately reviewable;
do not extract unlicensed artwork from the reference.

## Five independent cards

| Card | Compact proposal | Expanded proposal | Required fixture states |
| --- | --- | --- | --- |
| Clock | Large 24-hour time and one date line; no extra heading | Same hierarchy with more breathing room; no slogan required | Long localized date, missing/unsupported glyph case |
| Media | 56-pixel art, title/artist, compact progress and transport row | 80-pixel art, clearer progress/time and transport hierarchy | No player, paused, playing, missing art, long metadata, multiple-player label |
| Weather | Condition symbol, temperature, concise condition and location | Current conditions plus bounded high/low or forecast row | Unconfigured provider, unavailable, stale, long location/condition |
| CPU | Value and bounded linechart with explicit units/history meaning | Same face with additional labelled context that fits | Synthetic normal/high/constant history, unavailable |
| RAM | Used/total label and horizontal utilization bar | Same face with readable units and additional available-memory label | Synthetic low/high usage, unknown total, unavailable |

Clock vertical budget: compact time/date plus a 4-pixel gap fits within 88
pixels with 12-pixel padding; expanded uses an 8-pixel gap within 104 pixels
with 16-pixel padding. Media/weather details must be arranged within their
existing budgets rather than growing the stack. Long text is ellipsized at
measured boundaries in previews; preserve full fixture values in JSON and
accessible SVG descriptions. No automatic horizontal scrolling or animation.

CPU linechart and RAM horizontal bars remain defaults. The existing two-face
allowlist remains independently configurable per sensor card. Alternate-face
previews show a design alternative, never proof that a native applet supports
the requested presentation. Do not add disk, temperature or network sensors.

Use sanitized synthetic playback, forecast and sensor data only. Explicitly
label samples and time ranges; do not connect to MPRIS, weather providers,
KSystemStats or a desktop bus. Charts must not interpolate unavailable values
into a healthy-looking series.

## Top toolbar and floating application dock

Toolbar: full logical width, height 48, opaque `surface`, one bottom boundary.
Left: launcher and workspace indicators reflecting the supplied fixture count.
Center: flexible space; a future contextual title requires separate approval.
Right: compact system/status symbols and clock/date. Keep a short utility clock
in the toolbar alongside the independent large desktop clock. Do not add live
CPU/RAM indicators or reproduce the reference's Apps/Places/System menus.
Use consistent baselines and 16-pixel status glyphs; content must fit at all
supported logical widths without colliding with workspace indicators.

Dock: 56 logical pixels high, centered, content-sized, floating intent with
8 logical pixels of bottom clearance. Use an opaque rounded surface and clear
boundary; 40-pixel icons, 8-pixel spacing and 8-pixel padding retain D4A's formula.
Width is `2*padding + count*icon_size + max(0,count-1)*spacing`.
A two-slot fixture therefore produces a 104-pixel dock. Reflect distinct pinned
and running application slots from explicit fixtures, retaining identity/order.
Show running/selected/focus states with both shape and semantic color; keep
indicators inside the 56-pixel rectangle. No scale-on-hover requirement.

The dock contains applications only. Status, weather, workspaces and clocks stay
in their approved locations. Excess slots still trigger explicit overflow
refusal. Do not add parking, reparenting, hidden automatic shrinkage or a live
task-discovery path. Native floating margins remain unverified.

## Full HD / QHD adaptation

Keep D4A's 24-pixel outer margin, 12-pixel gaps, right-column placement
preference and five-card order. Styling consumes the computed logical
rectangles; it must not recalculate geometry based on flavor or screenshot size.

| Physical output | Scale | Logical workspace | Compact | Expanded |
| --- | --- | --- | --- | --- |
| 1920 × 1080 | 100% | 1920 × 1080 | Fits model | Fits model |
| 1920 × 1080 | 125% | 1536 × 864 | Fits model | Fits model |
| 1920 × 1080 | 150% | 1280 × 720 | Fits model | Refuse overflow |
| 2560 × 1440 | 100% | 2560 × 1440 | Fits model | Fits model |
| 2560 × 1440 | 125% | 2048 × 1152 | Fits model | Fits model |
| 2560 × 1440 | 150% | 1706.667 × 960 | Fits model | Fits model |

Compact: width 288; clock/media/weather/CPU/RAM heights 88/120/112/96/96.
Expanded: width 352; heights 104/168/144/120/120.
Compact is the proposed FHD review baseline; expanded is the proposed QHD
review baseline. Selection remains explicit; there is no automatic presentation
switch. FHD compact at 150% and expanded at 125% exactly consume the model's
available vertical budget, so style overflow at those cases is a blocking defect.

Export at physical dimensions with a logical viewBox. Preserve fractional
coordinates until export; evaluate text and strokes at 100/125/150% rather than
rounding each component independently. These are model fit results, not native
measurements or evidence of hotplug/right-edge anchoring behavior.

## Proposed implementation scope after approval

1. Add a small, strictly validated visual specification, tentatively
   `theme/panda/common/desktop/visual.toml`, containing shared dimensions and
   semantic token references. No duplicated palette literals or plugin IDs.
2. Add focused preview styling helpers, tentatively `desktop_style.py`, and
   extend `desktop_preview.py` with independent card, toolbar and dock drawing.
   Retain the existing CLI commands and stdout-only export boundary.
3. Add separately named sanitized visual-state fixtures and reviewed local
   icon/font provenance records. Preserve the original FHD fixture unchanged.
   Build plans still pass through D4A's schema, identity and geometry validators;
   visual samples use a separate strict schema rather than loosening that schema.
4. Extend preview tests and offline documentation. Produce ten representative
   review exports: five flavors at FHD compact/100% and QHD expanded/125%.
   Validate all 55 accepted matrix cases and five expected refusals; render
   representative state/contact sheets with explicit synthetic labels.
5. Review the visual outputs and capability gaps before considering any native
   translation. D4B acceptance is an offline milestone only.

Do not modify the package manifests/helper, theme manager, palette manifests,
canary code, original checkout or live configuration for this proposed phase.
A later implementation should use a separately approved development branch
based on the D4A commit, preserving this milestone. No branch is created now.

## Verification and acceptance proposal

- Rerun the complete suite, applicable Fish syntax and package validation,
  plus `git diff --check`. Assert D4A plans/structural hashes remain unchanged
  for the same fixture/config and all five palettes remain byte-identical.
- Validate exact visual-schema fields, token references, numeric bounds,
  independent face choices and failure handling before emitting output.
- Verify source fixture bytes/identities, instance bindings, panel pins and
  unrelated applet config are preserved. No automatic IDs or host discovery.
- Measure text/control contrast, actual font extents, bounds and truncation.
  Parse every SVG and reject scripting, external URLs/resources, unsafe XML
  and unescaped fixture content. All visual assets must be local and reviewed.
- Check independent card boundaries, icon consistency, label/unit legibility,
  all empty/error states, and dock slot/toolbar collision cases.
- Record font/asset hashes, renderer environment and explicit inputs. Repeat
  exports must be byte-identical under those recorded inputs. Different font
  metrics must be reported, not described as equivalent verified rendering.
- Label every export “SYNTHETIC OFFLINE DESIGN — NATIVE UNVERIFIED” with a
  visible caption outside the card/dock bounds and an accessible description.
  Present any wallpaper composite as a design illustration, never a screenshot
  of the actual desktop. Use a canonical plain background for palette comparisons.
- Offline success requires both automated checks and human visual review at
  physical output sizes. No native visual check is claimed by a passing SVG test.

## Native compatibility and recovery gates

| Desired result | Current evidence | Separate prerequisite |
| --- | --- | --- |
| Per-card radius, border, typography and icon treatment | Offline proposal only | Measure stock applet/style inheritance; establish what can be scoped to each card |
| Clock/media/weather compact and expanded presentations | Layout preferences only | Observe exact pinned Plasma/plugin versions and native minimums |
| CPU/RAM face selection and missing-data behavior | Allowlist and synthetic tests | Scoped sensor/backend authorization and verified IDs/configuration |
| Toolbar geometry, opacity and dock floating clearance | Declarative model only | Controlled native panel measurement with preserved identities/pins |
| Right-column persistence across output changes | Calculated placement only | Separately reviewed native output/scale behavior; no automatic anchoring claim |
| Safe live rollback | No D4A recovery execution | Approved recovery route with proven bytes/metadata restoration before desktop mutation |

Stock Plasma may not expose all proposed styling per applet. Document each
unsupported property; do not introduce hidden global overrides or custom
plasmoids to make the preview look deployable. Any custom widget fallback needs
a separate source/license/version/maintenance review and explicit authorization.
Optional third-party widgets remain outside the default installer.

D4B review cannot close the historical D3B1A/R3 observation issue. Native widget
deployment and recovery require separate scoped plans and approval, regardless
of offline visual acceptance.

## Review decision requested

Approve or amend the recommended offline renderer approach, shared card/type
values, semantic use of all five palettes, and representative FHD/QHD review
outputs. The next authorized phase would implement only that reviewed offline
scope. No native test, installation, service activation or recovery is bundled
with approval of this proposal.
