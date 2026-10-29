#!/usr/bin/env fish
# Convenience entrypoint: gaming only. --apply must be explicitly provided.
set -l root (path resolve (path dirname (status filename)))
fish "$root/panda-setup.fish" --modules gaming $argv
exit $status
