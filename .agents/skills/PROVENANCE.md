# Third-party skill provenance

The four `better-*` skills are globally managed regular files. Their canonical
sources are `home/dot_agents/skills/<name>/` in this checkout and their deployed
locations are `$HOME/.agents/skills/<name>/`. The Panda-local duplicates were
removed after approved deployment and fresh CLI/Desktop invocation checks.
A fresh standalone checkout needs a separate personal global-skill deployment.

`prototype` and `animate` remain vendored repository-local packages.
Each external package retains a verbatim upstream MIT `LICENSE`; no upstream
scripts or plugins were installed. Panda's repository rules, approved theme
specification, palettes, shared layout, and hardware constraints outrank
external design advice.

| Source repository | Upstream revision | Packages and scope | License |
| --- | --- | --- | --- |
| [jakubkrehel/skills](https://github.com/jakubkrehel/skills/tree/d574cc8a576dc24256ad38268b8d03d86724a1b3) | `d574cc8a576dc24256ad38268b8d03d86724a1b3` | Global: `better-colors`, `better-accessibility`, `better-layout`, `better-ui` | MIT, Copyright (c) 2026 Jakub Krehel |
| [emilkowalski/skills](https://github.com/emilkowalski/skills/tree/e8a175de22ae1e49370fc144c1f3bb9aeedf988d) | `e8a175de22ae1e49370fc144c1f3bb9aeedf988d` | Local: `prototype`, `animate` | MIT, Copyright (c) 2026 Emil Kowalski |

Upstream skill directories are `skills/<name>/`; licenses come from upstream
root `LICENSE`. All 32 global package files preserve their approved upstream
bytes and recorded SHA-256 and Git blob hashes, with no adaptations.
See [global provenance](../../home/dot_agents/skills/PROVENANCE.json) for the
exact inventory and [deployment, update, and recovery workflow](../../docs/ai-skills.md).

The retained local `graphify` and `panda-theme-system` skills are Panda-specific
and are outside this external-package migration. The earlier review identified
rigid picker styling and temporary-prototype cleanup in `prototype`, and
references to uninstalled skills in `animate`; those do not authorize extra
installations, production deletion, or overriding Panda's contracts.

The removed local copies are recoverable, without staging or broad reset, from
Git revision `f8220d5d0c6d0a26527a526a126336950b9f5d84`. Cleanup rollback restores
only affected local packages and preserves the global deployment.
