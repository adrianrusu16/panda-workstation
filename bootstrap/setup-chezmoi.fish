#!/usr/bin/env fish

set -l script_dir (path resolve (path dirname (status filename)))
set -l repo_root (path resolve "$script_dir/..")

source "$script_dir/lib/ui.fish"

ui_section '🏠' 'chezmoi source configuration'

if not command -q chezmoi
    ui_error 'chezmoi is not installed. Run the core package stage first.'
    exit 1
end

if not test -f "$repo_root/.chezmoiroot"
    ui_error 'Missing .chezmoiroot in the workstation repository.'
    exit 1
end

# Use this checkout explicitly, without replacing the user's source or settings.
ui_info "Source repository: $repo_root"
set -l destination (path normalize -- "$HOME")
set -l chezmoi_args --source "$repo_root" --destination "$destination"
if test "$PANDA_SETUP_SHELL_TOOLS" = 1
    # Do not run hooks or use target-mode overrides from another source.
    set -a chezmoi_args --config /dev/null --config-format toml --refresh-externals=never
end
set -l target_args
set -l changes
set -l gitconfig "$destination/.gitconfig"
set -l preserve_gitconfig 0
if test -e "$gitconfig"; or test -L "$gitconfig"
    # The portable Git config is a whole-file template. Replacing an existing
    # file here could erase the identity before the GitHub stage can reuse it.
    set preserve_gitconfig 1
    ui_info 'Existing ~/.gitconfig will be preserved.'
end
set -l scoped 0
if test $preserve_gitconfig -eq 1; or test "$PANDA_SETUP_SHELL_TOOLS" = 1
    set scoped 1
    set -l managed (chezmoi $chezmoi_args managed --path-style=absolute)
    or exit $status
    set -l home_prefix (string escape --style=regex -- "$destination/")
    set -l targets
    for target in $managed
        if not string match -qr -- "^$home_prefix" "$target"; or test (path normalize -- "$target") != "$target"
            ui_error 'Chezmoi returned a managed path outside the user home.'
            exit 1
        end
        if test "$target" = "$gitconfig"; and test $preserve_gitconfig -eq 1
            continue
        end
        if test "$PANDA_SETUP_SHELL_TOOLS" = 1
            set -l relative (string replace -- "$destination/" '' "$target")
            switch "$relative"
                case .config/fish '.config/fish/*' .config/ghostty '.config/ghostty/*' .config/kitty '.config/kitty/*' .config/starship.toml
                    continue
            end
        end
        set -a targets "$target"
    end
    if set -q targets[1]
        set target_args --recursive=false -- $targets
    end
end

ui_section '🔎' 'Dotfile preview'
if test $scoped -eq 0; or set -q target_args[1]
    set changes (chezmoi $chezmoi_args status $target_args)
    or begin
        set -l preview_status $status
        ui_error "chezmoi status failed (exit $preview_status)"
        exit $preview_status
    end
end
if test (count $changes) -eq 0
    ui_success 'Portable dotfiles already match'
    if test "$PANDA_SETUP_STAGE_REPORT" = 1
        echo already-satisfied >&3; or exit $status
    end
    exit 0
end
# Existing dotfiles can contain credentials. Show paths here and let the
# operator request the content diff in their own terminal if needed.
printf '%s\n' $changes
set -l diff_command (string join ' ' -- (string escape -- chezmoi $chezmoi_args diff $target_args))
ui_info "To inspect the full diff separately: $diff_command"

set -l answer
if isatty stdin
    fish_default_key_bindings
end
if not isatty stdin; or not read -P '  Apply these dotfile changes now? [y/N] ' answer; or not contains -- "$answer" y Y yes YES
    ui_skip 'Dotfile application skipped by user'
    if test "$PANDA_SETUP_STAGE_REPORT" = 1
        echo skipped >&3; or exit $status
        exit 0
    end
    exit 20
end

ui_section '⚙️' 'Applying portable configuration'
if test $preserve_gitconfig -eq 0
    if test -e "$gitconfig"; or test -L "$gitconfig"
        ui_error '~/.gitconfig appeared after the preview. Rerun to preserve it.'
        exit 1
    end
end
chezmoi $chezmoi_args apply $target_args
exit $status
