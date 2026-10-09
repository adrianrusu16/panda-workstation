# Personal Codex defaults

- Prefer concise plans followed by verified implementation.
- Use Fish-compatible interactive commands on Linux unless a project explicitly requires another shell.
- Make small, reviewable changes and inspect existing conventions first.
- Never expose or commit credentials, tokens, private keys, signing keys, or secrets.
- Prefer idempotent setup scripts that detect state and verify results.
- On Arch/CachyOS, never run `pacman -Sy` by itself; avoid partial upgrades.
- Ask before changing bootloader, kernel, partitioning, GPU policy, firewall policy, or other recovery-critical system state.
- When a task has a written design/specification, treat that document as authoritative and report deviations explicitly.

## Git and pull requests

- Follow explicit task limits, repository policy, and applicable scoped instructions.
  These defaults never weaken stricter local rules.
- Commit subjects and PR titles use `<type>(<scope>): <summary>`; scope is optional.
  Prefer `feat`, `fix`, `refactor`, `perf`, `docs`, `test`, `chore`, `build`, `ci`, or `revert`.
  Use concise, descriptive, imperative wording, lowercase where natural, no trailing
  period, and no vague summaries such as `changes`, `updates`, `misc`, `final`, or `wip`.
- Make coherent atomic commits. Related implementation, tests, and documentation may
  stay together; do not mix unrelated intents or split changes mechanically by file.
- Normally use a subject only. Add a body only for durable rationale, compatibility,
  migration implications, or a required `BREAKING CHANGE:` declaration.
  Never copy the full PR description into a commit.
- Never automatically add `Co-authored-by`, extra authors, AI/LLM or assistant/tool
  attribution, `Generated with ...`, promotional text, or unrelated metadata.
  Do not invent authors or change the configured Git identity.
- Name branches `<type>/<short-kebab-description>`: lowercase, meaningful, and short.
  Avoid personal names, dates unless externally required, and meaningless suffixes.
- Write for reviewers: explain the problem, result, and specific validation.
  Tiny PRs may have no headings; normal PRs usually need two to four compact sections.
  Give complex PRs more structure only when useful. Omit empty or irrelevant sections
  and file-by-file narration.
- Use purposeful emojis when they help scanning, without requiring one per heading.
  Use tables for comparisons, Mermaid for relationships or flows, sequence diagrams
  for ordering, screenshots for visible changes, charts for real measurements with
  their conditions, checklists for actual state, and callouts for significant risks.
  Prefer a sentence or short list when clearer; avoid decoration and duplication.
- Before publishing substantial PR prose, remove filler, robotic phrasing, repetition,
  staged introductions, and redundant conclusions. Preserve facts, commands, versions,
  measurements, validation results, IDs, behavior, and intentional visual structure.
  No external prose-editing tool is required.
- Prefer squash merging. Use the PR title as the final subject and leave the body empty
  unless durable commit-level context is needed. Include required breaking declarations
  and inspect the final message for unwanted attribution or metadata.
- Run applicable verification and report observed results and limitations.
  Never mark unexecuted checks as passed; AI review is advisory.
- Implementation tasks normally authorize local feature-branch preparation, staging
  named task files, and coherent commits unless task limits or repository policy forbid
  them. Review the diff and staged content; preserve unrelated work and exclude secrets,
  temporary files, and unintended generated or local runtime state.
  Prefer explicit paths or logical groups when staging; avoid broad staging
  such as `git add .` when unrelated changes may be present.
- A request to push authorizes a normal feature-branch push. A request to open a PR
  includes necessary branch preparation and a normal push. Do not ask again for
  already-authorized prerequisites. Implementation alone does not authorize publication.
- Require explicit scoped authorization for merging, force-pushing, destructive resets,
  rewriting shared history, branch deletion, tag creation/deletion, or bypassing
  protected branches/checks. Stop and report unexpected remote divergence.
