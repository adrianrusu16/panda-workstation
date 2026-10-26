# D4A offline implementation plan

Goal: reproducible native-first desktop intent, with no host application.

Authority: the approved Panda Theme System specification and the D4A request.
D4A refines panel heights to 48/56 logical pixels and explicitly limits this
implementation to offline planning. Existing workspace count and instances
are preserved; the older design's three-desktop target is not applied.

1. Add strict layout/fixture validators and geometry planning. Cover FHD/QHD
   at 100/125/150%, overflow refusal, malformed inputs, instance binding,
   preservation and flavor invariance with tests written first.
2. Add stdout-only JSON dry-run and SVG model preview through a separate
   panda-desktop Fish entry point. No live entry point, config writer,
   subprocess, sensor discovery, runtime bus or automatic fixture enrollment.
3. Add official package requirements to desktop.txt. Validate global duplicate
   detection and names. Make the existing package helper reject malformed or
   duplicate entries before pacman, and add a read-only --dry-run.
   Test installer calls only through disposable fake pacman/sudo executables.
4. Document native property intent, limitations, recovery design and the first
   separately authorized deployment. Run all tests, Fish syntax, manifest
   validation, preview parsing, diff review and original-checkout preservation.

Interfaces: desktop_layout builds a plan from validated TOML and JSON;
desktop_preview consumes that plan plus canonical palette tokens;
desktop_cli reads explicit fixture inputs and emits stdout; desktop_packages
checks repository manifests against the fixture's installed inventory.

Review focus: bool/NaN/unknown schema fields; scaled overflow without implicit
fallback; duplicate/conflicting IDs; stale/unbound instances without guessing;
package failure propagation and a dry-run that never calls sudo/install.

Rulings: use the current request as authorization for this bounded offline
implementation; keep the work uncommitted for review. No D3B1A access or claims.
All model card extents and presentation preferences remain runtime-unverified.

## Verification ledger

- Baseline: 249 existing tests passed.
- Tasks 1–3: 20 D4A tests passed, including geometry matrix and package failure
  propagation. Complete suite: 269 passed before final review.
- Fresh review: fixed guarded palette reads, huge-integer clean refusal and
  XML-invalid provider text. All three had failing regression tests first.
- Ruling: treat invalid SVG from accepted fixture text as a correctness defect
  requiring repair, despite the review's minor severity label; otherwise
  downstream preview consumers can fail on accepted input.
- No commits, staging, installation, native application or recovery performed.

- Final verification: all 272 tests passed (249 baseline + 23 D4A tests),
  eight changed/new Python sources compiled, all 13 bootstrap/machine Fish
  scripts validated, all 54 package entries validated, three changed/new Fish
  files passed fish -n, and git diff --check passed.
- Both exported SVG previews parsed successfully and match current generator
  output. They are schematics; no native rendering is claimed.
- Original canary branch, HEAD, index bytes/identity/mode/mtime and all four
  untracked file bytes/identities/modes/mtimes matched their captured baseline.
- Final review findings are addressed; no deferred findings. D3B1A retained
  evidence was not accessed. No live deployment is authorized or performed.

## D4A-Fix targeted follow-up

- Reproduced both P2 findings and the three missing-intent/gating observations
  before production changes. Targeted suite now has 30 tests.
- Selected one validated pacman -Qq inventory: any nonzero retrieval status
  fails; package absence is set membership only after successful validation.
- Reviewed sensor face allowlist contains only the existing official linechart
  and horizontalbars faces; defaults and fixed plugin/package IDs are preserved.
- Added explicit normal-install plasma profile selection, floating dock intent
  with 8 logical pixels of model clearance, and the independent top-bar clock.
- Native floating margins, status/clock widget instances and all real sensor
  presentations remain deferred. No live application or recovery is claimed.

- Final D4A-Fix verification: all 279 tests passed (30 D4A tests); 13 Fish
  scripts and 54 package entries validated; eight Python files compiled;
  55 geometry/flavor cases passed and five expected expanded-FHD-at-150%
  cases were refused; 10 alternate-face/flavor cases passed; both SVG
  previews match the current generator; git diff --check passed.
- The canary branch, HEAD, index bytes and four untracked file contents still
  match their preserved baseline. No D3B1A evidence was accessed.

## Offline milestone finalization

- User authorized committing the reviewed 18-file D4A implementation on
  codex/feat-panda-desktop-d4a. Earlier uncommitted/no-staging ledger entries
  describe the review stages above. No merge or deployment is authorized.
- Fresh verification: 279 tests passed; three changed/new Fish scripts and
  all 13 bootstrap/machine scripts passed syntax checks; 54 package entries
  validated; eight Python files compiled; 55 geometry/flavor cases accepted,
  five expected overflow cases refused, and 10 alternate-face cases passed.
- Both synthetic SVG exports matched the generator at their documented scales
  (FHD 100%, QHD 125%). An initial comparison used the wrong QHD scale; the
  corrected verification invocation passed without implementation changes.
- D4B visual design requires proposal review before implementation. Native
  widget deployment and unresolved D3B1A recovery remain separate gates.
