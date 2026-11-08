#!/usr/bin/env fish
# Compatibility shortcut for the canonical Workspace shell-tools selection.
set -l script_dir (path resolve (path dirname (status filename)))
for argument in $argv
    if not contains -- "$argument" -h --help --dry-run --check --verify --apply --yes
        printf 'Unsupported shell-tools shortcut option: %s\n' "$argument" >&2
        exit 2
    end
end
exec fish --no-config "$script_dir/panda-setup.fish" --modules workspace --with-shell-tools $argv
