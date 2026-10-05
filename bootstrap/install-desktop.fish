#!/usr/bin/env fish

set -l script_dir (path resolve (path dirname (status filename)))
set -l repo_root (path resolve "$script_dir/..")

source "$script_dir/lib/ui.fish"
source "$script_dir/lib/packages.fish"

ui_section '🖥️' 'Desktop package layer'
install_manifest "$repo_root/packages/desktop.txt" 'Desktop packages'
exit $status
