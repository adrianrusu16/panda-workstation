# Host Canary prospective supervisor contract

**Design for independent review; runtime adapter disabled.** This supplements the
[file-only fixture contract](host-canary-fixture.md). It grants no permission to
allocate Host Canary fixtures, run their dynamic tests, inspect historical roots,
or activate a theme. The existing 79 pre-allocation refusals remain visible.

## Authority and trust boundary

The supported model is a cooperative sole user with quiescent external writers.
`mkdir` followed by first `open` cannot prove creation custody against hostile
same-UID substitution. A checksum, inode tuple, JSON record, environment variable,
successful callback or later matching observation cannot repair that limitation.
An owner-authorized fresh session must establish the cooperative premise before
allocation; absent that premise, allocation and cleanup remain disabled.

The supervisor never reads or searches historical fixture paths. Preexisting or
interrupted resources are preserved indefinitely. Their journals are evidence,
not authority to reopen or adopt them. Lost original descriptors, custodian
restart, failed descriptor transfer or uncertain durability revoke cleanup.
An independently sustained custodian may retain original descriptors across a
worker crash; this is continuous custody, not restart recovery from pathnames.

The approved theme transaction, 24 roles, schema-2 baseline-last enrollment,
engine/operator separation and Helios safety rules remain unchanged. The
supervisor's ledger is a separate test-custody protocol, not schema-3 enrollment.

## Approaches and selected boundary

Path snapshots, `rmtree`, PGID scans, subreaper status and Python audit hooks alone
cannot establish complete creation/descendant custody; they are rejected.
A fully brokered runtime can establish prospective evidence but requires a new,
independently reviewed allocation, filesystem and lifecycle adapter.

The selected first stage is a **source-only state/protocol model** for that broker.
It has no filesystem allocator, process launcher, deletion implementation or
operator integration. Mock records exercise decisions; they cannot mint a live
capability. The future runtime design below is a prerequisite contract, not a
claim that this stage implements containment or cleanup.

## Custodian, runner and allocation protocol

The future custodian is outside the worker PID namespace and inside the same
approved private filesystem/user-namespace view. It holds the original parent,
runner, runtime, registry and active object descriptors. It performs no native
Fish startup. A fresh private runner has fixed isolated HOME/XDG/TMP/search paths,
0700 directories and an exclusively created 0600 registry with one writer.
No inherited display, session bus, auth home or unrelated environment is authority.

Bootstrap cannot register its own birth in a not-yet-created runner registry.
Before creating the runner, an owner-authorized external bootstrap anchor must
already provide private storage, an exclusive durable ledger and retained parent
descriptors, under a separately accepted creation boundary. Runner, runtime and
registry intents/results are recorded and synced in that external ledger. Only
after their creation and bindings are accepted may a handoff record bind the
internal registry to the external session. The external anchor stays outside
runner teardown and retains final evidence. Its creation, exclusivity and handoff
are unimplemented runtime acceptance gates; an ambient path or internal registry
content cannot self-certify them. The first-stage writer receives an **alleged
existing bound registry** and proves neither its exclusive birth nor this anchor.

Each resource has a session-local object ID and retained descriptor generation,
creation role, parent ID/name, device/inode, UID/GID, full mode, mount and namespace
binding. Regular files require one link; symlinks, special files, unexpected
ACL/xattrs, foreign mounts/owners or unknown names refuse. Numeric descriptor reuse
must not match a prior generation. This counter is an exclusive-custodian
protocol property: `fstat` plus a generation cannot detect an unreported close
and reopen of the same numeric descriptor onto the same inode. Descriptor
ownership must be exclusive; unsupported close/dup/replace operations are
forbidden. Known loss, transfer ambiguity or unsupported manipulation revokes
the session. Mock generation/replacement checks do not prove kernel open-file-
description identity. No descriptor number or recorded inode alone serves as a
transferable capability.

Every parent-relative name is one nonempty basename: reject absolute names,
`.`/`..`, separators, traversal, multi-component names and control/NUL characters
before any OS call. Observe metadata against original expectations; drift refuses
rather than replacing those expectations.

Before the first fixture allocation, a reviewed runtime must supply a narrow,
session-bound cleanup-policy handle. It names only fresh object roles for that
session; it contains no arbitrary root path or general delete function. It has
no removal authority until all registration, binding and lifecycle conditions
below hold. The current `fixture_cleanup = None` stays unchanged in this stage.

Using the external bootstrap ledger first, then the accepted internal registry,
for every runner, fixture, directory and file creation:

1. Verify the retained parent descriptor and its binding; persist an exclusive
   `create-intent` with a new object ID and fixed basename. Sync the ledger and
   required ledger parent before any allocation.
2. Perform one exclusive creation relative to that parent. Capture and retain the
   first descriptor immediately, under the stated quiescent-writer premise. A
   failed first open or uncertain creation preserves the object; do not retry by
   learning the path's current identity.
3. Verify descriptor type, identity, metadata, namespace/mount and parent binding;
   durably register the creation before returning a use grant. Sync newly created
   directory entries and the registry. After write, file fsync and parent fsync,
   recheck the registry descriptor, parent descriptor, parent/name binding and
   permitted metadata against the retained expectations **before acknowledgement**.
   Any post-sync mismatch or failure poisons the session and preserves partial
   effects. Until acknowledged, the worker cannot use the object, enroll it or
   create children.
4. Keep original descriptors while active. Recheck against original evidence
   before every modeled grant; observations compare and never replace evidence.

The ledger uses bounded canonical records with version, session/object IDs,
strictly increasing sequence, previous-record digest and event payload digest.
Hashes detect corruption, not hostile-user forgery. There is one exclusive writer
and a held advisory session lock. Any short/incomplete write, fsync failure,
sequence gap, duplicate/out-of-order event or ambiguous acknowledgement permanently
puts the session into `PRESERVE`; no use or cleanup grant follows. A durable intent
without durable registration is retained uncertainty, not an owned empty object.
Physical power-loss durability still requires separate validation.

All later file publication, replacement, rename, unlink and metadata changes must
pass through the same broker with pre-intent and post-result identity records.
Both rename endpoints and replaced objects remain accounted for. The existing
operator/direct engine syscalls and frozen subprocesses are not fully mediated;
a future adapter must close this gap before any real suite authorization. Late
tree walking cannot substitute for missed creation or mutation events.

## Process and descendant lifecycle authority

The proposed Linux lifecycle backend creates a fresh PID namespace with a trusted
init and a birth-bound pidfd/namespace descriptor held by the external custodian.
No test worker or helper runs before that identity handshake and durable session
registration. Every test/validator subprocess must be born below that init; the
custodian launches no uncontained test helpers. The init reaps descendants and
does not delegate launch to external services. `setsid` and double-fork do not
escape this PID namespace lineage.

The namespace is an explicit lifecycle boundary: Linux kills namespace processes
when its init terminates and prevents new forks into that dead namespace.
See the [Linux PID namespace contract](https://man7.org/linux/man-pages/man7/pid_namespaces.7.html).
The future adapter must independently verify birth bindings and the completed
kernel shutdown/wait semantics, including nested namespaces and delayed exits.
If it cannot demonstrate completion within its bound, it preserves resources.
This is not a promise that sending SIGKILL alone proves closure.

After tests: seal the launch channel, revoke all worker grants, terminate the
contained init using its retained process capability, and establish completed
namespace teardown with the reviewed backend before any filesystem deletion.
The custodian remains alive with all custody descriptors. A reaped test leader,
empty process group, liveness-pipe EOF or callback returning success is insufficient.
Process capability/namespace loss, unexpected external launch, timeout or uncertain
shutdown puts the session into `PRESERVE`. No PGID-only fallback is permitted.
Kernel feature availability, pidfd birth handshake, external-launch exclusion and
shutdown completion are live-adapter acceptance gates, unproved by model tests.

## Narrow teardown and interrupted-state preservation

Cleanup requires all of: continuously held original descriptors, durable complete
event history, closed worker grant set, accepted real lifecycle authority and an
exact current inventory matching original/authorized mutation evidence. Unknown
children or changed/missing bindings preserve the entire affected root, including
known siblings; their later identity must not be learned for deletion.

An authorized adapter removes only individually registered entries, deepest first,
relative to retained verified parent descriptors. Every removal has a durable
intent, identity/binding check, exact `unlinkat`/empty-directory removal, parent
sync and durable result. A directory must be empty; no recursive delete primitive,
glob, follow-symlink operation or inferred ownership is available. Retain removed
object descriptors until zero-link status and durable result are established.

Any failure stops remaining deletion. Successfully removed entries stay recorded;
remaining/ambiguous entries and evidence stay preserved. No automatic compensation,
journal-based resumption or adoption is permitted. Registry/runner removal is
last and requires its own held-parent authority; an external private final receipt
must be durable before the last evidence object is removed. A failed final receipt
keeps the runner. No expiry or historical cleanup job is introduced.

## First implementation stage and regression scope

After independent design approval, proposed files are
`tests/host_canary_supervisor.py` and `tests/test_host_canary_supervisor.py`.
The module implements three concrete verification components, plus state handling:

- A descriptor verifier accepts only already-supplied descriptors. Through an
  injected OS boundary it calls `fstat` and non-following parent-relative `stat`,
  checks type/owner/mode/link expectations and exact parent/object bindings, and
  tracks descriptor generations. It never opens or allocates a path. Its first
  capture is only an alleged birth descriptor until a future creation broker is
  accepted; its consistency checks do not prove the missing creation interval.
  Mount/namespace labels supplied by that boundary are unverified context. Their
  comparison detects label drift only; kernel identity/binding requires the
  separately accepted runtime backend. `fstat`/`stat` alone cannot establish it.
  The fixed pin includes directory link count: a legitimate new child directory
  can change that count and safely cause refusal. No accepted metadata-transition
  backend exists to approve such a change; this stage does not relax or relearn it.
- A bounded registry writer receives an alleged existing bound registry and
  parent; it does not establish exclusive creation or bootstrap provenance. It
  serializes canonical sequence/hash-linked records, checks the binding before
  writes, checks the exact write count, fsyncs the file and required directory,
  then repeats descriptor, parent/name and metadata checks before acknowledgement.
  The proposed fixed limits are 4 KiB per record, 100,000 records and 64 MiB per
  session. A short write, OS error,
  failed sync, limit violation or uncertain result irreversibly poisons it.
  Tests inject the low-level write/fsync/stat boundary; a successful arbitrary
  high-level persistence callback is not a durability acknowledgement.
  It does not establish descriptor flags, current file offset or `O_APPEND`, an
  actual exclusive lock, whole-history content readback or ctime continuity.
  These are prerequisites for an independently accepted runtime registry adapter;
  the first-stage checks grant no real append or durability authority. An alleged
  empty file, stable size and matching identity do not supply those prerequisites.
- A session state machine consumes that writer/verifier's local results, enforces
  intent/registration-before-use and irreversible preservation. `cleanup_plan`
  always refuses; it returns neither a teardown plan nor a permit. The model
  does not import paths/journals to restore state.

It exposes **no live cleanup permit**, accepts no root-path deletion request and
cannot set the operator's cleanup callable. The lifecycle gate has no accepted
backend and always refuses live teardown. Simulated records, boolean claims and
callbacks returning success cannot change that gate. No constructor parameter,
environment flag or public approval method can enable it in this stage.

Regression tests first reproduce: use before durable registration; missing intent;
short write/fsync/ack uncertainty; foreign/replaced parent; reused descriptor;
lost descriptors/restart; unsafe basenames; post-sync binding/metadata drift;
duplicate/gapped records; unknown descendants; teardown
before verified lifecycle closure; leader-reap/PGID/callback-only false closure;
partial cleanup failure; and any attempt to upgrade a simulated result to a live
permit. Pure tests prohibit OS open/stat/allocation/process/signal/delete calls.
Any descriptor-I/O test added later uses a separately named disposable sandbox
with no Host Canary prefix or operator integration, under explicit test scope.
The eight existing filesystem-prohibited offline checks remain unchanged.

The real allocator, runtime registry creation/adapter, IPC/descriptor transport, syscall broker,
PID-namespace/pidfd backend and actual cleanup adapter are **not implemented or
enabled in this authorization**. Their separate acceptance requires adversarial
failure/race review, then explicit permission for fresh fixtures and dynamic runs.
Host/native theme activation remains a later independent gate.

## CI reporting without hiding the block

Keep the general validation workflow and all79 existing methods unchanged. Do not
run those methods locally, even to reproduce their known supervisor refusals.
Static AST collection can produce a separate manifest naming all79 methods with
`NOT EXECUTED / BLOCKED: prospective supervisor and fresh-fixture authorization`.
It is blocked evidence, never a pass or skip. Report an aggregate dynamic status
of `BLOCKED`, alongside independently scoped permitted results.

A later separate source-only job may run the eight offline checks and model tests
with a name that states that scope. Its success cannot replace the existing broad
job or dynamic acceptance. Ordinary discovery currently reaches79 pre-allocation
guard refusals; preserve those visible CI failures and draft status. The sealed
native validation input is unchanged. Broader permitted regression discovery must
publish its explicit excluded-method manifest and aggregate blocked status.

## Requirement and review checklist

| Required property | Contract / first-stage evidence |
|---|---|
| Creation-time identity/custody | Durable intent, exclusive create, first descriptor; cooperative gap explicit |
| Private runner/runtime/exclusive registry | Fixed isolated tree, one writer, original descriptors; real adapter gated |
| Descriptor binding | Parent/name metadata and protocol generations; pinned link counts may refuse legitimate changes; mount/namespace labels remain unverified kernel context |
| Capability before allocation | Session-bound policy, initially inert; no live capability issued in model |
| Descendant supervision | Fresh trusted-init PID namespace; real closure backend separately accepted |
| Durable/fail-closed registration | Modeled ordering/poisoning only; flags, offset/append, actual lock, history readback and ctime require accepted runtime adapter |
| Preserve ambiguity/interruption | Irreversible PRESERVE; no restart adoption or late identity learning |
| No preexisting adoption | No adoption/import API; runtime birth and prior nonexistence proof remain gated |
| No unrestricted deletion | Exact registered entries only; no delete implementation in first stage |

Review must challenge missing creation intervals, interrupted registration, worker
death before descriptor handoff, false closure, stale FD/identity reuse, unknown
Fish descendants, partial teardown and final evidence durability. Source-only
success resolves none of the real adapter, fixture execution or live-use gates.

Implemented source-only checks are available in the separate
[offline/mock workflow](../../.github/workflows/host-canary-source.yml):

```fish
python3 -B -I -S tests/test_host_canary_offline.py
python3 -B -I -S tests/test_host_canary_supervisor.py
```

The workflow always prints the static 79-method NOT EXECUTED/BLOCKED manifest,
including when a permitted check fails. It executes neither the dynamic methods
nor a runtime adapter. General validation and its custody refusals remain unchanged.
