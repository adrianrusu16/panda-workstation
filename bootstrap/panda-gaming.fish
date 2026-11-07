#!/usr/bin/env fish
# Convenience entrypoint: gaming only. --apply must be explicitly provided.
set -l root (path resolve (path dirname (status filename)))
set -lx PANDA_SETUP_GAMING_ONLY 1
exec fish --no-config "$root/panda-setup.fish" --modules gaming $argv
