#!/usr/bin/env fish
# Read-only palette/schema validation. No theme application or runtime state.
set -l script_dir (path resolve (path dirname (status filename)))
if not command -q python3
    printf '%s\n' 'Python 3.11+ is required for TOML palette validation.' >&2
    exit 1
end
command python3 -B "$script_dir/../palette.py" $argv
exit $status
