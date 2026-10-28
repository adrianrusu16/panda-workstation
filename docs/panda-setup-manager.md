# Panda Setup Manager — initial opt-in implementation

## Safety contract

This adds **a second, selectable installer**. It does NOT change the existing
`bootstrap/setup-workstation.fish`, its stage list, `setup-machine.fish`, Limine,
NVIDIA drivers, kernel packages, GPU policy, suspend masks, disk layout, or existing VMs.

Default mode is **dry-run**. Nothing is installed without `--apply`. Terminal
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
| Virtualization | QEMU/libvirt/OVMF packages | Package installation only | No services, autostart, VM creation or Audit Lab integration |

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
VM. That remains a separate reviewed feature branch.

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
