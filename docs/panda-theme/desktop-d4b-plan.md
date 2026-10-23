# D4B offline implementation ledger

Base: bdfa0bf58c8091b4899401bd8b42bfda12e82cb3.
Authority: reviewed desktop-d4b-proposal.md plus the user's D4B refinements.
Branch: codex/feat-panda-desktop-d4b. No commit, merge or native application.

1. Verify assets/font provenance and freeze the D4A fixture, palette and geometry fingerprints.
2. Test strict semantic/visual schemas, then implement reusable text, SVG and style primitives.
3. Test independent desktop cards, toolbar and dock; implement against unchanged D4A plans.
4. Export ten flavor/resolution previews, a seven-slot dock, a separately labelled composition and state comparisons.
5. Verify actual glyph bounds, contrast, invariance, reproducibility, full tests and source scope. Stop for review.

Pre-flight: the renderer consumes build_plan output; it must never modify build_plan or native mappings.
Visual fixtures are separate from D4A fixtures. Data validity must precede drawing.
The CLI retains its existing schematic default and gains explicit visual input for detailed preview only.
The generic drawing/style/text modules may serve a future Command Center; no Command Center is implemented.

Baseline: 279 tests passed in 45.483 seconds in the new worktree.
Asset investigation: local Pango/Cairo available; Noto Sans Regular 2.015 has embedded OFL notice.
The generic installed font-package license is Apache; it is not used as this font's license.
Breeze 6.31.0 local icon source and upstream COPYING-ICONS are being recorded.
The approved design archive describes generated Panda wallpaper assets and records their SHA-256.
Archive design prose is provenance/context only, not authority to expand the current task.

Tasks 1–4: implementation and initial exports complete. Initial 12 renderer tests and two export tests passed; extended cases cover huge integers, stale/partial/gapped states and empty HOME/XDG.
Ruling: excluded the installed Okular SVG because real off-canvas paint violated the icon boundary; use the reviewed Ark source. Cost: the representative reader slot is an archive application instead.
Ruling: preserve the D4A schematic default and require explicit visual input. Cost: callers opt into the detailed renderer rather than receiving an implicit change.
Ruling: use actual glyph ink and rendered icon paint extents rather than viewBox/nominal line-box estimates. Cost: native Qt font-layout parity remains separately unverified.
Contrast: all used semantic pairs pass; Gothic primary/surface and secondary/surface candidate failures are reported without changing tokens.

Independent source review: no blocking layout/security finding; 17 focused tests passed.
Final review correction: optional GI imports escaped the documented refusal handler. Reproduced missing-GI main() raising instead of returning failure. Treated as a required failure-handling correction, not cosmetic polish; translate import/typelib failure to the existing actionable ValueError. Cost: one additional dependency-error regression, no new dependency or fallback.

## Final verification

- 297 complete Python tests passed in 62.243 seconds (279 D4A baseline + 18 visual/export cases).
- Ten Python source/test files compiled; three applicable Fish scripts passed syntax; bootstrap validation passed 13 Fish scripts and 54 package entries.
- 55 accepted geometry/flavor cases and five expected overflow refusals passed against the frozen D4A receipt.
- Tight FHD125 expanded/FHD150 compact cases passed actual glyph/icon/control bounds, padding and text/icon collision checks for four states each.
- All 33 final artifacts equal two complete regenerations, including PNG rasterization. Initial artifacts and superseded generated metadata are retained only in this worktree's ignored .local-ai review directories.
- Final missing-GI correction: regression RED (ModuleNotFoundError) → GREEN (failure status, actionable message, no output directory); complete suite green.
- Canonical palettes, original D4A fixture/layout decisions, D4A milestone and canary fingerprints remain unchanged. No D3B1A evidence access, native operations, package installation, commit, merge or deployment.

## Final review dispositions

The independent reviewer found no blocking layout/security issue. Its one minor
missing-GI finding was treated as required documented failure handling and fixed
in one test-backed pass. No second review was requested.

Ruling: retain explicit opt-in detailed rendering; D4A's planner/schematic are preserved. Cost if wrong: callers need the documented visual-fixture option.
Ruling: no native/provider/service adapters or implicit host configuration writes are introduced. Cost if wrong: native deployment remains separate work.
Ruling: missing/partial/stale states preserve absence rather than synthesize healthy readings. Cost if wrong: users see explicit unavailable/history-not-supplied labels.
Ruling: CPU history gaps stay disconnected. Cost if wrong: isolated history samples have no connecting stroke.
Ruling: retain actual-ink bounds/collision checks and refuse overflowing assets instead of hiding overflow with card clips. Cost if wrong: some otherwise usable assets/strings are rejected.
Ruling: selected-control focus/selection contrast was also independently checked across all flavors; minimum exceeds 3:1 (Wave approximately 3.114). Cost if wrong: future token changes need renewed contrast review.
Ruling: accept only local hash-verified reviewed icon data, escape fixture strings and reject remote/scripting SVG resources. Cost if wrong: adding assets requires source review.
Ruling: preserve the exporter's conflict refusal/exclusive creation boundary and document partial artifacts after I/O failure, rather than claim transactional recovery. Cost if wrong: an operator reviews incomplete new output after a failure.
Ruling: scope typography reproducibility to pinned assets and recorded rendering tools. Cost if wrong: other library/platform versions require fresh review.
Ruling: native Qt sizing, palette/style inheritance, sensor/provider behavior, anchoring and recovery remain unverified. Cost if wrong: an offline preview may require native-specific adjustments under a later approved plan.

Deferred minors: none.

Packaging check found three upstream trailing-space lines in two license notices. Preserved raw fetched notices and source hashes; removed trailing whitespace only from vendored notices, preserving all license words. Updated asset receipts and derived SVG metadata; PNG bytes unchanged.
