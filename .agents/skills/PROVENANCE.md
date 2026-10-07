# Third-party skill provenance

These six skills are vendored unchanged from the revisions below. Each skill
directory includes a verbatim copy of its upstream MIT `LICENSE` notice so the
notice accompanies copies of that skill. No upstream scripts or plugins were
installed. Panda's repository rules and approved specification take precedence
over external design advice.

| Source repository | Upstream revision | Skill directories | License |
| --- | --- | --- | --- |
| [jakubkrehel/skills](https://github.com/jakubkrehel/skills/tree/d574cc8a576dc24256ad38268b8d03d86724a1b3) | `d574cc8a576dc24256ad38268b8d03d86724a1b3` | `better-colors`, `better-accessibility`, `better-layout`, `better-ui` | MIT, Copyright (c) 2026 Jakub Krehel |
| [emilkowalski/skills](https://github.com/emilkowalski/skills/tree/e8a175de22ae1e49370fc144c1f3bb9aeedf988d) | `e8a175de22ae1e49370fc144c1f3bb9aeedf988d` | `prototype`, `animate` | MIT, Copyright (c) 2026 Emil Kowalski |

Source directories are `skills/<skill-name>/` in each repository. All 32 original
files were rechecked against these revisions before Phase 1: Markdown and YAML
only, with no executable files or symlinks. The review identified rigid picker
styling and temporary-prototype cleanup in `prototype`, and references to
uninstalled skills in `animate`; these do not authorize extra installations,
production deletion, or overriding Panda's opaque-first/layout contracts.
