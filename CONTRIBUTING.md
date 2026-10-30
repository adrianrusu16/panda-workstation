# Contributing to Panda Workstation

Propose changes to `main` through focused pull requests. Read [AGENTS.md](AGENTS.md)
before editing or testing. Host boot, kernel, GPU, storage and sleep policy require
separate authorization. Fixture, native VM and theme activation gates still apply;
source review and unit tests do not authorize a live experiment.

## Branches and commits

Start from current `origin/main` in a dedicated worktree when recovering old work.
Use `<prefix>/<short-kebab-description>` with one of `feat`, `fix`, `docs`,
`refactor`, `test`, `ci` or `chore`. For example, `fix/reject-invalid-enrollment`.
Do not create new `codex/` branches. Historical merged branches need no rewriting.

Use Conventional Commit subjects for new non-merge commits and PR titles:

```text
fix(theme): reject invalid enrollment
docs: clarify native execution prerequisites
```

Allowed types are `feat`, `fix`, `refactor`, `perf`, `docs`, `test`, `chore`,
`build`, `ci` and `revert`. Scope is optional; use `!` and a `BREAKING CHANGE:`
body when required. Keep subjects concise, with no trailing period. Prefer a
subject alone; reserve bodies for durable rationale or compatibility details.
Actual merge commits are exempt from subject validation; unrelated historical
commits already on the base are not revalidated.

Before committing, verify `gh auth status`, `gh api user`, `git var GIT_AUTHOR_IDENT`
and `git var GIT_COMMITTER_IDENT`. Use the authenticated contributor's intended
normal local Git identity. The repository owner's identity is Adrian Rusu
`<hello@adrianrusu.dev>`; other human contributors use their own intended identity.
Never replace it with an assistant identity, artificial author/committer environment
variables or invented authors. Do not automatically add assistant attribution,
coauthor trailers or promotional metadata. CI cannot prove that an email belongs
to an authenticated person; that check remains part of the contributor's review.

Review the complete diff and stage explicit logical paths. Never use `git add .`.
Preserve unrelated changes. Do not amend/rebase shared history, force-push, merge,
delete branches/worktrees or bypass checks without explicit scoped authorization.
Prefer squash merging with the approved PR title and an empty commit body unless
durable context or a breaking declaration is necessary. Inspect the final message.

## Validation and private files

Use the existing dependencies; do not install packages or start services/guests
just to validate a patch. From the repository root:

```fish
fish --no-config bootstrap/validate.fish
python3 -B -m unittest discover -s tests -v
git diff --check
```

Run `fish -n` for every changed Fish script, including scripts under `home/` and
`theme/`. Follow the [README](README.md#development-and-verification) and relevant
feature guide for schema, rendering and static checks. Report failures, skipped
tests, missing tooling and blocked live acceptance explicitly. A fixture pass
does not prove desktop or VM behavior. Native sources remain unexecuted until
their own authorization and provenance gates pass.

Keep credentials, signing material, `.env` files, private machine evidence,
recovery snapshots, `.local-ai/`, tool caches, virtualenvs and bytecode outside
tracked content. Disposable plans belong in ignored private paths. The policy
check rejects common private/generated paths in new PR changes; it is not a
credential-content scanner. Review the staged contents for secrets separately.
Recover old branches by comparing actual patches and PR history: squash ancestry
alone is not evidence that work is missing.

## Pull requests and owner settings

Describe the concrete problem, resulting behavior, provenance when recovering
existing work, observed validation and remaining gates. Request independent review.
Resolve critical/high findings before ready-for-review status; use a draft when
an explicit authorization or runtime acceptance gate remains. Do not combine
unrelated recovery streams or publish private recovery reports.

The `Contribution standards` CI job checks branch names, PR titles, new non-merge
commit subjects, assistant attribution and common private/generated paths.
The existing validation, schema and native preparation workflows remain required
evidence where applicable. PR metadata is read from event JSON and never evaluated
as shell input.

Repository owners must configure a GitHub ruleset or branch protection for `main`:
require PRs and approval, dismiss stale approvals, require resolved review threads,
require the applicable successful CI checks and block force pushes/deletion.
Choose required status checks after their first successful run so exact check names
are available. Limit bypass permissions deliberately. CI policy files alone cannot
prevent direct pushes or enforce owner settings; no repository script changes those
settings. Review and merge remain owner actions.
