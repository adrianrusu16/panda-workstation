# Host Canary prospective supervisor contract

**OS adapters implemented; execution and custody acceptance blocked.** This
supplements the [file-only fixture contract](host-canary-fixture.md). No adapter,
native helper, fresh fixture or dynamic Host Canary test may run without a
separately approved trial. Historical roots and retained runners remain excluded
from inspection, adoption and cleanup. All 79 original dynamic refusals remain.

## Authority and supported boundary

The controller, interpreter and reviewed native helper are trusted. External
writers must be quiescent and descriptor ownership exclusive. The mediated
worker has a kernel-restricted view described below; the older generic worker
profile remains cooperative and cannot authorize canonical fixture cleanup.
This is prospective custody, not a hostile same-UID sandbox: `mkdir` and first
`open` are separate syscalls, and an unknown close/reopen onto the same inode is
not detectable from `fstat`. Losing original descriptors or restarting a
custodian permanently loses cleanup authority. A later matching path, digest,
environment variable, registry record or callback cannot restore it.

The root of trust is an independently authorized controller outside all fixture
roots. It supplies already-held, private allocation-parent and separate external
evidence-parent descriptors. Their prior selection/custody is an explicit trusted
bootstrap precondition, never a claim learned from their metadata. The adapter
checks current effective non-root UID/GID, ownership, exact 0700 mode, no ACL/xattrs,
supported backing filesystem and namespace context before allocating anything.
Both external parents remain outside teardown.

`TrustedBootstrap` exclusively creates a 0600 external ledger and retains its
original descriptor and advisory lock. This bootstrap action is authorized by
the external controller; the ledger does not certify its own birth or supply
permission to delete itself. The ledger and its parent are retained indefinitely.
The first fixture intent is durable there before any fixture allocation, avoiding
a circular runner-registry bootstrap. No replay/import, path-adoption, environment
bootstrap exists. Calling the trusted Python constructor
is itself a live operation; only import and bare `LinuxKernel()` are inert.

The approved theme transaction, 24 roles, schema 2 baseline-last enrollment,
engine/operator separation and Helios boot/kernel/GPU/sleep/storage boundaries
remain unchanged. This separate custody ledger is not a new enrollment schema.

## Creation, descriptors and durable acknowledgement

[`tests/host_canary_runtime.py`](../../tests/host_canary_runtime.py) contains the
actual Linux filesystem adapter and prospective broker. It uses parent-relative
exclusive creation, no-follow/no-atime/CLOEXEC descriptors, retained mount/user
namespace descriptors, kernel mount IDs, filesystem identity and full pinned
metadata. Temporary binding observations are nonblocking to avoid a raced FIFO
blocking an observation. Symlinks, special files, unexpected links/ACL/xattrs,
foreign mounts, descriptor flags, metadata changes or unknown children refuse.

Every allocation follows this ordering:

1. Check the complete registered graph and original external-parent binding.
2. Append and synchronize one bounded exclusive creation intent in the external
   ledger, including its parent, role, mode and exact basename.
3. Perform exclusive creation, immediately retain the first descriptor, and
   capture birth identity. Failed first open preserves the uncertain entry;
   there is no retry by learning its pathname.
4. Verify empty-directory/fresh-file state, kernel context and parent/name
   binding. Synchronize the new object and parent, then durably register birth.
5. Apply only explicitly logged metadata transitions, recheck bindings after
   synchronization/registration, then return the local object handle.

Only fixed runner scaffolding and the file-only fixture's exact roles are allowed.
Names are single basenames; absolute paths, traversal, separators and controls
are rejected before syscalls. Originals remain held through successful removal
and retained terminal evidence. Numeric descriptors or a copied object record
are not transferable cleanup authority.

Birth requests use 0600 files and 0700 directories; unexpected resulting modes
refuse. Ordinary 022/077 umasks preserve those requested modes; owner-stripping
umasks remain unsupported. The source/deployed baseline and paired stage roles
use a separately recorded fixed transition to 0644. Directory link changes are explicit:
ext4 increments/decrements for child directories; btrfs keeps its directory link
count at one. Potential btrfs subvolume roots (directory inode 256) refuse. Current
metadata is updated only across the broker's exact permitted syscall transition;
unexplained drift is never relearned as a new expectation.

The ledger requires one retained read/write append descriptor, CLOEXEC, a held
exclusive advisory lock, exact offset/size/ctime/content and parent/name binding.
It checks the complete committed history before append and after write, file
fsync and parent fsync. Canonical records bind session, sequence, preceding record
digest and event. Limits are 4 KiB per record, 100,000 records and 64 MiB per session.
Short writes, invalid records, budget overflow, interruption, failed fsync or
ambiguous acknowledgement irreversibly poison the session. Partial bytes and all
descriptors remain evidence. Logical successful fsync calls do not prove physical
power-loss durability on the actual storage stack.

## Narrow filesystem mutations

The broker exposes scoped creation, bounded append, fixed-role timestamp freeze,
paired stage-to-target publication and transient unlink. There is no arbitrary
chmod, destination path, recursive deletion or general rename/unlink interface.
Freeze verifies both atime and mtime; retained no-atime descriptors keep broker
observations from silently changing them. Once frozen, a file cannot be appended
through the same handle.

Publication records both endpoints and any replaced original before mutation.
Only an allowlisted frozen stage can replace its paired registered target. The
replaced original remains held, with its zero-link identity checked throughout
the rest of the session. File and parent synchronization, explicit parent metadata
transition, new binding verification and a durable completion precede a returned
grant. Partial rename/sync/registration preserves both original descriptors.

Transient unlink is limited to the fixed staging roles and generated fragment.
Support evidence, baseline files and directories cannot be removed through it.
Removal during final teardown has the stricter lifecycle and graph conditions
below. These are controller operations. The mediated engine reaches them only
through the authenticated protocol described below.

## Linux process lifecycle and handoff

[`tests/host_canary_lifecycle.py`](../../tests/host_canary_lifecycle.py) binds the
standalone [native custodian source](../../tests/native/host_canary/custodian.c).
There is no automatic helper compilation, PATH selection or executable download.
The controller must independently review/build the helper, authorize the exact
binary digest and reviewed worker arguments, and retain its executable descriptor.
Binary metadata/content are checked across launch. No source-only hash attests an
unobserved executable.

`start_worker` requires all private HOME, XDG, TMP and system-search scaffolding
roles to be registered first. The original root descriptor is retained in the
controller and explicitly duplicated through the native launch. Child paths/cwd
derive from that descriptor, not inherited HOME/XDG or a retrospective pathname.
There is no inherited display/session bus, authentication home or worker control
socket. The native helper uses atomic `clone3(CLONE_NEWPID|CLONE_PIDFD)` and keeps
init blocked until its birth has been durably registered. It verifies the new
namespace's parent and hands pidfd/namespace descriptors through SCM_RIGHTS while
retaining originals. Per-message kernel credentials, session, descriptor type,
namespace identity and pidfd binding are checked before START.

The trusted init traces worker fork/vfork/clone and exit events. Each bounded
sequenced task event must be durably recorded by the controller and acknowledged
before the stopped tracee continues. Unknown creators/tasks, gaps, lost tracing,
unsupported nonleader exec/TID changes, resource limits or timeout preserve the
session. The helper drops worker capabilities, sets no-new-privileges and uses
seccomp to refuse namespace/untraced-clone/ptrace escapes and external socket or
service delegation. This remains a cooperative worker contract, not a general
security boundary against hostile programs.

`run()` synchronously processes this event protocol; worker success alone does
not close the namespace. `finish()` requires the registered run to be complete,
durably records STOP intent, and uses the held pidfd to kill namespace init.
The native parent must observe completed `waitid(P_PIDFD,WEXITED)` for that exact
init, then send authenticated CLOSED. The controller checks original descriptors,
bounded helper termination and exit 0 before recording namespace closure.
PGID, init-death notification, pipe EOF, a callback returning true or a reaped
ordinary worker is insufficient. Failure to establish completion preserves all
filesystem resources; there is no stale numeric PID/group signal fallback.

This closure reasoning follows the Linux [PID namespace](https://man7.org/linux/man-pages/man7/pid_namespaces.7.html)
and [atomic clone/pidfd](https://man7.org/linux/man-pages/man2/clone.2.html)
contracts. The kernel's namespace shutdown path terminates namespace processes
before init becomes waitable; actual target-kernel behavior, trace ordering,
descriptor transport and failure cleanup still require a separately approved
live trial. Native syntax and mocked protocol tests establish none of those
runtime facts.

## Mediated engine and operator integration (implemented, unexecuted)

The original engine now has an explicit storage seam. Its default native path,
schema 2, frozen stdlib program and transaction ordering remain. The new
[`host_canary_mediated.py`](../../theme/panda/common/host_canary_mediated.py)
driver uses the same Provider, install, recovery and CleanupProvider algorithms
over a fixed-role broker. It supports a bounded explicit plan of initialization,
provisioning, status, preview, install, recovery and empty-output cleanup. It
does not enable general unittest discovery or the old ambient operator callback.

| Mutation | Controller authority and evidence | Failure boundary |
|---|---|---|
| Fresh root / fixed directories | Durable exclusive creation intent, original parent/root FDs, registered birth before dependent operation | Failed first open, foreign child or replaced binding preserves |
| Baseline / support / paired stages | Approved baseline/source bytes; exact role, mode and timestamps; original FD; synchronized registration | No arbitrary path, content restoration authority, chmod or utime |
| Stage publication / generated unlink | Paired endpoints and expected full images; retained replaced originals; intent, data/parent sync and result | Partial mutation or acknowledgement preserves both old and current identities |
| LOCK | Registered empty file and exact expected object; broker-held non-reentrant lease | Lost/reentrant lease or closing its view preserves |
| Empty output removal | Validated restored enrollment/journal, exact CLEANUP.pending, reverse order and original empty-directory FD | No general rmdir, recursive deletion or inferred ownership |
| Final teardown | Original graph plus exact registered, completed mediated lifecycle | Unknown children, missing acknowledgement or incomplete namespace closure preserves |

`CanonicalTmpGrant` is a separate explicit bootstrap for schema 2's actual `/tmp`
meaning. It compares the supplied original allocation FD to fixed `/tmp`, requires
root-owned sticky 1777, verifies retained namespaces and keeps the external ledger
private. The root is `panda-theme-b3b1-<session>`. The default private-0700 parent
constructor is unchanged. `/tmp` is never deleted; unexplained shared-parent
metadata churn causes refusal. No environment or JSON record supplies authority.

The external controller supplies a `RuntimeGrant` with retained original
descriptors and an independently reviewed manifest digest for a curated runtime.
The bounded manifest rejects symlinks, special files, foreign mounts, hardlinks,
unexpected ownership/attributes and changed identities. Its engine bytes must
match the separately approved program grant. Ordinary host `/usr` or a runtime's
self-reported hash is not such a grant. No runtime is built or downloaded here.

`start_mediated_worker` selects a distinct native mode. It clones the runtime
mount tree into a new mount namespace, makes the detached clone recursively
read-only, private, nosuid, nodev and nosymfollow, then chroots into it. The worker
receives no fixture, ledger, parent or namespace custody FD. Only fixed RPC FD 3
and validated stdio survive. A closed x86_64 seccomp policy prevents direct
filesystem/metadata mutation, writable shared mappings, descriptor replacement
or transfer, service delegation and new descendants. Tracing permits the initial
exec only. A forbidden syscall or second exec prevents accepted completion.
Missing privileges/APIs refuse; there is no host-policy or user-namespace fallback.

The native init checks kernel SCM_CREDENTIALS against the original acknowledged
inner-namespace worker PID and birth generation. Outer helper credentials are
checked independently by the controller. JSON IDs are comparison fields only.
Policy installation and initial exec require durable controller acknowledgement
before engine RPC is accepted. Requests/results use bounded fragments, full
message digests and durable intent/result/ack records. Complete request/result
bytes are retained as bounded compressed ledger fragments before dispatch or
response. Identical payloads are retained once; later durable references bind
their original sequence, direction, digest and length after an exact bounded
byte comparison. Existing record/count/size ceilings refuse without truncation.
Partial input never mutates;
lost replies are never retried. Failed broker results permanently revoke grants.
Root metadata advances only from the same broker-held birth after a complete
graph check, never from worker-submitted metadata or a late pathname inventory.

The controller validates and binds the explicit plan before helper launch.
Status/preview-only plans latch the broker read-only: creation, publication,
unlink, synchronization, leases and directory mutation are refused before kernel
calls. Mixed plans authorize only the fixed legal state transitions; the reviewed
worker still selects the requested actions and their order within that scope.
The broker does not independently interpret a mixed plan as a command-by-command
authorization schedule. This is an explicit worker trust requirement, not a
general hostile-program transaction service.

This first integration supports **one worker lifetime per prospective session**.
Recovery within that lifetime uses the existing transaction protocol. Starting a
replacement worker after process death, controller restart, or reconstructing
custody from the journal is unsupported. The original negative suite's deliberate
hardlinks, symlinks, FIFOs, foreign entries and metadata edits are not normal broker
capabilities. They need a separately reviewed prospective fault-injection design.
No Fish process or application launch is added. All 79 original methods remain
unchanged and blocked before fixture creation.

## Teardown and interrupted states

Teardown accepts only the exact birth-bound native lifecycle registered by that
session. It verifies the entire graph before lifecycle closure and before the
first deletion. Unknown descendants, changed/missing names, replaced roots,
incomplete registration or uncertain process custody preserve the affected tree,
including known siblings. No late inventory grants ownership of an unknown entry.

Removal visits only individually registered entries, deepest first, through held
verified parent descriptors. Each exact unlink/empty-directory removal has a
durable intent, binding check, parent fsync, zero-link original descriptor check
and durable result. Before removing the final runner root, an external final
evidence record must be durable. A failed final record keeps that root. Any
partial teardown failure stops remaining deletion; surviving entries and all
original/superseded descriptors remain preserved. There is no compensation,
restart cleanup, expiry, historical cleanup or `rmtree` fallback.

The native default engine and old test operator retain direct operations for
their legacy contract. They cannot be substituted for the mediated worker or
used to remove its gates. The new integration is a bounded transaction pilot,
not acceptance of the full adversarial test harness.

The full six-action in-memory RPC/broker cycle with the actual engine source and
real ledger algorithm took 77.312 seconds after removing redundant last-record
scans and duplicate compression (125.155 seconds before those corrections).
It stayed within the unchanged evidence ceilings: 2,966 requests, 16,736 records,
8,598,478 bytes and a largest record of 2,417 bytes. These synthetic timings exceed
the fixed 30-second worker deadline. **A full transaction trial is blocked**;
source tests do not establish viable target-runtime performance. The deadline,
full-history checks and synchronization remain intact. Further batching or
replacement-worker support needs a separately reviewed engineering change.

Unsupported environments include hostile/concurrent same-UID writers, external
reapers, unknown FD duplication/close, nonlocal/overlay/tmpfs storage, missing
procfs/kernel APIs, unexpected ACL/xattrs, unavailable existing PID-namespace
and mount-namespace privilege, non-x86_64 mediated workers, unsupported runtime
layouts or tracing/exec behavior and any
unregistered mutation. The adapter does not obtain privilege, create a user
namespace, install capabilities or change host policy to work around a refusal.
Physical power-loss behavior remains unvalidated on every filesystem.

## Offline verification and retained gates

The [source-only workflow](../../.github/workflows/host-canary-source.yml) runs the
eight original filesystem-prohibited checks, old model tests, new fake-kernel and
mock-transport tests, plus native `-fsyntax-only`. A separate compiled mock harness
exercises deadline and task-wait code with syscall boundaries replaced; it never
calls the production custodian entry point. Neither the real helper nor real
adapters are executed. The new tests inject descriptors/syscalls and deliberately fail
partial initialization, registration, publication, process acknowledgement and
teardown boundaries. A simulated successful deletion is not validated custody.

The general validation workflow and all 79 dynamic methods remain unchanged. Local
permitted regression discovery excludes their module **before import** and names
all 79 as `NOT EXECUTED / BLOCKED`; this is neither a pass nor a skip. Broad hosted
discovery continues to expose the79 expected supervisor refusals. A green scoped
source check must never replace that general custody gate.

Remaining acceptance requires an exact supported kernel/storage/privilege
decision, reviewed helper binary and curated runtime manifests, and separately
authorized isolated fresh trials covering creation,
transport, trace ordering, descendant completion, interrupted registration and
partial teardown. Historical resources are permanently outside that trial.
Host/native theme activation is a later independent authorization gate. Keep the
PR draft until complete runtime custody and operator acceptance are recorded.

The first proposed trial must identify the exact helper/runtime digests, owner,
kernel, filesystem/mount identities, supplied external descriptors, privilege
source, plan and evidence destination before allocation. Runtime/interpreter
compatibility and timing must be reviewed first. The narrow initial request is
one new canonical fixture and external ledger, a restricted worker with only
the `initialize` action, its registered creation receipts and complete termination.
Full provisioning/install/rollback is deferred by the timing gate above. Stop
and preserve on any identity,
durability, syscall-policy, output, lifecycle or timeout failure. Teardown is not
implied by a successful mock or worker exit: it needs complete original custody
and the explicit trial's removal scope. Historical roots, full hostile fault
tests, replacement-worker recovery and host/native theme activation stay deferred.
