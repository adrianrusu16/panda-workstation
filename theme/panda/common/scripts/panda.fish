#!/usr/bin/env fish
# Repository-local command, not installed or automatically sourced.
set -l script_dir (path resolve (path dirname (status filename)))
if not command -sq python3
    echo 'ERROR: Panda requires Python 3.11+' >&2
    exit 1
end
command python3 -B "$script_dir/../shell.py" panda $argv
exit $status
