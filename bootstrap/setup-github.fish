#!/usr/bin/env fish

set -l repo_root (path resolve (path dirname (status filename))/..)

echo "🐼 Panda Workstation — GitHub setup"
echo

# ─────────────────────────────────────────────
# Requirements
# ─────────────────────────────────────────────

for command_name in git gh
    if not command -q $command_name
        echo "❌ Missing required command: $command_name"
        echo "Run the core package bootstrap first."
        exit 1
    end
end

# ─────────────────────────────────────────────
# Git identity
# ─────────────────────────────────────────────

set -l existing_name (git config --global --get user.name 2>/dev/null)
set -l existing_email (git config --global --get user.email 2>/dev/null)

read -P "👤 Git commit name [$existing_name]: " git_name
if test -z "$git_name"
    set git_name "$existing_name"
end

read -P "✉️  Git commit email [$existing_email]: " git_email
if test -z "$git_email"
    set git_email "$existing_email"
end

if test -z "$git_name" -o -z "$git_email"
    echo "❌ Name and email are required."
    exit 1
end

mkdir -p ~/.config/git

printf "[user]\n    name = %s\n    email = %s\n" \
    "$git_name" \
    "$git_email" \
    > ~/.config/git/local.inc

chmod 600 ~/.config/git/local.inc

echo "✅ Git identity stored in ~/.config/git/local.inc"
echo "   This file remains machine-local and is not committed."
echo

# ─────────────────────────────────────────────
# GitHub CLI
# ─────────────────────────────────────────────

gh config set git_protocol ssh

if gh auth status --hostname github.com >/dev/null 2>&1
    set -l github_user (gh api user --jq .login 2>/dev/null)
    echo "✅ GitHub CLI already authenticated as: $github_user"
else
    echo "🔐 GitHub authentication required."
    echo "A browser/device login will be started."
    echo

    gh auth login \
        --hostname github.com \
        --git-protocol ssh \
        --web

    if test $status -ne 0
        echo "❌ GitHub authentication failed."
        exit 1
    end
end

echo
echo "🔍 Verifying GitHub connection..."

if gh auth status --hostname github.com
    set -l github_user (gh api user --jq .login 2>/dev/null)
    echo
    echo "✅ GitHub ready: @$github_user"
else
    echo "❌ GitHub authentication could not be verified."
    exit 1
end

echo
echo "🐼 Git + GitHub setup complete."
