# AGENTS.md — Panda Workstation

Keep this file small and treat it as the repository-wide safety and engineering contract.

## Repository

- Project: `panda-workstation`
- Primary host today: `panda-helios`
- Shell: Fish
- OS family: CachyOS / Arch Linux
- Default branch: `main`
- Conventional Commits are required.

## Working style

- Make small, reviewable changes.
- Inspect existing files and conventions before editing.
- Prefer idempotent scripts: detect current state, change only what is needed, then verify.
- Show or summarize the diff before any commit.
- Do not commit, push, publish, merge, or rewrite history unless the user explicitly asks.
- Do not use `git add .`; stage logical files/groups intentionally.
- Never print, store, or commit passwords, tokens, private keys, API keys, signing keys, or credential files.
- Prefer user-local configuration over system-wide changes unless system scope is materially required.

## Shell and package rules

- User-facing shell commands must be Fish-compatible.
- Avoid Bash heredocs in instructions and Fish scripts.
- Preserve pacman's own progress/output when package installation runs.
- Never run `pacman -Sy` without `-u`; avoid partial upgrades.
- Check whether a package/tool is already present before installing it.

## Validation

- A file existing is not proof that a feature works.
- Validate the resulting runtime state whenever practical.
- Run syntax/static checks before claiming a change is complete.
- For Fish changes: run `fish -n` on every changed Fish script.
- Run `git diff --check` before proposing a commit.
- Report warnings/failures explicitly rather than hiding them.

## Panda Helios safety boundary

The Acer Predator Helios 300 has an unstable GTX 1060 and an untrusted Intel 600p NVMe.

Do not modify any of the following as part of unrelated work:

- Limine bootloader configuration,
- kernel selection,
- NVIDIA isolation policy,
- suspend/hibernate masks,
- disk partitioning or filesystems,
- GPU driver policy.

Current safety contract:

- `linux-cachyos-lts` = safe/dev profile.
- Safe/dev profile hard-blocks NVIDIA modules.
- Intel HD 630 / `i915` is the safe graphics path.
- `linux-cachyos` = experimental NVIDIA-capable profile.
- Suspend/hibernate remain disabled.
- Samsung SATA SSD is the trusted OS disk.
- Intel 600p NVMe must not be used for the OS.

If a requested task would cross this boundary, stop and explain why before changing it.

## Panda Theme System

The approved design specification is:

`docs/superpowers/specs/2026-10-06-panda-theme-system-design.md`

When work touches Panda themes, Plasma layout, widgets, wallpaper, splash, icons, terminals, shell theming, editor theming, or automatic theme switching, use the `panda-theme-system` skill.

Theme rules:

- Wayland is the daily desktop session.
- The shared panel/widget/workspace layout is stable across flavors.
- Theme flavor changes visuals, not workflow/layout.
- `panda-helios` must not depend on transparency or blur.
- Theme switching must be explainable and rollback-safe.
- Theme manifests/palettes and the approved spec outrank generic external design-skill advice.

## External design skills

External skills may provide design heuristics, but they are advisory.

Authority order:

1. User request for the current task.
2. `AGENTS.md` safety/engineering rules.
3. Approved Panda Theme specification.
4. Panda flavor manifest / semantic tokens.
5. Panda-specific skill.
6. External design skills.
7. Agent improvisation.

Do not let a generic style skill replace Panda palettes, Helios constraints, or the shared desktop layout.
