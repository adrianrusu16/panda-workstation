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

if not isatty stdin
    ui_error 'GitHub setup needs a terminal for identity and browser login.'
    exit 1
end

ui_section '👤' 'Git commit identity'
ui_info 'Identity is stored locally and is never committed to panda-workstation.'

set -l identity "$HOME/.config/git/local.inc"
set -l git_name (git config --global --includes --get user.name)
set -l git_email (git config --global --includes --get user.email)
set -l identity_created 0
if test -n "$git_name"; and test -n "$git_email"
    ui_success 'Existing effective Git identity preserved.'
else
    set -l includes (git config --global --includes --path --get-all include.path)
    if not contains -- "$identity" $includes
        ui_warn 'Apply the portable Git config or configure a global Git identity before GitHub setup.'
        if test "$PANDA_SETUP_STAGE_REPORT" = 1
            echo needs-git-identity >&3; or exit $status
            exit 0
        end
        exit 1
    end
    if test -e "$identity"; or test -L "$identity"
        ui_error 'Review the existing ~/.config/git/local.inc; Git does not resolve a complete identity from it.'
        exit 1
    end
    if test -z "$git_name"; or test -z "$git_email"
        ui_prepare_terminal_read; or exit $status
    end
    if test -z "$git_name"
        read -P '  Git commit name: ' git_name; or exit $status
    end
    if test -z "$git_email"
        read -P '  Git commit email: ' git_email; or exit $status
    end
    if test -z "$git_name"; or test -z "$git_email"
        ui_error 'Git name and email are required.'
        exit 1
    end
    mkdir -p (path dirname -- "$identity")
    or exit $status
    set -l temporary (mktemp "$identity.XXXXXX")
    or exit $status
    git config --file "$temporary" user.name "$git_name"
    and git config --file "$temporary" user.email "$git_email"
    and ln -T -- "$temporary" "$identity"
    set -l write_status $status
    rm -f -- "$temporary"
    if test $write_status -ne 0
        ui_error 'Could not create the local Git identity.'
        exit $write_status
    end
    git config --global --includes --get user.name >/dev/null
    and git config --global --includes --get user.email >/dev/null
    or begin
        set -l verify_status $status
        ui_error 'Local Git identity was created, but Git cannot load it. Review the global include.'
        exit $verify_status
    end
    set identity_created 1
    ui_success 'Git identity written to ~/.config/git/local.inc and loaded by Git.'
end

ui_section '🔐' 'GitHub CLI authentication'
if gh auth status --hostname github.com >/dev/null 2>&1
    ui_success 'GitHub CLI authentication is already active.'
    if test $identity_created -eq 0; and test "$PANDA_SETUP_STAGE_REPORT" = 1
        echo already-satisfied >&3; or exit $status
    end
    exit 0
end
ui_info 'GitHub CLI will open its browser login flow.'
gh auth login --hostname github.com --git-protocol ssh --web
set -l auth_status $status
if test $auth_status -ne 0
    ui_error "GitHub authentication failed (exit $auth_status)."
    exit $auth_status
end

gh auth status --hostname github.com >/dev/null 2>&1
set -l auth_status $status
if test $auth_status -ne 0
    ui_error "GitHub authentication could not be verified (exit $auth_status)."
    exit $auth_status
end
ui_success 'GitHub CLI authenticated.'
exit 0
