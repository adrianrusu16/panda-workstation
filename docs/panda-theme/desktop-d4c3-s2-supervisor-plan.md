# S2 sandbox supervisor — implementation plan for separate review

Status: design only. No supervisor/probe code, namespace trial or native run is
implemented or authorized by this document.

The first trial is an **inert non-Qt process only**. Independent review of its
evidence must precede a distinct request for approval of one direct KSvg frame.
Neither an attestation record nor an offscreen setting grants execution authority.

## Minimal implementation scope

Prepare these files in a separately authorized source-only step:

| Proposed file | Responsibility |
| --- | --- |
| tests/native/sandbox_supervisor.py | direct argument/environment construction, input provenance, fresh-root journal, timeouts, trace collection and evidence validation |
| tests/native/inert_probe.c | small libc/Linux probe; no Qt, KSvg, display, bus, provider, sensor or graphics library |
| tests/native/inert-profile.json | immutable namespace/mount/syscall/environment and executable allowlists |
| tests/test_sandbox_supervisor.py | fixture-driven refusal/cleanup/manifest tests; default suite never launches a real namespace or native worker |

No generic command runner, shell evaluation, package installation or policy
repair is needed. The initial supervisor accepts only the inert executable
identity and profile. It has no worker-binary argument or frame-execution mode.
Its default entry point emits a plan/refusal, not a process launch.

Use the accepted source receipts and a newly reviewed Linux x86-64 syscall
policy. The worker's in-process checks are supplementary; the outer boundary
must already cover ELF loading and constructors before main.

## Gate 1 — source and build review

1. Implement the small supervisor, inert C probe, profile and safe fixture tests.
   Build only from reviewed local sources with existing tools; no downloads or
   automatic dependency acquisition.
2. Pin the exact supervisor, probe, loader, libc, tracing tool and bubblewrap
   identities, hashes, owner/modes, build IDs and distribution provenance.
   An inert runtime needs no Qt packages, fonts, theme assets or display plugins.
3. Review every process initialization/teardown path, inherited descriptor,
   environment variable and allowed filesystem write. Include failure before
   main, crash-handler/dumpability behavior and resource accounting.
4. Review the complete classic-BPF policy, architecture/x32 handling, thread/
   process creation, socket and io_uring denial, namespace/ptrace/mount controls.
   Do not claim a filter is proven merely because PR_GET_SECCOMP reports a filter.
5. Run source-only tests against disposable fixtures, including stale identities,
   symlinks, hostile paths, wrong hashes, malformed evidence, cleanup refusal and
   timeout handling. Mock only process dispatch; validate real argument/manifests.
6. Obtain review of the concrete implementation. Ask separately for authorization
   to run **only the inert isolation trial** with exact source/profile/binary hashes.

No real namespace test, probe invocation or Qt process is part of Gate1.

## Gate 2 — separately authorized inert trial

Create one new private root:
`<worktree>/.local-ai/d4c3-s2-isolation/run-<nonce>/`.
Verify existing ancestors without modifying them; reject symlinks, unexpected
objects, unsafe metadata and parent-binding drift. New directories are0700 and
private files0600. Preserve evidence; cleanup only own identified disposable
objects after review. Do not reuse any historical unresolved root.

The supervisor must establish:

- Mandatory user, mount, PID, IPC, network, UTS and cgroup namespaces. No
  best-effort/try fallbacks, host networking or joining the desktop session.
- A minimal read-only runtime root and input snapshot. Only new work/output/cache
  directories are writable. Fresh procfs, minimal synthetic devices and private
  tmp/run/shared-memory locations expose no host HOME, /run/user, /sys, display
  socket, bus socket, GPU device, credentials or unrelated configuration.
- Empty/whitelisted environment, private HOME/XDG, synthetic passwd/group/NSS
  resources and intentionally absent valid bus addresses. No DISPLAY,
  WAYLAND_DISPLAY, session, input-method, proxy, agent or credential environment.
- No-new-privileges, dropped capabilities, fixed descriptors, bounded CPU/memory/
  output/fd use and a wall timeout. No policy, kernel, global crash setting,
  service or graphics modification.
- A reviewed outer syscall filter installed before exec of the inert probe.
  The initial executable and its runtime closure are an explicit allowlist;
  the payload cannot spawn a shell, bus helper or arbitrary second program.
- Tracing of only the newly created process tree, from launch through waitpid
  and complete teardown. Never attach to an existing process. Tracer behavior
  and any required permissions must be included in the trial review.

The inert probe produces measured records, never an approval flag:

| Boundary | Required evidence |
| --- | --- |
| Namespaces | parent and child namespace identities differ for every required namespace; child procfs belongs to the new PID namespace |
| Mounts | complete child mount table matches the approved graph; read-only root/inputs and only declared new writable mounts |
| Descriptors/capabilities | exact descriptor inventory, expected private standard streams, no inherited socket/agent fd, zero effective capabilities |
| Syscalls | generic socket creation denied with the expected errno, namespace/ptrace/helper controls verified; no network endpoint or real bus connection attempted |
| Bus/display | no live address/fd/path in the exposed mount/environment; no D-Bus method, X11/Wayland handshake, loader or GUI used |
| Filesystem | read/write attempts operate only on purpose-created sentinels; readonly sentinel writes fail and deliberately unexposed sentinels remain inaccessible |
| Preservation | input/sentinel hashes and creation identities match; trace and final journal show only permitted new writes |
| Lifetime | bounded resource use, expected exit status, complete trace and post-exit inventory; partial evidence or timeout is not a pass |

Do not read live Plasma configuration simply to demonstrate that it is
inaccessible or unchanged. The mount graph, policy, controlled sentinels and
trace establish the boundary without inspecting unrelated user data.

On any mandatory namespace/filter/mount/provenance failure, stop and retain
evidence. Report the exact unsupported prerequisite and failing operation.
Do not use weaker flags, root/sudo, install another runtime, change host policy,
start a service or substitute a live-session test. If the necessary prerequisite
inspection itself needs additional access, include it in the next reviewed scope.

## Gate 3 — independent confirmation

An independent reviewer examines the raw private evidence and source/profile
hashes, not just a supervisor-generated summary. Required output:

- verdict with each mandatory boundary supported by measured evidence;
- exact approved profile/runtime/probe identities and successful trial identity;
- list of unexplained reads/writes/attempts, failures and missing evidence;
- explicit scope limit: the result proves only the inert profile and its bundle.

A missing, contradictory or unsupported result blocks further execution.
Do not populate the current worker's attestation schema with fabricated IDs or
reuse an inert result as proof of Qt initialization.

Public summary contains only counts, verdicts, curated file identities and
redacted findings. Namespace IDs, raw traces, paths and process details stay
private. Retain the complete evidence for review before disposable cleanup.

## Gate 4 — prepare a one-frame candidate, still without execution

The current worker validates **35 cases per job** and the existing700-case
contract. It cannot legitimately run one frame as-is.

After successful independent inert confirmation, prepare and review a separate
narrow single-frame profile/entry point. It must accept only the proposed Cyber
standard widget asset,288×88 logical pixels,DPR1, with exact source hashes.
Preserve the full-batch fixture identities and validation; do not truncate a
35-case job, discard extra captures or relax the current contract.

Extend the runtime bundle only with the pinned Qt/KSvg dependency closure,
reviewed offscreen plugin and necessary private font/config resources. Review
all new constructors, caches, plugin loading and shutdown paths, then revalidate
the corresponding boundary with the inert process where applicable. The changed
bundle requires new provenance and attestation; the small inert bundle alone
does not certify Qt behavior.

## Gate 5 — request separate approval for one direct frame

Only after Gates1–4 are satisfied, present the concrete single-frame diff,
exact binaries/profile, evidence and initialization/teardown audit. Request
scoped approval for **one direct KSvg frame**, including output paths, resource
bounds and stop conditions.

Approval would cover that one explicit capture, not the700-case matrix, native
widget deployment, live theme activation or Plasma Theme fallback resolution.
If approved later, trace the entire process, analyze its native frame/mask and
stop for review. Never automatically expand to the full matrix.

Actual libplasma FallbackTheme/Breeze Dark behavior remains a different test.
It requires its own typed consumer, initialization review and authorization;
successful direct Panda asset rendering cannot mark that requirement passed.

## Present state

This document is the bounded implementation proposal. No supervisor or inert
probe exists in this change, no namespace or sandbox trial ran, and no host
isolation prerequisite is represented as established. The current worker and
all700 native cases remain unexecuted.
