# Host Canary file-only fixture

This B3-B1b prototype is a separate audit artifact. It does not provision the
host, change live files, launch/reload applications, validate a GUI, or integrate
with the normal `panda-theme` CLI. All engine destinations are fixed simulations
inside an explicitly enrolled fixture.

**Recovery status: draft; custody blocked.** The preserved final handoff reports
13 ambiguous historical roots and a retained runner with two unwitnessed Fish
children. No existing root may be enumerated, adopted, changed or deleted as part
of source recovery. Do not create further fixtures until the custody/provenance
decision and a prospective supervisor are approved. The private recovery snapshot
retains exact historical evidence; this guide does not grant cleanup authority.

## Scope and authority

The accepted model is a cooperative sole user with quiescent writers. Checksums
detect inconsistency; they do not authenticate against a hostile same-UID process.
Locks are advisory, path checks are non-atomic, and physical power-loss behavior
has not been proved. Theme work must retain the approved Panda specification and
the Helios boot, kernel, GPU, suspend and storage safety boundaries.

| Component | Allowed work | Required limits |
|---|---|---|
| Test operator | Create fresh private roots; witness creation; provision directories after durable intent; remove empty outputs after cleanup intent | No preexisting-root adoption or ambiguous cleanup |
| `Provider` | Validate operator witnesses; create backups, frozen program, lock and records; attest directories | No directory creation/removal or interrupted provisioning resumption |
| `install_minimal` / `recover` | Fixed-role file staging, publication and recognized target unlink | Enrolled parents and existing pinned lock only; no foreign overwrite |
| `CleanupProvider` | Record cleanup intent and verified absence against restored checkpoint | No directory removal or adoption after unattested removal |
| `preview` / `status` | Observe roles, hashes, absences and ledger consistency | No lock, writes, fsync, temporary files or repair; no durability claim |

The engine accepts only direct `/tmp/panda-theme-b3b1-*` roots owned by the current
UID/GID, mode 0700. Fixed private ancestors require exact identity/permissions,
the same visible mount, and no ACL/xattrs. `/tmp` and user/mount namespace bindings
are enrolled. Only the unmapped parent owner in a rootless namespace may be 65534;
private child ownership is never relaxed. Potential subvolume roots (inode 256)
refuse without storage probing.

## Fixed role manifest


All paths below are relative to an explicitly enrolled fixture root. They are
simulations, never aliases or redirects to real source/HOME/XDG paths. Existing
fixture parents are provisioned by the test operator and have mode 0700.

| # | Role / exact path | Mode / initial state | Writer and retention |
|---:|---|---|---|
| 1 | `source/home/dot_config/ghostty/config.ghostty` | 0644, 1376-byte baseline | Engine publishes second; recover independently |
| 2 | `config/ghostty/config.ghostty` | 0644, independent baseline metadata | Engine publishes last; recover first |
| 3 | `config/panda` | 0700, initially absent | Operator provisions and later removes last |
| 4 | `config/panda/generated` | 0700, initially absent | Operator provisions and later removes first |
| 5 | `config/panda/generated/ghostty.conf` | 0600, initially absent | Engine publishes first; recovery unlinks last |
| 6 | `state/panda-ghostty-b3b-canary` | Operator-provisioned 0700 support | Retained through closure until fixture teardown |
| 7 | `state/panda-ghostty-b3b-canary/canary.py` | Frozen 0600 stdlib program | Provider exclusively creates; retain |
| 8 | `state/panda-ghostty-b3b-canary/source.before` | Independent 0600 backup | Provider exclusively creates; retain |
| 9 | `state/panda-ghostty-b3b-canary/deployed.before` | Independent 0600 backup | Provider exclusively creates; retain |
| 10 | `state/panda-ghostty-b3b-canary/lock` | Persistent empty 0600 | Provider creates once; engine opens existing inode |
| 11 | `state/panda-ghostty-b3b-canary/provisioning.json` | 0600 durable intentions/attestations | Provider; retained |
| 12 | `state/panda-ghostty-b3b-canary/baseline.json` | Immutable 0600 enrollment | Provider creates only after complete verified provisioning |
| 13 | `state/panda-ghostty-b3b-canary/journal.json` | 0600, initially absent | File engine; retained |
| 14 | `state/panda-ghostty-b3b-canary/cleanup.json` | 0600, initially absent | Cleanup provider; retained |
| 15 | `source/home/dot_config/ghostty/.config.ghostty.panda-b3b-stage` | Exclusive, initially absent; config's mode | Source stage |
| 16 | `config/ghostty/.config.ghostty.panda-b3b-stage` | Exclusive, initially absent; config's mode | Deployed stage |
| 17 | `config/panda/generated/.ghostty.conf.panda-b3b-stage` | Exclusive 0600, initially absent | Fragment stage |
| 18 | `state/panda-ghostty-b3b-canary/.journal.json.panda-b3b-stage` | Exclusive 0600, initially absent | Journal stage |
| 19 | `state/panda-ghostty-b3b-canary/.provisioning.json.panda-b3b-stage` | Exclusive 0600, initially absent | Provisioning stage |
| 20 | `state/panda-ghostty-b3b-canary/.cleanup.json.panda-b3b-stage` | Exclusive 0600, initially absent | Cleanup stage |
| 21 | `source/home/dot_config/ghostty` | Existing private 0700 parent | Identity pinned; publication changes directory timestamps |
| 22 | `config/ghostty` | Existing private 0700 parent | Identity pinned; publication changes directory timestamps |
| 23 | `config` | Existing private 0700 ancestor | Identity pinned; operator output provisioning/cleanup affects metadata |
| 24 | `state` | Existing private 0700 ancestor | Identity pinned; support provenance checked |


Additional `home`, `data`, `cache`, `runtime` and source ancestors are fixed private
scaffolding. Runner logs and registration are separate supervisor-owned objects.
These roles never alias real HOME, XDG or source paths.

## Schema 2 and enrollment

Records use scope `b3b1-file-only-fixture`, schema 2, and one provider-generated
32-character lowercase hex `enrollment_id`. The ID correlates records; it is not
authentication. Canonical envelopes contain exactly `payload` and `sha256`.
Duplicate keys, unsupported fields, invalid metadata, corrupt hashes, oversized
records and impossible histories refuse. Schema 1, mixed schemas and partial
upgrades refuse without migration or adoption.

Validated baseline **content** is restart bootstrap authority under the cooperative
model. The fixed role, canonical bytes, mode/owner, regular-file single link,
zero atime/mtime, size, absent ACL/xattrs, root/parents, mount and namespaces are
checked. An identical-byte baseline on another inode is accepted after restart;
baseline inode continuity and independent ctime anchoring are not promised.

The baseline binds both original images, directory pins, support objects, all
24 roles, historical `preseal`, and independently captured `completed_provisioning`.
Immutable objects have exactly `{image, pin, ctime_ns}`; pins contain
`dev, ino, uid, gid, mode, mount`. Expected completed-receipt bytes/pin/ctime come
only from baseline content. The receipt cannot supply its own expected identity.
Both backups, lock and frozen program bind ctime. Record/backup atime is strict;
only interpreter read-atime on the frozen program is advisory. Explicit `utime`
still changes ctime and counts as an immutable-object edit.

Preseal has `state=provisioning`, `preseal=null`, all directory attestations and
`pending=null`. The completed receipt has `state=completed` and embeds that exact
checkpoint, without self-pin or future-baseline reference. The provider publishes
and syncs the receipt using its existing stage, then captures post-rename ctime.
Only afterward does it exclusively create baseline, sync files then parents and
revalidate all authority before `enrolled=True`. Failed seals cannot be retried
through the same provider. No baseline stage or extra role exists.

Receipt without baseline, partial/corrupt baseline, unknown stages and changed
bindings refuse before locking or syncing. Complete visible baseline bytes do
not prove past fsync success. Explicit successful replay may establish **current**
durability; it cannot certify historical durability. Install replays and rechecks
enrollment before creating a journal. Recovery replays and rechecks before
reconciliation or journal mutation. Read-only observation never replays.
Journal and cleanup bind the exact final baseline-byte digest and enrollment ID.

## Transaction and recovery

Forward operations stage/publish fragment, source, then deployed. Each mutation
requires verified durable intent and completion. Stages use exclusive creation,
bounded writes, supported metadata, file/parent fsync and descriptor/path rechecks
before atomic replacement. Identities must be fresh, distinct and on the enrolled
backing mount. The engine never creates parents or the lock.

Recovery stages/publishes deployed and source independently, then unlinks the
recognized fragment. It validates the ledger and objects before locking/writing.
A publication that reached its attested after-image may be reconciled only after
sync and fresh verification of every role; unlink reconciliation has the same
post-sync check. A failed sync or late foreign edit preserves the journal without
a completion write. Interrupted recovery can resume supported prefixes. Unknown
partial/record stages and unpublished forward stages are retained for inspection.
Installation is single-use after any journal exists.

Final checks replay surviving files/parents and verify images, absences, provenance
and journal, including after lock release and before return. EIO, ENOSPC, quota
faults and contention return `incomplete`; unsupported or unknown state returns
`manual-inspection-required`. Later recovery retries sync even for completed
ledgers. The last observation-to-return interval remains non-atomic.

Original source/deployed bytes, mode, UID/GID, atime and mtime restore independently.
Atomic replacement changes inode/ctime; directory timestamps are not restored.
The sole hook is `config-file = ?../panda/generated/ghostty.conf` plus newline.

| Image | Bytes | SHA-256 |
|---|---:|---|
| Baseline | 1376 | `87d967432b7086b7c746929ce712a2dc5b2fc40899c2faf4456d16e6d234c359` |
| Hooked source/deployed | 1423 | `408e26c4b9e6a89728276051670a37ca2bd8ba11c8ea675ff7631bbfec2977b6` |
| Opaque Minimal | 516 | `5241a5b1d58bb15fa5d72e48bd8b9a1b89f12b4cddabb9474fcbc59e376ab03d` |

The frozen stdlib program exposes only `recover`, `preview`, `status`, intended
for `/usr/bin/python3 -B -I -S` with an already enrolled fixture. It has no
provision/install CLI, project imports, palette lookup, launch or environment
override. Do not supply historical roots merely to inspect them during recovery.

## Operator cleanup and retention

File rollback returns `files-restored / manual-directory-cleanup-pending`.
Cleanup receipts bind the exact restored journal and enrollment digest. The
operator removes empty `generated`, then `panda`, with recorded identities and
held-parent binding checks. Before absence attestation, the provider checks durable
intent and all other objects, allowing only that requested absence, then fsyncs
the parent. Missing/inconsistent receipts and unattested removals require manual
inspection. There is no automatic cleanup resumption or ownership inference.
Recovery verifies complete receipts, absences and surviving durability before
`fully-restored after verified cleanup`. Support evidence stays until supervised
fixture teardown.

A future separately approved host canary requires rollback even if Minimal looks
correct. Evidence stays at least seven days after verified rollback, post-restore
checks and operator acceptance; unresolved evidence stays indefinitely. No expiry
job is implemented. Later cleanup requires separate supervision.

## Test custody and validation gates

Ordinary unittest discovery refuses before fixture creation. A supervisor must
create a private runner and exclusive registry, retaining creation descriptors and
the complete creation/move/metadata inventory. It supplies `PANDA_TEST_RUNNER`
with exactly `root`, `root_identity`, `runtime_identity`, `registry_identity`;
identities are `[device, inode, uid, gid, full_mode]`. `XDG_RUNTIME_DIR` must be the
runner's fixed `runtime` child; the registry is `runtime/owned-fixtures.jsonl`.
The operator validates identities, bindings, 0700/0600 modes, owner, link count
and no xattrs before fixture creation or registry append.

Before any fixture exists, the supervisor must also inject a prospective
`fixture_cleanup(root, creation_identity)` callable into `host_canary_operator`.
Teardown delegates to this captured capability; there is no `rmtree` fallback.
Unknown descendants or changed/missing evidence require preservation. An env var
alone, ambient XDG runtime, a reconstructed inventory or later stat is insufficient.
The full supervisor is **not shipped by this recovery**. Do not improvise one to
make discovery pass. Native Fish may create XDG data/cache children, so future
supervision must witness them prospectively or prevent their creation by design.

The recovered suite covers interruption, replacement/redirects, metadata, locks,
impossible ledgers, injected I/O failures, final verification, frozen recovery and
manual/full cleanup. Simulated mount faults and SIGKILL are not physical power-loss
tests. Repository-unavailability probes deny repository reads in Python; they do
not establish OS-wide isolation. No native Ghostty or GUI result is claimed.

The historical final handoff reports 328 full-discovery tests passing and eight
independent reconciliation challenges, followed by a **blocked custody verdict**.
Those results have not been rerun during source recovery and do not establish
successful cleanup. Fresh recovery checks are limited to syntax/static analysis
and filesystem-free refusal/schema probes. PR review must retain draft status
until the custody/provenance decision, prospective supervisor validation and
fresh isolated dynamic checks are recorded. Live deployment needs separate
authorization and native/GUI evidence even after fixture validation.

The current broad CI workflow (`.github/workflows/validate.yml`) invokes ordinary
unittest discovery and supplies no supervisor. Its 79 Host Canary methods cannot
run successfully under that invocation. CI integration needs the approved
prospective custody design; do not bypass guards or silently skip the suite.

Safe offline checks are reproducible without a supervisor:

```fish
python3 -B -I -S tests/test_host_canary_offline.py
```

These eight tests read source and the fixed baseline before entering their
filesystem guards, then prohibit file open/stat/list/mutation/sync calls during
the pure probes. They do not allocate fixtures or replace the blocked suite.
