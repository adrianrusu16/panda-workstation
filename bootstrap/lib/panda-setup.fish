#!/usr/bin/env fish
# Fish helpers for the opt-in Panda Setup Manager.

# Authoritative module metadata, in the existing interactive menu order.
# Fields: id | name | status | operations | manifests | selectors | scripts |
# arguments | limitations | menu | step | info | warning.
# Pipes delimit fields; commas delimit only the list fields. Selectors choose
# manifests, never execute operations. Text fields may contain commas.
# Scripts are existing post-package stages, relative to the repository root.
function panda_setup_module_contracts
    string join '|' -- workspace Workspace implemented 'dry-run,check,verify,apply' \
        'packages/core.txt,packages/development.txt' 'always,always' \
        'bootstrap/install-core.fish,bootstrap/setup-chezmoi.fish,bootstrap/setup-github.fish,bootstrap/setup-development.fish' '' \
        'Existing stages may configure the user and download development tools; no automatic machine provisioning.' \
        'core tools, chezmoi, Git, development; no boot changes' \
        'Workspace: install-core → setup-chezmoi → setup-github → setup-development' \
        'Existing workstation scripts may change user configuration and install dev tools on --apply.' ''
    string join '|' -- desktop 'Panda Desktop' packages-only 'dry-run,check,verify,apply' \
        packages/desktop.txt always bootstrap/install-desktop.fish '--profile,plasma' \
        'Plasma packages only; no automatic Panda theme or layout activation.' \
        'Plasma packages only; no theme activation' \
        'Panda Desktop: install-desktop.fish --profile plasma (packages only)' \
        'Panda theme/layout activation is not part of this release.' ''
    string join '|' -- gaming Gaming implemented 'dry-run,check,verify,apply' \
        'setup/manifests/gaming-base.txt,setup/manifests/gaming-steam.txt,setup/manifests/gaming-heroic.txt,setup/manifests/gaming-other.txt,setup/manifests/gaming-intel.txt,setup/manifests/gaming-amd.txt' \
        'always,steam,heroic,other,intel,amd' '' '' \
        'Official packages and user-scoped Heroic only; no NVIDIA activation, accounts, games or automatic machine tuning.' \
        'multi-store gaming stack' '' '' ''
    string join '|' -- android 'Android / AOSP' preview-only dry-run '' '' '' '' \
        'Check, verify and apply are blocked; no SDK, Studio, AOSP or Android runtime-stage dispatch.' \
        'planning only, not deployable yet' '' '' \
        'Android / AOSP is NOT IMPLEMENTED; --apply will refuse the entire selection.'
    string join '|' -- virtualization Virtualization packages-only 'dry-run,check,verify,apply' \
        setup/manifests/virtualization-base.txt always '' '' \
        'Packages only; no libvirt service activation, autostart, VM creation or Audit Lab execution.' \
        'packages only; never creates/boots a VM' \
        'Virtualization: QEMU/libvirt/virt-manager/OVMF package layer only' \
        'No libvirt service configuration, VM disk, firmware changes, or guest startup.' ''
end

function panda_setup_module_ids
    for row in (panda_setup_module_contracts)
        set -l fields (string split '|' -- "$row")
        echo "$fields[1]"
    end
end

# Pure lookup: no eval, global state, discovery, package queries or dispatch.
# List properties emit one value per line; an empty property emits nothing.
function panda_setup_module_get --argument-names module field
    set -l keys id name status operations manifests selectors scripts arguments limitations menu step info warning
    set -l index (contains -i -- "$field" $keys)
    if test (count $argv) -ne 2; or test -z "$index"
        printf 'Unknown module contract property: %s\n' "$field" >&2
        return 2
    end
    for row in (panda_setup_module_contracts)
        set -l fields (string split '|' -- "$row")
        if test "$fields[1]" != "$module"
            continue
        end
        if contains -- "$field" operations manifests selectors scripts arguments
            string split -n ',' -- "$fields[$index]"
        else if test -n "$fields[$index]"
            echo "$fields[$index]"
        end
        return 0
    end
    printf 'Unknown module: %s\n' "$module" >&2
    return 2
end

# Preserve manifest order independently of store selection order. GOG/Epic
# share one Heroic selector; installed-package deduplication remains downstream.
function panda_setup_module_manifests --argument-names module gpu
    set -e argv[1..2]
    set -l selected always "$gpu" $argv
    if contains -- gog $argv; or contains -- epic $argv
        set -a selected heroic
    end
    set -l manifests (panda_setup_module_get "$module" manifests)
    or return 2
    set -l selectors (panda_setup_module_get "$module" selectors)
    set -l index 1
    for manifest in $manifests
        if contains -- "$selectors[$index]" $selected
            echo "$manifest"
        end
        set index (math $index + 1)
    end
    return 0
end

function panda_setup_csv --argument-names value
    set -l normalized (string replace -a ',' ' ' -- "$value")
    for part in (string split -n ' ' -- "$normalized")
        set -l trimmed (string trim -- "$part")
        if test -n "$trimmed"
            echo "$trimmed"
        end
    end
end

function panda_setup_show_manifest --argument-names manifest
    if not test -f "$manifest"
        ui_error "Missing manifest: $manifest"
        return 1
    end
    set -l name (path basename -- "$manifest")
    set -l installed
    if command -sq pacman
        set installed (pacman -Qq 2>/dev/null)
        if test $status -ne 0
            ui_warn 'Cannot read pacman inventory; installed status unknown (read-only preview).'
            set installed
        end
    else
        ui_warn 'pacman is unavailable; listing desired packages only.'
    end
    ui_section '📦' "$name"
    while read -l line
        set line (string trim -- "$line")
        if test -z "$line"; or string match -q '#*' -- "$line"
            continue
        end
        if not string match -qr '^[a-z0-9][a-z0-9@+_.-]*$' -- "$line"
            ui_error "Invalid package in $manifest: $line"
            return 1
        end
        if contains -- "$line" $installed
            ui_info "Installed: $line"
        else
            ui_step "Would install: $line"
        end
    end < "$manifest"
end

function panda_setup_gpu_profile --argument-names requested
    if test "$requested" = auto
        if test (hostname) = panda-helios
            echo intel
            return 0
        end
        ui_error 'Automatic GPU selection only supports panda-helios. Use --gpu intel or --gpu amd explicitly.' >&2
        return 1
    end
    echo "$requested"
end

function panda_setup_check_gpu_safety --argument-names gpu strict
    if test (hostname) != panda-helios
        ui_info "GPU profile $gpu requested; inspect actual drivers on this host before --apply."
        if test "$strict" = 1
            if not command -sq lspci
                ui_error 'lspci required for vendor verification'
                return 1
            end
            set -l bound (lspci -k 2>/dev/null | string collect)
            if test "$gpu" = amd; and not string match -q '*Kernel driver in use: amdgpu*' -- "$bound"
                ui_error 'AMD profile selected without an active amdgpu driver'
                return 1
            end
            if test "$gpu" = intel; and not string match -q '*Kernel driver in use: i915*' -- "$bound"
                ui_error 'Intel profile selected without an active i915 driver'
                return 1
            end
        end
        return 0
    end
    if test "$gpu" != intel
        ui_error 'panda-helios is Intel-safe only; refusing other GPU profiles'
        return 1
    end
    if not string match -q '*cachyos-lts*' -- (uname -r)
        ui_warn 'panda-helios is not running the safe LTS kernel.'
        if test "$strict" = 1
            return 1
        end
    end
    set -l cmdline (string collect < /proc/cmdline)
    set -l blacklist 'module_blacklist=nvidia,nvidia_drm,nvidia_modeset,nvidia_uvm,nouveau'
    if not string match -q "*$blacklist*" -- "$cmdline"
        ui_warn 'Helios safe NVIDIA kernel blacklist not detected.'
        if test "$strict" = 1
            return 1
        end
    end
    set -l loaded (grep -E '^nvidia' /proc/modules 2>/dev/null)
    if test (count $loaded) -gt 0
        ui_warn 'NVIDIA kernel module is loaded. Apply is prohibited on Helios.'
        if test "$strict" = 1
            return 1
        end
    end
    if test "$strict" = 1
        set -l igpu (lspci -k -s 00:02.0 2>/dev/null | string collect)
        if not string match -q '*Kernel driver in use: i915*' -- "$igpu"
            ui_error 'Helios Intel HD 630 is not bound to i915'
            return 1
        end
        set -l root (findmnt -n -o SOURCE / 2>/dev/null)
        if not string match -q '/dev/sda2*' -- "$root"
            ui_error 'Helios system root not on approved Samsung SATA partition'
            return 1
        end
        if test -b /dev/nvme0n1
            set -l mounts (lsblk -nrpo MOUNTPOINT /dev/nvme0n1 2>/dev/null | string trim | string match -rv '^$')
            if test (count $mounts) -gt 0
                ui_error 'Untrusted Intel NVMe has mounted filesystems'
                return 1
            end
        end
    end
    ui_success 'Helios GPU setup does not require any NVIDIA driver or boot changes.'
end

function panda_setup_repo_available --argument-names manifest
    if not test -f "$manifest"
        ui_error "Missing package manifest: $manifest"
        return 1
    end
    while read -l line
        set line (string trim -- "$line")
        if test -z "$line"; or string match -q '#*' -- "$line"
            continue
        end
        if not pacman -Qq "$line" >/dev/null 2>&1
            # A failure may mean an unavailable package OR broken repository
            # metadata/signatures. Keep pacman's actual diagnostic visible.
            set -l repo_query (pacman -Si "$line" 2>&1)
            set -l repo_status $status
            if test $repo_status -ne 0
                ui_error "Cannot verify package: $line (pacman -Si exit $repo_status)"
                for message in $repo_query
                    printf '  pacman: %s\n' "$message" >&2
                end
                ui_error 'Fix the repository/query error before applying; package availability is unverified.'
                return 1
            end
        end
    end < "$manifest"
end

function panda_setup_multilib_check
    if not command -sq pacman-conf
        ui_error 'pacman-conf is required to check multilib'
        return 1
    end
    set -l repos (pacman-conf --repo-list 2>/dev/null)
    if test $status -ne 0
        ui_error 'Cannot read enabled pacman repositories; refusing to guess multilib state.'
        return 1
    end
    if not contains -- multilib $repos
        ui_error 'Arch multilib is not enabled; refusing to modify pacman.conf automatically.'
        return 1
    end
end

function panda_setup_has_flathub
    if not command -sq flatpak
        return 1
    end
    set -l remotes (flatpak remotes --user --columns=name 2>/dev/null)
    if test $status -ne 0
        return 1
    end
    contains -- flathub $remotes
end

# Shared strict preflight for --check and --apply. Nothing is modified here.
function panda_setup_preflight_scripts --argument-names script_dir
    set -e argv[1]
    set -l scripts
    for module in (panda_setup_module_ids)
        if contains -- "$module" $argv
            set -a scripts (panda_setup_module_get "$module" scripts)
        end
    end
    set -l root (path dirname -- "$script_dir")
    for script in $scripts
        set -l path "$root/$script"
        if not test -f "$path"
            ui_error "Missing setup stage: $path"
            return 1
        end
        if not fish -n "$path"
            ui_error "Invalid Fish syntax in setup stage: $path"
            return 1
        end
    end
    return 0
end

function panda_setup_preflight_packages --argument-names root
    set -e argv[1]
    set -l modules
    set -l manifests
    set -l separator 0
    for token in $argv
        if test "$token" = --
            set separator 1
            continue
        end
        if test $separator -eq 0
            set -a modules "$token"
        else
            set -a manifests "$token"
        end
    end
    if test $separator -eq 0
        ui_error 'Internal error: package preflight missing separator'
        return 2
    end

    # A failed or empty inventory must never be mistaken for no installed packages.
    panda_installed_inventory >/dev/null
    or return 1

    if contains workspace $modules
        # Rust and rustup conflict; check before installing ANY selected packages.
        if pacman -Qq rust >/dev/null 2>&1; and not pacman -Qq rustup >/dev/null 2>&1
            ui_error 'Arch rust conflicts with workstation rustup; resolve before --apply.'
            return 1
        end
    end
    for module in workspace desktop
        if contains -- "$module" $modules
            for manifest in (panda_setup_module_get "$module" manifests)
                set -a manifests (string replace -r '\.txt$' '' -- "$manifest")
            end
        end
    end
    for name in $manifests
        set -l manifest "$root/setup/manifests/$name.txt"
        if string match -q 'packages/*' -- "$name"
            set manifest "$root/$name.txt"
        end
        panda_setup_repo_available "$manifest"
        or return 1
    end
    return 0
end

function panda_setup_preflight_heroic --argument-names enable_flathub
    # The managed Heroic installation is always user-scoped, even if the
    # machine also happens to have a system-wide Flatpak installation.
    if command -sq flatpak
        if flatpak info --user com.heroicgameslauncher.hgl >/dev/null 2>&1
            ui_success 'User-scoped Heroic is already installed.'
            return 0
        end
        if panda_setup_has_flathub
            return 0
        end
    end
    if test "$enable_flathub" = 1
        ui_info 'Flathub user remote creation explicitly authorized for --apply.'
        return 0
    end
    ui_error 'User Flathub remote not ready; provide --enable-flathub to authorize adding it.'
    return 1
end

# Offline transaction guard. Does not synchronize databases or acquire sudo.
# This checks current cached state only; it cannot guarantee repository freshness.
function panda_setup_guard_transaction
    if not command -sq pacman-conf
        ui_error 'pacman-conf is needed for transaction safety checks.'
        return 1
    end

    set -l pending (pacman -Qu 2>&1)
    set -l pending_status $status
    # pacman -Qu can return 1 with no output when no upgrades are available.
    # Exit 1 with ANY diagnostic is still an error: do not bypass failures.
    if test $pending_status -eq 1; and test (count $pending) -eq 0
        ui_info 'No cached upgrades (pacman -Qu returned 1 without output).'
    else if test $pending_status -ne 0
        ui_error "Cannot query pending upgrades (pacman -Qu exit $pending_status)."
        for line in $pending
            printf '  pacman: %s\n' "$line" >&2
        end
        return 1
    end
    if test (count $pending) -gt 0
        ui_error 'Cached repositories show pending upgrades; refusing a partial upgrade.'
        for line in $pending
            ui_warn "$line"
        end
        return 1
    end

    # Read the resolved config once so an absent IgnorePkg/IgnoreGroup is OK,
    # while a broken configuration query still blocks the transaction.
    set -l config (pacman-conf 2>&1)
    if test $status -ne 0
        ui_error 'Unable to inspect pacman configuration; refusing to guess package holds.'
        return 1
    end
    if string match -qr '^\s*Ignore(Pkg|Group)\s*=\s*\S' -- $config
        ui_error 'IgnorePkg or IgnoreGroup is configured; review it before installing packages.'
        return 1
    end

    set -l installed (panda_installed_inventory)
    or return 1
    set -l targets
    for manifest in $argv
        if not test -f "$manifest"
            ui_error "Transaction manifest missing: $manifest"
            return 1
        end
        while read -l line
            set line (string trim -- "$line")
            if test -z "$line"; or string match -q '#*' -- "$line"
                continue
            end
            if not string match -qr '^[a-z0-9][a-z0-9@+_.-]*$' -- "$line"
                ui_error "Invalid transaction package: $line"
                return 1
            end
            if not contains -- "$line" $installed; and not contains -- "$line" $targets
                set -a targets "$line"
            end
        end < "$manifest"
    end

    if test (count $targets) -eq 0
        ui_success 'No new pacman packages needed (cached-database check only).'
        return 0
    end

    # This asks libalpm to resolve the *whole* selected target set, including
    # dependencies. --print does not install, download, or refresh databases.
    set -l preview (pacman -Sp --needed --print-format '%n %v' -- $targets 2>&1)
    set -l preview_status $status
    if test $preview_status -ne 0
        ui_error "Cannot resolve package transaction (pacman -Sp exit $preview_status)."
        for line in $preview
            printf '  pacman: %s\n' "$line" >&2
        end
        return 1
    end
    if test (count $preview) -eq 0
        ui_error 'No package transaction returned despite missing targets; refusing to guess.'
        return 1
    end
    set -l planned
    for line in $preview
        set -l fields (string split -n ' ' -- (string trim -- "$line"))
        if test (count $fields) -ne 2
            ui_error "Unexpected package transaction output: $line"
            return 1
        end
        if not string match -qr '^[a-z0-9][a-z0-9@+_.-]*$' -- "$fields[1]"
            ui_error "Unexpected package name in transaction: $fields[1]"
            return 1
        end
        # %v is an Arch package version (optionally with epoch and pkgrel).
        # Reject diagnostics that happen to contain exactly two words.
        if not string match -qr '^[[:alnum:]][[:alnum:]._:+~-]*$' -- "$fields[2]"
            ui_error "Unexpected package transaction output: $line"
            return 1
        end
        if contains -- "$fields[1]" $installed
            ui_error "Planned transaction would modify installed package: $fields[1] ($fields[2]); refusing."
            return 1
        end
        if contains -- "$fields[1]" $planned
            ui_error "Duplicate package in transaction preview: $fields[1]"
            return 1
        end
        set -a planned "$fields[1]"
    end
    ui_success (count $planned)' planned new pacman packages; no upgrades to installed packages in offline preview.'
    ui_warn 'Offline preview cannot prove sync databases are fresh or guarantee a future install.'
    return 0
end

# Validate usable space on the root, user home and pacman cache volumes.
# 8 GiB is a conservative minimum for launcher packages and first-run runtimes,
# not a promise that any large game itself will fit.
function panda_setup_check_disk_space
    if not command -sq df
        ui_error 'df is required for the disk-space safety check.'
        return 1
    end
    set -l minimum_kib 8388608
    for directory in / "$HOME" /var/cache/pacman/pkg
        set -l usage (df -Pk -- "$directory" 2>&1)
        set -l disk_status $status
        if test $disk_status -ne 0; or test (count $usage) -ne 2
            ui_error "Cannot determine free space for $directory."
            for line in $usage
                printf '  df: %s\n' "$line" >&2
            end
            return 1
        end
        set -l columns (string split -n ' ' -- (string trim -- "$usage[2]"))
        if test (count $columns) -lt 5; or not string match -qr '^[0-9]+$' -- "$columns[4]"
            ui_error "Invalid disk capacity output for $directory."
            return 1
        end
        if test "$columns[4]" -lt $minimum_kib
            ui_error "Less than 8 GiB available for $directory; package install blocked."
            return 1
        end
    end
    ui_success 'Disk-space preflight: root, home and pacman cache each report at least 8 GiB free.'
    return 0
end

# Verify installed package manifests and Heroic without starting any GUI app.
# The caller passes a 0/1 Heroic flag followed by manifest paths.
function panda_setup_verify_installation --argument-names heroic
    set -e argv[1]
    set -l installed (panda_installed_inventory)
    or return 1
    set -l verified
    for manifest in $argv
        if not test -f "$manifest"
            ui_error "Missing verification manifest: $manifest"
            return 1
        end
        while read -l line
            set line (string trim -- "$line")
            if test -z "$line"; or string match -q '#*' -- "$line"
                continue
            end
            if not contains -- "$line" $installed
                ui_error "Selected package missing after installation: $line"
                return 1
            end
            if not contains -- "$line" $verified
                set -a verified "$line"
            end
        end < "$manifest"
    end
    if test "$heroic" = 1
        if not command -sq flatpak; or not flatpak info --user com.heroicgameslauncher.hgl >/dev/null 2>&1
            ui_error 'Selected Heroic user Flatpak is not installed.'
            return 1
        end
        ui_success 'Heroic user-scoped installation verified.'
    end
    ui_success (count $verified)' selected pacman packages verified.'
    ui_info 'Verification does not launch Steam, modify drivers, or sign into game stores.'
    return 0
end

# Collect missing packages across manifests in one deduplicated list. Never
# silently treat an unreadable package inventory as an empty installation.
function panda_setup_missing_targets
    set -l installed (panda_installed_inventory)
    or return 1
    set -l missing
    for manifest in $argv
        if not test -f "$manifest"
            ui_error "Missing selected package manifest: $manifest"
            return 1
        end
        while read -l package
            set package (string trim -- "$package")
            if test -z "$package"; or string match -q '#*' -- "$package"
                continue
            end
            if not string match -qr '^[a-z0-9][a-z0-9@+_.-]*$' -- "$package"
                ui_error "Invalid selected package: $package"
                return 1
            end
            if not contains -- "$package" $installed; and not contains -- "$package" $missing
                set -a missing "$package"
            end
        end < "$manifest"
    end
    if test (count $missing) -gt 0
        printf '%s\n' $missing
    end
end

# Execute exactly one combined pacman transaction for all selected manifests.
# The shared G1.2 transaction guard must run immediately before this helper.
function panda_setup_install_selected
    set -l missing (panda_setup_missing_targets $argv)
    or return 1
    if test (count $missing) -eq 0
        ui_success 'All selected pacman packages are already installed.'
        return 0
    end
    ui_section '📦' 'Combined pacman installation'
    ui_info (count $missing)' missing manifest packages; dependencies resolved by pacman.'
    ui_info 'One pacman transaction and one native confirmation; no repository refresh.'
    sudo pacman -S --needed -- $missing
    set -l result $status
    if test $result -ne 0
        ui_error "Combined pacman installation failed (exit $result)."
        return $result
    end
    ui_success 'Combined pacman installation completed.'
    return 0
end

# Verify existing safety policy; never run the machine/boot setup stage.
function panda_setup_helios_validate --argument-names repo_root
    if test (hostname) != panda-helios
        return 0
    end
    set -l validator "$repo_root/machines/panda-helios/validate.fish"
    if not test -f "$validator"
        ui_error 'Helios safety validator is missing; refusing package changes.'
        return 1
    end
    ui_section '🔒' 'Helios machine safety validation'
    fish "$validator"
    or begin
        ui_error 'Helios safety validator failed.'
        return 1
    end
    return 0
end

# Read-only generated-Limine check. Must match the FIRST LTS entry rather
# than an older snapshot. sudo is used only after --apply confirmation.
function panda_setup_helios_limine_lts
    if test (hostname) != panda-helios
        return 0
    end
    set -l section (sudo grep -F -A 6 -m 1 'comment: kernel-id=linux-cachyos-lts' /boot/limine.conf 2>&1)
    if test $status -ne 0
        ui_error 'Cannot read generated Limine LTS entry; refusing to proceed.'
        return 1
    end
    set -l cmdlines (string match -r '^ *cmdline:.*' -- $section)
    if test (count $cmdlines) -ne 1
        ui_error 'Generated Limine LTS entry is missing an unambiguous cmdline.'
        return 1
    end
    set -l expected 'module_blacklist=nvidia,nvidia_drm,nvidia_modeset,nvidia_uvm,nouveau'
    if not string match -q "*$expected*" -- "$cmdlines[1]"
        ui_error 'Generated Limine LTS entry lost its NVIDIA hard blacklist.'
        return 1
    end
    ui_success 'Generated Limine LTS entry preserves NVIDIA isolation.'
end

# Return a hash only; do not modify the bootloader or filesystem.
function panda_setup_limine_hash
    set -l result (sudo sha256sum /boot/limine.conf 2>&1)
    if test $status -ne 0
        ui_error 'Cannot fingerprint generated Limine configuration.' >&2
        return 1
    end
    set -l fields (string split -n ' ' -- "$result")
    if test (count $fields) -lt 2; or not string match -qr '^[0-9a-f]{64}$' -- "$fields[1]"
        ui_error 'Unexpected generated Limine checksum output.' >&2
        return 1
    end
    echo "$fields[1]"
end

# Read-only launcher/runtime diagnostics. Noncritical GUI/runners are reported,
# not automatically started or downloaded; no attempt is made to sign in.
function panda_setup_smoke_gaming --argument-names gpu
    set -e argv[1]
    ui_section '🎮' 'Launcher and Vulkan diagnostics'
    if contains steam $argv
        if command -sq steam
            ui_success 'Steam executable is available.'
        else
            ui_warn 'Steam executable not on PATH; test from desktop launcher.'
        end
    end
    if contains other $argv
        if command -sq lutris
            ui_success 'Lutris executable is available.'
        else
            ui_warn 'Lutris executable not on PATH; test from desktop launcher.'
        end
        if python -c 'import google.protobuf' >/dev/null 2>&1
            ui_success 'Lutris Battle.net protobuf binding imports successfully.'
        else
            ui_warn 'Lutris Battle.net Python protobuf import failed.'
        end
    end
    if command -sq vulkaninfo
        set -l vk (vulkaninfo --summary 2>&1)
        if test $status -ne 0
            ui_warn 'vulkaninfo failed; investigate graphics runtime separately.'
        else if test "$gpu" = intel; and string match -qi '*Intel*' -- $vk
            ui_success 'Intel Vulkan physical device discovered.'
        else if test "$gpu" = amd; and string match -qi '*AMD*' -- $vk
            ui_success 'AMD Vulkan physical device discovered.'
        else
            ui_warn 'Vulkan ran but did not identify the selected GPU vendor.'
        end
    else
        ui_warn 'vulkaninfo unavailable; graphics runtime not exercised.'
    end
    return 0
end
