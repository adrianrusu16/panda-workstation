# Panda Setup Manager — initial opt-in implementation

## Safety contract

This adds **a second, selectable installer**. It does NOT change the existing
`bootstrap/setup-workstation.fish`, its stage list, `setup-machine.fish`, Limine,
NVIDIA drivers, kernel packages, GPU policy, suspend masks, disk layout, or existing VMs.

Default mode is **dry-run**. An explicit `--check` performs strict, read-only readiness validation before installation (no downloads or writes). Nothing is installed without `--apply`. Terminal
apply requires the literal `APPLY` confirmation; noninteractive apply requires
both `--apply` and `--yes`. On `panda-helios`, gaming application is blocked
unless booted into the verified Intel-safe LTS profile. Experimental GTX 1060
mode is never activated by these tools.

No `sudo` is called in dry-run. There is no `pacman -Sy`, no AUR helper, no
unverified downloads, and no game account credential management.

## Commands

```fish
# Interactive selection (then a read-only preview, not installation)
fish bootstrap/panda-setup.fish

# All requested modules — current Android/AOSP entry is plan-only
fish bootstrap/panda-setup.fish --modules workspace,desktop,gaming,android,virtualization --stores steam,gog,epic,other --dry-run

# Gaming-only preview; on panda-helios GPU defaults to Intel safe profile
fish bootstrap/panda-gaming.fish --stores steam,gog,epic,other --dry-run

# Strict read-only readiness check; no installation performed
fish bootstrap/panda-gaming.fish --stores steam,gog,epic,other --check

# Future approved action, explicitly prompted (DO NOT use until reviewed)
fish bootstrap/panda-gaming.fish --gpu intel --stores steam,gog,epic,other --enable-flathub --apply

# Noninteractive apply needs explicit --apply --yes; not used automatically.
```

For a non-Helios machine, supply `--gpu intel` or `--gpu amd` explicitly. The
planner won't choose a vendor silently. During apply, the active kernel driver
is checked for the selected GPU. The current Helios path is always `intel`.

## Module implementation levels

| Module | Dry run | Apply | Limitations |
|---|---|---|---|
| Workspace | Existing steps listed | Core, chezmoi, Git, dev setup | Uses existing bootstrap scripts; may change user config; does not run machine stage |
| Panda Desktop | Plasma package plan | Existing `install-desktop.fish --profile plasma` | Theme activation and layout deployment are not implemented |
| Gaming | Steam, GOG/Epic, Lutris, Intel/AMD dependencies | Official pacman packages; Heroic user Flatpak | Doesn't log into stores, download games, enable NVIDIA, or tune game settings |
| Android / AOSP | Placeholder, pending | **Blocked** | No Android Studio/SDK/AOSP installation yet; including module in --apply blocks whole plan before writes |
| Virtualization | QEMU/libvirt/OVMF and Audit Lab support packages | Package installation only | Separate [Audit Lab commands](../virtualization/README.md); no service, media or VM actions |

## Store choices

- `steam`: Arch multilib Steam and a corresponding explicit Intel or AMD Vulkan driver.
- `gog`, `epic`: Heroic Games Launcher, installed once via official Flathub
  (`com.heroicgameslauncher.hgl`). Adding the *user* Flathub remote requires
  `--enable-flathub`; no automatic global remote modification.
- `other`: Lutris package; optional game-specific runners and accounts remain
  manual until verified. Supports EA, Ubisoft, Battle.net routes where viable.

A selected gaming module always includes GameMode, MangoHud and Vulkan tools.
On `panda-helios`, even a successful package install does not imply Cyberpunk
2077 or Mortal Kombat 1 will perform acceptably. Both are targeted primarily
at a future modern AMD gaming machine.

## Idempotence and failure mode

Package manifests use the repository's `install_manifest` helper, which detects
installed packages, calls `sudo pacman -S --needed` only for missing packages,
and verifies afterwards. Heroic checks `flatpak info` before installing.
Existing workspace scripts retain their own idempotence contracts.

Before applying, the manager checks required script paths, repositories,
multilib, package availability and GPU policy; unsupported Android/AOSP
selections fail before writes. Installing multiple modules is not an atomic
transaction. If a later stage fails, previous successful stage changes remain
and may be rechecked on rerun; no rollback is claimed.

The manager never enables a `libvirt` system service or creates an offline audit
VM. `bootstrap/setup-virtualization.fish` is a package-only shortcut to this
module with the same default preview and explicit apply gates. The recovered
[Audit Lab](../virtualization/README.md) provides a pure `plan` command and
separate explicit media/preflight/lifecycle commands. Its live acceptance remains
gated; package installation does not establish that a guest works.

## Git and CI

Keep this feature on `feat/panda-setup-manager` (do not use a `codex/*` branch).
AI can prepare a diff and review; **the logged-in user performs the commit**.

```fish
fish -n bootstrap/panda-setup.fish bootstrap/panda-gaming.fish bootstrap/lib/panda-setup.fish
python -m unittest discover -s tests -p 'test_panda_setup_manager.py' -v
fish bootstrap/panda-setup.fish --modules workspace,desktop,gaming,android,virtualization --stores steam,gog,epic,other --gpu intel --dry-run
git diff --check
```

No commands in this document should be considered authorization to apply the
selected packages or modify the boot/GPU configuration.

## G1.1 readiness contract

`--check` runs the same eligibility checks as `--apply`, without an APPLY prompt
or any mutations. It validates selected Workspace/Desktop stage files and Fish
syntax, the installed pacman inventory, availability in the **existing** synced
package databases for **every** selected manifest, multilib for gaming, Flathub
user-scope readiness, and the Helios Intel-only runtime guard.

Package metadata is not refreshed by this tool; if the pacman database is stale,
resolve that manually with a supported full system upgrade, never `pacman -Sy`.
The `--enable-flathub` flag explicitly authorizes creation of the **user**
remote on apply; readiness checks still never create it.

Failure handling is fail-fast, not atomic rollback. If a package installation or
stage fails after the first write, prior successful packages or user changes
remain installed; rerunning re-evaluates installed packages. Existing Workspace
stages can make additional user-level changes. Real `--apply` must not be used
until mocked failure tests and host readiness checks are reviewed.

## G1.1 host-preflight corrective update

Fish does not support `string match -qx`. Multilib and user Flathub checks
now read their lists and compare exact entries with `contains --`. A failing
`pacman -Si` query is reported as an **unverified repository query**, not
necessarily a missing package. The original pacman diagnostic is preserved,
including signature errors. The manager never disables repository signature
verification or refreshes package databases to work around this failure.

If `--check` reports a repository signature problem, inspect it separately
using read-only `pacman -Si <package>` and review `pacman-conf --repo-list`.
Do not run `--apply` until the package manager has been repaired through a
separately reviewed action.

## G1.2 offline transaction safety

`--check` and `--apply` additionally fail closed when `pacman -Qu` reports
cached pending upgrades, when pacman config has a non-empty `IgnorePkg` or
`IgnoreGroup`, when inventory/config queries fail, when `pacman -Sp --needed`
cannot resolve dependencies, or when its **combined selected-target** preview
would modify any installed package. `--apply` rechecks this gate after the
interactive confirmation and before any write. No `-Sy`/database refresh, sudo,
package download, or user configuration change is made by this guard.

**Limit:** These are checks against the *existing cached* sync databases.
An empty `pacman -Qu` is not a freshness guarantee. `pacman -Sp` does not test
all interactive installation choices, repository changes, file conflicts or
future state, and the actual installer still performs separate package-layer
transactions. A successful check is a necessary safety screen, **not a promise
that installation is safe or conflict-free**. Keep Helios hardware boundaries
and review any full system upgrades separately.

### G1.2 host regression corrections

`pacman -Qu` can return exit code **1 with no output** when no upgrades are
available. The guard accepts only that particular empty-output case; nonzero
exit codes accompanied by diagnostics still fail closed. `pacman -Sp` preview
records now validate both package names and Arch-style version tokens, so
malformed two-word output cannot accidentally pass the safety check.

## G1.3 — One-command orchestration and automatic verification

The same `bootstrap/panda-setup.fish` command selects all desired modules and
stores, performs complete G1.2 cached-database checks, verifies usable disk
space on the root/home/package-cache volumes, installs only missing packages,
installs a single **user-scoped** Heroic Flatpak for GOG/Epic if selected, then
verifies installed package manifests and Heroic automatically. It does not
invoke Steam or other GUI launchers as installation side effects.

The disk gate requires at least **8 GiB reported free** on each relevant volume.
This covers launcher package installation as a conservative minimum, **not**
a full games library, especially Cyberpunk 2077 or Mortal Kombat 1.
Failure to read disk capacity stops the installation; the storage and
transaction guards repeat after the explicit confirmation and before changes.

```fish
# Interactive, select modules/stores, review plan, type APPLY when prompted:
fish bootstrap/panda-setup.fish --interactive --enable-flathub --apply

# One-command gaming-only setup: same guards and automatic post-install checks:
fish bootstrap/panda-gaming.fish --stores steam,gog,epic,other --enable-flathub --apply

# Non-mutating verification of currently installed selections:
fish bootstrap/panda-gaming.fish --stores steam,gog,epic,other --verify
```

After installation, Steam, Heroic and Lutris may still require interactive
first-run dialogs, user logins, Steam Play/Proton settings and per-game
configuration. The manager never collects credentials, downloads games,
changes the boot/GPU policy, or claims that first-run GUI operation was tested.
`--verify` checks installed package state, not that a game can launch.
Android/AOSP remains a planning-only option and blocks any combined apply.

## G1.4 — One transaction and Helios hook-awareness

The manager now deduplicates missing packages across all selected manifests
and invokes **one** `sudo pacman -S --needed -- ...` transaction after the
existing cached-repository and disk-space safeguards. The existing workspace
and desktop scripts still run for non-package setup, but their package stages
should be no-ops when the combined transaction has already installed the
manifest packages. This reduces package-manager prompts; it does not make
interactive user configuration or external downloads noninteractive.

On `panda-helios`, strict modes call `machines/panda-helios/validate.fish`.
Apply also checks the **generated** first Limine LTS entry before and after
package hooks, fingerprints `/boot/limine.conf`, and flags any change. The
installer **does not** disable package hooks, modify boot configuration,
change kernels, touch NVIDIA isolation, or reboot. Pacman hooks can still
regenerate boot artifacts as an indirect effect; this is explicitly reported
and a post-change validation failure stops later setup stages. Users should
not reboot following a failed safety validation until investigated.

`--verify` and post-apply verification provide read-only launcher presence
and Vulkan device checks, plus a Python protobuf import for Lutris Battle.net.
These diagnostics do **not** start game launchers, authenticate stores,
install optional runners, or prove that any game can launch successfully.
`python-protobuf` is required in `setup/manifests/gaming-other.txt` for this
Lutris integration (already added locally before this patch).

## G1.4.1 — Failed transaction safety hotfix

On Helios, pacman can run hooks and change boot artifacts even when a package
transaction reports an error. The manager now records the original pacman exit
code and **always** runs the read-only machine validator, generated first-LTS
Limine blacklist check, and `/boot/limine.conf` fingerprint comparison after
the attempted transaction. It attempts all three even when one fails, then
blocks later stages. A failed pacman transaction retains its original exit code.
A successful transaction with a failed safety check exits nonzero.

**Scope:** these checks validate policy and compare the generated Limine
configuration file; they do **not** verify initramfs contents or guarantee a
subsequent boot. Pacman hooks are neither disabled nor rolled back. On a
failed Helios safety validation, investigate before rebooting.
