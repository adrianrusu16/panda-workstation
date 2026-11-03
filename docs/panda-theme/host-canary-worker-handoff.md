# Host Canary bounded worker handoff proposal

**Design only; not implemented or authorized.** PR #26 still supports one worker
lifetime. This document grants no restart, adoption, fixture or cleanup authority.
It addresses the contingency that a complete supported plan does not fit the
unchanged 30-second run window after safe computational optimization.

## Decision and alternatives

Current profiling identifies complete-history comparisons and immutable prefix
copies as the main costs. In-place controller history removes a copy; all current
reads, comparisons, graph checks, synchronization, record ordering and ceilings stay.
The fake kernel's separate immutable-file copy remains deliberately unchanged.

Do not cache current filesystem observations, replace complete history with a
rolling digest, suppress full checks or extend/reset the existing run deadline.

The smallest next protocol proposal is **ordered observation aggregation** for
adjacent independent file expectations. It could reduce RPC/evidence volume
without adding process custody. It is not implemented: before approval it must
retain every original per-occurrence read/dispatch check, original failure order,
complete completed-prefix/failure evidence, original duplicate reads, unchanged
2 MiB aggregate message bounds and full result acknowledgement before dependent
operations. No mutation, synchronization, lease, source-grant or lifecycle barrier
may enter a batch. Two legal 1 MiB images may exceed the RPC ceiling after base64;
partitioning must be decided before requests, never by retrying a failed batch.

If that work still lacks comfortable margin, the bounded phase-worker design
below is the next lifecycle option. Timings alone do not prove it safe or necessary.
Do not implement it by calling the existing start method a second time, clearing
`preserved`, replacing `_lifecycle`, resetting a timer or trusting a saved journal.

## Candidate successful phase boundaries

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
These are candidate boundaries, not accepted new worker lifetimes. Native startup,
runtime validation, real sync costs and extra evidence must be measured afresh.

Only clean successful phases qualify. A stopped/incomplete/manual-inspection
result, nonzero exit, signal, policy failure or timeout remains preserved. Crash
recovery is **not** added by this proposal. No phase may declare a partial mutation
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

This ordering must be embodied by a new typed controller transition, not an
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
that new proven birth. This is a proposed new lifecycle architecture, not a reset
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

## Required review and validation before implementation acceptance

First implement/refuse transitions over synthetic descriptors and fake transports:
normal A→B→C→D, repeated/skipped/out-of-order phase, duplicate handoff, stale old
frames, equal numeric PID in a new birth, failed intent/birth/exec/ACK/closure sync,
controller loss, missing original FD, replaced root, unexpected descendant, all
ceilings and interrupted teardown. No successor may become active while any old
lifetime is incomplete or any broker grant is outstanding.

Then independently review the complete Linux/native authority path, not only a
cooperative state model. Neither a mock handoff nor an exported closure record
constitutes real custody. Finally request separately scoped isolated fresh trials
for the exact reviewed helper/runtime/kernel/storage/privilege combination.
The existing 79-test refusal gate remains unchanged throughout this work.
