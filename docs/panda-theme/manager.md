# Panda theme manager — previews and Phase 3A fixtures

Phase 3A adds the [Transaction Foundation](transactions.md) in explicitly enrolled
temporary fixtures. Phase 3B will add Controlled Live Integration only after a
separate reviewed plan and authorization. This split preserves the approved
design. Ordinary live commands remain disabled; the Phase 2 selection/state
contracts below remain intact. No real home or chezmoi-managed source is changed.

The default interface reads established state and proposes selections. It never
applies a live theme or writes real preferences. The command is repository-local;
bootstrap does not install it. Python 3.11+ and Fish are sufficient; no extra
packages are used.

From the repository root:

```fish
fish theme/panda/common/scripts/panda-theme.fish list
fish theme/panda/common/scripts/panda-theme.fish status
fish theme/panda/common/scripts/panda-theme.fish doctor
fish theme/panda/common/scripts/panda-theme.fish auto --explain
fish theme/panda/common/scripts/panda-theme.fish wave --dry-run
fish theme/panda/common/scripts/panda-theme.fish auto --dry-run --focus
fish theme/panda/common/scripts/panda-theme.fish next --dry-run
fish theme/panda/common/scripts/panda-theme.fish previous --dry-run
```

For deterministic fixtures, add `--state /absolute/temporary/theme-state.toml`
and `--now 2026-10-09T18:00:00+03:00` or `--no-time`. An absent state file is
valid and establishes no active flavor. The same arguments work with
`python3 -B theme/panda/common/cli.py`.

## Selection rules

Inputs are supplied explicitly; there is no project, window or game detector.

| Priority | Input | Automatic candidate / source |
| --- | --- | --- |
| 1 | `--special FLAVOR` | Explicit flavor / `special` |
| 2 | `--project pandawave` (or `wave`) | `pandawave` / `project` |
| 3 | `--gaming` | `cyber` / `gaming` |
| 4 | `--focus` | `minimal` / `focus` |
| 5 | Local time 07:00 inclusive to 18:00 exclusive | `hybrid` / `schedule` |
| 5 | Local time 18:00 inclusive to 21:00 exclusive | `cyber` / `schedule` |
| 5 | Remaining local hours, including midnight | `gothic` / `schedule` |
| 6 | Unavailable clock with no higher rule | `hybrid` / `fallback` |

All five canonical flavors are valid special/manual inputs. `wave` normalizes
to the single canonical `pandawave` flavor through the existing palette API.
Project identifiers are case-sensitive ASCII letters/digits/underscore/hyphen,
starting with a letter or digit, at most 64 characters. Only `pandawave` and
`wave` match the project rule; other identifiers fall through. Paths and malformed
signals fail without echoing their values. Unavailable boolean providers are
represented by `None` in the Python API and do not match a context rule.

`select_auto(now, ContextSignals(special, project, gaming, focus))` returns
`Decision(slug, reason, source)`. It uses the supplied datetime's local hour,
including timezone-aware/DST fixtures; it performs no I/O, clock reads or
timezone conversion. The CLI reads the local clock once unless one is injected.

`effective_decision(state, decision)` respects a loaded manual choice.
`auto --explain` reports the automatic candidate, rule, sanitized inputs and
whether manual mode blocks it. It does **not** re-enable Auto. Only the explicit
`auto --dry-run` command proposes returning to Auto; it still changes no state.

`propose_command(state, command, decision)` returns an immutable `ThemeState`
proposal. For proposals only, `active` means the candidate to apply later; CLI
output labels it `selected candidate`. Persisted `active` is reported separately
as `recorded active`, with live appearance unverified. Manual commands update
the proposal's `last_manual`; Auto preserves it. Existing `context` is preserved.

Cycling uses the canonical palette order: Minimal → Cyber → Gothic → Hybrid →
PandaWave → Minimal. `next` and `previous` propose manual mode. With no
established active flavor, `next` proposes Minimal and `previous` PandaWave.
The mode/flavor remains unchanged in the existing file across all previews and
process restarts. Phase 3A implements persistence after verified fixture
application; Phase 3B will enable the separately reviewed live integration.

## State reads and diagnostics

The default path is `$XDG_CONFIG_HOME/panda/theme-state.toml`, falling back to
`~/.config/panda/theme-state.toml` when XDG config is unset or empty. A nonempty
XDG config path must be absolute. `--state` overrides the location for fixtures.

Existing TOML must contain exactly these four fields:

```toml
mode = "auto"
active = "hybrid"
last_manual = "gothic"
context = ""
```

Mode is `auto` or `manual`. `active` and nonempty `last_manual` must be canonical
slugs; aliases are accepted at command input only. Empty `last_manual` means no
manual history. `context` is legacy plain text, never printed; control characters
are rejected. These files have no persisted decision reason, so `status` reports
`historical reason unavailable` rather than guessing. It cannot verify that the
recorded flavor matches the current desktop.

Malformed TOML, unknown fields, invalid modes/slugs, unreadable paths, symlinks in
any traversed component, parent (`..`) traversal, directories (including the root)
and special files produce errors. Reads
use directory-relative no-follow opens and are limited to 64 KiB. Existing bytes
are never replaced, repaired or deleted; no locks or state directories are made.
`doctor` validates the five manifests, required contrast pairs and state only.
It explicitly reports application adapters deferred; it makes no desktop claims.

Mutating commands without fixture opt-in or `--dry-run` fail with a Phase 3B
diagnostic. No service, watcher, hook, timer, application adapter or global
command is installed. Real
state writes and application integration remain Phase 3B work. Fixture-only
transactions and recovery are available with `--fixture-root` plus
`--allow-fixture-writes`; see the transaction guide for enrollment, boundaries and
limitations. Layout/widgets and automatic transitions remain later-phase work.

Fish itself initializes shell config/data/cache directories when started in an
empty home, even with `--no-config`. The Python entry avoids that shell startup.
Tests verify Python commands against empty temporary homes and Fish commands
against separately initialized temporary Fish homes. All preview and rejection
checks preserve file bytes, permissions and modification times.

## Verification

```fish
python3 -B -m unittest discover -s tests -p test_theme_state.py -v
python3 -B -m unittest discover -s tests -p test_theme_selection.py -v
python3 -B -m unittest discover -s tests -p test_theme_cli.py -v
python3 -B -m unittest discover -s tests -v
fish -n theme/panda/common/scripts/panda-theme.fish
fish theme/panda/common/scripts/validate-palettes.fish
fish bootstrap/validate.fish
git diff --check
```

Tests use temporary homes/config roots and injected clocks. No automated check
themes the real desktop or writes the user's Panda runtime state.
