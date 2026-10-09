#!/usr/bin/env fish

# Repository-local previews/Phase 3A fixtures; live integration disabled until Phase 3B.
set -l script_dir (path resolve (path dirname (status filename)))

if not command -sq python3
    echo 'ERROR: Panda theme previews require Python 3.11+' >&2
    exit 1
end

command python3 -B "$script_dir/../cli.py" $argv
exit $status
