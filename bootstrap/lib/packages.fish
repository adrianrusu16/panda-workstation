#!/usr/bin/env fish

# Package helpers. ui.fish must be sourced before this file.

# Return only a successfully retrieved and validated installed-name inventory.
# With -Qq, any nonzero status is an inventory failure, not package absence.
function panda_installed_inventory
    if not command -sq pacman
        ui_error 'pacman executable unavailable; package inventory refused' >&2
        return 127
    end
    set -l inventory (command pacman -Qq)
    set -l inventory_status $status
    if test $inventory_status -ne 0
        ui_error "Package inventory retrieval failed (exit $inventory_status)" >&2
        return $inventory_status
    end
    if test (count $inventory) -eq 0
        ui_error 'Empty package inventory refused' >&2
        return 1
    end
    set -l checked
    for package in $inventory
        if not string match -qr '^[a-z0-9][a-z0-9@+_.-]*$' -- "$package"
            ui_error 'Malformed package inventory refused' >&2
            return 1
        end
        if contains -- "$package" $checked
            ui_error 'Duplicate package inventory entry refused' >&2
            return 1
        end
        set -a checked "$package"
    end
    printf '%s\n' $checked
end

function install_manifest --argument-names manifest label mode
    if test (count $argv) -lt 2; or test (count $argv) -gt 3
        ui_error "Expected manifest, label and optional --dry-run"
        return 2
    end
    if test -n "$mode"; and test "$mode" != --dry-run
        ui_error "Unknown package mode: $mode"
        return 2
    end
    if not test -f "$manifest"
        ui_error "Missing package manifest: $manifest"
        return 1
    end

    set -l packages

    while read -l line
        set line (string trim -- "$line")

        if test -z "$line"
            continue
        end

        if string match -q '#*' -- "$line"
            continue
        end

        if not string match -qr '^[a-z0-9][a-z0-9@+_.-]*$' -- "$line"
            ui_error "Invalid package entry: $line"
            return 1
        end
        if contains -- "$line" $packages
            ui_error "Duplicate package entry: $line"
            return 1
        end

        set -a packages "$line"
    end < "$manifest"

    set -l total (count $packages)

    if test $total -eq 0
        ui_warn "No packages listed in $label"
        return 0
    end

    set -l installed (panda_installed_inventory)
    set -l inventory_status $status
    if test $inventory_status -ne 0
        return $inventory_status
    end
    set -l already 0
    set -l missing

    for package in $packages
        if contains -- "$package" $installed
            set already (math "$already + 1")
        else
            set -a missing "$package"
        end
    end

    ui_success "$total packages discovered"
    ui_info "$already already installed · "(count $missing)" need installation"

    if test "$mode" = --dry-run
        ui_info "dry-run: no packages installed"
        for package in $missing
            ui_info "Would install: $package"
        end
        return 0
    end

    if test (count $missing) -gt 0
        echo
        ui_step 'Handing package installation to pacman'
        ui_info "Pacman's native progress bars stay visible."
        echo

        sudo pacman -S --needed $missing
        set -l pacman_status $status

        if test $pacman_status -ne 0
            echo
            ui_error "$label installation failed"
            return $pacman_status
        end

        echo
        set installed (panda_installed_inventory)
        set inventory_status $status
        if test $inventory_status -ne 0
            return $inventory_status
        end
        ui_success "$label installation completed"
    else
        ui_success "$label is already fully installed"
    end

    ui_section '🔍' 'Package verification'

    set -l verified 0
    set -l failed

    for package in $packages
        if contains -- "$package" $installed
            set verified (math "$verified + 1")
        else
            set -a failed "$package"
        end
    end

    if test (count $failed) -gt 0
        for package in $failed
            ui_error "Missing package: $package"
        end
        return 1
    end

    ui_success "$verified/$total packages verified"
    return 0
end
