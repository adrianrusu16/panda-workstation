#!/usr/bin/env fish

set -l script_dir (path resolve (path dirname (status filename)))
set -l repo_root (path resolve "$script_dir/..")

source "$script_dir/lib/ui.fish"

set -l failed 0
set -l checked_scripts 0

ui_section '🐟' 'Fish syntax'

for script in (find "$repo_root/bootstrap" "$repo_root/machines" -type f -name '*.fish' | sort)
    set checked_scripts (math "$checked_scripts + 1")

    if not fish -n "$script"
        ui_error "Invalid Fish syntax: "(string replace "$repo_root/" '' "$script")
        set failed (math "$failed + 1")
    end
end

if test $failed -eq 0
    ui_success "$checked_scripts Fish scripts passed syntax validation"
end

ui_section '📦' 'Package manifests'

set -l seen_packages
set -l package_entries 0
set -l manifest_failures 0

for manifest in "$repo_root"/packages/*.txt
    set -l line_number 0

    while read -l line
        set line_number (math "$line_number + 1")
        set line (string trim -- "$line")

        if test -z "$line"
            continue
        end

        if string match -q '#*' -- "$line"
            continue
        end

        set package_entries (math "$package_entries + 1")

        if string match -qr '\s' -- "$line"
            ui_error "Invalid package entry in "(path basename "$manifest")":$line_number → $line"
            set manifest_failures (math "$manifest_failures + 1")
            continue
        end

        if contains -- "$line" $seen_packages
            ui_error "Duplicate package across manifests: $line"
            set manifest_failures (math "$manifest_failures + 1")
        else
            set -a seen_packages "$line"
        end
    end < "$manifest"
end

if test $manifest_failures -eq 0
    ui_success "$package_entries package entries validated"
else
    set failed (math "$failed + $manifest_failures")
end

ui_section '🔧' 'Bootstrap permissions'

set -l permission_failures 0

for script in "$repo_root"/bootstrap/*.fish
    if not test -x "$script"
        ui_error "Not executable: "(path basename "$script")
        set permission_failures (math "$permission_failures + 1")
    end
end

if test $permission_failures -eq 0
    ui_success 'All top-level bootstrap scripts are executable'
else
    set failed (math "$failed + $permission_failures")
end

echo

if test $failed -ne 0
    ui_error "Validation failed with $failed problem(s)"
    exit 1
end

ui_success 'Panda Workstation validation passed'
exit 0
