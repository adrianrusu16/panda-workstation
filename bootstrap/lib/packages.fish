#!/usr/bin/env fish

# Package helpers. ui.fish must be sourced before this file.

function install_manifest --argument-names manifest label
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

        set -a packages "$line"
    end < "$manifest"

    set -l total (count $packages)

    if test $total -eq 0
        ui_warn "No packages listed in $label"
        return 0
    end

    set -l already 0
    set -l missing

    for package in $packages
        if pacman -Q "$package" >/dev/null 2>&1
            set already (math "$already + 1")
        else
            set -a missing "$package"
        end
    end

    ui_success "$total packages discovered"
    ui_info "$already already installed · "(count $missing)" need installation"

    if test (count $missing) -gt 0
        echo
        ui_step 'Handing package installation to pacman'
        ui_info "Pacman's native progress bars stay visible."
        echo

        sudo pacman -S --needed $packages
        set -l pacman_status $status

        if test $pacman_status -ne 0
            echo
            ui_error "$label installation failed"
            return $pacman_status
        end

        echo
        ui_success "$label installation completed"
    else
        ui_success "$label is already fully installed"
    end

    ui_section '🔍' 'Package verification'

    set -l verified 0
    set -l failed

    for package in $packages
        if pacman -Q "$package" >/dev/null 2>&1
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
