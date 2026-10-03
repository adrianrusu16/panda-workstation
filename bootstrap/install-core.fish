#!/usr/bin/env fish

set -l script_dir (path dirname (status filename))
set -l repo_root (path resolve "$script_dir/..")
set -l manifest "$repo_root/packages/core.txt"

if not test -f "$manifest"
    echo "Missing package manifest: $manifest"
    exit 1
end

set -l packages
while read -l line
    set line (string trim -- "$line")

    if test -z "$line"
        continue
    end

    if string match -qr "^#" -- "$line"
        continue
    end

    set -a packages "$line"
end < "$manifest"

if test (count $packages) -eq 0
    echo "No packages listed in $manifest"
    exit 0
end

echo "Installing core workstation packages..."
sudo pacman -S --needed $packages
