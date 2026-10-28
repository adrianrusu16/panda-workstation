#!/usr/bin/env fish
# Fish helpers for the opt-in Panda Setup Manager.

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
            if not pacman -Si "$line" >/dev/null 2>&1
                ui_error "Package not available in synchronized repositories: $line"
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
    if not pacman-conf --repo-list 2>/dev/null | string match -qx multilib
        ui_error 'Arch multilib is not enabled; refusing to modify pacman.conf automatically.'
        return 1
    end
end

function panda_setup_has_flathub
    if not command -sq flatpak
        return 1
    end
    flatpak remotes --user --columns=name 2>/dev/null | string match -qx flathub
end
