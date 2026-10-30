#!/usr/bin/env fish
# Package shortcut only. VM probing, media and lifecycle remain explicit.
set -l script_dir (path resolve (path dirname (status filename)))
set -l manager_args $argv
argparse 'help' 'dry-run' 'check' 'verify' 'apply' 'yes' -- $argv
or exit 2
if test (count $argv) -gt 0
    echo 'Unexpected positional arguments' >&2
    exit 2
end
if set -q _flag_help
    echo 'Usage: fish bootstrap/setup-virtualization.fish [--dry-run | --check | --verify | --apply [--yes]]'
    echo 'Default: package preview. Apply uses Panda Setup Manager confirmation and safety gates.'
    echo 'Audit Lab preview: python virtualization/audit_lab.py plan'
    exit 0
end
fish --no-config "$script_dir/panda-setup.fish" --modules virtualization $manager_args
exit $status
