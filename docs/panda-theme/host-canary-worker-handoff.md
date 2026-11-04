# Host Canary bounded worker handoff contract

**Explicit Linux integration implemented; all live custody acceptance remains blocked.**
The default PR #26 entry still grants one worker lifetime. The opt-in
`ProspectiveSession.offline_phases()` controller accepts only explicit injected
boundaries and refuses the real Linux kernel adapter or implicit native spawn.
The separate explicit typed native entry described below connects Linux adapters.
Importing source grants no host trial, restart, adoption or cleanup authority.

## Decision and alternatives

Current profiling identifies complete-history comparisons and immutable prefix
copies as the main costs. In-place controller history removes a copy; all current
reads, comparisons, graph checks, synchronization, record ordering and ceilings stay.
The fake kernel's separate immutable-file copy remains deliberately unchanged.

Do not cache current filesystem observations, replace complete history with a
rolling digest, suppress full checks or extend/reset the existing run deadline.

A separate possible protocol optimization is **ordered observation aggregation** for
adjacent independent file expectations. It could reduce RPC/evidence volume
without adding process custody. It is not implemented: before approval it must
retain every original per-occurrence read/dispatch check, original failure order,
complete completed-prefix/failure evidence, original duplicate reads, unchanged
2 MiB aggregate message bounds and full result acknowledgement before dependent
operations. No mutation, synchronization, lease, source-grant or lifecycle barrier
may enter a batch. Two legal 1 MiB images may exceed the RPC ceiling after base64;
partitioning must be decided before requests, never by retrying a failed batch.

The bounded phase-worker mechanism below can be studied independently of that
optimization. Timings alone do not establish native safety or sufficient margin.
It must never be implemented by calling the existing start method a second time, clearing
`preserved`, replacing `_lifecycle`, resetting a timer or trusting a saved journal.

## Fixed successful phase boundaries

| Phase | Explicit plan | Controller-verified terminal checkpoint |
|---|---|---|
| A | initialize, provision | Complete baseline-last enrollment; no journal; source/deployed baseline; provisioning complete |
| B | install | Installed journal, six forward operations, no intent/stages; exact proposed managed images |
| C | recover | Restored journal, five reverse operations, no intent/stages; source/deployed restored and generated target absent |
| D | cleanup_outputs, recover | Verified output absences/cleanup receipt and closed journal bound to that receipt |

Initialization and provisioning cannot be split: the current Provider is not an
interrupted-provisioning resumption capability. Cleanup uses a new operator view
but obtains all authority from the continuously held broker and validated records.
Each phase must close every view/source grant/lease and pending record stage.
These are enforced controller boundaries, not accepted native worker lifetimes.
Native startup, runtime validation, real sync costs and extra evidence remain
unmeasured and require separate implementation review and authorization.

Only clean successful phases qualify. A stopped/incomplete/manual-inspection
result, nonzero exit, signal, policy failure or timeout remains preserved. Crash
recovery remains unsupported. No phase may declare a partial mutation
successful merely to obtain another 30 seconds.

## Controller authority and durable state

One original external controller retains the same trusted bootstrap, evidence
ledger, root/parent/source/runtime descriptors, object birth registrations,
expected current pins, retired originals and kernel namespace context throughout.
No descriptor is closed/reopened by path, imported from JSON or learned again.
Each current full-history and full-graph check remains mandatory.

Durable phase records bind the global fixture session, approved total plan digest,
phase ordinal, allowed next checkpoint, previous namespace-closure record,
original root birth/descriptor identity, current graph/checkpoint digests, helper
and runtime approvals, original held namespace proofs and cumulative budgets.
Their bytes must be reconstructable and synchronized before the corresponding
grant. Controller memory advances only after that durable record succeeds.

The ledger is evidence under uninterrupted custody, **not bootstrap authority**.
Controller loss, descriptor loss, ambiguous state or external changes permanently
prevent handoff; a new process may not reconstruct authority from these records.
Matching paths, inodes, hashes and journal contents do not revive custody.

## Prove the previous lifetime closed

Before a handoff intent, require all of the following in order:

1. The controller verifies the expected engine checkpoint from its own original
   descriptors, including exact file images/absences, record transitions and
   source/baseline/provisioning authority. A worker-reported status is insufficient.
2. Every RPC is fully evidenced and acknowledged; no fragments, result, view,
   program grant, lease or staged record is pending. The old epoch is revoked
   permanently; late frames cannot be accepted by another server.
3. The original native lifecycle records every task's termination and the exact
   original worker's zero status, with no unexpected descendants or policy events.
4. Existing STOP intent is durable, the held init pidfd is used, native
   `waitid(P_PIDFD)` proves namespace completion, authenticated CLOSED arrives,
   helper exit/output/retained namespace evidence passes, and closure is durable.
5. The controller rechecks its entire original graph and ledger. Every old
   lifecycle/pidfd/nsfd proof stays retained; a boolean or EOF cannot replace it.

This ordering is embodied by an opt-in typed controller transition, never an
arbitrary callback or worker-provided receipt. Existing `finish()` and `teardown()`
are one-shot and cannot simply be called again; a reviewed epoch-collection API
must distinguish already-proved closure from missing closure without rereaping
or signalling a historical PID.

## Birth, generation, RPC and resumed authorization

After the old lifetime is proved closed, append/sync the new phase's handoff intent
before clone. Allocate a new monotonically increasing epoch and independent native
invocation nonce. Keep the global filesystem session unchanged. Do not overload
the present single `session` equality: split filesystem binding from invocation
identity explicitly in both native/Python protocols.

Create a fresh namespace through the reviewed native helper's atomic birth path.
Validate received original pidfd/nsfd, helper credentials/binary and root binding;
durably register birth before START. Require new policy installation, runtime
binding and initial exec acknowledgements before any RPC. Inner namespace PID,
task birth generation, outer helper identity, native invocation nonce and epoch
must all agree with the controller's current active lifetime.

Create a fresh server/connection with RPC sequence one, but retain a controller
aggregate request ceiling of 4,096 across the whole fixture session. Also retain
the per-worker ceiling. Preserve existing frame/message/record limits, 100,000
ledger events and 64 MiB total evidence across all epochs; no budget resets.
Keep the original 1 MiB stdout and 1 MiB stderr caps both per worker and in
aggregate across the fixture session. Durably carry completed byte counts and
check the cumulative remaining allowance during each capture; a new transport
does not grant another output allowance. Overflow preserves/revokes before any
successor or teardown grant. Retain all original per-stream bounds and the
original task/event limits alongside the cumulative ledger ceiling.
Start with an empty per-epoch evidence cache so references cannot accidentally
resolve a prior epoch's equal sequence number. Cross-epoch deduplication would
need a separate fully qualified reference design and is outside this proposal.

The controller grants only the reviewed next phase whose predecessor was verified.
Read-only phases remain independently read-only; legal mutation/record transition
checks and owning leases remain in force. A newly valid journal alone cannot
authorize a resumed action. No handoff grant transfers fixture descriptors to a
worker; the external broker retains them continuously.

Each new worker gets its own absolute 30-second run window, established once for
that new proven birth. This is a separate lifecycle architecture; no timer is reset
inside a running transaction worker. Bootstrap/closure bounds remain unchanged.
No handoff is allowed simply because a previous deadline is approaching.

## Interrupted initialization, handoff and teardown

| Failure point | Required behavior |
|---|---|
| Old phase/status/RPC/closure incomplete | Revoke and preserve; no new birth |
| Handoff intent sync or memory update fails | Preserve original descriptors/evidence; never retry/reconstruct from intent |
| Clone or initial descriptor transfer interrupted | Retain partial lifecycle/transport; preserve, no guessed PID/group cleanup |
| New birth/policy/exec registration fails | Existing native containment only; no RPC grant, no next epoch |
| Stale epoch/sequence/nonce/PID reuse | Reject before dispatch; preserve; numeric equality is not birth evidence |
| Controller/helper/namespace/descriptor custody lost | Preserve all known/unknown resources; no fallback adoption |
| Any record/frame/message/event/byte/request ceiling reached | Preserve; no epoch or budget reset |
| Final cleanup interrupted | Stop at the first uncertainty; keep all original/retired descriptors and surviving resources |

Before final fixture deletion, validate the complete collection of closed native
lifetimes, final engine checkpoint, quiescent broker, original current graph and
durable external final evidence. Do not substitute the last worker's closure for
all prior births. Existing narrow descriptor-relative deletion constraints remain.
Historical resources and resources without prospective custody are always excluded.

## Offline implementation and review boundary

`tests/host_canary_phases.py` keeps the original controller/session/broker/ledger,
root birth and immutable original FD values. It appends durable phase intent,
registers fresh birth before START, validates an authoritative checkpoint, retires
the RPC server, completes original namespace closure, and records phase completion
before granting the next lifetime. Only this original object can advance; there
is no receipt import or reconstruction API. All failure states are permanent.

`PhaseLifecycle` deliberately shares the inherited native packet, policy, task,
RPC, run deadline and finish protocol. It has a separate constructor because
`start_mediated()` binds one plan and conflates filesystem session with native
invocation identity. The phase constructor repeats its runtime/source/interpreter
approval checks, then uses the inherited birth path. It never clears the existing
one-worker latch or replaces the session's single-worker lifecycle. Each phase
uses an independent random native nonce, the same filesystem session, a strictly
increasing RPC epoch and a fresh evidence cache. Broker role/journal guards reject
mutations outside that phase before allocation or publication; an eventual failed
checkpoint is not the authorization boundary.

The closed-lifetime collection retains original transports, pidfd/nsfd birth
records, output counts and durable closure sequences. Rechecks use the original
transport's identity check; they do not call a closed lifecycle's `check()` against
obsolete root metadata, send another STOP, signal a saved PID or reap again.
Current filesystem authority is checked separately through the original broker.
Deletion itself requires the exact typed collection, complete final checkpoint,
quiescence and durable final collection evidence before the existing narrow
registered-role removal. Interrupted deletion preserves survivors and descriptors.

`tests/host_canary_phase_fixture.py` supplies fake descriptors, fake kernel packets
and a cooperative in-process Python thread running the actual mediated engine.
All real Linux filesystem methods and native spawn are patched to fail. This
harness exercises the controller protocol but cannot enforce a kernel boundary or
prove descendant termination. Tests cover missing/reordered acknowledgements,
unauthorized phase mutations, descriptor/controller loss, stale grants, incomplete
closure, output/request ceilings and failure before/after durable transition writes.
The original 79 dynamic refusals and mandatory general CI workflow stay unchanged.

For a reproducible **synthetic** sample, run from the repository root:

```fish
env PYTHONHASHSEED=0 python3 -B tests/host_canary_phase_performance.py --out /tmp/panda-phase-sample.json
```

Choose a new output path for every run. The benchmark runs the full reviewed engine
source with unchanged 30-second lifecycle deadlines, full history equality checks,
synchronization calls and aggregate budgets over fake boundaries. It reports
per-phase wall/CPU time, worker run time and controller overhead, request/record/
frame counts, retained compressed payloads and Linux `ru_maxrss` in KiB. Each RSS
sample is the process cumulative high-water mark, not an independent phase peak.
Total timing includes controller initialization; teardown is tested separately.
No measured fake sync or closure counts constitute actual durability or custody.

## Explicit Linux adapter integration

| Controller boundary | Concrete implementation and retained evidence |
| --- | --- |
| Allocation and mutation | Original TrustedBootstrap, LinuxKernel, external DurableLedger and BrokerStore; unchanged descriptor-relative fixed roles and intent/sync/registration ordering |
| Authorization | One-use LinuxPhaseGrant, original session/runtime/source/helper descriptors and reviewed fixed-plan digest; consumed before launch; no instance-injected transport factory |
| Birth | Existing NativeLifecycle.start and LinuxTransport.spawn; C clone3 with PIDFD/PID namespace, authenticated SCM_RIGHTS, policy/exec acknowledgements and independent invocation nonce |
| Capture | Original phase Capture; read at most 64 KiB and remaining worker/aggregate stream allowance plus one; retain overflow before refusal, including final drain |
| Closure | Original helper process/channel, stdout/stderr FD and FIFO identities, pidfd/nsfd and hashes; native P_PIDFD termination, clean helper exit, pipe EOF and original pidfd readiness |
| Handoff | Durable checkpoints, retired RPC grants and complete retained closure collection before a new generation |
| Final removal | Distinct one-use LinuxRemovalGrant bound to the reviewed final graph, then existing narrow role teardown; execution approval alone never authorizes fixture deletion |

ProspectiveSession.linux_phases(LinuxPhaseGrant(...)) requires the original typed
Linux session and internally selects the concrete transport. It has no CLI,
environment switch or ordinary-discovery activation. Capability construction
is a live action requiring separate owner authorization.

Each acquisition failure retains known partial handles. Failed post-birth binding
retains the full lifecycle/server/capture. Controller loss, replaced pipes, missing
closure, identity drift, failed durable records and grant replay preserve the
session. Closed verification never waits, reaps, signals or checks obsolete
fixture-root metadata again.

The pidfd must have a distinct retained **pidfs** inode on a 64-bit platform;
anonymous-inode pidfds and unsupported filesystem identities refuse. Pid=-1 is
only a dead-process observation, never original identity. Linux documents pidfs
inode uniqueness and the older anonymous-inode limitation in
[pidfs.c](https://raw.githubusercontent.com/torvalds/linux/v6.18/fs/pidfs.c);
the required magic is in
[linux/magic.h](https://raw.githubusercontent.com/torvalds/linux/v6.18/include/uapi/linux/magic.h).
This requirement has not been checked against the host.

Across all four phases the original request budget remains 4096; stdout and
stderr each remain 1 MiB aggregate, evidence remains 64 MiB/100,000 records,
and compressed RPC retention is explicitly capped at 64 MiB/8192 entries.
Complete ledger history comparisons and synchronization remain unchanged.
Source (1 MiB), helper (4 MiB), runtime (128 MiB), frame and message caps remain.
These are component bounds, **not a hard total RSS or worker address-space
limit**. Byte copies, Python objects, native buffers and benchmark instrumentation
add overhead. Observed RSS must be reported separately.

The Linux, native-grant and native-integration test suites exercise concrete
methods over fake kernel, libc, transport and filesystem boundaries. No real
custodian, socketpair, subprocess, namespace, procfs observation or fixture is
used by these paths. Cooperative engine threads are never custody witnesses.

Original native parent, namespace-init and Python absolute deadlines remain
30 seconds per worker. No budget, timer, full-history check or sync is reset.
Phase D's previously measured 2.62-second synthetic margin does not establish
native margin. Removing repeated observations or fsyncs is not safe reduction.
A possible separately reviewed five-phase contract could split D after
cleanup_outputs: exact output absences, durable cleanup receipt, restored journal
without pending transitions, original retired-directory custody, quiescence and
complete closure before a final recover. That needs a new plan digest,
checkpoints, guards and final-count rules; it is **not implemented or authorized**
by the current four-phase grant.

## Current synthetic concrete-method measurement

A reviewed complete full-source sample through the concrete Linux methods with fake OS
boundaries measured worker A/B/C/D at 4.393/18.782/19.889/21.965 seconds, cumulative
66.102 seconds (65.703 CPU seconds). Per-phase controller overhead was
0.097/0.184/0.252/0.266 seconds. Phase D's synthetic remaining margin was 8.035
seconds. This is a different harness/run from the earlier 2.620-second minimum;
it is not evidence of a production improvement or an accepted native margin.

The sample retained 17,537 records / 10,439,169 ledger bytes, 2,970 requests,
3,493,179 compressed cache bytes / 718 entries, 1000 stdout bytes and zero stderr.
It performed four synthetic launches, four helper waits and 26 pidfd readiness
checks. Process execution peak RSS was 338,324 KiB; phase endpoint high-waters
were cumulative, not independent phase peaks. Fake syscall, synchronization and
closure costs do not model kernel latency. No durability/integrity work was removed.
An earlier sample completed phases but failed in report formatting; its incomplete
log is retained privately and is not counted as a successful benchmark.

Reproduce using the existing benchmark with the explicit --linux-methods option;
it selects only the fake OS bridge and never runs real Linux adapters. Preserve
each output path. Exact source hashes, phase counts and timings are in the private
measurement record. No host acceptance follows from these numbers.

## Remaining live acceptance gates

The concrete Linux path is implemented and tested only over fake OS boundaries.
Its source integration does not establish an accepted multi-invocation closure
collection on a real kernel. No callback, environment flag, serialized proof or
adapter-name disguise can establish that acceptance.
Real storage latency, kernel namespace/pidfd continuity, process descendants,
resource use and deadline margin remain unvalidated. Mock success cannot accept
any of them.

The first possible separately scoped trial is the existing **one-worker,
initialize-only** path, on a newly and exclusively created fixture. Before asking
for execution, pin and review exact helper source/binary/toolchain digest, curated
runtime manifest and source/baseline digests; specify the nonroot controller,
approved allocation/evidence/runtime parents, kernel namespace/seccomp/Landlock/
pidfd support, supported ext4/btrfs state, descriptor handoff and private evidence
retention. Define exact creation and closure steps and the stopping/preservation
conditions for every failed birth, policy, RPC, registration, sync, timeout or
closure proof. Initialization remains inside 30 seconds and must establish
creation-time custody and enforced denial of direct mutation before any broader
phase plan is considered. Any deletion requires its own explicit scoped approval
and complete original custody; ambiguity preserves all resources. No historical
fixture interaction, host policy change, provision/install/recover/output cleanup
or four-phase live acceptance follows from an initialize-only authorization.

See the [initialize-only preflight](host-canary-initialize-preflight.md) for the remaining owner decisions.
