# S2 native FrameSvg worker — source/build review only

**Do not run the worker, including --help, until the separate isolation and initialization review authorizes execution.**
No launcher, native test target or installation target is supplied.
The Python repository suite never launches this binary.

The worker is Linux x86-64 specific. It links Qt6::Gui and KF6::Svg, not
Plasma::Theme, QtQuick, a widget loader or a compositor.
CMakeLists.txt is build-only, with AUTOMOC and package registries disabled.
Current worker verification uses the installed compiler directly. A separate
static regression configures this real CMake target with synthetic import
targets and a forced compiler fixture: no installed Qt package script, compiler
probe, worker target or native process is executed by that configure test.

## Reproduce the strict build — compilation only

From the repository root with the existing private .local-ai directory and
development tools already available:

```fish
set -l build_dir (mktemp -d .local-ai/d4c3-s2-build.XXXXXX)
and c++ -std=c++20 -fPIC -O2 -Wall -Wextra -Wpedantic -Werror \
    -I/usr/include/KF6/KSvg tests/native/plasma_frame_worker.cpp \
    -o "$build_dir/panda-frame-worker" \
    (pkg-config --cflags --libs Qt6Gui Qt6Svg | string split -n ' ') \
    -lKF6Svg -Wl,--build-id=sha1
```

This creates an unexecuted candidate in a fresh0700 directory. It does not
install or run it. The dedicated CMake target carries the same -fPIC,-O2,
warning/error and build-ID settings and disables compiler extensions. Real
Qt-package CMake configuration still requires its own reviewed build boundary;
the regression uses synthetic imports only.

The screen DPR helper explicitly throws for a null primary screen before any
DPR access or KSvg capture. Compile-only regressions exercise the nonnull and
null paths without constructing Qt, and test the generated CMake compile flags
against a warning-producing syntax-only fixture.

## Data flow

1. native_frame_plan.py builds 20 canonical jobs: five flavors × four DPRs.
   Each job contains 35 direct frames (five assets × seven sizes), package ID,
   semantic surface/border, source SHA256s and one named missing-asset probe.
2. A future reviewed supervisor must validate the canonical job bytes, stage
   immutable private inputs, verify the exact binary/runtime bundle and establish
   the sandbox **before exec**, including the ELF loader and static constructors.
3. The worker consumes only /inputs/job.json and /inputs/attestation.json.
   It verifies mounts, environment, namespace differences, empty private output,
   inherited descriptors, executable mapping hashes and denied generic socket creation.
   It then installs an additional no-helper syscall filter before QGuiApplication.
4. Real KSvg::FrameSvg supplies framePixmap, alphaMask, section bounds, margins,
   insets and prefix availability. Files are absolute Panda paths; no theme
   fallback is exercised. PNG and straight RGBA buffers are written with
   exclusive creation under /out.
5. The pure Python analyze_pixels function checks captured or synthetic buffers
   for bounds, masks, rounded exteriors, opaque interiors/seams and center paint.
   Its result always leaves native_runtime_verified=false and fallback unverified:
   pixel correctness cannot establish isolation or how pixels were produced.

The main matrix has **700 direct frame cases plus 20 missing probes**:
24×24, 288×88, 288×120, 352×168, 1024×48, 352×56 and 303×119 at
1, 1.25, 1.5 and 2 DPR, for all five flavors and five asset paths.
Frame DPR is explicit; the offscreen QScreen DPR is separately recorded.
This does not observe an active output or prove QtQuick/widget scale behavior.

Unsupported jobs/paths are refused before GUI initialization. For the one
reserved absent absolute path, the worker checks that no native center resolves
and records missing/rendered=false. It does not paint an invalid frame or turn
the absence into a healthy fallback result. Real Plasma FallbackTheme resolution
remains a separate unverified requirement.

## Source audit and attestation boundary

Read the full [S2 report](../../docs/panda-theme/desktop-d4c3-s2.md).
The [attestation schema](isolation-attestation.schema.json) describes data, not
an authenticated proof. No instance was produced, and no isolation test ran.

The external supervisor must establish all of these before any native launch:

- Fresh private HOME/XDG/work/output directories, mandatory user/mount/PID/IPC/
  net/UTS/cgroup namespaces, no-new-privileges, dropped capabilities and a reviewed
  outer seccomp policy. No soft namespace fallbacks.
- A minimal read-only runtime and input snapshot, not the host root or whole
  HOME, /run, /tmp, /etc, /sys or Qt plugin tree. No host display/bus/device fds.
- Only the hash-verified offscreen plugin, synthetic NSS/fontconfig resources,
  and approved S1/Panda/font/wallpaper inputs. No network/provider resources.
- Read-only provenance review of the binary, compiler, linked dependencies,
  plugin and distribution build/patch origins. Hashes alone do not authenticate
  provenance. Review constructors before main and shutdown paths too.
- An inert non-Qt isolation attestation, verified filter behavior, full lifetime
  tracing, waitpid exit status and before/after artifact/creation journals.
- Resource limits and crash-handler/dumpability review, including failures before
  main. Do not change global crash, namespace, kernel or graphics policy.

The in-worker checks are defense in depth. Parent namespace IDs and manifest
hashes supplied by a caller are assertions; a forged attestation is not approval.
External policy identity must be verified by the supervisor. Socket denial in
the worker is a negative generic syscall check, never a connection or a D-Bus
query. A fresh writable /out and private logs are required.

## Initialization and teardown audit

- ELF loading maps Qt/KSvg and transitive shared libraries before main; source
  guards cannot contain this stage. The external boundary must already exist.
- main disables dumpability/core output, reads bounded controlled JSON and performs
  the guard. This uses QtCore hashing/JSON before QGuiApplication; it is not
  “no Qt initialization.” No global Panda QObject is constructed.
- The x86-64 helper filter denies exec/fork/vfork, non-thread clone, clone3
  (ENOSYS), namespace/mount/ptrace/BPF/userfaultfd/io_uring operations, alternate
  syscall architectures and x32 syscall numbers. It supplements the outer policy.
  These branches are compiled but not executed or experimentally validated.
- Fixed internal Qt arguments prevent caller-supplied -plugin/-platform flags.
  Library paths are restricted, AA_DisableSessionManager is set and the
  offscreen/NO_GLX settings are required. Input/portal/session variables are absent.
- The offscreen platform still initializes font infrastructure. Private
  fontconfig must constrain enumeration and cache writes even though the worker
  does not render text.
- ImageSet reads metadata/colors in the private XDG data tree. FrameSvg/Svg
  construction opens the KSvg rectangle cache. Disabling rendered-frame caches
  does **not** disable that cache or possible shutdown synchronization.
- QImage PNG encoding can require further installed capability; compilation
  does not prove it works. An unreviewed plugin must never be added automatically.
- Scoped KSvg objects and QGuiApplication are destroyed before capture.json is
  written. Global cache destructors may still run at process exit. The report
  is capture-only, not proof of completed teardown, a clean trace or acceptance.
- Executable mappings are checked separately from font/cache data mappings;
  hashing all file-backed mappings as libraries would incorrectly reject valid
  private font/cache use. Anonymous executable mappings other than the kernel
  vdso/vsyscall entries are refused.
- No app.exec/processEvents loop, service dispatch, sensor/MPRIS/weather API,
  Plasma Theme, QML or GPU context is used.

No native assertion, mask, margin, scale, PNG encoder, process guard, seccomp
branch or teardown behavior has been observed at runtime. The screen helper
was checked only by compile-time evaluation. Their approval gate remains open.

## Offline-safe verification

```fish
python3 -B theme/panda/common/native_frame_plan.py --check
python3 -B theme/panda/common/plasma_style.py --check
python3 -B -m unittest discover -s tests -v
fish bootstrap/validate.fish
git diff --check
```

These commands validate data/generation and existing offline fixtures. They
neither build a sandbox nor launch the worker. Native capture data, actual
Plasma fallback and running-desktop visual compatibility remain unverified.

The next-stage [supervisor plan](../../docs/panda-theme/desktop-d4c3-s2-supervisor-plan.md)
requires an inert non-Qt trial and independent confirmation before any separate
one-frame approval. The current35-case worker cannot be used as a one-frame
trial unchanged.
