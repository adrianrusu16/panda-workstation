#!/usr/bin/env fish
# D4A: explicit fixture input; no native apply/install entry point.
set -l script_dir (path resolve (path dirname (status filename)))
python3 -B "$script_dir/../desktop_cli.py" $argv
exit $status
