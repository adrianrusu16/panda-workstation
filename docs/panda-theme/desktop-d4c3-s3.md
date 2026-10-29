# D4C3-S3 — external VM native rendering preparation

Date: 2026-10-29. Base: PR #14 merge
`217e62a9dc141e3f600974a982b1484c61eaf375`.
Status: **source preparation for review; execution disabled**.

The selected environment is GitHub's standard x64 `ubuntu-24.04` hosted VM.
The prepared workflow validates and exports sources and receipts only. It does
not provision a runtime, compile a worker or render a frame. The separate C++
candidate has an unconditional refusal in `main`; its capture body is dormant.
No dispatch, package installation, native worker, inert probe, supervisor,
theme activation, live Plasma operation or D3B1A evidence access occurred.
Source-only publication is approved; native execution remains disabled. The existing automatic workflow, sealed
Helios infrastructure, 700-case matrix and fixtures are unchanged.

## Dependency compatibility and choice

Ubuntu's [Noble package index](https://packages.ubuntu.com/search?keywords=qt6&suite=noble)
lists Qt 6.4.2, so installing its default Qt packages cannot reproduce Qt 6.12.0.
The [Qt release directory](https://download.qt.io/official_releases/qt/6.12/)
and [KDE release information](https://kde.org/info/kde-frameworks-6.31.0/)
confirm the requested upstream releases exist.

| Criterion | Signed distribution snapshot | Reviewed version-pinned build/runtime bundle |
| --- | --- | --- |
| Correct versions | The inspected Arch 2026-10-15 snapshot contains Qt 6.12.0 and KSvg 6.31.0 with exact revisions. | Build Qt 6.12.0 and Frameworks 6.31.0 from authenticated sources; pin every tool and system dependency. Version strings alone do not establish ABI or patch equivalence. |
| Reproduction | Lock every package filename, SHA256, signature packet, dependency/provider edge and epoch. Use the complete Arch userspace and loader inside the Ubuntu VM. | Pin build image, compiler/linker, sources, patches, flags, generated files and runtime outputs. Preserve build logs/SBOM and verify a rebuild. No reviewed bundle currently exists for this candidate. |
| Storage | Measured package metadata: 269,772,825 compressed bytes; 1,209,618,720 installed bytes including compiler tools. | A pruned runtime could be smaller. Build peak and toolchain closure are unmeasured; building Qt/Quick/Frameworks on every 14 GB runner introduces a larger storage/time uncertainty. |
| Closure | 151 runtime packages; 158 including direct worker build tools. No Plasma session. Distribution dependencies include libraries unused by this one frame. | Potentially narrower runtime, but plugin/font/cache/loader dependencies must be discovered and authenticated independently. |
| Maintenance | Frozen package graph; refresh only through review. Archive retention, historical key validation and package patch review remain necessary. | Own build recipe, build infrastructure, patch policy, license/source obligations, closure extraction and rebuild comparison. |

**Select the signed Arch snapshot package set.** It has concrete matching
metadata, a bounded closure and lower preparation cost for the first frame.
This is an independently recreated Arch userspace, not a copy of Helios or a
claim of byte-equivalence to CachyOS builds. Matching upstream versions does
not prove matching distribution patches, flags or output pixels.

The [package lock](../../tests/native/external_vm/packages.lock.json) pins:

| Package | Revision | SHA256 |
| --- | --- | --- |
| qt6-base | 6.12.0-3 | `dea8a8c45a7929af115a2ba96c60dff927425f8c65432cf5d1027c79c8aa98f0` |
| qt6-svg | 6.12.0-1 | `922e48a36b2c8e1ac16c2b5f222f0e33e52fb2ec5384e69715eb427512af7ebf` |
| ksvg | 6.31.0-1 | `6b6c8aedffd3d4a5f598ed9b09c05afbe7c417744a00425ee5769b5594689b3f` |

Lock SHA256:
`f4034660aa04de28123ccaf80fd6d12d2d7eb9c8f2d29e5043f1f4511fe16618`.
The core index receipt is
`6934bca80575ac127e105be771203e79c2eb52728520e23ecaf3f319d7ba9c87`;
the extra index receipt is
`06d0136d06b713b2be141efb0c121b2e10e1a2c5bdc1a5bf44e7f32d4b9756f8`.
Only these two metadata archives were downloaded. Package payloads were not.
Hashes and embedded PGP packets have **not** been authenticated as package
signatures. HTTPS index acquisition is a recorded origin, not a signing trust root.

Runtime roots are `ksvg`, `qt6-base`, `qt6-svg`, `ttf-dejavu`; build roots are
`gcc`, `pkgconf`. Recursive **required** dependencies are retained. Optional and
make dependencies are not pulled in. Explicit virtual-provider choices are
`libgl→libglvnd`, `opengl-driver→mesa`, `libz.so→zlib`, and
`dbus-units→dbus-broker-units`. Versioned ABI providers and version constraints
were resolved with the existing Arch `vercmp` metadata utility. No package
manager transaction was used. Epoch-bearing filenames and zero-payload
metapackages are retained exactly as the index reports them.

The 151-package runtime graph is 198,693,766 compressed bytes / 924,018,548
installed bytes. It contains Qt Declarative because the packaged KConfig
requires it. The upstream KSvg build additionally requires CMake >=3.30, ECM,
Qt Quick/QML/QuickControls2 and KirigamiPlatform. Upstream native KF6Svg linkage
is QtGui, QtSvg, KArchive, KCoreAddons, KGuiAddons, KConfigCore and KColorScheme;
KColorScheme adds KI18n. A native-only consumer does not justify installing
Plasma desktop/workspace, KWin, Breeze, a display manager or widget session.
Mesa, X11, Wayland, D-Bus and sensor-related **libraries/packages** occur in the
distribution closure; their presence does not authorize device access or
starting daemons. `linux-api-headers` supplies userspace headers, not a kernel.

The alternative build bundle remains feasible in principle. It would require
Qt Base/Svg/Declarative/ShaderTools 6.12.0, ECM and the required Frameworks
6.31.0 graph, pinned native build prerequisites, reviewed feature flags and a
separate runtime ELF/plugin/font manifest. No unverified third-party Qt binary
installer, rolling repository or host library fallback is substituted here.

## Reproducing the selected userspace after authorization

This is the required construction contract, **not an implemented launcher**:

1. In a fresh eligible VM, download only lock URLs; enforce compressed-size and
   total-disk budgets. Hash every archive before any extraction. Never mix dates,
   mirrors with different metadata, Ubuntu libraries or locally copied files.
2. Authenticate a separately reviewed, digest-pinned Arch signing keyring and
   master-key trust policy. Verify every locked PGP signature against the exact
   archive bytes and record full signer fingerprints and historical validity.
   Do not bootstrap trust from an unverified keyring package or disable signatures.
3. Review each package's signed `.PKGINFO`, `.BUILDINFO`, `.MTREE`, packaging
   source commit and patches. Record source/build origins for Qt, KSvg, compiler,
   loader/libc, plugins and transitive code. Distribution authentication is not
   proof of a reproducible build. Failure or unavailable provenance stops here.
4. Assemble an isolated Arch rootfs from verified files with a separately
   reviewed safe extractor. Do not run package install hooks, enable services,
   use a general `base`/Plasma group, or install into the Ubuntu runner root.
   Review symlink/hardlink/collision/path handling before extraction. Record a
   canonical file manifest, modes, symlinks, owner policy and rootfs digest.
5. Build only the new single-frame source in the isolated build root using the
   locked GCC/pkgconf closure and direct C++20 compilation. Record compiler,
   flags, source and ELF/build-ID/DT_NEEDED/interpreter/RPATH receipts. The
   optional CMake target is build-only; choosing that route first requires
   adding a pinned CMake >=3.30 closure. Do not use host Qt or `ldd` execution.
6. Establish and verify the future capture boundary before the ELF loader
   starts. Use the rootfs's loader and complete shared-library closure. Stage
   only the offscreen platform plugin, PNG capability and one verified DejaVu
   font under private paths; record their file hashes. No unreviewed plugin tree.
7. After a separate reviewed source change removes the candidate seal and
   explicit execution approval is given, run exactly one frame, export bounded
   evidence, confirm complete teardown, then let the disposable VM be destroyed.

`lock_snapshot.py` regenerates the package graph from the two original index
files, without installation. With those files already present and the existing
`vercmp` utility, a Fish-compatible metadata-only command is:

```fish
python3 -B tests/native/external_vm/lock_snapshot.py \
    --core /tmp/panda-s3-core.db --extra /tmp/panda-s3-extra.db \
    > /tmp/panda-s3-regenerated.lock.json
cmp tests/native/external_vm/packages.lock.json /tmp/panda-s3-regenerated.lock.json
```

The recorded index hashes must match before accepting regeneration. Archive
availability, package signatures and rootfs execution are still untested.

## Exact proposed workflow and resource contract

The complete proposed file is
[panda-native-vm-preparation.yml](../../.github/workflows/panda-native-vm-preparation.yml).
It is separate from `validate.yml` and has only `workflow_dispatch`, no inputs
that enable execution, read-only `contents` permission, an immutable checkout
revision, no persisted Git credentials, no secrets, no cache, and SHA-pinned
checkout/upload actions. It performs no dependency installation or native build.
The job guard requires `workflow_dispatch` on `refs/heads/main`.
Its only repository process checks source bytes and writes a preparation packet.

[GitHub documents](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
that standard `ubuntu-24.04` x64 is a fresh hosted VM. Public repository capacity
is 4 CPU / 16 GB RAM / 14 GB SSD; private repository capacity is 2 CPU / 8 GB /
14 GB. `ubuntu-slim` uses a container and is excluded. `ubuntu-latest`, ARM,
self-hosting, Helios and nested virtualization are excluded.

The workflow **must exist on the default branch before manual dispatch is
available**, as [GitHub specifies](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow).
Source-only publication is authorized. Dispatch requires separate authorization. Even a
dispatch of this exact preparation workflow cannot render a frame.

| Resource | Preparation workflow, implemented | Future single-frame capture, required |
| --- | --- | --- |
| CPU | Source process affinity: 1 CPU; RLIMIT_CPU 60 s | Cgroup 1 CPU; 30 CPU s |
| Memory | Source process RLIMIT_AS 1 GiB | Whole capture cgroup 1 GiB; swap disabled |
| Time | Job 5 min; preparation 2 min; export 2 min | 60 s wall, kill/reap entire process tree; encompassing job <=15 min |
| Output | <=24 regular files, <=8 MiB total, <=4 MiB each, no core dumps | <=16 MiB total; <=1 MiB per log stream; 2×101,376-byte raw buffers; bounded PNG/JSON files |
| Processes/fds | Source code has no subprocess launch; 64 fds | Cgroup pids.max=64; no helper processes; 64 fds; parent supervision separately bounded |
| Storage | Small source packet; no package/rootfs disk use | <=512 MiB archives; <=2 GiB installed closure; <=4 GiB total staging/build scratch; require >=6 GiB free before work |
| Retention | Artifact retained 7 days; one concurrency group | Same bounded retention, subject to later review |

GitHub provides the outer VM hardware ceiling. Checkout/upload actions run
outside the repository Python process's rlimits and rely on that ceiling and
job/step timeouts. This workflow makes no claim of a configurable whole-job
CPU/memory cgroup. The future native limits require an actual enforced cgroup;
recording numbers in JSON is not enforcement.

`runner-provenance.json` records `ImageOS`, `ImageVersion`, OS/architecture,
kernel, source/workflow SHAs and run identity using an explicit environment
allowlist. `dependency-provenance.json` records the lock digest and explicit
false download/install/signature/runtime-manifest states. The workflow records
provider identity, not a cryptographic VM attestation. Standard runner images
[change weekly](https://docs.github.com/en/actions/concepts/runners/github-hosted-runners);
`ubuntu-24.04` cannot pin their immutable image digest. Retain the exact
`Set up job` included-software/image links and image SBOM in future evidence.
Reject unavailable provenance; do not claim identical kernels across runs.

## Single-frame source and inputs

[candidate.json](../../tests/native/external_vm/candidate.json) fixes Cyber,
`widgets/background.svg`, 288×88 logical pixels, DPR 1 and `KSvg::FrameSvg`.
It is separate from the S2 jobs and contains no missing-asset probe or matrix.
Expected margins are 12 logical pixels in top/right/bottom/left order.
The SVG SHA256 is
`acdc56b7cae58f5943d7f18371e69161fdc8d4ed1ebd6a9b2929e797073609fe`.

[single_frame_candidate.cpp](../../tests/native/external_vm/single_frame_candidate.cpp)
uses real FrameSvg `framePixmap`, `alphaMask`, section bounds, margins, fixed
margins and insets. Exact compile-time Qt/KSvg versions and runtime Qt version
are checked. The KSvg header version is explicitly identified as a header
version; actual runtime identity must come from verified loaded-library receipts.
No `Plasma::Theme`, QML engine, compositor, application event loop or service
provider is constructed. Qt and ImageSet/cache/font infrastructure can still
initialize; this is why pre-main containment and shutdown review remain required.

The separate [CMakeLists.txt](../../tests/native/external_vm/CMakeLists.txt) has
no install, test or launch target. Its package queries require exact versions.
The selected direct compiler route avoids adding CMake to the package lock.

Input receipts cover the existing Cyber SVG, colors, metadata, plasmarc and
license, plus private fontconfig. Nothing is installed into a desktop theme
directory. Future capture HOME and XDG config/cache/runtime directories are
fresh private tmpfs paths; data points only to `/inputs/data`; locale/timezone
are `C.UTF-8` / `UTC`. Require `QT_QPA_PLATFORM=offscreen`,
`QT_QPA_OFFSCREEN_NO_GLX=1`, `QT_SCALE_FACTOR=1`, `QT_FONT_DPI=96`,
`FONTCONFIG_FILE=/inputs/fonts.conf`, and empty system config/data search paths.
Start from an empty environment allowlist; omit display/session/bus/portal,
SSH/GitHub credentials, proxy, preload and user plugin variables. Disable
networking before loading Qt. Resolve and pin the font, plugin and complete
runtime manifest before execution; these are explicit pending candidate inputs.

The source preparation packet includes candidate/build/checker sources, schemas,
the package lock and exact theme input bytes. It contains **no rendered pixels**.

## Expected future evidence

[capture.schema.json](../../tests/native/external_vm/capture.schema.json) defines
the worker capture; [artifact.schema.json](../../tests/native/external_vm/artifact.schema.json)
defines the enclosing future evidence index. No actual instance is supplied.

- `frame.png`, `frame.rgba`, `mask.png`, `mask.rgba`: native image and alpha-mask
  outputs. Raw buffers are packed row-major straight RGBA8888, 288×88×4 =
  101,376 bytes each, without row padding. Preserve encoded and decoded hashes.
- `capture.json`: actual dimensions/DPR, 18 section rectangles, measured margins,
  fixed margins/insets, Qt compile/runtime version, KSvg header version and
  output digests. Write after scoped Qt/KSvg teardown; global exit still follows.
- `runtime-manifest.json`, `loaded-mappings.json`, `build-receipt.json`: all
  package/signature/keyring/source/build/ELF/plugin/font origins and hashes,
  including library mappings before and after capture. No host library fallback.
- `boundary-receipt.json`, `exit-receipt.json`, `stdout.txt`, `stderr.txt`: enforced
  limits and networking/mount/device/fd/environment exclusions, parent-observed
  exit/signal/timeout/OOM state, accounting, completed teardown and file inventory.
  Preserve bounded failure logs and partial outputs as failures; do not call them
  a frame pass. No execution receipt is a replacement for independent review.
  Failed setup records identify the failed stage and use explicit null/false
  unavailable provenance. Successful records require authenticated provenance
  and the loaded-mappings file in the export inventory.
- `reproducibility-receipt.json`: candidate/source/input/lock/runtime/workflow
  digests and exact runner/capture conditions, followed by per-output hashes.
  The first run says `not-yet-compared`. Only separately authorized repeated
  runs can establish equality; compare raw pixels and masks as well as PNGs and
  measurements. Runner image/kernel differences must remain visible.

Capture success does not set `native_runtime_verified=true`. Independent
provenance/boundary/output review is still required. Neither schema attests
live Plasma compatibility, libplasma fallback, the old matrix or Helios safety.

## Threat-model comparison

The protected asset is the user's daily Helios workstation and session. The
trust boundary moves to an independently operated GitHub VM/VMM before any
guest loader, constructor or Qt code executes. An in-guest minimal container
or namespace may organize the Arch userspace, but **the independent VM** supplies
the Helios boundary. No local VM or workstation shares are involved.

| Helios-hosted requirement/problem | External VM treatment | Still required |
| --- | --- | --- |
| Shared Helios kernel; pre-main worker/loader containment | GitHub guest kernel/VMM separates all guest execution from Helios before the process starts. | Trust GitHub/Azure isolation and control plane. Guest approved-code-only identity is not proved by this boundary; dependency/code provenance remains mandatory. |
| Desktop UID/session, private HOME and real display/bus/device paths | No Helios mount, SSH/agent forwarding, session socket, clipboard, GPU or physical device passthrough exists. Fresh guest HOME/XDG inputs only. | Verify in-guest minimal mounts/fds/env; no workspace, Docker socket, display/bus, `/dev/dri`, input or host device exposure to capture. |
| `RLIMIT_NPROC=1` conflicts with launcher initialization | Separate supervisor resources from capture cgroup pids/CPU/memory limits; guest failure is disposable. | Implement and test full-tree kill/reaping/accounting and timeout/OOM/failure evidence. Do not relax or change the old limit. |
| Non-owner `O_NOATIME` inspection of root-owned host pins | No host root-owned runtime pins are inspected; verified downloaded files are guest staging inputs. | Read-only inputs, authenticated bytes and stable content identities; no fallback in the old inspector. |
| Mandatory local namespace/cgroup availability and inert Gate 2 attestation | The old supervisor/profile/attestation protocol is not used by the new candidate. No false attestation is generated. | Review and demonstrate the new guest capture controls before execution. This does not certify or unblock Gate 2 on Helios. |
| Runtime provenance from mutable installed CachyOS packages | Whole dated Arch package closure and guest loader replace host dependencies. | Authenticate packages, patches, toolchain, actual mapped files, offscreen plugin and font. Metadata hashes alone are insufficient. |
| Network/provider isolation | Future capture network namespace is disabled before exec; no providers or credential env are passed. | Actions control-plane checkout/export networking remains outside capture. A fresh VM by itself does not block egress. |
| Host write journals and cleanup proof | No Helios writes are possible through guest mounts; VM is discarded. | Guest input preservation, private caches, export allowlist/size/link validation, parent-observed complete shutdown and bounded retention. |

This explicitly replaces the Helios protection mechanism; it does not weaken,
expand, execute or repair the sealed supervisor. A VM is not proof of exclusive
approved code inside the guest. Untrusted native code could corrupt guest
evidence, so independent provenance and review remain material trust assumptions.

## Remaining blockers and limitations

1. The signing trust bootstrap, actual package signature checks, packaging
   commits/patch review and file-level ELF/plugin/font provenance are incomplete.
2. No rootfs was assembled or booted. A reviewed safe assembler/build/capture
   harness and failure exporter still need implementation and source review.
   This preparation workflow deliberately has no native execution path.
3. The candidate entry point remains sealed. Removing it requires a reviewed
   source change and separate execution authorization, never a dispatch input.
4. Guest kernel/cgroup/namespace availability, environment sanitization,
   pre-main isolation, PNG encoding, cache writes/destructors and complete
   teardown are not runtime-tested. No runtime compatibility claim is made.
5. Snapshot bytes can be redownloaded and checked, but archive availability and
   signing-key lifecycle are external dependencies. Preserve reviewed payloads
   in a content-addressed store if later authorized; no publication occurs here.
6. The moving standard runner image prevents bit-identical whole-VM replay.
   Version-pinned userspace and receipts support controlled comparison, not
   identical kernels or deterministic pixel output before observation.
7. A single opaque direct SVG cannot establish Wayland desktop behavior,
   fractional scaling, widget/QML integration, Plasma fallback, the 700-case
   matrix or visual/performance acceptance on Helios. It does not need a
   complete Plasma session.

The authoritative Panda layout, Cyber palette and Helios opaque-first design
are preserved. The only scope reduction from a fully executable VM environment
is deliberate source preparation: provisioning and capture remain blocked on
the explicitly listed authentication/harness/review/authorization gates.

## Source-only verification and changed-file inventory

Verification commands and exact final results are retained in
[desktop-d4c3-s3-verification.json](desktop-d4c3-s3-verification.json).
The 13 new source-contract tests and 12 existing offline/native-static tests
pass. The candidate passes strict C++20 syntax checking with warnings as errors.
The package lock regenerates byte-for-byte from the two recorded indexes.
Workflow YAML structure, its Python run block, Python ASTs and JSON parsing are
checked. Draft 2020-12 schema meta-validation passes with the existing
JSON Schema validator. actionlint and GitHub service acceptance are not claimed. The hosted
receipt/export path has not run; its refusal outside hosted context is tested.
An independent read-only review found two evidence-schema defects: unavailable
failure provenance and missing mandatory successful loaded-mapping export.
Both were corrected with regressions observed failing before the corrections
and passing afterward. Finalization review also found that whole-object uniqueness did not guarantee
section-ID coverage. The schema now requires each of the 18 IDs exactly once;
the duplicate/missing-ID regression failed before the correction and passes after.
The review did not authorize execution.
Local source checking reads repository sources, never D3B1A evidence. The C++
check uses `-fsyntax-only`; no object, linked binary or compiler probe executable
is created or launched. Existing native-static fixtures use synthetic CMake
imports and compile-only expressions; they do not execute the KSvg worker.
The full repository suite is intentionally not invoked because it includes
the sealed supervisor's Python execution fixtures. No supervisor execution is
part of this task. No Fish file changed.

Complete publication inventory (15 additions relative to the recorded base):

- `.github/workflows/panda-native-vm-preparation.yml`
- `docs/panda-theme/desktop-d4c3-s3-plan.md`
- `docs/panda-theme/desktop-d4c3-s3-source-references.json`
- `docs/panda-theme/desktop-d4c3-s3-verification.json`
- `docs/panda-theme/desktop-d4c3-s3.md`
- `tests/test_external_vm_preparation.py`
- `tests/native/external_vm/CMakeLists.txt`
- `tests/native/external_vm/artifact.schema.json`
- `tests/native/external_vm/candidate.json`
- `tests/native/external_vm/capture.schema.json`
- `tests/native/external_vm/fonts.conf`
- `tests/native/external_vm/lock_snapshot.py`
- `tests/native/external_vm/packages.lock.json`
- `tests/native/external_vm/prepare.py`
- `tests/native/external_vm/single_frame_candidate.cpp`

The source references distinguish documentation, inspected upstream build
declarations, package-index measurements and unverified authentication claims.
The preparation plan records the bounded implementation decisions. Publication
is source-only; workflow dispatch and native execution remain unauthorized.
