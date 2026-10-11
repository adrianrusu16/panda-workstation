# B3-B0 private Ghostty canary safety prototype

**Verdict: B3-B0 READY FOR INDEPENDENT RE-AUDIT.**

**Gate:** private fixture implementation for independent code audit. **Live B3-B1
deployment, installed hooks, native Ghostty execution and GUI activation are NOT
AUTHORIZED.** This prototype has no normal `panda-theme` dispatch, live backend,
CLI flags, environment-based destination or HOME override. B1 and Phase 3A guards
and their transaction code are unchanged.

The implementation base is `34a716844dc82dbd7a3ae46501113938c787b319`.
The proposed changes belong on local branch `feat/panda-ghostty-canary-safety`,
unstaged and uncommitted. The owner-supplied B3-B0 plan authorizes code and private
fixtures only. The owner separately allowed running unchanged legacy tests in
their existing disposable roots; that exception does not widen this capability.

## Capability and fixture layout

`canary.create_fixture(baseline_bytes)` creates a new owned mode-0700 direct child
of `/tmp`, named `panda-theme-b3b-*`. It requires the approved 1,376-byte baseline
and cannot accept a source/destination path. Construction creates private HOME,
XDG config/data/state/cache/runtime and source directories. `dry_run`, `apply`,
`inspect` and `recover` accept only such a root, with its checksummed immutable
fixture manifest, matching root and parent identities and approved images. A
preview result is descriptive; supplying it to `apply` refuses execution.

| Role | Exact fixture-relative path |
| --- | --- |
| Source config | `source/home/dot_config/ghostty/config.ghostty` |
| Deployed config | `config/ghostty/config.ghostty` |
| Minimal fragment | `config/panda/generated/ghostty.conf` |
| Fixture manifest | `.panda-b3b-fixture.json` |
| Recovery journal | `state/canary/journal.json` |
| Advisory lock | `state/canary/lock` |
| Source stage | `source/home/dot_config/ghostty/.config.ghostty.b3b-stage` |
| Deployed stage | `config/ghostty/.config.ghostty.b3b-stage` |
| Fragment stage | `config/panda/generated/.ghostty.conf.b3b-stage` |
| Journal stage | `state/canary/.journal.json.b3b-stage` |

All directories are 0700. Source and deployed images are 0644, generated output
and support files 0600. Files must be singly linked, regular, owned by the current
uid/gid and free of xattrs. All fixed ancestors, including unused private XDG
directories, are checked before any transaction write. Special modes, symlinks,
unexpected output ancestors, foreign target content, existing stages and journals
are refused. The persistent empty lock is created during fixture construction;
its device/inode/ctime identity is bound to the manifest. Transaction locking
never creates or repairs a lock.

`CanaryFS` performs descriptor-relative, no-follow traversal with exact file and
directory allowlists. The root is opened through `/tmp`; each opened directory
and file must share its mount ID, obtained from Linux `/proc/self/fdinfo`.
Preexisting parents are pinned by device, inode, uid/gid, mode and mount identity.
New output directories additionally record mtime and ctime provenance. Reads use
`O_NOATIME`; file contents and metadata are rechecked during bounded reads. Root,
manifest, ancestors, lock, output provenance and expected images are rechecked
before mutation and in recovery.

Provenance refresh compares device, inode, uid/gid, mode and mount identity before
updating mutable stamps. It never adopts a replacement identity. Mkdir opens the
child through the held, revalidated parent descriptor and compares the opened
child with the path binding before and after directory fsync, before recording
creation. A substituted parent/child or metadata drift retains unknown provenance
and evidence for manual inspection. Staging descriptor ownership covers provenance
refresh as well as writing, metadata changes and fsync; errors retain the stage
without leaking its descriptor.

## Journal schema and durability

The fixture manifest and journal use canonical JSON envelopes with exactly
`payload` and `sha256`; SHA-256 covers the canonical payload. Duplicate keys,
noncanonical encodings, bad checksums and unknown/legacy schema versions are
refused. Envelopes are limited to 1 MiB; each managed image to 64 KiB. Journal
images contain canonical base64 bytes, an independent content checksum, mode,
uid/gid and nanosecond atime/mtime. Initial absence is explicit `null`.

Journal schema 1 is scoped to `b3b-private-fixture-only` and contains exactly:

- `schema`, `scope`, `manifest_sha256`, `phase`;
- the three ordered `entries`, with exact `path`, `before`, `after` values bound
  to the immutable manifest and validated against the approved baseline/hook and
  canonical Minimal renderer;
- two ordered `directories`, each with exact `path`, `state` and `identity`;
  states are `pending`, `created`, or `removed`;
- `intent` for one exact `mkdir`, `stage`, `replace`, `unlink` or `rmdir` operation;
- bounded integer `sequence` and `completed` counters (maximum 128), recording
  operation intent and completion checkpoints. `prepared` requires zero
  checkpoints and pending directories; `applied` requires all eight operation
  checkpoints (two mkdir, three stage, three replace) and proven created dirs.

Before locking, loading also checks current managed images and cross-field
operation semantics. Forward records must match the exact eight-operation
prefix, including an outstanding intent whose rename may already be visible.
Recovery uses a bounded reachable-ledger search over reverse-order mutations,
recorded directory events, exact before/after images, stage presence, intents and
counters. A completed stage needs its artifact; removing it requires the baseline
rename. Retries may add intents without a completion, or skip a rename already
visible after EIO; those histories remain eligible. Final restoration can resolve
an outstanding intent that failed before any mutation when no restoration remains.
Checksum-valid zero-checkpoint records
with created directories/installed images and contradictory forward intents are
refused before replay. This consistency check does not authenticate a same-user
author who can rewrite a whole fixture and recompute checksums.

The immutable manifest durably records all before/after images, preexisting
parents and the metadata bootstrap intent before `apply` can initialize its
journal. Creating the disposable fixture itself is preparation, outside the
canary transaction. Interrupted construction preserves its exact root for the
creator's inspection; it does not produce an enrolled canary or automatic
recovery claim. No canary operation accepts an incomplete construction.

Each transaction intent is written to an exclusive fixed journal stage, fsynced,
renamed and followed by support-parent fsync and content verification before its
operation starts. A stage intent covers exclusive creation, writing and setting
the intended file metadata. Completion records follow successful file/directory
fsync and image verification. The previous durable record supplies recovery
evidence while a new record is staged; a leftover journal stage is ambiguous and
preserved for manual inspection.

Apply proves `config/panda` and `config/panda/generated`, then installs the
Minimal fragment, appends the source hook and updates the deployed hook last.
Each file uses exclusive private staging, file fsync, expected-image/provenance
rechecks, atomic rename and containing-directory fsync. The exact staged image
must match before rename. Installation is not globally atomic.

Recovery validates the whole record and every current image before writing. An
`applied` record requires all after-images; a `restored` record requires all
before-images and output-directory absence. Other valid interrupted phases may
contain matching before/after images. Recovery durably enters `recovering`,
restores deployed config, source config and generated-target absence in reverse
order, then removes only proven, still-empty created directories in reverse order.
Later edits, changed parents, unknown provenance and leftover stages preserve all
evidence and cause refusal. Restoration retains the journal, manifest and lock;
the fixture remains single-use. Repeated verified recovery writes no files.

Parent fsync obligations are reconstructed from every fixed and output directory,
including preexisting source/deployed/support parents and the root. Removed
directories resolve to their nearest existing ancestor. `inspect`, completed
recovery and final apply/recovery verify images and replay these obligations.
After the last sync, they revalidate enrollment/lock/ancestor bindings, all managed
images and absence requirements, created-directory provenance, and the exact
journal image and parsed ledger. A late file edit, corrupt or changed journal,
reappeared output directory or replacement ancestor returns incomplete and keeps
evidence. Unused recovery repeats baseline verification under the lock after sync;
completed recovery repeats the same post-sync checks before reporting restoration.
An `applied` or `restored` label, or a completion counter, alone never proves
success. Persistent EIO fails the gate; clearing an unambiguous durability fault
permits a retry even when bytes already match.

Mkdir and provenance persistence cannot be crash-atomic. A crash or failed fsync
after mkdir but before its identity checkpoint leaves an unknown directory;
recovery never infers ownership from its name or emptiness. A child mutation can
also change an owned parent stamp before its checkpoint is durable. These gaps
preserve the directory and record for manual inspection. The prototype makes no
speculative repairs or cleanup to close them. Failed stages are likewise retained,
even when an in-process cleanup might be possible. It prioritizes evidence over
automatic recovery from every failure.

## Threat model and limits

Protected assets are both real Ghostty configs, real HOME/XDG/chezmoi state,
unrelated fixture files and the evidence needed to restore the private canary.
The entry boundary is an untrusted root/path/preview or persisted record. The
trusted inputs are this gate's approved hashes, pure renderer and explicitly
created private fixture. Corruption, stale plans, late edits, permission changes,
symlinks, linked/special files, replacement parents and interrupted storage
operations must fail closed.

Checksums detect corruption and consistency errors; they are not authentication
against an attacker with the same uid. Advisory locks coordinate cooperating
processes. Check-before-rename is not filesystem compare-and-swap. A hostile
same-user process can race open/stat/rename, modify a manifest and recompute its
checksum or change namespace/mount topology. Prefix/ownership/manifest checks do
not create isolation from that attacker.

The mkdir-to-first-child-open window and the final verification-to-return window
remain non-atomic. Descriptor/path reconciliation catches the bounded substitutions
tested here; it does not prove that every same-user event is detectable. Timestamp
refresh cannot attribute all concurrent directory activity to this transaction.

`O_NOFOLLOW` is not bind-mount protection. Mount-ID equality rejects visible
separate mount instances at open time, including nested aliases. The test uses
an injected mount-ID mismatch; actual bind-mount attacks were not exercised.
Aliases outside the visible namespace, concurrent mount changes and host-vs-
sandbox ownership differences remain limits. This is Linux-specific; missing
fdinfo or unsupported xattrs/metadata operations cause refusal.

Atomic replacement restores bytes, supported mode, uid/gid (only the current
uid/gid are supported), atime and mtime. It does not restore inode, ctime, original
directory timestamps or unsupported ACL/xattr metadata. A benign later read that
changes an image's atime can also require inspection; matching bytes alone are
insufficient. Modified empty directory stamps are intentionally ambiguous.

EIO and ENOSPC regressions inject actual `OSError` results into selected calls;
ENOSPC does not mean the physical disk was filled. An actual controlled SIGKILL
and fresh-process abrupt exit exercise specific process interruption windows.
They do not establish arbitrary SIGKILL, reboot, power-loss, hardware-failure,
write-cache or full-disk guarantees. A checksum-valid record visible after a
failed fsync remains uncertain until the required syncs succeed. No native parser
or GUI test runs at B3-B0; B3-A parser evidence is inherited and appearance remains
unverified.

## Regression and verification scope

The initial ten contracts failed before the canary existed, then passed. Later
failing-first regressions found and fixed six specific gaps: acceptance of an
external before-image under an `applied` record, acceptance of a substituted empty
lock, failure to verify journal bytes after rename, failure to verify foreign
staged bytes before overwriting a baseline, acceptance of inconsistent completion
counters, and a root-descriptor leak when mount identity was unavailable.

Focused tests also exercise exact root/path confinement, every fixed ancestor,
actual user xattrs, hardlinks, symlinks, a FIFO, unsafe/special modes, foreign
output/staging/recovery files, replaced parents, malformed and checksummed legacy
records, changed/unknown directory provenance, late edits, write/rename/file-fsync
EIO and injected ENOSPC, mkdir faults, journal-parent fsync after rename, new and
preexisting parent durability, unlink/rmdir failures, repeated recovery, lock
contention, abrupt subprocess exit and the SIGKILL mkdir/provenance gap. Tests
verify that the selected fault actually fired and that conservative refusals
preserve evidence. Unambiguous retries restore the fixture baseline and output
absence; ambiguous gaps remain manual.

Run the focused contracts with
`python3 -B -m unittest discover -s tests -p test_theme_canary.py -v`.
Full repository tests, palette validation, bootstrap
validation and syntax checks use a new private B3B HOME/XDG. During this gate the
initial prototype validation used Bubblewrap's root filesystem read-only and
only `/tmp` writable, with dropped capabilities and a cleared environment. The
four-finding remediation uses a cleared environment and new private HOME/XDG/TMP
without mount operations. No broader isolation guarantee is inferred from that
environment setup.
The unchanged legacy tests keep their existing isolated fixture roots under the
owner's explicit clarification. Protected config/index fingerprints and the
absence of real Panda-generated/recovery paths are checked before and after.
Native Ghostty, chezmoi apply and installed Fish startup are never invoked.

Observed gate validation on 2026-10-10:

| Check | Observed result |
| --- | --- |
| Focused canary suite | 39 tests passed in 12.028 seconds |
| Full repository suite | 233 tests passed, including all 39 canary contracts |
| Python syntax | AST parsing passed for both modules and the test file; no bytecode written |
| Palette validator | 140/140 required pairs passed; six existing Gothic fill advisories remain |
| Bootstrap validator | 13 Fish scripts and 49 package entries passed; executable permissions passed |
| Whitespace | Tracked diff check and explicit new-file checks had no diagnostics |
| Scoped credential patterns | No matches in the four proposed files; this is a pattern check, not a secret-audit guarantee |
| Activation boundary | No normal CLI canary dispatch or production native/network/B1 imports; no HOME/env destination fallback |
| Protected snapshots | 12 of 13 path fingerprints identical; only repository-root mtime/ctime advanced, informational and unexplained |

Both protected Ghostty configs retained the approved SHA-256, size, ownership,
mode, inode, atime/mtime/ctime and empty xattrs. The Git index fingerprint was
unchanged. Real Panda-generated paths and the proposed real canary support root
remained absent. Validation roots were removed by exact owned path; a subsequent
read-only inventory found no remaining B3B roots. No nonowned temporary artifact
was modified or cleaned. There was no native/GUI execution or live activation.

## Four-finding remediation evidence

Only the four existing untracked prototype files were edited. Nine new regression
methods failed against the original implementation with 22 assertion failures,
zero errors and zero skips. Each finding's focused run passed after its correction.
The journal contradiction test was also rerun with separate fixtures for all four
variants: four failures before the fix, then refusal before any lock entry and
unchanged fixture snapshots after it.

| Finding | Regression methods | Observed correction |
| --- | --- | --- |
| Directory adoption | `test_parent_substitution_after_mkdir_is_preserved`, `test_refresh_never_adopts_replaced_child` | Replacement inodes/bytes survive; apply and repeated recovery refuse with evidence retained |
| Final-sync false success | `test_apply_final_sync_rejects_late_changes`, `test_recovery_final_sync_rejects_late_changes`, `test_inspect_final_sync_rejects_late_changes`, `test_restored_retry_final_sync_rejects_late_edit`, `test_unused_recovery_final_sync_rejects_late_edit` | Late edits/corruption/ancestor or provenance drift return incomplete; repeated retries preserve the external state |
| Impossible journal | `test_interrupted_journal_rejects_impossible_prefixes_before_lock` | Contradictory phase/counter/intent/image/provenance combinations are refused before locking or replay |
| Stage FD leak | `test_stage_refresh_failure_closes_fd_and_retains_evidence` | Actual stage creation followed by EIO or mode 0500 leaves no extra FD; stage/journal evidence remains |

A fresh-context implementation review found two additional shapes of the journal
finding: installed images with insufficient completed checkpoints, and a completed
recovery-stage checkpoint with no required stage artifact. The actual-filesystem
regressions `test_recovery_intent_requires_installation_completion_evidence` (three
variants) and `test_recovery_completion_without_required_stage_is_refused` failed
before correction and pass with the reachable-ledger validator. This limited
review does not replace the separately required independent adversarial re-audit.

Related challenges include opened-child substitution, metadata drift, all eight
durable application checkpoints, all seven restoration checkpoints, and persistent
cleanup retries. Stage checkpoints remain manual; unambiguous states restore after
faults clear. An intermediate focused run exposed the missing final resolution of
a first-mkdir intent that failed before mutation (EIO/ENOSPC); the model now includes
that existing no-op restoration behavior, and both regressions pass.

| Final remediation check | Observed result |
| --- | --- |
| Focused canary suite | 55 tests passed in 31.357 seconds; zero failures/errors/skips |
| Entire repository suite | 249 tests passed in 46.720 seconds; zero failures/errors/skips |
| Palette/bootstrap | 140 required pairs; six existing Gothic advisories; 13 Fish scripts and 49 package entries passed |
| Syntax/whitespace/scope | Python AST, five theme Fish syntax checks, tracked and explicit four-file whitespace checks; scoped credential patterns and import/activation boundary checks passed |
| Bounded model challenge | Counter 128 rejected an impossible all-after completion and admitted a valid long retry history; pure model evidence only |

Both real Ghostty SHA-256 and full captured file/parent metadata remained unchanged,
as did chezmoi mappings, all 131 tracked-file fingerprints and the Git index. Real
Panda output/support paths remained absent. Repository-root mtime/ctime drift is
informational and its cause is unverified. New test cleanup checks each fixture's
retained creation device/inode, owner, directory type and 0700 mode before removing
that exact root. No new canary probe targets a real-home path. Native, GUI, mount,
power-loss and hardware durability guarantees remain outside this remediation.

Final expected `git status --short` contains exactly four `??` paths: this
document, `tests/test_theme_canary.py`, `theme/panda/common/canary.py` and
`theme/panda/common/canary_fs.py`. No staging, commit or publication is performed.

## Future B3-B1 live footprint — NOT AUTHORIZED

This is a proposal to review after an independent audit, not an implemented path
map, deployment capability or instruction to perform a live operation.

| Future primary target | Proposed result |
| --- | --- |
| `/home/adrian/Workspace/system/panda-workstation/home/dot_config/ghostty/config.ghostty` | Append only the 47-byte optional include; retain 0644 and original uid/gid |
| `/home/adrian/.config/ghostty/config.ghostty` | Same hook, deployed last; retain 0644 and original uid/gid |
| `/home/adrian/.config/panda/generated/ghostty.conf` | Canonical 516-byte Minimal, 0600 |
| `/home/adrian/.config/panda` and `/home/adrian/.config/panda/generated` | Create only if independently verified absent, mode 0700 |

Proposed adjacent stages are the exact `.config.ghostty.panda-b3b-stage` files in
the source/deployed parents, and `.ghostty.conf.panda-b3b-stage` in the generated
parent. All would require independently verified absence and exclusive creation.

The proposed private support root is
`/home/adrian/.local/state/panda-ghostty-b3b-canary` (0700), containing 0600
`baseline.json`, `source.before`, `deployed.before`, `journal.json`, `lock`,
`canary.py` and `.journal.json.panda-b3b-stage`. Each name, bytes, ownership, native
validation scratch footprint and installation procedure needs separate review.
The prototype does not create or target any of these locations, and must not be
converted into a live capability by changing a prefix or a constant.

A future reversible procedure would freshly fingerprint the source/deployed
baseline and all ancestors/stages/support paths, prove writable host mount and
metadata support, durably capture complete before-images and intentions, prove
new directories, install Minimal first, source hook second and deployed hook
last, then verify native effective config inside separately approved isolation.
Recovery would first reject external edits/unknown provenance, restore deployed
and source before-images, remove only matching generated output and proven empty
created directories, replay all parent durability checks and retain recovery
evidence until independently verified complete. GUI reload/reopen and Wayland
appearance checks remain a separate explicit authorization.

Baseline digest: `87d967432b7086b7c746929ce712a2dc5b2fc40899c2faf4456d16e6d234c359`.
Hooked digest: `408e26c4b9e6a89728276051670a37ca2bd8ba11c8ea675ff7631bbfec2977b6`.
Minimal digest: `5241a5b1d58bb15fa5d72e48bd8b9a1b89f12b4cddabb9474fcbc59e376ab03d`.

No future live gate is requested by this prototype. Stop for independent code
audit before considering a separate authorization proposal.
