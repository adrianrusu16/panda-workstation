# D4C3-S1 native Plasma Style implementation plan

**Goal:** reusable offline native frame sources for five canonical Panda flavors.
**Base:** 1a8b655334e2b906022a9c97ef169ed3aa930343, integrated main with PR #10.
**Spec:** approved Panda Theme System, D4B visual.toml and desktop-d4c-proposal.md.
Execute inline; no commits, installation, runtime queries or retained R0/D3B1A access.

- [x] Pin Plasma 6.8.1 package metadata, fallback, SVG consumers and KSvg 6.31
  frame/stretch contracts. Keep raw source private; publish immutable receipts.
- [x] Test-first implement one deterministic package generator/profile validator.
  Four assets: widgets/background.svg, widgets/translucentbackground.svg (opaque
  alias), widgets/panel-background.svg, dialogs/background.svg. Each has nine
  base and mask pieces, stretch hint and explicit margins; no shadow/blur prefix.
- [x] Generate identical package structures from canonical theme.toml palettes;
  metadata, colors, plasmarc and license. Radius12; widget margin12, panel8,
  dialog16. Retain breeze-dark fallback; disable blur/contrast/adaptive effects.
- [x] Test-first implement CPU-only nine-slice model and deterministic five-flavor
  gallery over light/dark/approved wallpaper, plus D4B Cyber comparison.
  Label synthetic/native-unverified. Test alpha coverage, seams, stretch limits,
  palette use and contrast; preserve any contrast failures in reports.
- [x] Run full repository tests, Fish/package checks, SVG/security/profile checks,
  regeneration equality and whitespace checks. Fresh final review; fix confirmed
  important defects with failing regressions before reporting.
- [x] Return complete diff/inventory, gallery and installation/rollback design.
  Keep all work uncommitted and prior checkout files unchanged.

Review focus: SVG resource/script rejection; no transparent interior or seam;
palette/structure invariance; export cannot target live configuration/install
paths or overwrite conflicts; model rendering never claimed as KSvg/native proof.

Decisions: reuse only the existing licensed wallpaper/font for previews. Colors
are generated outputs, not new canonical palettes. Rounded corners intentionally
leave alpha outside the frame silhouette. Missing controls/icons use fallback;
this is a small frame set, not a complete new control theme. Source baseline and
render-model/runtime limits must stay explicit. No applet identities/layout keys
are touched. Generic skill commit/cleanup steps yield to the user's review gate.

Specification SHA256:5904eb5532d5fc66d70918f959b499f3906bd20b0098c1a8fba5896eaad22db0.

## Execution ledger

- Source task complete: 19 pinned upstream payloads verified by content, Git
  blob and commit-tree membership; public receipts contain no private paths.
- Package task complete: 40 files / 20 SVGs, one shared structural specification.
  Initial generator/preview tests were observed red before implementation.
- Preview task complete: five individual exports, gallery and Cyber comparison;
  all 49 generated artifacts repeat exactly in an independent process.
- Ruling: supply an opaque translucent-background alias — stock desktop
  consumers can select that path — native choice of background remains unmeasured.
- Ruling: use canonical on_selection for all selected foregrounds — initial
  direct link/status mapping failed 14 contrast pairs — selected status needs
  non-color cues; no canonical token is changed and failures remain recorded.
- Ruling: reject processing instructions before XML parsing — ElementTree
  discarded the injected stylesheet PI — the profile must reject external
  resource intent even when the parser ignores it. RED then GREEN observed.
- Ruling: hold directory descriptors and recheck parent bindings while writing —
  a reproduced late parent-symlink substitution redirected the initial writer —
  repository generation must refuse that race. RED then GREEN observed.
- Ruling: use CPU section rasterization with integer device seams — no native
  execution is authorized — it models source assets, not KSvg fidelity.
- Ruling: retain wallpaper edge-contrast failures — canonical palettes outrank
  improvised adjustments — native boundary visibility remains an acceptance gap.
- Verification complete: 328 tests passed; focused 14 passed; Fish 13 scripts,
  54 package entries passed; source receipts and regeneration verified; all
  new-file whitespace and local document links checked.
- Fresh final review complete: no important confirmed defects; no native claims.
- Preservation: six prior checkout HEAD/branch/status listings and 16 prior
  untracked receipts plus approved spec match. The existing tracked canary
  bootstrap modification had no initial byte receipt; do not claim exact bytes.
- Handoff complete: full binary diff and complete hashed 57-file inventory
  retained privately for review; sources remain untracked and index empty.
- Ruling: preserve S1 private source/test/provenance evidence — user requests
  review and prior evidence preservation — generic skill cleanup/commit steps
  do not apply. No commit or deployment authorized.

- Final whitespace scan found ConfigParser's extra blank line at colors EOF.
  A final-newline regression was observed RED, then GREEN after normalizing to
  exactly one newline. Seven own artifacts changed: five colors files and two
  hash reports. No palette or PNG bytes changed. Full suite rerun after this fix.
