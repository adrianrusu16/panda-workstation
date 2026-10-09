# Personal global design skills

## Migration status

The four design skills are deployed and the Panda-local duplicates have been
removed following explicit source, preview, deployment, runtime, and cleanup
approvals. The canonical packages contain 32 unchanged upstream files. The
deployed provenance manifest records finalized migration and verified deployment,
CLI, and Desktop checks.

Fresh CLI and Desktop sessions verified global discovery and actual instruction
loading before and after cleanup on 2026-10-09. The migration is ready for final
review. No staging, commit, or publication is authorized
by the migration approvals.

## Sources and scope

The canonical sources are `home/dot_agents/skills/<name>/` in the Panda checkout.
The existing `.chezmoiroot` selects `home/`; `dot_agents` becomes `.agents`
under the destination home. Chezmoi deploys regular files to
`$HOME/.agents/skills/<name>/`, with files `0644`, directories `0755`, and
current-user ownership (UID/GID 1000 on the verified host). There is no checkout
symlink, installer, startup hook, external download, or background synchronization.

| Skill | Scope | Use |
| --- | --- | --- |
| `better-ui` | User/global | Surface, icon, and motion polish |
| `better-layout` | User/global | Grouping, alignment, resizing, translation, and RTL |
| `better-colors` | User/global | Semantic colors, palette construction, measured contrast |
| `better-accessibility` | User/global | Keyboard, focus, semantics, forms, motion, and zoom |
| `prototype`, `animate` | Repository-local | Explicit UI exploration and requested motion construction |
| `graphify`, `panda-theme-system` | Repository-local | On-demand architecture analysis and Panda-specific theme work |

Humanizer remains deferred. Prototype, Animate, Graphify, and Panda Theme System
remain local. External skills are advisory: the current user request and Panda's
repository rules, approved theme specification, manifests, palettes, shared layout,
and hardware constraints take precedence. Lumora's stricter approval and Git
policies remain authoritative there. Skills do not grant withheld permissions.

A fresh standalone Panda checkout needs a separate personal global-skill
deployment to use the four `better-*` skills. Cloning alone does not deploy them.
The source packages remain available for reviewed chezmoi deployment.
Installed regular files keep working if the checkout moves; update chezmoi's
source configuration before deploying from the new location.

## Provenance

All four packages are pinned to
[jakubkrehel/skills at d574cc8](https://github.com/jakubkrehel/skills/tree/d574cc8a576dc24256ad38268b8d03d86724a1b3),
commit `d574cc8a576dc24256ad38268b8d03d86724a1b3`, under MIT,
Copyright (c) 2026 Jakub Krehel. Each retains the upstream license notice.
Source paths upstream are `skills/<name>/<path>`; license copies come from
the upstream root `LICENSE`. No adaptations were made.

[PROVENANCE.json](../home/dot_agents/skills/PROVENANCE.json) is also deployed
to `$HOME/.agents/skills/PROVENANCE.json`. Schema version 1 records portable
source and target roots, migration phase, pinned upstream origins, licenses,
scope, adaptations, verification states, and sorted file inventories.
Each package file has a SHA-256 and an upstream Git blob SHA-1.
The manifest does not hash itself or contain credentials, runtime logs, or
machine-specific session data. JSON uses sorted keys, two-space indentation,
and a final newline.

`migration_phase: finalized` means the four local duplicates have been removed.
Deployment and CLI/Desktop discovery-plus-invocation states are marked
`verified` only after observed checks. Metadata changes are separately reviewed
and deployed to the single provenance target; they do not change package hashes.
The remaining vendored local packages are documented in
[local provenance](../.agents/skills/PROVENANCE.md).

## Discovery and runtime verification

Codex exposes skill names and descriptions in its session catalog and reads
instructions when using a skill. Explicit invocation examples are
`$better-layout` and `$better-accessibility`. Read supporting references as
needed. Missing companion skills mentioned upstream do not authorize installation.

Before cleanup, a fresh Panda CLI session exposed both copies of each name and
selected the first-listed local copy in that test. This observation is not an
override contract. Global-only CLI and Desktop sessions each exposed all four
global names and loaded all four manifests and supporting references.
Synthetic reviews applied grouping, motion, contrast, and accessibility guidance.
One unrelated CLI arithmetic request read none of the four design manifests;
this is an observed negative control, not a guarantee about all automatic routing.

Post-cleanup CLI 0.160.1 and Desktop (backend 0.162.0-alpha.2) sessions each
exposed all four global names exactly once. Both Panda sessions preserved the
four local specialty entries and read AGENTS.md before applying layout and
accessibility instructions. Outside Panda, both runtimes loaded global UI and
color instructions, measured contrast, and used the motion references without
local skill copies. CLI ran in an isolated temporary Git repository. Desktop
used an unrelated app-created projectless directory; its Git identity check
returned "not a git repository," so that environment difference is recorded.
No skill invocation failed or required rollback.

For later updates, check fresh sessions inside Panda and outside it: each global
name must appear once, resolve to `$HOME/.agents/skills/<name>/SKILL.md`, and
actually load instructions during representative explicit invocations. Panda's
four specialty skills must remain local and available. Read repository policy
to establish authority; never test restrictions by attempting forbidden actions.
Report CLI and Desktop separately and keep unavailable checks pending.

These are local CLI/Desktop workflows. Availability here does not establish
cloud or other-machine availability. Selector presence alone does not prove
invocation. Synthetic reviews do not establish browser or screen-reader behavior.
Future name collisions require reviewed ownership or an explicit selection
decision; do not assume local-over-global precedence or merge unknown packages.
Leave Codex's bundled `.system` skills untouched and avoid extra copies under
`$HOME/.codex/skills`.

## Validation

Run from the Panda checkout:

```fish
python3 -B -m unittest discover -s tests -p test_global_skills.py -v
python3 -B -m unittest discover -s tests -v
fish bootstrap/validate.fish
git diff --check
```

The focused standard-library tests check inventory, pinned metadata, SHA-256 and
Git blob hashes, licenses, scalar skill headers, relative references, regular
file types and permissions, source mapping, and migration state. Finalized
migration requires exactly the four specialty directories locally. Tests do not
contact upstream or modify the live home; they are not a full YAML parser,
secret scanner, or substitute for runtime invocation evidence.
Check untracked-file whitespace separately before staging.

The approved source inventory excludes credentials, executable scripts, hooks,
caches, plans, graphs, and temporary runtime data. Preserve existing exclusions
for `.local-ai/`, `docs/superpowers/`, `.serena/`, `graphify-out/`, and `tmp/`.
Git ignore rules do not prevent deployment if a file enters chezmoi's source tree.

## Deployment and updates

First confirm `chezmoi source-path` resolves to this checkout's `home/`.
Check the current configuration for hooks, candidate name collisions, parent
symlinks, ownership, and file types. Unknown content or ownership stops deployment.
Preview only these targets using Fish:

```fish
set -l skill_targets \
    "$HOME/.agents/skills/better-accessibility" \
    "$HOME/.agents/skills/better-colors" \
    "$HOME/.agents/skills/better-layout" \
    "$HOME/.agents/skills/better-ui" \
    "$HOME/.agents/skills/PROVENANCE.json"

chezmoi --refresh-externals=never --mode=file --no-pager --use-builtin-diff diff --recursive --include=files,dirs $skill_targets
```

Review the exact operations and rollback baseline before authorizing live apply.
In a Fish scope with the same list, after deployment authorization:

```fish
chezmoi --refresh-externals=never --mode=file apply --recursive --include=files,dirs $skill_targets
chezmoi --refresh-externals=never --mode=file verify --recursive --include=files,dirs $skill_targets
```

Use no broad home apply, `exact_` pruning, symlink deployment, external downloads,
or workstation setup operations. Check all 33 files against source SHA-256,
regular file type, permissions, and ownership. Record hashes, modes, and
nanosecond modification times before repeating the targeted apply to prove
idempotency. Fingerprint protected configuration separately; normal Codex
session bookkeeping is not a skill modification.

Updates require an immutable upstream commit, review of changed instructions
and dependencies, license review, and independent comparison with upstream
bytes. Hash checks detect drift against recorded inventory; they cannot
authenticate an upstream claim without that independent comparison.
Update hashes only after review, preserve notices, and record deliberate
adaptations. Repeat safe runtime checks before approving changed instructions.

## Recovery and rollback

The pre-cleanup local baseline is Git commit
`f8220d5d0c6d0a26527a526a126336950b9f5d84`. Every removed file was verified
byte-identical to that revision before deletion. If cleanup causes a failure,
restore only the affected local package from that revision, without staging.
For example, for a failed layout invocation:

```fish
git restore --source=f8220d5d0c6d0a26527a526a126336950b9f5d84 --worktree -- .agents/skills/better-layout
```

The other eligible recovery paths are `.agents/skills/better-ui`,
`.agents/skills/better-colors`, and `.agents/skills/better-accessibility`.
Check for independent replacements before restoring. Preserve unrelated work,
report the failure, and stop. Do not reset the repository or rewrite history.
If local copies are restored, report that migration is no longer finalized and
review matching metadata changes before reapplication. Cleanup recovery does
not delete or change global skill packages.

The original live deployment baseline was absence of the 33 approved files
and 10 directories. Retain its exact file/hash/type/owner inventory outside
skill discovery. Removing global deployment requires separate authorization:
only explicitly inventoried task-created files still matching deployed hashes,
types, and owners are eligible. Never delete a user's replacement or recursively
prune shared skill directories. Remove only task-created empty directories with
nonrecursive removal. Revert matching chezmoi sources before any later apply
so rejected instructions cannot be silently reintroduced.
