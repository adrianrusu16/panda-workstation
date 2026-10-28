# Panda Desktop D4C3-S2 — source preparation and isolation review

Status: uncommitted source milestone from integrated main
`94ba4580d44f0585663a8be1ae2cf1232b70dc52` (merged PR #11).
**The native worker has not been executed. No isolation attestation exists.**

## Completed native asset contract

Each existing `panda-<flavor>-s1` package gains exactly one asset:
`solid/widgets/panel-background.svg`. It is generated from the same canonical
surface/border roles and shared geometry as `widgets/panel-background.svg`;
the two files are byte-identical within each flavor.

The [pinned Plasma 6.8.1 Panel.qml](https://github.com/KDE/plasma-desktop/blob/bb989636959f9edc7263f2f75dc2630835305b95/desktoppackage/contents/views/Panel.qml#L167)
explicitly requests `solid/widgets/panel-background` for opaque rendering.
This closes that static path-coverage gap. It does not establish actual panel
painting, floating behavior or precise native dimensions.

| Asset path in every package | Margin hint |
| --- | ---: |
| widgets/background.svg | 12 |
| widgets/translucentbackground.svg | 12 |
| widgets/panel-background.svg | 8 |
| solid/widgets/panel-background.svg | 8 |
| dialogs/background.svg | 16 |

Five packages now contain **45 files, including 25 SVGs**.
IDs, metadata, license, colors, plasmarc, all 40 original package files and all
five canonical theme.toml palettes remain byte-identical to the integrated
baseline. No Breeze artwork is copied. Radius12, one-unit borders, masks,
stretch behavior, color mappings and declared Breeze Dark fallback are unchanged.

The generator/specification and regression tests enforce the extra path and
geometry equivalence. The existing synthetic preview renderer covers all five
assets in its scale matrix (600 modeled frames). Seven PNGs remain unchanged;
only verification.json and manifest.json are recomputed for the expanded
inventory/structural hashes. There are **54 reproducible generated artifacts**.
No Cairo output is represented as a native result.

Wallpaper-boundary contrast still fails the recorded 3:1 advisory for every
flavor. Canonical colors have not been adjusted. See the retained
[contrast report](previews/d4c3-s1/verification.json).

## Prepared native capture source

[Worker and audit](../../tests/native/README.md) and
[C++ source](../../tests/native/plasma_frame_worker.cpp) use actual
KSvg::FrameSvg. The fixed-path worker captures real nine-slice output, masks,
section geometry, margins, insets, prefix availability and fractional DPR.
Its pre-GUI checks and no-helper policy are source-only defenses pending review.

The [offline planner](../../theme/panda/common/native_frame_plan.py) generates
20 strict jobs of 35 frames: five assets × seven sizes × five flavors × four
scales = **700 direct frames**, plus **20 explicit missing probes**.
[Fixture digests](../../tests/fixtures/desktop/native-frame-contract.json)
pin canonical job bytes. Invalid paths/IDs, duplicates, non-finite/bool numbers,
stale hashes, unknown fields, missing/extra cases and unsafe dimensions are refused.

Sizes: 24×24, 288×88, 288×120, 352×168, 1024×48, 352×56 and 303×119.
Scales: 100%,125%,150%,200%.
The worker's explicit frame DPR and the synthetic screen's DPR are separate
measurements; no active output is queried.

The Python pixel analyzer is tested against clearly synthetic Cairo buffers.
It checks native-sized buffer bounds, masks, rounded exterior and opaque interior
pixels (with a one-device-pixel antialias band), seam holes and canonical center
paint. It deliberately does not certify native execution or isolation.
The C++ worker has no automatic Python/CTest launch path.

A strict compile/link with `-Wall -Wextra -Wpedantic -Werror` succeeded using
existing development tools. The resulting executable and ELF metadata remain
in private local evidence. It was not launched, including for help/version output.
Only a configure-only regression with synthetic CMake import targets and a
forced compiler fixture ran; no installed Qt package configuration, compiler
probe, ldd or Qt inspection executable was used.

## Harness source audit

[18 immutable source receipts](desktop-d4c3-s2-source-references.json) cover
KSvg6.31.0, Qt6.12.0, libplasma/plasma-desktop6.8.1 and bubblewrap0.13.1.
All source payloads are verified by Git blob, SHA256 and length.
The worker's audited sequence is:

1. External isolation must precede ELF loading. Libraries and their constructors
   can run before main; source guards cannot establish that outer boundary.
2. main restricts dumps, reads bounded controlled job/attestation JSON, verifies
   read-only mounts, private paths, exact environment, namespace differences,
   inherited fds, denied generic socket creation and pinned runtime hashes.
   QtCore parsing/hashing is already in use at this point.
3. The worker installs a reviewed-in-source no-helper policy, sets fixed Qt
   arguments/library paths and disables session management.
4. QGuiApplication creates the offscreen integration with NO_GLX required.
   Input modules and desktop integration variables are absent; no window,
   QtQuick engine, compositor or graphics context is constructed.
5. Font infrastructure and KSvg caches can read/write private resources.
   Disabling frame caches does not make initialization/teardown read-only.
6. Named ImageSet and FrameSvg objects read absolute verified Panda assets.
   All output uses exclusive creation under the one fresh /out directory.
7. Scoped objects and QGuiApplication are destroyed, mapped hashes rechecked,
   and capture.json written. Static destructors can still run afterward; a
   future parent trace/waitpid/journal must cover the entire lifetime.

The [pinned KSvg rectangle-cache constructor](https://github.com/KDE/ksvg/blob/7367d0da1442deba4cabb2ad878b0a75f4b36a88/src/ksvg/svg.cpp#L165)
opens a cache configuration and synchronizes it on shutdown.
The [pinned Qt offscreen factory](https://github.com/qt/qtbase/blob/025bdad181de241e81bf853c8a2d7bf3d19261a9/src/plugins/platforms/offscreen/qoffscreenintegration.cpp#L400)
can select a GLX variant; the worker requires the NO_GLX setting rather than
treating the word offscreen as an isolation guarantee.

These findings inform the proposed sandbox. They are not an experimentally
validated initialization trace, complete transitive-library audit or runtime pass.

## Isolation attestation proposal and blockers

The [attestation schema](../../tests/native/isolation-attestation.schema.json)
contains hashes for the canonical job, exact worker, runtime bundle and outer
filter, parent namespace identities and per-file runtime hashes. No sample with
fabricated “passing” identities is supplied. Checksums and caller-supplied
namespace IDs do not authenticate approval or replace an independently verified
supervisor.

Before any worker execution, separately approve and implement an isolated
supervisor with these gates:

- Create new private HOME/XDG/work/output/runtime directories below a new
  `.local-ai/d4c3-s2/run-<nonce>/` root. Record ownership, modes, parent bindings
  and creation identities; do not reuse earlier runs or historical roots.
- Establish mandatory user, mount, PID, IPC, network, UTS and cgroup namespaces;
  no-new-privileges, dropped capabilities, resource limits and reviewed syscall
  policy. Do not use best-effort namespace fallbacks.
- Stage a minimal read-only runtime/asset/font snapshot. Expose no host HOME,
  /run/user, display/bus sockets, /sys, graphics devices, credentials or whole
  Qt plugin tree. Only the reviewed offscreen plugin and needed libraries are
  candidates for inclusion.
- Set the exact private HOME/XDG/fontconfig/environment values in the worker
  audit. Use deliberately absent valid session/system bus addresses. Namespace
  and syscall controls must prevent access independently of those variables.
- Review exact binary/plugin/compiler/dependency provenance and pre-main
  initialization, including distribution patches and crash-handler behavior.
  Current hashes/build IDs/static ELF closure are measurements, not provenance
  authentication or proof of loaded code.
- Run a separately approved inert non-Qt attestation first. Check mounts,
  namespaces, fds and syscall denials without probing a real bus/display/provider.
  If any mandatory boundary is unavailable or unproven, stop before native exec.
- For an approved native trial, retain whole-process tracing, source/input
  hashes, stdout/stderr, native pixels/masks/measurements, exit status and all
  created-object/caching evidence. Clean only verified disposable objects.

No supervisor, sandbox, namespace probe or native trial was executed here.
The candidate worker's guard/filter/margins/encoder/rendering/teardown branches
are compiled and source-reviewed, not runtime-tested. Execution remains blocked
on the separate approval and successful isolation/provenance gates above.
No system security or graphics policy may be weakened to pass them.

## Fallback remains a separate unverified test

This worker tests **direct Panda file rendering**. Its missing probe is also an
absolute Panda path, so it cannot establish Plasma Theme fallback.
Raw KSvg ImageSet/default lookup is distinct from libplasma's FallbackTheme
processing; no Plasma::Theme object is constructed.

Actual fallback into Breeze Dark remains **unverified**. A separately reviewed
typed resolver/consumer and its complete initialization/isolation path are
required. A copied fallback algorithm, direct rendering of a Breeze resource,
custom default alias, live shell or QML loader cannot substitute for that test.

## Verification and preservation

Observed checks:

- Baseline: 328 tests passed. Latest suite: **341 tests passed** in 89.135 s.
  Ten regressions cover the solid path and safe job/pixel behavior; three more
  compile/configure-only regressions cover checked screen access and strict
  target warning handling without executing the worker.
- **13 Fish scripts**, **54 package entries** and bootstrap permissions passed.
- **25 SVGs** validated; five package structures match. Existing model tests
  cover **600** frame/scale combinations; these are Cairo models, not native runs.
- **54 generated artifacts** reproduced in an independent process, preserving
  their identities, modes, owners and mtime. All40 old package files and five
  canonical palettes match baseline; all seven PNG bytes remain unchanged.
- **700 native frame cases +20 missing probes prepared; zero executed.**
- Final worker compiled/linked with warnings as errors. SHA256:
  `e233456db742b909bbcc13be14e6ec7f3708beaf4a3cfe22cbb2098669eab2bf`.
  Build ID: `46fc26271bbc5407a03d667290841996031eba60`.
  Static ELF inspection records61 linked closure entries plus offscreen plugin
  and compiler hashes. No target execution or ldd was used.
- All18 source receipts match bytes, SHA256 and Git blobs.
- The earlier S2 source review found no important confirmed defects. The
  targeted correction review could not complete because its reviewer hit a
  usage limit. Corrections and the supervisor proposal were self-checked; no
  completed independent correction review is claimed.
- Tracked and new-file whitespace checks pass; exact diff and inventory are
  retained locally for review. The index is empty and all work is uncommitted.

Static binary hashes do not authenticate the full compiler/distribution supply
chain, loaded runtime or pre-main behavior. Those remain execution blockers.
No runtime attestation, Qt/KSvg render, guard/filter trial or fallback pass is
claimed. Safe regressions cover asset coverage/preservation,
job refusal and synthetic pixel analysis. Native runtime results remain absent.
The S1 checkout and its proposal files, original canary checkout and unrelated
work are retained. No live configuration, theme manager, widgets, sensors,
services, graphics settings, packages or D3B1A/R0 evidence are modified.
No commit, push, merge or deployment is authorized or performed.


## Final corrections and next-stage handoff

Primary-screen DPR access now uses an explicit null-refusing helper before any
KSvg capture. Compile-time tests accept a nonnull fixture and reject a null one
at the throw branch. The helper adds no Qt process or altered frame behavior.

The dedicated CMake target now specifies -fPIC,-O2,-Wall,-Wextra,-Wpedantic,
-Werror, strict C++20 and the reported build-ID option. The worker README gives
the exact Fish-compatible direct compilation recipe. A synthetic-import CMake
configuration and warning-producing syntax-only fixture verify the target's
actual settings; no Qt package scripts or native target are run.

The separately reviewable [supervisor implementation plan](desktop-d4c3-s2-supervisor-plan.md)
starts with a tiny non-Qt process and independent boundary confirmation.
Only afterward may a separately reviewed one-frame profile and new execution
approval be considered. The current35-case worker remains unchanged in scope;
it cannot serve as a single-frame trial by truncating its validated job.
