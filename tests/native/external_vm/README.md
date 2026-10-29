# External VM source preparation

This directory supplies a frozen Arch userspace contract and a sealed C++
candidate for one Cyber `widgets/background.svg` frame at 288×88 logical pixels,
DPR 1, using `KSvg::FrameSvg`. It supplies no approved native launcher. The
[offline preparation proposal](s4/README.md) adds authentication and rootfs
admission interfaces; its delivered trust policy remains `pending-review`.

Only source validation and synthetic tests are currently permitted. Workflow
dispatch, package authentication/decoding, installation, rootfs assembly, native
build/capture, theme activation and D3B1A access require separate authorization.
Do not run either native worker, the inert probe or the supervisor. Their
[existing safety contract](../README.md) is independent and remains sealed.

## Source checks

Run from the repository root with existing tools:

```fish
python3 -B tests/native/external_vm/prepare.py --check
python3 -B tests/native/external_vm/s4/harness.py --plan
python3 -B -m unittest discover -s tests -p 'test_external_vm*.py' -v
```

`--check` validates source hashes and seals. `--plan` emits a data-only stage
design to stdout; it grants no execution authority. Neither command provisions
a runtime. Authentication and assembly CLIs refuse execution. Capture and
`export_evidence()` refuse unconditionally; caller-supplied receipts cannot
enable them. `check_export_manifest()` validates data only. Preparation/build
stage assertions are design checks, not an executable dispatcher.

## Frozen userspace and provenance

[packages.lock.json](packages.lock.json) fixes the 2026/10/15 x86-64 Arch snapshot,
158 packages including 151 runtime packages, exact filenames, hashes, embedded
signature packets, revisions, dependency/provider edges and build epochs.
Qt Base is 6.12.0-3, Qt Svg 6.12.0-1 and KSvg 6.31.0-1. The lock digest is
`f4034660aa04de28123ccaf80fd6d12d2d7eb9c8f2d29e5043f1f4511fe16618`.
The set totals 269,772,825 compressed bytes and 1,209,618,720 installed bytes;
the runtime subset totals 198,693,766 and 924,018,548 bytes respectively.

Runtime roots are `ksvg`, `qt6-base`, `qt6-svg`, `ttf-dejavu`; build roots are
`gcc`, `pkgconf`. Required dependencies are recursive; optional/make dependencies
are excluded. Explicit providers are `libgl→libglvnd`, `opengl-driver→mesa`,
`libz.so→zlib`, `dbus-units→dbus-broker-units`. Arch `vercmp` semantics apply.
Dependency-only metapackages and epoch-bearing filenames are intentional.
Distribution closure includes Qt Declarative and graphics/bus/sensor libraries;
this does not authorize QML engines, devices, daemons or a Plasma session.
`linux-api-headers` is userspace headers, not permission to change a kernel.

[Source and index receipts](../../../docs/panda-theme/desktop-d4c3-s3-source-references.json)
record two metadata archives and inspected build declarations. Index hashes and
embedded signature packets are not authenticated package signatures. No payload
set, rootfs, compiled candidate or guest attestation has been validated. Matching
upstream versions does not establish CachyOS patch/ABI/pixel equivalence.

`lock_snapshot.py` deterministically regenerates the graph from the two original
index files using an existing Arch `vercmp`, without installation. With reviewed
metadata already available, the metadata-only procedure is:

```fish
python3 -B tests/native/external_vm/lock_snapshot.py \
    --core /tmp/panda-s3-core.db --extra /tmp/panda-s3-extra.db \
    > /tmp/panda-s3-regenerated.lock.json
cmp tests/native/external_vm/packages.lock.json /tmp/panda-s3-regenerated.lock.json
```

Verify the index hashes in the source receipts first. Do not fetch/decode package
payloads or infer trust from an unverified keyring package. Signing identity,
historical validity/revocation, packaging commits, patches, `.PKGINFO`,
`.BUILDINFO`, `.MTREE`, compiler/loader/plugin/font file provenance and actual
mapped libraries require separate review. A reviewed version-pinned source build
bundle remains an alternative requiring its own complete closure and recipe.

## Workflow and evidence boundary

[The manual preparation workflow](../../../.github/workflows/panda-native-vm-preparation.yml)
is restricted to `workflow_dispatch` on `refs/heads/main`, standard x64
`ubuntu-24.04`, read-only contents permission and SHA-pinned actions with no
persisted credentials, secrets or cache. It performs no package installation,
native build or execution. Its source packet does not include an executable S4
dispatcher. Being present on main is a dispatch prerequisite, not authorization.

Preparation limits are one CPU affinity, 60 CPU seconds, 1 GiB address space,
64 descriptors, no core dumps, at most 24 regular packet files, 4 MiB per file
and 8 MiB total. Job timeout is five minutes; preparation/export steps have two
minutes each; artifact retention is seven days. Checkout/upload actions run
outside the repository Python process limits. No configurable whole-job cgroup
or cryptographic VM attestation is claimed.

Runner identity records `ImageOS`, `ImageVersion`, OS/architecture, kernel,
source/workflow SHAs and run identity through an explicit environment allowlist.
Moving runner images prevent bit-identical whole-VM replay. Retain exact image,
included-software and SBOM links for any future authorized run; do not substitute
`ubuntu-latest`, slim containers, ARM, self-hosting or Helios.

[candidate.json](candidate.json) pins six input files and nine preserved sources,
including the existing worker, supervisor, profile, fixtures, automatic workflow
and 700-case planner. The Cyber SVG hash is
`acdc56b7cae58f5943d7f18371e69161fdc8d4ed1ebd6a9b2929e797073609fe`.
Expected margins are 12 logical pixels on all sides. The candidate's `main`
refuses before Qt initialization. The dormant body uses FrameSvg frame/mask,
sections and margins; it does not construct Plasma::Theme, QML, an event loop
or providers. Loader, cache, font and teardown code still require containment.

`CMakeLists.txt` has no launch/install/test target. The frozen direct compiler
design uses locked GCC/pkgconf and `-lKF6Svg`; the optional CMake route first
requires a reviewed CMake >=3.30 closure. Do not use host Qt or execute `ldd`.
[Capture](capture.schema.json) and [artifact](artifact.schema.json) schemas
describe future data, not authenticated proof. Success requires each of the
18 section IDs once, loaded mappings and authenticated provenance. Failed setup
may declare unavailable provenance; that does not authorize capture or export.

## Future capture environment

Future capture HOME and XDG config/cache/runtime directories must be fresh
private tmpfs paths; data points only to `/inputs/data`; locale/timezone are
`C.UTF-8` / `UTC`. Require `QT_QPA_PLATFORM=offscreen`,
`QT_QPA_OFFSCREEN_NO_GLX=1`, `QT_SCALE_FACTOR=1`, `QT_FONT_DPI=96`,
`FONTCONFIG_FILE=/inputs/fonts.conf`, and empty system config/data search paths.
Start from an empty environment allowlist; omit display/session/bus/portal,
SSH/GitHub credentials, proxy, preload and user plugin variables. Disable
networking before loading Qt. Resolve and pin the font, plugin and complete
runtime manifest before execution; these remain explicit pending candidate inputs.
The S4 stage plan is a source design, not a complete launcher environment or
execution authority.

## Gates before execution

The independent hosted VM protects Helios before any guest loader runs; no local
VM, workstation shares, agent forwarding, clipboard, session sockets or device
passthrough are permitted. Trust in the provider/VMM does not prove approved-only
guest code, evidence integrity or denied network access. This mechanism does not
certify or unblock the existing Helios supervisor or its Gate 2 attestation.

After separate source review and scoped authorization, future work must:

1. Authenticate every locked payload and reconcile signed metadata/closure under
   a reviewed public keyring, signer lifecycle policy and hash-pinned tools.
2. Admit the complete archive graph before creating rootfs files; reject unsafe
   paths, collisions, links, special files and budget excess. Run no package
   scriptlets/hooks or services. Never install into the Ubuntu runner root.
   Require 6 GiB free space, <=512 MiB archives, <=2 GiB rootfs and <=4 GiB
   combined staging. Incomplete workspaces must never be resumed as rootfses.
3. Review a build launcher, read-only rootfs, nonexecuting ELF reader, private
   HOME/XDG/build/output, denied network, and toolchain/runtime manifests.
4. Review source unsealing separately. Enforce pre-main namespaces, minimal
   mounts/devices, no display/bus/GPU exposure, exact environment/descriptors,
   plugin/font hashes and loaded mappings. Enforce whole-process cgroups: one
   CPU, capture 30 CPU/60 wall seconds/1 GiB RAM with swap disabled, build
   120 CPU/180 wall seconds/2 GiB RAM, 64 pids/fds, <=1 MiB per log stream and
   <=16 MiB exported evidence. The encompassing job timeout must be <=15 minutes.
   Record the two 101,376-byte raw frame/mask buffers and bounded PNG/JSON data.
5. Prove full-tree kill/reap, no further producer writes and failure accounting
   before implementing export. Test descendants, timeouts, races, truncated
   logs, failed setup/build and teardown. Retain bounded private evidence for
   independent review before destroying the disposable VM.

No single-frame result establishes the 700-case matrix, native fallback,
Wayland behavior, fractional scaling, QML/widget integration, desktop fidelity
or Helios performance. Deployment and retained D3B1A recovery remain separate.
