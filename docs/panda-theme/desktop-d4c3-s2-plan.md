# D4C3-S2 implementation plan

Goal: extend the native asset contract and prepare a real KSvg worker; never run it in this milestone.
Base: integrated main 94ba4580d44f0585663a8be1ae2cf1232b70dc52 (merged PR11).
Authority: current user request, AGENTS.md, approved Panda Theme System, accepted S2 direction.
Execution: inline under executing-plans; one fresh whole-change review after verification.
No commits, publication, installation, service/session/graphics actions or D3B1A/R0 access.

- [x] Baseline: preserve S1/current checkout state, record the 40 package and canonical palette hashes; run 328-test baseline with private HOME/XDG.
- [x] Task A, RED: add literal solid-panel path/semantic-equivalence regressions, observe missing-path failure.
- [x] Task A, GREEN: extend plasma_style.ASSETS/spec with solid/widgets/panel-background.svg margin8; produce 45 files /25 SVGs with every old package byte unchanged.
- [x] Refresh only generated verification hashes/manifests; confirm all seven PNG bytes unchanged and 54 generated artifacts repeat.
- [x] Task B, RED: behavioral tests for strict 700-case job generation and synthetic pixel validation (holes, masks, bounds, palette, rounding and missing/unsupported cases).
- [x] Task B, GREEN: native_frame_plan.py pure data generation/validation and pixel analysis; checked fixture inventory. No launcher/native imports.
- [x] Write tests/native/plasma_frame_worker.cpp with fixed input/output roots, pre-GUI guard, explicit asset paths, real KSvg frame/mask/margin/prefix capture and supported/missing/unsupported classification.
- [x] Compile/link and inspect ELF dependencies without running the worker, CMake probes or ldd. If tooling is unavailable report it; do not install.
- [x] Audit full initialization/teardown against 18 immutable source receipts; prepare isolation attestation schema/procedure without performing native isolation trials.
- [x] Full repository tests, Fish/package checks, SVG and generated identity/hash checks, source review, whitespace, complete binary diff/inventory; leave uncommitted.

Files: plasma_style.py/spec.json and two existing tests; five new solid SVGs; existing generated verification/manifest JSON; new native_frame_plan.py plus two native tests/fixtures; C++ worker source/build-only instructions; S2 report, plan and source receipts.

Interfaces: build_packages() produces the reviewed asset bytes; native_frame_plan produces 20 strict jobs of 35 cases (5 assets ×7 sizes) =700 direct frames, plus20 explicit missing checks. Pixel analysis consumes synthetic/native raw RGBA and masks but never claims a native run from synthetic fixtures.

Review focus: no hidden native execution in tests/build scripts; no arbitrary asset/output paths; exact old-package preservation; no fake fallback success; guard/attestation is defense in depth, not proof of isolation. Worker behavioral assertions cannot be executed under current authorization: compile/source audit only; report this limitation explicitly.

Rulings: user execution prohibition overrides native TDD runtime steps. Test-first applies to safe Python/generator behavior; no source-text tests masquerading as native tests. Existing S1 report remains a historical snapshot with a pointer to S2. IDs, metadata, canonical palettes, border geometry and contrast advisories are retained. Full Plasma Theme fallback remains unverified and is excluded from the worker.

## Execution ledger

- Baseline328 passed; isolated feature branch at integrated main94ba458.
- TaskA RED observed missing literal solid path; GREEN generated45files/25SVGs.
  All40 old package bytes and all5 palettes preserved; seven PNGs unchanged.
- TaskB nine data/pixel tests observed RED before module existed, then GREEN.
  Native case contract700 +20 missing probes; runtime count remains0.
- Native C++ runtime assertions were not executed: explicit user restriction.
  Three separately identified compile/link candidates retained privately; latest
  strict compilation passes. No CMake configure probes or ldd were used.
- Ruling: in-worker checks are defense in depth, never an isolation certificate.
  The external pre-exec boundary and authenticated provenance remain mandatory.
- Ruling: inspect executable mappings, not all file-backed maps — font/cache
  mappings are legitimate private data, not libraries — future trace must still
  verify all non-code resource paths. Tighten read-only library/plugin mounts.
- Ruling: no native fallback test is substituted by direct rendering; no
  Plasma::Theme, QML loader or copied resolver is included.
- Existing preview tests reused without textual changes; they automatically
  cover the fifth asset (600 model cases). No unnecessary new preview art.
- Full verification338 tests; Fish13/package54;18 source receipts;54 artifacts
  reproduced with identities/metadata stable. Fresh final review: no important
  confirmed defects. Complete changed-file/asset inventories and binary diff
  prepared for review; all changes remain uncommitted.
- No native worker, namespace probe, service, live configuration or installation
  action. No D3B1A/R0 access; prior S1 proposal/evidence preserved.


## Final targeted corrections

- Preserved the21-file pre-correction source state and60 package/artifact/
  palette/fixture receipts before changes; no earlier evidence overwritten.
- Added checked_screen_dpr.h and explicit primary-screen acquisition. The
  compile-only null test rejects at the throw branch without constructing Qt.
- CMake target and documented direct command now reproduce the strict flags;
  a real configure-only target fixture verifies warnings become errors. The
  fixture uses synthetic imports and forces compiler metadata, without Qt
  package scripts or compiler/native probes.
- Three static regressions observed RED then GREEN. Latest full suite341 passed
  (89.135s); Fish13/package54 passed; the corrected strict worker build passed.
- New supervisor implementation proposal only: first trial inert/non-Qt,
  independently reviewed evidence, then separate single-frame preparation and
  execution approval. No supervisor/probe implementation or invocation.
- Independent targeted reviewer failed on its usage limit before completing
  review. Self-review used for this handoff; earlier S2 review is not presented
  as independent approval of these later corrections.
- Native execution, frame capture, sandbox/isolation probing and actual Plasma
  fallback remain unperformed/unverified. No commits, publication or live actions.
