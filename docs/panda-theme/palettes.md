# Canonical Panda palettes — Phase 1

This phase provides five TOML manifests, a strict data model, a read-only
validator, and tests. It does not apply themes, write runtime state, or generate
application configurations. The approved specification remains authoritative.

## Manifest schema v1

Each `theme/panda/<slug>/theme.toml` contains exactly:

- `schema_version`: integer `1`.
- `name`: the approved display name.
- `slug`: `minimal`, `cyber`, `gothic`, `hybrid`, or `pandawave`, matching its directory.
- `aliases`: `[]`, except `pandawave` has `["wave"]`.
- `[palette]`: exactly the 17 semantic roles below, each an opaque sRGB
  `#RRGGBB` string. Hexadecimal letter case is accepted either way.

The executable schema is `theme/panda/common/palette.py`. It rejects missing or
unknown fields/roles, unsupported versions, wrong names/slugs/aliases, duplicate
TOML keys, malformed TOML, non-string colors, short hex, alpha, and non-hex colors.
Family validation requires exactly the five canonical manifest paths; `wave`
resolves to `pandawave` and must not introduce a sixth manifest.

| Role | Intended use |
| --- | --- |
| `background` | Page/desktop base |
| `surface`, `surface2` | Two levels of opaque surface |
| `text` | Normal content on any base surface |
| `muted` | Secondary text, still readable at normal size |
| `primary`, `secondary` | Brand emphasis fills, not general text colors |
| `accent_text` | Readable accent-colored text on base surfaces |
| `success`, `warning`, `error` | Status text/icons on base surfaces |
| `border` | Meaningful control boundaries against base surfaces |
| `focus` | Focus indicator against base surfaces or selection |
| `selection` | Selected-content background |
| `on_primary`, `on_secondary`, `on_selection` | Normal-size text on the matching fill |

Semantic values may coincide without merging roles: changing `success` must not
implicitly recolor `secondary`. Where secondary and success share green, future
adapters must distinguish status through text/icons. Primary actions and
destructive actions must also remain distinguishable by labels and treatment.

The existing Minimal, Cyber, Gothic and Hybrid semantic values are retained.
The specification's Gothic metallic color becomes `focus`. Cyber's accent-dark
example is a visual reference, not an extra component or semantic role. Missing
status, muted, boundary and selection roles are Phase 1 additions. They do not
introduce a new palette for each application or unused color ramps.

## Contrast and accessibility contract

The validator computes linearized sRGB relative luminance using the WCAG transfer
function (`0.04045` breakpoint), RGB weights `0.2126`, `0.7152`, `0.0722`, and
`(lighter + 0.05) / (darker + 0.05)`. It compares unrounded ratios against:

- **4.5:1**, [WCAG 2.2 SC 1.4.3](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html):
  `text`, `muted`, `accent_text`, and all three status roles on each of
  `background`, `surface`, `surface2`; the three paired `on_*` foregrounds on
  their respective fills.
- **3:1**, [SC 1.4.11](https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html):
  `border` and `focus` against each base surface, plus `focus` against `selection`.

That is **28 required checks per flavor**, plus six informational checks of brand
fill visibility against base surfaces. The CLI exits nonzero for a structural
error or failed required contrast pair. Advisory fill results remain visible.

These pairings define the allowed palette uses, not blanket WCAG conformance.
Future adapters must remeasure actual adjacent/rendered colors, keep a surface
gap around an external focus ring if its fill is not among the checked pairs,
and provide non-color state cues. Neither a selected row nor a status may rely
only on its background hue. Palette validation cannot check focus geometry,
keyboard behavior, screen-reader output, or reduced-motion behavior.

### Gothic fill restriction

The approved burgundy `primary` (`#741D32`) and wine `secondary` (`#992E4D`)
remain unchanged. They are too dark for accent text or standalone meaningful
boundaries on the base surfaces. Use `accent_text` (`#DBA5B5`) for text; use
`border` for control edges and the paired `on_*` foregrounds for labels. This
preserves the brand while avoiding an unreadable role mapping.

The lowest fill/base results are **1.632852:1** (`primary`/`surface2`) and
**2.370990:1** (`secondary`/`surface2`), both below 3:1. These are explicit
restrictions for future adapters, not permission to use failing text colors.

## PandaWave reference

Repository: [adrianrusu16/PandaWave](https://github.com/adrianrusu16/PandaWave).
Pinned revision: `bb1e83c3c178e5a315aa799c105c3cab5b662c9c`.
Asset: `core/designsystem/src/main/res/drawable-xxxhdpi/pandawave_ic_logo.png`.
SHA-256: `47d8238ac9a1d77aea3f65fa41228e2cc8376cfac70a0c86a3794ddb1ddf71ea`.

The original 1254×1254 RGBA logo was downloaded to `/tmp`, visually inspected,
and sampled with Pillow. Coordinates are zero-based from the top-left. These
are stored source RGB samples, not a transparent pixel composited against a
chosen background. Their RGB values become opaque manifest tokens, then those
tokens are contrast-tested. No logo binary is vendored and PandaWave was not
modified.

| Role | Coordinate | Source RGBA | Manifest RGB |
| --- | --- | --- | --- |
| `primary` | `(627, 100)` headband | `(251, 42, 169, 254)` | `#FB2AA9` |
| `secondary` | `(627, 280)` inner arc | `(250, 38, 163, 253)` | `#FA26A3` |
| `background` | `(627, 200)` dark field | `(6, 10, 19, 254)` | `#060A13` |
| `text` | `(627, 350)` forehead | `(255, 253, 255, 254)` | `#FFFDFF` |

As a cross-check, among source pixels with alpha >= 250, the most frequent
saturated pink was `#FB29A9` (1,923 pixels), followed by `#FB2AA9` (1,804).
This sample class used R > 180, B > 80, R > 2G and B > 1.5G.

These four values refine the specification's initial Wave estimates
(`#FF25AC`, `#F31599`, `#070A12`, `#F8F8FA`) as explicitly allowed by its logo
reference requirement. The specification itself is otherwise unchanged.
Surface, muted, plum-selection and blush-focus values retain its direction.
Wave's `error` uses the same revision's `pandawave_theme_pink_error`, `#FFB4AB`.
Success, warning and control-border colors are semantic additions, not logo
samples. The paired label colors are dark because light text on hot pink is
not a safe default.

## Measured results

Each cell is the minimum ratio among that category's required pairs; displayed
values are rounded to six decimals. All 140 required pairs pass at full precision.

| Theme | Body | Muted | Accent text | Status | Filled labels | Selected text | Border/focus |
| --- | --- | --- | --- | --- | --- | --- | --- |
| minimal | 14.722891 | 5.327912 | 12.645547 | 6.879102 | 10.241898 | 6.902282 | 3.019984 |
| cyber | 14.984926 | 6.296179 | 9.489805 | 5.789767 | 11.334010 | 6.794434 | 3.663104 |
| gothic | 14.700457 | 5.171968 | 8.363156 | 7.750327 | 6.200134 | 9.002935 | 3.548043 |
| hybrid | 12.967528 | 5.054806 | 7.512635 | 5.363880 | 9.289825 | 6.235864 | 3.441499 |
| pandawave | 16.699494 | 7.048848 | 4.834461 | 9.659458 | 5.535654 | 7.831667 | 3.113633 |

Body, muted, accent text and status minima include all three base surfaces.
Filled labels cover both primary and secondary. Border/focus includes focus
against selection. All colors are opaque 8-bit sRGB, so no gamut or alpha
compositing approximation is needed. Only the five specified dark appearances
exist; no separate light appearance is claimed.

## Reproduce validation

From the repository root, with Python 3.11+ and Fish installed:

```fish
python3 -B -m unittest discover -s tests -v
fish -n theme/panda/common/scripts/validate-palettes.fish
fish theme/panda/common/scripts/validate-palettes.fish
fish theme/panda/common/scripts/validate-palettes.fish --json
git diff --check
```

No additional Python packages are required for validation. `--json` reports
every measured pair, its criterion/threshold, whether it is required, and its
unrounded result. A positional directory can validate an isolated five-manifest
family. Validation writes no files. Re-run it after any manifest change; the
summary above records the Phase 1 values.

Color review: no actionable findings within the documented role pairings;
Gothic fill restrictions remain visible. Accessibility review: required palette
contrast passes. Actual desktop rendering, keyboard/screen-reader behavior and
motion are **not verified** in this data-only phase.
