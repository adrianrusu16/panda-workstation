# 🐼 Panda Workstation

Reproducible Fish bootstrap, chezmoi configuration and Panda theme tooling for
CachyOS / Arch Linux with KDE Plasma Wayland. The current supported machine is
`panda-helios`. GPU, boot, sleep and storage policy are safety-critical; read
[AGENTS.md](AGENTS.md) and the [machine guide](machines/panda-helios/README.md)
before operating setup scripts.

## Repository map

| Path | Responsibility |
| --- | --- |
| [bootstrap/](bootstrap/) | Ordered setup, package helpers and repository validation |
| [packages/](packages/) | Core, desktop, development and plugin package manifests |
| [home/](home/) | Portable chezmoi source (selected by `.chezmoiroot`); no credentials |
| [machines/](machines/) | Hardware-specific setup and validation |
| [theme/panda/](theme/panda/) | Five canonical palettes, theme manager, offline desktop tools and generated styles |
| [tests/](tests/) | Disposable fixtures, preservation/security regressions and sealed native sources |
| [docs/](docs/) | Maintained operational and compatibility documentation |
| [.agents/skills/](.agents/skills/) | Repository-scoped skills and provenance |
| [.github/workflows/validate.yml](.github/workflows/validate.yml) | Offline CI validation |
| [.github/workflows/schema-regressions.yml](.github/workflows/schema-regressions.yml) | Pinned evidence-schema regression checks |

The five flavors are Minimal, Cyber, Gothic, Hybrid and PandaWave Pulse.
`wave` resolves to the canonical `pandawave` palette directory. Flavor changes
visuals while preserving the shared workflow and desktop structure.

## Setup and operation

Use an existing Fish installation to inspect implemented and planned stages:

```fish
fish bootstrap/setup-workstation.fish --list
fish bootstrap/setup-workstation.fish --help
fish bootstrap/install-desktop.fish --dry-run
```

The stage listing is read-only. Desktop dry-run validates one `pacman -Qq`
inventory and never installs packages. It requires the existing package tools.
Normal desktop installation requires explicit `--profile plasma` or an exported
`PANDA_DESKTOP_PROFILE=plasma`; no session detection is used.

The normal `bootstrap/setup-workstation.fish` entry point runs implemented
package, machine, chezmoi, GitHub, desktop, plugin, development and validation
stages. **It can change boot/GPU policy through the machine stage**, install
packages and apply configuration: inspect each stage and obtain the required
scoped authorization first. It is not a read-only health check. Its gaming and
full Panda experience stages are still planned; a complete fresh-system restore
has not been demonstrated. Never use `pacman -Sy` alone.

The separate [Panda Setup Manager](docs/panda-setup-manager.md) provides opt-in
workspace, desktop, gaming and virtualization modules. It defaults to dry-run;
installation requires explicit apply and confirmation. Android/AOSP remains
plan-only. Read its readiness checks, Helios guard and failure limits before use.

The separate [Android profile](docs/android-development.md) adds metadata plans,
process-local Fish selection and individually approved SDK operations. Legacy
`setup-workstation.fish --android` runs only that stage and defaults to `--plan`;
Android stays OFF in ordinary setup. The Setup Manager Android/AOSP apply gate
remains blocked. [CLI checks](docs/android-cli.md) require their own runtime
approval and may access the network or write caches.

Portable configuration belongs in `home/`; machine exceptions belong in
`machines/`. Keep credentials, local Git identity and signing keys outside Git.
The AI bootstrap has its own [prerequisites and recovery behavior](bootstrap/dev/README.md).
Curated skill installation and provenance are covered in [AI skills](docs/ai-skills.md).

## Panda documentation

| Guide | Use it for |
| --- | --- |
| [Theme manager](docs/panda-theme/manager.md) | Selection, Auto/manual behavior and command usage |
| [Palettes](docs/panda-theme/palettes.md) | Semantic tokens, contrast and wallpaper provenance |
| [Transactions](docs/panda-theme/transactions.md) | Fixture enrollment, apply/rollback contracts and failures |
| [Live integration](docs/panda-theme/live-integration.md) | Ghostty integration limits and recovery |
| [Canary safety](docs/panda-theme/canary-safety.md) | Private canary invariants and unresolved safety gates |
| [Desktop planning](docs/panda-theme/desktop.md) | Five-card layout, fixtures, synthetic previews and native gates |
| [Desktop compatibility](docs/panda-theme/desktop-compatibility.md) | Pinned KDE properties, identity preservation and observation limits |
| [Plasma Style assets](docs/panda-theme/plasma-style.md) | Generated package structure, provenance, fallback and reproducibility |
| [Native sources](tests/native/README.md) | Worker/supervisor seals, initialization, containment and execution prerequisites |
| [External VM sources](tests/native/external_vm/README.md) | Locked package provenance, preparation restrictions and separate build/capture/export gates |
| [Terminal comparison](docs/terminal-trial.md) | Optional Ghostty/Kitty comparison; Konsole fallback |

The five desktop cards are clock, media, weather, CPU and RAM. They are currently
offline models; no automatic layout applicator is supplied. Existing applet IDs,
panel clock, tray weather, task pins and desktop count are preservation inputs.
Plasma Style packages are generated sources, not activated desktop themes.
Native rendering and actual Breeze Dark fallback remain unverified. Historical
D3B1A/R3 recovery is unresolved; do not access or clean its retained evidence.

## Development and verification

With the existing Python, Fish and renderer/build dependencies available:

```fish
python3 -B -m unittest discover -s tests -v
fish --no-config bootstrap/validate.fish
python3 -B theme/panda/common/plasma_style.py --check
python3 -B theme/panda/common/native_frame_plan.py --check
git diff --check
```

Tests use disposable homes/configuration, fixture CLIs, synthetic rendering and
dispatch doubles. Static tests use an existing C++ compiler and synthetic CMake
imports; they never execute a native worker or launch a sandbox. Detailed visual
checks need PyGObject/Pango/PangoCairo/librsvg, pycairo and Fontconfig. Use a Python
installation that can import those existing bindings. Missing tooling is a
limitation, not permission to install it automatically. Strict ownership checks
can refuse a restricted environment that remaps trusted filesystem ancestors;
use the normal trusted filesystem context rather than weakening the checks.

The bootstrap validator checks Fish syntax, duplicate/invalid package entries
and executable permissions. For full Fish coverage, also run `fish -n` on tracked
Fish files under `home/` and `theme/`. The separate schema CI workflow installs
`jsonschema==4.25.1` in an isolated environment, validates native evidence schemas
and rejects skipped schema regressions. The [desktop](docs/panda-theme/desktop.md)
and [style](docs/panda-theme/plasma-style.md) guides describe deterministic exports.
Generated manifests, schema fixtures, source receipts, notices and package aliases
are required contracts; keep them with their generators.

Keep implementation changes small and reviewable. Leave disposable plans,
validation logs and intermediate reports in ignored `.local-ai/` or temporary
attachments. Maintain documentation that helps build, test, operate, troubleshoot
or recover the product; do not rewrite Git history to remove old development records.
