# Panda Workstation bootstrap

Start from the repository root with Fish already installed.

```fish
fish --no-config bootstrap/panda-setup.fish --modules workspace
```

The default is a dry run. Omit `--modules` in a terminal to choose from the
five-module menu. Use `--interactive` to prompt for Gaming stores too. For
scripts and CI, pass `--modules` explicitly.

| Mode | What it does |
| --- | --- |
| Default or `--dry-run` | Shows the selected packages, user configuration, prompts, external services, and hardware or deployment gates. |
| `--check` | Runs offline preflight against current inventory, cached package databases, selected stage files, and applicable hardware and remote configuration. |
| `--apply` | Shows the plan, runs preflight, then requires literal `APPLY` in a terminal. With redirected input, use `--apply --yes`. Native pacman and sudo prompts still apply. |
| `--verify` | Checks selected installed packages and user-scoped Heroic. For Gaming, it also prints read-only launcher and Vulkan diagnostics. Workspace user configuration, authentication, and development runtime need separate checks. |

For the same selection, append `--check` first. Once ready, replace it with
`--apply`, then run with `--verify` after installation.

## Module scope

| Module ID | Apply scope | User action or separate gate |
| --- | --- | --- |
| `workspace` | Core and development packages, portable dotfiles, Git identity and GitHub CLI, Rust, fish-lsp and uv tools | Review and confirm the chezmoi changes separately. GitHub may open a browser and prompt about SSH keys. Without a terminal, the dotfiles and GitHub stages are pending. Install the [official Codex CLI prerequisite](../bootstrap/dev/README.md) before development tooling. |
| `desktop` | Official Plasma packages | Native Panda Desktop deployment and session activation are separately gated. |
| `gaming` | Selected launcher packages and GPU support, plus user-scoped Heroic for GOG or Epic | First-run dialogs, account sign-in, runners and game downloads are manual. |
| `android` | Planning only | Strict modes refuse the entire selection until Android/AOSP runtime acceptance is complete. |
| `virtualization` | QEMU, libvirt, virt-manager and OVMF packages | Service activation and guest creation or startup are separate operations. |

Workspace uses this checkout as the explicit chezmoi source. It preserves the
existing chezmoi configuration, even if that configuration points elsewhere.
The prompt lists changed paths. It also prints the command to inspect the
full diff separately before accepting replacements to managed dotfiles.
Bootstrap preserves an existing `~/.gitconfig` and applies the other selected
dotfiles. A fresh home can receive the portable Git config.
An effective Git identity and an active GitHub CLI login are reused. If Git
has no identity and the portable include is missing, the GitHub stage stays
pending. An existing Fish user PATH customization is preserved. The
development stage can set Rust stable as the default and install the pinned
fish-lsp binary under `/usr/local/bin` with sudo.

### Optional Workspace shell tools

```fish
fish --no-config bootstrap/panda-setup.fish --modules workspace --with-shell-tools
fish --no-config bootstrap/panda-setup.fish --modules workspace --with-shell-tools --check
fish --no-config bootstrap/panda-setup.fish --modules workspace --with-shell-tools --apply
fish --no-config bootstrap/panda-setup.fish --modules workspace --with-shell-tools --verify
```

Select Workspace in the terminal menu to get the same opt-in. The optional
preflight needs Python 3.11 or later. The four packages in
`packages/plugins.txt` join the same guarded pacman transaction. An existing
Konsole installation remains available as the fallback terminal.

With the option selected, Workspace's regular chezmoi stage excludes Fish,
Ghostty, Kitty, and Starship. The shell stage lists the exact paths it can
create and prints a `diff -u` command for each file. It uses this checkout as
the explicit chezmoi source and renders only named files. It creates missing
files under `$XDG_CONFIG_HOME` or `~/.config` and leaves matching files alone.
An existing customized file or other startup preference can put its entire
configuration group into manual review. Existing files are never replaced by
the shell stage. Workspace still asks separately about its other dotfiles
and preserves an existing `~/.gitconfig` and chezmoi configuration.
If the list of shell files to create changes after the preview, apply stops
the shell stage and asks for a fresh plan.

The selected configuration root must be inside a real HOME directory.
Symlinks and nonregular files at managed paths block execution. A distribution
that seeds its own Fish configuration on first launch can cause the Fish
group to require review. Fish can initialize its standard directories before
the manager starts, including with `--no-config`. Use a real HOME and config
root before invoking Fish so that initialization stays inside the intended
directory.

If the Fish group is suitable and Fisher is missing, apply downloads the
Fisher 4.4.8 function from the [pinned upstream commit](https://raw.githubusercontent.com/jorgebucaran/fisher/a04308be92daa6cfecdbb0ca58b1e8508664cff2/functions/fisher.fish).
The bootstrap checks its reviewed SHA-256 before publishing the function.
It leaves existing Fisher installations in place and reports the checks
it could perform. The repository's `fish_plugins` selects
[`PatrickF1/fzf.fish@v11.0`](https://github.com/PatrickF1/fzf.fish/tree/v11.0).
Bootstrap checks the user's manifest, Fisher registration, and the expected
files. A missing or partial installation is a manual action. Fisher 4.4.8
can pick up extra manifest entries during an initial install and rewrite the
manifest. Review the installed plugins and manifest before running a
selective install in your own shell.

Verification runs without downloads and reports the package layer, each
configuration group, Fisher, fzf.fish, the Nerd Font, and baseline startup
separately. It uses disposable XDG paths to parse the baseline Ghostty,
Kitty, and Starship files and load the repository's Fish snippets. A
compatible Ghostty also parses all five standalone profiles. Custom startup
scripts and terminal configuration require manual review. Pending actions
are listed separately from probe failures. See the
[terminal trial](terminal-trial.md) for the separate attended Wayland check.

Gaming accepts `--stores steam,gog,epic,other`. Choose a subset to limit
launcher installations. The shared Gaming utilities and GPU manifest apply to
all store selections. GOG and Epic share one user-scoped Heroic Flatpak.
`--enable-flathub` authorizes adding the official user remote if needed.
Use `--gpu intel` or `--gpu amd` explicitly away from Helios. Helios uses the
Intel-safe profile. The convenience script `bootstrap/panda-gaming.fish` has
the same modes and restricts selection to Gaming.

## Safety and recovery

The installer uses one guarded `pacman -S --needed` transaction across the
selection. It queries existing cached databases and refuses pending upgrades,
package holds, unresolved targets, and a preview that would change already
installed packages. It never refreshes package databases. Cached readiness
does not guarantee freshness or predict every package conflict or prompt.
Gaming also checks multilib and requires at least 8 GiB free on the root,
home, and package cache volumes.

On Helios, strict modes run the machine safety validator. Apply checks the
first generated Limine LTS entry and fingerprints the generated configuration
before and after the package attempt, even when pacman fails. Pacman hooks can
regenerate boot artifacts. Investigate a failed safety check before rebooting
or retrying. The package checks do not validate initramfs contents.

The apply report distinguishes completed, already satisfied, skipped,
deferred, blocked, failed, and pending manual work. Failed commands keep
their diagnostics and exit codes. A package failure may leave packages or
hook effects in place. A later failure can leave earlier configuration or
downloads in place. Resolve the reported cause, run the printed scoped
`--check` command, and confirm a new apply. Use the affected module where
indicated and review any blocked modules separately. Existing packages and
Heroic are detected on retry.

## Legacy entrypoint

`bootstrap/setup-workstation.fish --list` still lists the historical stages.
`--help` explains the supported compatibility path. An explicit `--dry-run`,
`--check`, or `--verify` as the first argument forwards to the canonical
bootstrap. Bare invocation and apply requests through this entrypoint are
refused. `bootstrap/setup-plugins.fish` is a shortcut for the canonical
Workspace shell-tools selection and defaults to preview. Repository
validation remains a standalone stage. Machine provisioning requires
separate scoped authorization.
