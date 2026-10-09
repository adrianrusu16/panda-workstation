# AI tooling bootstrap

The Development stage runs `setup-ai-tools.fish` after fish-lsp. To run only
AI tooling from the repository root:

```fish
fish bootstrap/dev/setup-ai-tools.fish
```

Prerequisites: Fish, the unpinned Arch/CachyOS `python` package, `uv` from
`packages/development.txt`, and official Codex CLI **0.160.1 or newer**. This
version floor is the tested bootstrap baseline, not a pin. Keep newer working
Codex installations. If Codex is missing, the script reports the official
standalone release location; install the matching Linux binary as
`~/.local/bin/codex`, then rerun. Authentication remains outside this repository.

The helper installs Serena with `uv tool install --python 3.14 serena-agent`.
This supersedes the approved plan's older Python 3.13 example. Only Serena's
isolated tool environment requires the 3.14 minor version; system Python stays
on the distribution's stable version. Existing Serena tool environments using
another Python minor version are reinstalled. Working 3.14 environments are
kept without upgrades. The managed Fish `conf.d/panda-user-path.fish` template
adds `~/.local/bin` on every shell startup without universal PATH mutations.

`serena init` runs only when the global Serena configuration is missing. The
installed Serena library must load that configuration successfully, and the
Serena executable on PATH must belong to the verified uv environment.
`serena setup codex` runs only when the enabled stdio MCP entry needs setup.
The guard validates TOML before setup, checks unrelated settings and hooks
afterward, and restores original bytes on failure. Existing valid entries
retain their settings, including any startup timeout. No hooks are installed
or rewritten. Rollback snapshots live in memory, not persistent backup files.
`CODEX_HOME`, `SERENA_HOME`, `XDG_CONFIG_HOME`, and uv's directory environment
variables are honored. Custom uv binary directories must already be on PATH.

Graphify is installed with `uv tool install graphifyy` only when its CLI is
missing. Both `graphify --version` and `graphify --help` must execute. The
bootstrap never runs `graphify install`, project integration, graph generation,
or skill installation. Review integration changes to `AGENTS.md` and `.agents/`
separately. Generated Serena/Graphify state and local AI plans are ignored.

Verification:

```fish
python -B -m unittest discover -s tests -v
fish -n bootstrap/setup-development.fish bootstrap/dev/setup-ai-tools.fish home/dot_config/fish/conf.d/panda-user-path.fish
fish bootstrap/validate.fish
git diff --check
```

Tests run the Fish bootstrap twice in isolated homes with fixture CLIs instead
of downloading tools. They exercise install arguments, preservation, rollback,
version checks, PATH deduplication, and an unchanged second run. Also run the
helper twice with real tools before accepting a bootstrap change. The CLI MCP
check verifies registration; confirm a connected server in Codex Desktop with
`/mcp` and a read-only Serena symbol query after reloading a newly configured
client.

Upstream references:

- [Serena Codex setup](https://oraios.github.io/serena/02-usage/030_clients.html#codex-cli-and-app)
- [Official Codex releases](https://github.com/openai/codex/releases/latest)
- [Graphify package and CLI](https://pypi.org/project/graphifyy/)
