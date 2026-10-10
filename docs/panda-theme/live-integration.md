# Phase 3B Gate B1 — isolated Ghostty foundation

Gate B1 models Ghostty enrollment, preview, switching and recovery exclusively in
deliberately enrolled disposable roots. It does not install a hook, invoke
Ghostty, enroll another application, or enable a real-HOME/XDG write backend.
Phase 3A and all existing CLI behavior remain unchanged. Gate B2 and Gate B3
require separate explicit approval; the approved design and implementation plan
have not been rewritten.

## Ownership and target layout

The simulation root must be an existing owned mode-0700 directory immediately
under `/tmp`, named `panda-theme-b1-*`. It must contain existing private mode-0700
`home`, `config`, `data`, `state`, `cache` and `source` directories. Test processes
use these HOME/XDG roots; no installed application or interactive shell runs.

| Relative path inside the simulation | Role / write authority |
| --- | --- |
| `source/home/dot_config/ghostty/config.ghostty` | Simulated chezmoi source; read-only |
| `config/ghostty/config.ghostty` | Simulated deployed baseline; read-only |
| `.panda-theme-b1.json` | Explicit versioned enrollment; exclusive creation only |
| `config/panda/generated/ghostty.conf` | The only generated application fragment |
| `state/panda-ghostty-simulation/managed-files.json` | Scoped fragment ownership hash |
| `state/panda-ghostty-simulation/decision.json` | Scoped simulated selection explanation |
| `state/panda-ghostty-simulation/selection.json` | Four-field proposal inside a `ghostty-simulation-only` envelope |
| `state/panda-ghostty-simulation/journal.json` | Schema-2 checksummed recovery images, directory provenance, enrollment binding and phase |
| `state/panda-ghostty-simulation/lock` | Persistent advisory lock inode |

No `panda/theme-state.toml` is written. A Ghostty-only simulation must not imply
that the terminal/shell slice or desktop follows a flavor. The Phase 2
`ThemeState(mode, active, last_manual, context)` API is reused without migration;
simulation persistence has its own scope and location.

The Stage A inventory found Ghostty 1.3.1, with the live regular configuration
matching `home/dot_config/ghostty/config.ghostty` in the configured chezmoi source
repository. B1 enrollment supports only the reviewed `1.3.1` application contract,
with Ghostty marked critical. Package release suffixes and other application
versions are not silently accepted.

Enrollment validates exact paths and distinct source/deployed fingerprints:
SHA-256, device/inode, uid/gid, links, mode, size and mtime. It requires matching
source/deployed baseline bytes. A copied marker cannot authorize another root.
Missing, malformed, duplicate, extra or ambiguous fields are refused. Enrollment
does not repair or replace an existing marker and has no implicit HOME fallback.

## Optional hook model

The future hook proposal appends exactly this line to an unchanged baseline:

```text
config-file = ?../panda/generated/ghostty.conf
```

The leading `?` makes a missing fragment optional. Resolution is relative to
`config/ghostty/config.ghostty`, yielding `config/panda/generated/ghostty.conf`.
Ghostty loads an included configuration after the enclosing file; included scalar
values and indexed ANSI entries therefore override baseline values in the model.
Fonts, padding, cursor shape/blink, shortcuts and all other original bytes remain
unchanged. This proposal is returned in memory; neither simulated baseline nor
chezmoi source is edited by switching.

Evidence: installed `/usr/share/ghostty/doc/ghostty.5.md`, `config-file` section
(lines 2704–2732 at B1 review), and the
[official option reference](https://ghostty.org/docs/config/reference#config-file).
The model is deliberately limited to the reviewed assignment/ANSI subset. It is
not the native parser. Existing `config-file` or `theme` directives, malformed
lines, unsupported controls, absent final newline and oversized hook proposals
require separate review rather than implicit rewriting or include-graph guessing.

The generated fragment reuses Phase 3A canonical rendering, including opacity 1,
paired selection colors and the shared ANSI map. Native parser acceptance,
duplicate palette semantics, reload behavior and visible Wayland results remain
unverified. B3 must validate the composed configuration with the installed
`+validate-config` command before claiming native acceptance.

## Transaction and recovery contract

Python APIs are `enroll_fixture(root, version="1.3.1")` (version is required),
`prepare_simulated(candidate, root, decision=...)`,
`switch_simulated(candidate, root, decision=...)`, and `recover_simulated(root)`.
There is no new CLI mutation or preview flag in B1. The optional CLI integration
was omitted to keep the installed-facing surface and Phase 3A flag meanings
unchanged. The library preview supplies the B2 design foundation; a real-path
read-only inventory/preview API is still a separately approved B2 deliverable.

1. Validate explicit enrollment and source/deployed fingerprints.
2. Render and validate the Ghostty fragment and composed hook model in memory;
   snapshot the exact managed images and validate old scoped metadata.
3. Validate the existing lock and recovery journal before any directory or lock
   creation. A pending journal blocks further switching.
4. Acquire the nonblocking fixture lock. Recheck input fingerprints and current
   images and intended missing directories; regenerate the internal plan under
   the lock. Directories created by lock acquisition are accounted for separately;
   external creation makes the preview stale before any application. Every
   supplied execution plan, including a valid preview, is refused before writes.
5. Persist/fsync the prepared journal before changing the fragment.
6. Apply by same-directory atomic replacement, verify, and perform the refresh
   model. The refresh model invokes no native program and always labels native
   behavior unverified.
7. Recheck inputs and fragment before each metadata replacement. Persist scoped
   ownership, decision and selection only after verification; verify the entire
   slice and then mark the journal committed.

Byte-identical repeats verify and skip replacements/refresh. Explicit Auto
requires its Phase 2 decision and preserves manual history. No context detector,
watcher, timer, installation or notification is added.

On caught failure, reverse restoration accepts only recognized before/after
images and verifies the result. Cleanup accepts only actually created, still-empty
application directories whose recorded provenance matches. The persistent
`state/panda-ghostty-simulation` directory remains with its lock and recovery record.
Unrelated later contents survive. Failure and incomplete restoration remain
distinct. A failed result's `active` is the last known-good *simulated*
selection, not evidence of current files, native configuration or appearance.

Journal preparation failures occur before target writes. From the first prepared
journal write attempt, failures are recovery-required unless full restoration,
cleanup, parent durability and the final journal update are verified. This also
applies when provenance validation or rollback setup itself fails. A rename can
succeed before its writer raises, so these failures cannot be labeled
`not-started` merely because the write call did not return. Before preparation,
unsafe inputs remain zero-write refusals. A validated pending journal is checked
before current-slice or candidate validation, so mixed images from an incomplete
rollback and external edits keep repeated switches `incomplete` without writes.
Recovery validates the complete checksummed record, enrollment binding,
exact ordered paths, image limits/metadata, canonical fragment and scoped
selection/decision/ownership consistency before restoring anything. Later edits
cause refusal and retained records. Repeated completed recovery changes no files;
`restored` records must also have no pending application directory cleanup.
Both `committed` and `restored` records must match their respective after-images
or before-images. A different valid simulated slice is still an external change
and cannot be silently accepted as this record's completed transaction.

Parent durability obligations are reconstructed deterministically from every
managed path plus cleanup and journal paths, including preexisting directories.
Restoration retries these fsyncs even when current bytes already match the
before-images. Preparation and recovery also retry them before accepting a
completed record; byte-identical switches and final commit verify them too.
The generated-file parent, state/index/decision/selection/journal parent, cleanup
parents and `config` are synced, or their nearest existing ancestor when removed.
These retries change no directory entries, file bytes or metadata and need no
in-memory debt flag or new journal schema. Persistent EIO returns `incomplete`
with retained evidence; clearing the fault permits a later verified retry.

Schema-2 directory records are limited to `config/panda` and
`config/panda/generated`, in that order. A pending identity is `null` and authorizes
no removal of an existing directory. After mkdir, identity comes from the opened
directory descriptor: device/inode, uid/gid, mode, mtime and ctime. Each legitimate
child creation or file replacement/removal refreshes the owned directory stamp.
The prepared journal is persisted again after mkdir/fsync and application file
changes, before those operations return. Recovery rechecks these stamps before
locking and under lock. Replacement, changed permissions/metadata, or later child
creation/removal makes provenance ambiguous even if the directory is now empty;
recovery preserves it and reports incomplete/manual review.

A crash between mkdir or an owned directory mutation and provenance persistence
cannot safely establish the new stamp. Recovery preserves the unknown/changed
directory and retains the record for manual review; harmless empty directories or
partial managed images may remain. There is no claim of closing that crash window.
Schema-1 journals contain only path lists. They are retained and refused without
lock creation or automatic replay, including records marked `restored` or
`committed`; there is no inferred migration to schema 2. Selection metadata and
enrollment keep their existing schema versions.

Cleanup treats absence as benign. A populated directory is preserved and cleanup
remains incomplete. Other rmdir failures and parent fsync failures propagate into
an incomplete result with retained recovery images and updated known provenance.
Recovery can retry after a transient failure, including a failed fsync after a
successful removal. A final recovery-journal failure triggers a best-effort
`incomplete` replacement. If that replacement cannot be written, a `restored`
record may already be visible from the preceding rename even though its fsync
failed. Its phase alone never proves success: recovery must retry the parent
durability checks, and continuing fsync failures remain incomplete. If updating
the recovery record itself fails, the previous record remains where available;
mismatched stamps require manual review. Cleanup never promotes an incomplete
result to `restored` or `not-needed` while recorded
application directories remain.

An independently reproduced informational edge case requires manual review:
a committed-journal rename can succeed while its parent-directory fsync fails,
followed by failures of the rollback-journal writes. Even when all managed files
have been restored to verified before-images, the retained journal can still
show `committed`. Later recovery conservatively reports `incomplete`, even after
the faults clear, and preserves the files and recovery evidence without replay
or deletion. Manual inspection and reconciliation of that evidence are required;
automatic recovery has not succeeded in this case.

## File capability and limits

`live_fs.py` is independent of `FixtureFS`; Phase 3A guards are unchanged. Every
operation rejects real roots and Phase 3A roots. Reads/writes use exact allowlists,
descriptor-relative no-follow traversal, singly linked owned regular files,
safe modes and bounded images. Unsupported extended attributes/ACL names are
refused on files and every opened directory, including prospective target and
transaction-metadata ancestors. Setgid, setuid and sticky directory bits are
unsupported: preflight refuses them before lock, journal, child or temporary-file
creation. Existing directories are never chmodded to repair inheritance.
Parent identities are pinned and rechecked, as is the lock inode.
The enrollment source/hook paths are never writable. No backend dispatch can
convert simulation enrollment or Phase 3A CLI flags into real-path writes.

Individual replacements are atomic; the multi-file transaction is not. Checksums
detect corruption, not malicious same-user tampering. Advisory locks and
check-before-rename do not provide filesystem compare-and-swap or hostile
same-user isolation. Mount aliases have not been validated. Bytes, modes and
mtimes are compared for restoration; inode
identity, ctime and directory timestamps are not restored. A crash during staging
may leave a `.panda-b1-*` temporary file; recovery never glob-deletes artifacts.
Power loss, SIGKILL, ENOSPC, reboot, hardware failure and network-filesystem
durability have not been demonstrated.

## Verification and later gates

Focused regressions cover fail-closed enrollment, capability separation, source
and deployed drift, include modeling, every managed-write failure boundary,
verification/refresh failures, later edits, incomplete restore, lock contention,
fresh-process abrupt-exit recovery, mkdir/provenance interruption, external empty
directories, directory replacement/timestamp drift, cleanup EIO/fsync failures,
retry, repeated recovery and corrupted/semantically incomplete or legacy journals.
Additional regressions cover preexisting-parent persistent/one-shot fsync EIO,
missing and existing before-images, fresh-process durability retries, completed
record/image mismatch, unsupported ancestor modes/xattrs with unchanged metadata,
and post-preparation write/provenance failures with truthful rollback status.
Native programs and real GUI sessions are not test subjects.

Run the full suite and Fish validations with sanitized disposable HOME and all
four XDG roots. Python uses `-B`; Fish startup is permitted only in those fixtures.
Read-only before/after fingerprints of real application configuration, runtime
locations, relevant chezmoi source files and global instructions must match.

**B2 proposal:** separately authorize a real-path read-only preview that captures
source/deployed ownership, fingerprints, version and exact hook/fragment deltas,
without enrollment, staging, lock, journal, backup, cache, native reload or writes.

**B3 prerequisites:** review that preview; authorize the exact Ghostty hook source
and deployment procedure, generated target and support/backup paths; prove native
validation under safe cache isolation; separately approve GUI reload/reopen and
Wayland inspection; exercise controlled failure and restore the starting state.

Kitty's automatic reload, Konsole's profile reference, Starship's full-config
ownership/palette wiring, Fastfetch's config invocation and Fish's session hooks
remain separate adapter decisions. No other adapter or Phase 4 capability is
enrolled by B1. The committed B1 work remains fixture-only. Gates B2 and B3 have
not been approved.
