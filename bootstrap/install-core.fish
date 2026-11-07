#!/usr/bin/env fish

set -l script_dir (path resolve (path dirname (status filename)))
set -l repo_root (path resolve "$script_dir/..")

source "$script_dir/lib/ui.fish"
source "$script_dir/lib/packages.fish"

ui_section '📦' 'Core package layer'
install_manifest "$repo_root/packages/core.txt" 'Core packages' $PANDA_SETUP_PACKAGE_MODE
exit $status
