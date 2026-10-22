#!/usr/bin/env fish

set -l script_dir (path resolve (path dirname (status filename)))
set -l repo_root (path resolve "$script_dir/..")

source "$script_dir/lib/ui.fish"
source "$script_dir/lib/packages.fish"

argparse 'dry-run' 'profile=' -- $argv; or exit 2
if test (count $argv) -gt 0
    ui_error "Unexpected desktop installer arguments"
    exit 2
end
# Explicit target eligibility; do not infer it from a running session.
set -l desktop_profile "$PANDA_DESKTOP_PROFILE"
if set -q _flag_profile
    set desktop_profile "$_flag_profile"
    if test "$desktop_profile" != plasma
        ui_error 'Only the explicitly selected plasma desktop profile is supported'
        exit 2
    end
end
if test -n "$desktop_profile"; and test "$desktop_profile" != plasma
    ui_error 'Unsupported PANDA_DESKTOP_PROFILE'
    exit 2
end
if not set -q _flag_dry_run; and test "$desktop_profile" != plasma
    ui_error 'Select --profile plasma or export PANDA_DESKTOP_PROFILE=plasma before installation'
    exit 2
end

set -l package_mode
if set -q _flag_dry_run
    set package_mode --dry-run
end

ui_section '🖥️' 'Desktop package layer'
install_manifest "$repo_root/packages/desktop.txt" 'Desktop packages' $package_mode
exit $status
