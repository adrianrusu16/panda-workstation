# Phase 3A — Transaction Foundation

Phase 3 is split into **3A: Transaction Foundation** and **3B: Controlled Live
Integration**. This is an implementation sequence, not a permanent change to the
approved Panda design. Phase 3B requires a separately reviewed integration plan
and explicit authorization. Nothing here enables live theming.

Phase 3A renders and verifies owned fragments in disposable fixtures for Ghostty,
Kitty, Konsole, Starship, Fastfetch and Fish. It implements persistence, locking,
rollback and conservative interrupted-process recovery. Real configuration hooks,
native refresh, terminal ergonomics comparisons and Wayland verification remain
Phase 3B work. Plasma, editors and the rest of desktop Tier 1 remain Phase 4 work;
layout and automatic background evaluation remain later phases.

## Authority and preserved contracts

The approved design sections 8, 11–13 and 18 establish terminal parity, manual
precedence, the four-field state, transactional ordering and honest verification.
The approved implementation plan's Phase 3 specifies the six adapters, separate
decision file, locking, recovery and shell commands. The user's Phase 3A approval
defers live enablement and config hooks to Phase 3B. The approved documents and
five manifests are unchanged.

`ThemeState(mode, active, last_manual, context)`, `read_state()`, pure selection
and the canonical cycle remain unchanged. `wave` still resolves to `pandawave`.
Manual requests preserve context and update `last_manual`; explicit Auto uses its
supplied `Decision` and preserves manual history. No process, cwd or window
context is inferred. There is no schema migration or additional state field.

## Explicit fixture enrollment

Every write API requires an existing, owned, mode-0700 directory whose immediate
parent is `/tmp` and whose name begins `panda-theme-fixture-`. Enrollment adds a
mode-0600 `.panda-theme-fixture.json` marker. It never creates a user home or chooses
an implicit writable root. The CLI additionally requires
`--allow-fixture-writes`. An XDG override alone cannot enable mutation.

This runnable example uses Python so Fish startup cannot initialize directories
outside the fixture. Run it from the repository root:

```fish
set -l fixture (mktemp -d /tmp/panda-theme-fixture-XXXXXXXX)
set -l manager "$PWD/theme/panda/common/cli.py"
python3 -B "$manager" init-fixture --fixture-root "$fixture" --allow-fixture-writes
python3 -B "$manager" gothic --fixture-root "$fixture" --dry-run --no-time
python3 -B "$manager" gothic --fixture-root "$fixture" --allow-fixture-writes --no-time
python3 -B "$manager" status --fixture-root "$fixture"
python3 -B "$manager" doctor --fixture-root "$fixture"
python3 -B "$manager" doctor --recover --fixture-root "$fixture" --allow-fixture-writes
```

The reported success means **fixture fragments verified**, with live appearance
unverified. Ordinary flavor, `auto`, `next` and `previous` calls without fixture
opt-in still fail. `list`, `status`, `doctor`, `auto --explain` and proposal
previews retain their read-only behavior. A fixture dry-run enumerates planned
creates/replacements/unchanged files and creates no temps, state, locks or backups.
Enrollment is a separate mutation and cannot be combined with a dry-run.

The Fish entry forwards the same options, but Fish itself initializes XDG
directories at startup. When running it experimentally, supply a disposable
HOME and all four disposable XDG roots; changing only `XDG_CONFIG_HOME` is
insufficient to isolate the shell. Tests initialize Fish startup separately.

## Managed boundaries

All paths below are relative to the enrolled fixture. Existing application
configs are never included, merged, sourced, redirected or replaced.

| Target | Owned generated file | Purpose / limitation |
| --- | --- | --- |
| Ghostty | `config/panda/generated/ghostty.conf` | Opaque palette, cursor and selection fragment |
| Kitty | `config/panda/generated/kitty.conf` | Equivalent opaque palette, cursor and selection fragment |
| Konsole | `config/panda/generated/konsole.colorscheme` | Native INI color scheme; profile cursor/selection behavior needs Phase 3B probing |
| Starship | `config/panda/generated/starship.toml` | Named palette fragment; existing prompt format/styles are not replaced |
| Fastfetch | `config/panda/generated/fastfetch.json` | Display color fragment; module list/artwork are not replaced |
| Fish | `config/panda/generated/fish.fish` | Global-session color statements, never sourced by this milestone |

`config/panda/managed-files.json` stores hashes of enrolled fragments. An existing
fragment without a valid matching ownership entry is refused. A modified owned
fragment is also refused, rather than silently reasserting ownership. Existing
unrelated keys and files are preserved by leaving their enclosing application
configs untouched. Symlinks, including parents and dangling links, are rejected
without following or replacing them; hardlinks and special files are rejected.

State is `config/panda/theme-state.toml`; decision metadata is the separate
`config/panda/theme-decision.toml` containing `active`, `reason` and `source`.
Malformed state or inconsistent decision metadata blocks preparation. Legacy
four-field state without a sidecar remains valid and has no invented historical
reason. Existing safe file modes are preserved; new files use 0600. Existing
read-only destinations and unsafe/writable-by-others directories are refused.
All snapshot images are limited to 64 KiB and safe ordinary modes; timestamps
must fit nonnegative signed 64-bit nanoseconds. Unsupported original metadata
and oversized proposed state/reasons fail during preparation, before journaling.

`render_component(component, theme, destination)` is a standalone staging API
restricted to `fixture/state/render`; it does not participate in state commits.
The transaction uses the same renderer in memory so planning stays write-free.
Ghostty/Kitty/Fish use token templates. Konsole/Starship/Fastfetch use native
INI/TOML/JSON serialization. No independent application palette exists.

## Rendering and ergonomics

The 17 schema-v1 tokens remain authoritative. The shared terminal ANSI-role map
is `common/templates/terminal/roles.toml`. Normal/bright ANSI entries use readable
semantic text/status colors; ANSI black is explicitly a background/control role,
not promised as readable text. Gothic accent text uses `accent_text`, never its
low-contrast burgundy brand fill. Selection uses `on_selection` on `selection`.

Fragments omit font family/size, keybindings, padding, cursor shape/blink,
scrollback and prompt structure. Existing Ghostty/Kitty trial settings remain
JetBrainsMono Nerd Font Mono, 11.5, and unchanged in the repository. Actual
Konsole font units and cross-terminal size conversion must be inventoried in
Phase 3B before enrolling profiles. The foundation does not guess a conversion.

The Konsole color scheme and Starship/Fastfetch palette fragments do not prove
all selection, focus, greeting or module colors are active. Wiring those roles
into existing profiles without changing workflow is a Phase 3B review item.
Native installed-app parsers, launch checks and live refresh are unverified.
Structural parsers, exact canonical output validation, palette contrast and
Fish syntax checks cannot substitute for those runtime checks.

## Transaction sequence

1. Validate the explicit fixture, candidate, decision and canonical palette.
2. Probe all six fixture models; prepare and validate deterministic fragments
   in memory. An unavailable required target fails; an explicitly optional
   unavailable target produces a warning and is never reported verified.
3. Read and validate old managed content, state, ownership and decision metadata.
   Record every intended path, before/after bytes, mode and timestamps.
4. Acquire a nonblocking Linux `flock` on the fixture-local lock. Recheck state,
   old images and any pending journal. A busy lock fails clearly; an interrupted
   transaction blocks new switches until explicit recovery.
5. Atomically write and fsync a prepared recovery journal before target writes.
6. Replace enrolled fragments using same-directory temporary files, file fsync,
   rename and directory fsync. Never truncate managed files in place.
7. Verify all enrolled fragments; run fixture refresh outcomes. A required
   refresh failure triggers rollback. Fixture refresh invokes no native apps.
8. Recheck fragments after refresh and before persistence. Commit ownership and
   decision metadata, then the four-field state; verify each replacement.
9. Mark the journal committed only after core and state verification.

Adapter lifecycle: `probe`, `prepare`, `validate`, `snapshot`, `apply`, `verify`,
`refresh`, `restore`. Outcomes are structured; no shell command strings are
assembled from state. A byte-identical repeat verifies owned content and skips
replacement/refresh, preserving file modes and mtimes.

The lock persists as a file; its held descriptor determines lifetime. Process
exit releases the advisory lock. The lock file is never deleted to “break” a
lock. Locks coordinate participating processes, not hostile same-user programs.

## Rollback and interrupted recovery

The checksummed mode-0600 `state/panda-transactions/journal.json` is the inspectable
backup manifest. It contains old and intended new bytes, modes, atimes/mtimes,
paths, intended new directories and phase. It stays outside Git. One completed
snapshot is retained; it is replaced only when the next transaction starts.

On a caught failure, restore old images in reverse order and verify restoration.
Only files absent before that transaction are removed. Newly created directories
are removed only if empty. Existing directories and later unrelated contents
remain. A file matching neither recorded image is not overwritten; recovery
reports an incomplete restore and retains its backup. Failure and restore failure
have distinct `SwitchResult.rollback_status` values. `active` on failure identifies
the last known-good selection, not proof that current files or a desktop match it.

`doctor --recover` validates the entire journal and all current images before
starting recovery. Missing journal means there is no recoverable transaction,
not proof that an arbitrary partial configuration is correct. Corrupt, incomplete,
duplicate, absolute/traversing paths or ambiguous current content cause refusal.
Ownership hashes are cross-checked against generated backup entries so a valid
checksum cannot conceal an omitted changed target. Image metadata is validated
before the first restoration.
Recovery does not invent missing backups or overwrite later edits.

### Demonstrated guarantees

- Rendering/preparation failures leave targets untouched.
- Apply, verification, refresh, state-write and final journal failures restore
  the old fixture bytes, safe modes and mtimes in the tested cases.
- New files are removed on rollback; unrelated content survives.
- A second process cannot transact while the first holds the lock.
- Caught `KeyboardInterrupt` rolls back before propagation.
- Abrupt `os._exit` after an individual replacement releases the lock. The
  durable prepared journal allows explicit recovery of the interrupted fixture.
- Stale plans and later edits cause refusal; a failed restore remains visible
  and a subsequent explicit recovery can use the retained backup.
- The generated Fish fragment is sourced in an isolated, noninteractive Fish
  process and its actual color-variable values are checked. This verifies that
  hex tokens are arguments rather than comments; it does not verify the user's
  interactive shell, greeting, terminal display or Wayland session.

### Limits, separately from those guarantees

Distinct files are not replaced atomically as a group. Abrupt exit can leave a
mixed fixture until recovery; state and its sidecar are distinct replacements.
There is a small window after state replacement but before the committed journal
record. During it the prepared journal still requires recovery. A restore error
can leave an inconsistent fixture; the manager reports failure and retains the
record rather than claiming a successful selection.

File/directory fsyncs provide ordering on a working local Linux filesystem; no
power-loss, hardware-failure, ENOSPC exhaustion, filesystem-corruption or network
filesystem durability guarantee has been demonstrated. SIGKILL, reboot and all
possible interruption boundaries have not been tested exhaustively. Checksums
detect accidental journal corruption, not malicious same-user tampering.

Directory-relative no-follow opens and destination rechecks prevent following
symlinks. They are not filesystem compare-and-swap. An uncooperative same-user
writer can still race the final check/rename, rename a pinned directory, replace
a lock inode or recreate identical bytes/metadata. Private fixtures and
cooperative locking are assumptions, not adversarial user isolation. Preserve
this limitation in Phase 3B design rather than widening write roots now.

An abrupt exit while staging can leave a `.panda-*` temporary file. Recovery
does not glob-delete it or any unrelated file. Inspect retained artifacts in the
disposable fixture; cleanup is an explicit caller decision. ACLs, xattrs, inode
identity, ctime and directory timestamps are not restored by these file snapshots.
Atimes are captured/restored where applicable; mtime/mode/byte preservation is
what the automated rollback comparisons assert.

## Shell entry points

Repository-local `panda.fish`, `panda-big.fish` and `panda-status.fish` are not
installed or automatically sourced. Artwork inherits the terminal's current
appearance. Fastfetch uses a preset-free explicit structure and reports absence.
The status command reads established theme state and bounded health summaries;
it reports unavailable tools, unverified GPU policy and untested physical disk
health. It never alters those policies. `--no-health` skips health commands.

## Verification and Phase 3B handoff

```fish
python3 -B -m unittest discover -s tests -v
fish bootstrap/validate.fish
fish theme/panda/common/scripts/validate-palettes.fish
fish -n theme/panda/common/scripts/panda-theme.fish theme/panda/common/scripts/panda.fish theme/panda/common/scripts/panda-big.fish theme/panda/common/scripts/panda-status.fish
git diff --check
```

Use temporary HOME/XDG roots for executing Fish, as described above. Tests use
temporary roots and fake failure/availability outcomes, never real app activation.
All 140 required palette pairs must pass; the six Gothic fill advisories remain
expected restrictions. A Phase 3A test pass does not close live acceptance criteria.

Before Phase 3B, separately review installed versions, native validation/refresh
mechanisms, exact include/merge ownership, Konsole profiles, font units, opaque
rendering, Starship prompt styles, Fish greeting and Fastfetch artwork. Propose
backed-up user-local integration and real Wayland comparisons with controlled
failure/rollback evidence. Do not enable hooks, install commands, modify chezmoi,
apply KDE settings or start Phase 4 through this foundation milestone.

## Phase 3A file inventory

Paths are repository-relative. No files outside these boundaries are proposed
for version control; the approved documents, palettes, selection and state-reader
modules, chezmoi sources, bootstrap and machine policies remain unchanged.

| Status | Files | Role |
| --- | --- | --- |
| Modified | `theme/panda/common/cli.py`, `theme/panda/common/scripts/panda-theme.fish` | Explicit fixture opt-in, truthful preview/status/doctor/recovery |
| Added | `theme/panda/common/fixture_fs.py`, `theme/panda/common/transaction.py` | Scoped I/O, planning, persistence and recovery |
| Added | `theme/panda/common/render.py` | Native deterministic fragments |
| Added | `theme/panda/common/adapters/base.py`, `theme/panda/common/adapters/terminals.py`, `theme/panda/common/adapters/shell.py` | Structured fixture lifecycle |
| Added | `theme/panda/common/templates/terminal/roles.toml`, `theme/panda/common/templates/ghostty/theme.tmpl`, `theme/panda/common/templates/kitty/theme.tmpl`, `theme/panda/common/templates/fish/theme.tmpl` | Shared ANSI mappings and token templates |
| Added | `theme/panda/common/shell.py`, `theme/panda/common/scripts/panda.fish`, `theme/panda/common/scripts/panda-big.fish`, `theme/panda/common/scripts/panda-status.fish` | Repository-local artwork/health commands |
| Added | `tests/test_theme_rendering.py`, `tests/test_theme_transaction.py`, `tests/test_theme_fixture_cli.py`, `tests/test_panda_shell.py` | Behavioral and adversarial regression tests |
| Modified / added | `docs/panda-theme/manager.md`, `docs/panda-theme/transactions.md` | Phase split, contracts, examples, limitations and review inventory |
