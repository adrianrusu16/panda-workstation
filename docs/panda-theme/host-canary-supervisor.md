# Host Canary prospective supervisor contract

**OS adapters implemented; execution and custody acceptance blocked.** This
supplements the [file-only fixture contract](host-canary-fixture.md). No adapter,
native helper, fresh fixture or dynamic Host Canary test may run without a
separately approved trial. Historical roots and retained runners remain excluded
from inspection, adoption and cleanup. All 79 original dynamic refusals remain.

## Authority and supported boundary

The controller, interpreter, reviewed native helper and cooperative worker are
trusted. External writers must be quiescent and descriptor ownership exclusive.
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
bootstrap or untrusted-worker RPC exists. Calling the trusted Python constructor
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

The broker exposes scoped creation, bounded append, fixed zero-timestamp freeze,
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
below. All operations are controller APIs; no direct worker filesystem mutation
has been mediated merely by adding these sources.

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

## Teardown, interrupted states and unaccepted integration

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

The old operator and frozen engine still perform direct filesystem operations;
they are **not integrated** with this broker. Their 79 tests retain the original
pre-allocation refusal. The new process adapter is a synchronous, bounded worker
pilot primitive, not a full unittest harness or accepted mutation-broker RPC.
Direct writes, interpreter atime changes or Fish-created cache/data descendants
can therefore cause preservation rather than accepted cleanup. Closing this
integration gap requires reviewed mediation and separate fresh-fixture authority.

Unsupported environments include hostile/concurrent same-UID writers, external
reapers, unknown FD duplication/close, nonlocal/overlay/tmpfs storage, missing
procfs/kernel APIs, unexpected ACL/xattrs, unavailable existing PID-namespace
privilege, non-x86_64/aarch64 ABIs, unsupported tracing/exec behavior and any
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

Remaining acceptance requires independent source review, an exact supported
kernel/storage/privilege decision, helper binary review, broker/worker integration
review, and separately authorized isolated fresh trials covering creation,
transport, trace ordering, descendant completion, interrupted registration and
partial teardown. Historical resources are permanently outside that trial.
Host/native theme activation is a later independent authorization gate. Keep the
PR draft until complete runtime custody and operator acceptance are recorded.
