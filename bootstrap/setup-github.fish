#!/usr/bin/env fish

set -l script_dir (path resolve (path dirname (status filename)))

source "$script_dir/lib/ui.fish"

ui_section '🔍' 'GitHub preflight'

for command_name in git gh
    if not command -q $command_name
        ui_error "Missing required command: $command_name"
        ui_info 'Run the core package stage first.'
        exit 1
    end

    ui_success "$command_name detected"
end

ui_section '👤' 'Git commit identity'
ui_info 'Identity is stored locally and is never committed to panda-workstation.'

set -l existing_name (git config --global --get user.name 2>/dev/null)
set -l existing_email (git config --global --get user.email 2>/dev/null)

read -P "  Git commit name [$existing_name]: " git_name
if test -z "$git_name"
    set git_name "$existing_name"
end

read -P "  Git commit email [$existing_email]: " git_email
if test -z "$git_email"
    set git_email "$existing_email"
end

if test -z "$git_name" -o -z "$git_email"
    ui_error 'Git name and email are required.'
    exit 1
end

mkdir -p ~/.config/git

printf '[user]\n    name = %s\n    email = %s\n' \
    "$git_name" \
    "$git_email" \
    > ~/.config/git/local.inc

chmod 600 ~/.config/git/local.inc

ui_success 'Git identity written to ~/.config/git/local.inc'

ui_section '🔐' 'GitHub CLI authentication'

gh config set git_protocol ssh
if test $status -ne 0
    ui_error 'Could not set GitHub CLI protocol to SSH.'
    exit 1
end

ui_success 'GitHub Git protocol set to SSH'

if gh auth status --hostname github.com >/dev/null 2>&1
    set -l github_user (gh api user --jq .login 2>/dev/null)

    if test -n "$github_user"
        ui_success "Already authenticated as @$github_user"
    else
        ui_success 'GitHub CLI authentication is active'
    end
else
    ui_warn 'GitHub authentication is required.'
    ui_info 'GitHub CLI will open the secure browser/device login flow.'
    ui_info 'No GitHub password or token is stored by this script.'
    echo

    gh auth login \
        --hostname github.com \
        --git-protocol ssh \
        --web

    set -l auth_status $status

    if test $auth_status -ne 0
        ui_error 'GitHub authentication failed.'
        exit $auth_status
    end
end

ui_section '✅' 'GitHub verification'

if not gh auth status --hostname github.com >/dev/null 2>&1
    ui_error 'GitHub authentication could not be verified.'
    exit 1
end

set -l github_user (gh api user --jq .login 2>/dev/null)

if test -n "$github_user"
    ui_success "GitHub ready: @$github_user"
else
    ui_success 'GitHub CLI authenticated'
end

ui_success 'Git + GitHub setup complete'
exit 0
