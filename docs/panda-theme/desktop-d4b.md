# Panda Desktop D4B — offline visual implementation

D4B adds a detailed SVG/PNG renderer for five independent cards, the top toolbar
and floating application dock. It consumes unchanged D4A plans; it has no Plasma,
DBus, sensor, weather or player connection. All previews are synthetic designs.

Development branch: `codex/feat-panda-desktop-d4b`, based on reviewed D4A commit
`bdfa0bf58c8091b4899401bd8b42bfda12e82cb3`. Work remains uncommitted for review.
The reviewed proposal is retained unchanged as historical design input; this document records implementation.
The original D4A milestone, canary checkout, palette manifests and D4A layout
schema/geometry/identity decisions are preserved. D3B1A/R3 remains unresolved;
this work neither accesses that rehearsal tree nor establishes recovery success.

## Review images

| Flavor | Full HD: compact, 100% | QHD: expanded, 125% |
| --- | --- | --- |
| Minimal | [PNG](previews/d4b/fhd-compact-minimal.png) · [SVG](previews/d4b/fhd-compact-minimal.svg) | [PNG](previews/d4b/qhd-expanded-minimal.png) · [SVG](previews/d4b/qhd-expanded-minimal.svg) |
| Cyber | [PNG](previews/d4b/fhd-compact-cyber.png) · [SVG](previews/d4b/fhd-compact-cyber.svg) | [PNG](previews/d4b/qhd-expanded-cyber.png) · [SVG](previews/d4b/qhd-expanded-cyber.svg) |
| Gothic | [PNG](previews/d4b/fhd-compact-gothic.png) · [SVG](previews/d4b/fhd-compact-gothic.svg) | [PNG](previews/d4b/qhd-expanded-gothic.png) · [SVG](previews/d4b/qhd-expanded-gothic.svg) |
| Hybrid | [PNG](previews/d4b/fhd-compact-hybrid.png) · [SVG](previews/d4b/fhd-compact-hybrid.svg) | [PNG](previews/d4b/qhd-expanded-hybrid.png) · [SVG](previews/d4b/qhd-expanded-hybrid.svg) |
| PandaWave Pulse | [PNG](previews/d4b/fhd-compact-wave.png) · [SVG](previews/d4b/fhd-compact-wave.svg) | [PNG](previews/d4b/qhd-expanded-wave.png) · [SVG](previews/d4b/qhd-expanded-wave.svg) |

Additional review artifacts:

- [Five-flavor comparison](previews/d4b/five-flavor-comparison.png): same data,
  typography, geometry and seven applications; card-column/dock crops are assembled
  for comparison only after full-layout bounds validation.
- [Cyber desktop composition](previews/d4b/cyber-composition.png):
  approved generated Panda wallpaper, opaque cards/chrome and explicit offline label.
  [Self-contained SVG](previews/d4b/cyber-composition.svg).
- [Unavailable/offline/missing sensors](previews/d4b/state-unavailable.png),
  [paused/missing artwork](previews/d4b/state-paused.png).
- [FHD 125% expanded](previews/d4b/tight-fhd125-expanded.png) and
  [FHD 150% compact](previews/d4b/tight-fhd150-compact.png): deliberately long text.
- [Export verification](previews/d4b/verification.json) and
  [output SHA-256 manifest](previews/d4b/manifest.json).

All SVGs contain a visible outlined “SYNTHETIC OFFLINE DESIGN — NATIVE UNVERIFIED”
caption and accessible descriptions. PNGs are rasterizations of those SVGs.
They are not screenshots of running widgets. The comparison board repeats that label.

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

## Native implementation recommendation

1. Review this offline result and agree which stock-supported differences are
   acceptable. Measure per-applet frame/style/font capabilities before deciding
   whether any custom widget is warranted.
2. Under separate native authorization, pin the Plasma/plugin/font versions and
   map existing instance IDs, panels, workspace count and application pins.
   Establish supported card minima and Qt text metrics; do not assume these
   offline rectangles or compact/expanded modes are universally available.
3. Resolve the separately gated recovery prerequisites before desktop mutation.
   D4B does not read, repair, restore or close historical D3B1A/R3 evidence.
4. First native visual proposal remains one official clock and one media widget
   under operator control, with before/after evidence. Keep CPU/RAM backend
   activation, weather provider access and panel/dock migration separately scoped.
5. Verify native opacity, floating clearance and output/scale behavior before
   expanding deployment. No automatic anchoring, parking or hotplug reparenting.

No packages, widgets, services, theme-manager settings, graphics drivers or live
Plasma configuration are changed by this implementation.

## Final verification status

297 Python tests passed in 62.243 seconds, including all 18 new visual/export
tests. Ten source/test files compiled; applicable Fish syntax, bootstrap's 13
Fish scripts/54 package entries and diff checks passed. All 33 artifacts matched
two complete regenerations. Independent source review found no blocking issue;
its missing-optional-tooling diagnostic finding was reproduced and fixed with a
regression and a fresh full suite. Human review of these offline designs is the
next gate; no native validation or recovery result is implied.
