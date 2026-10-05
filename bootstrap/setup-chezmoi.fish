#!/usr/bin/env fish

set -l script_dir (path resolve (path dirname (status filename)))
set -l repo_root (path resolve "$script_dir/..")

source "$script_dir/lib/ui.fish"

ui_section '🏠' 'chezmoi source configuration'

if not command -q chezmoi
    ui_error 'chezmoi is not installed. Run the core package stage first.'
    exit 1
end

if not test -f "$repo_root/.chezmoiroot"
    ui_error 'Missing .chezmoiroot in the workstation repository.'
    exit 1
end

mkdir -p ~/.config/chezmoi

printf 'sourceDir = "%s"\n' "$repo_root" > ~/.config/chezmoi/chezmoi.toml
chmod 600 ~/.config/chezmoi/chezmoi.toml

ui_success 'chezmoi source directory configured'
ui_info "Source repository: $repo_root"

ui_section '🔎' 'Dotfile preview'
ui_step 'Showing proposed changes'

chezmoi diff
set -l diff_status $status

if test $diff_status -ne 0
    ui_error 'chezmoi diff failed'
    exit $diff_status
end

echo
read -l -P '  Apply these dotfile changes now? [Y/n] ' answer

if test -n "$answer"
    if not string match -qi 'y*' -- "$answer"
        ui_skip 'Dotfile application skipped by user'
        exit 20
    end
end

ui_section '⚙️' 'Applying portable configuration'

ui_spinner 'Applying chezmoi configuration' chezmoi apply
set -l apply_status $status

if test $apply_status -ne 0
    exit $apply_status
end

ui_success 'Portable home configuration applied'
exit 0
