# Host Canary initialize-only preflight

**Preparation only. No helper build, host capability inspection, fixture allocation,
worker execution or teardown is authorized by this document.** Keep PR #26 draft.
The explicit multi-phase adapter does not replace the narrower first trial.

## Owner review packet before execution

Record these exact selections privately. An empty or unverified field is a stop,
not permission to discover alternatives, install dependencies or alter host policy.

| Required selection | Evidence and stop condition |
| --- | --- |
| Reviewed checkout | Absolute cwd, HEAD, tracked diff and SHA256 of controller, lifecycle, broker, RPC, mediated engine, operator and native C source. Recheck before execution; changed source stops. |
| Helper binary/toolchain | Reviewed compiler/linker versions, build command/flags, source and toolchain digests, helper SHA256 and retained original executable FD. A C syntax check is not a reviewed binary or build provenance. No helper currently selected or built by this preparation. |
| Curated runtime | Exact root and canonical manifest digest; interpreter, loader, shared libraries, stdlib, engine/RPC/mediated source and baseline bytes, ownership/modes/links/xattrs, permitted entries and original held FDs. Do not use an inherited interpreter, arbitrary host tree or matching pathname as authority. |
| Nonroot controller | Explicit UID/GID, original controller/interpreter provenance, umask, trusted startup/PATH and exclusive descriptor ownership. No other actor may close/reopen descriptors or reap children. Root controller and unknown same-UID interference are unsupported. |
| Existing kernel support | Owner-approved read-only evidence of x86_64, clone3/PIDFD, PID namespaces, pidfs identity, namespace ioctls, seccomp, mount isolation and syscall tracing. No Landlock implementation is supplied by this adapter; any separately retained Landlock policy requirement remains an unresolved gate. Exact existing privilege source for the native helper must be reviewed; do not add capabilities, user namespaces or policy to pass. Metadata does not prove syscall behavior. |
| Filesystem/context | Exact ext4/btrfs mount, mount/user namespace identities, normal directory state and supported attributes. Reject subvolume roots, foreign mounts, unsupported ACL/xattrs or ambiguous ownership. Do not probe historical fixture paths. |
| External authority | Independently selected allocation parent and separate mode-0700 evidence parent, original held descriptors and custody provenance originating outside every fixture. Canonical temporary-parent allocation additionally requires the original CanonicalTmpGrant. Retrospective stat results do not establish bootstrap authority. |
| Fresh resource names | New session ID, exact fixture basename and external ledger basename, evidence destination and runtime parent. Verify absence only within separately approved parents at the approved start. No historical path may be inspected or adopted. Parents and ledger are outside fixture teardown. |
| Exact action | Existing one-worker mediated entry with the single initialize action, original source/baseline grants and unchanged absolute 30-second worker deadlines. No provisioning, installation, recovery, output cleanup, phase transition or original dynamic test execution. |

Source review can prepare hashes for repository files. Actual binary, toolchain,
runtime, parent descriptors, kernel capabilities and backing filesystem identities
remain **unverified**. Request a separately scoped read-only provenance/capability
inspection first. It must enumerate the selected paths/metadata reads and private
output effects; it must not launch the helper, allocate a fixture or change policy.
Only after that packet is reviewed can the owner authorize the initialize trial.
There is no approved generic CLI that supplies these original descriptor grants.
A controller invocation must be reviewed with the actual retained-FD handoff;
substituting shell environment variables or a receipt loader is unsupported.

## Exact trial effects and required evidence

The later request must name one fresh fixture under the approved allocation
parent, one new mode-0600 external ledger under the separate private evidence
parent, registered fixed-role initialization files/directories, and one native
helper/PID namespace/worker lifetime. The curated runtime is read, not populated
from the host during the trial. Account for retained descriptors, private diagnostic
files, CPU/RAM, output limits and filesystem synchronization. Keep both external
parents, ledger and all ambiguous resources. No host theme or protected settings
are changed. No network, package, profile or historical-resource action is included.

Review the actual controller call sequence before approval:

1. Retain the independently supplied parent/runtime/helper/source descriptors;
   verify exact reviewed identities and context without allocating on mismatch.
2. Durably create the external ledger, then intent before exclusive fixture
   creation, immediate original-FD retention, synchronization and registration.
   Dependent operations require completed registration acknowledgements.
3. Start one mediated worker through the original helper FD. Preserve authenticated
   birth pidfd/nsfd, kernel namespace relationship, policy/exec/START acknowledgements,
   complete ordered task trace and broker RPC request/result/ack evidence.
4. Accept initialize only after the controller verifies the original registered
   graph: the allowed runner scaffolding, `FIXED_DIRS` and the two approved
   `SOURCE`/`DEPLOYED` baseline images, including their birth bindings, bytes,
   modes and timestamps. Require the `initialized` result, no pending RPC,
   mutation, lease, view or program grant, status zero and within-budget output;
   the worker result alone supplies no custody authority. The support directory
   remains empty: no frozen program, backups, lock, provisioning/enrollment
   records, journal, cleanup record or staging files exist. Output directories
   and the generated target remain absent. Demonstrate enforced direct-mutation
   denial using only a separately reviewed harmless negative case; a cooperative
   callback is not proof.
5. Record durable STOP intent, original pidfd termination, complete descendant
   closure, native P_PIDFD wait, authenticated CLOSED, helper status zero, output
   EOF/hashes and retained original namespace/process/pipe identities. A saved PID,
   process group or worker exit alone is insufficient.

The `initialize` action stops after constructing the provider over those
creation witnesses; it does not call `Provider.start()` or `Provider.seal()`.
Baseline-last enrollment belongs to the separate `provision` action and remains
required for its later acceptance. Do not add that action to this trial or
invent an initialization receipt. The external custody ledger and its durable
creation/RPC/closure records are still required; absence of an enrollment file
does not replace any original-descriptor or lifecycle evidence.

This list is an evidence requirement, not a claim that these events have occurred.
Retain private mode-0600 output in a new mode-0700 evidence directory, immediate
exit statuses, exact source/binary/runtime hashes and signed-off observations.
Publish only sanitized summaries. Do not expose private environment or credentials.

## Failure, preservation and optional removal

Any unsupported syscall, provenance mismatch, unexpected child, FD/path replacement,
unregistered resource, missing/reordered acknowledgement, failed write/fsync,
interrupted creation, output/evidence overflow, deadline, controller loss or
incomplete termination is a stop. Native timeout containment stays active; do not
weaken it or improvise PID-based cleanup. Preserve known handles, partial lifecycle,
ledger and resources; do not rerun, adopt, reconstruct or clear a preservation latch.
Loss of the original controller/descriptors permanently loses removal authority.

**Teardown is excluded by default.** A separate optional owner decision may name
only the original registered fixture and require uninterrupted original custody,
complete lifecycle closure, quiescence, exact graph identities and durable removal
intent before the broker's narrow role deletion. Stop on a foreign file or partial
teardown; retain survivors and evidence. No recursive deletion, ledger/parent removal
or historical cleanup is authorized. A native multi-phase final removal would also
require the separate LinuxRemovalGrant; that is outside this initialize-only trial.

Success accepts only the observed initialize boundary. It cannot accept enrollment,
the six-action transaction, four-phase handoff, real durability under failures, performance margin,
the 79 dynamic cases or host theme activation. Each remains a separate later gate.
