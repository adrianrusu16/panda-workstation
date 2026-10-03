#!/usr/bin/env fish

set -l repo_root (path resolve (path dirname (status filename))/..)
set -l failed 0

echo "🐟 Checking Fish syntax..."
for script in $repo_root/**/*.fish
    if not fish -n "$script"
        echo "❌ Invalid Fish syntax: $script"
        set failed 1
    end
end

echo "📦 Checking package manifests..."
set -l seen_packages

for manifest in $repo_root/packages/*.txt
    set -l line_number 0

    while read -l line
        set line_number (math $line_number + 1)
        set line (string trim -- "$line")

        if test -z "$line"
            continue
        end

        if string match -q "#*" -- "$line"
            continue
        end

        if string match -qr "\s" -- "$line"
            echo "❌ Invalid package entry in $manifest:$line_number → $line"
            set failed 1
            continue
        end

        if contains -- "$line" $seen_packages
            echo "❌ Duplicate package across manifests: $line"
            set failed 1
        else
            set -a seen_packages "$line"
        end
    end < "$manifest"
end

echo "🔧 Checking bootstrap permissions..."
for script in $repo_root/bootstrap/*.fish
    if not test -x "$script"
        echo "❌ Bootstrap script is not executable: $script"
        set failed 1
    end
end

if test $failed -ne 0
    echo "❌ Validation failed."
    exit 1
end

echo "✅ Panda Workstation validation passed."
