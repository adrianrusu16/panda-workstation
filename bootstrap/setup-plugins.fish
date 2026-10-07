#!/usr/bin/env fish

set -l script_dir (path resolve (path dirname (status filename)))
set -l repo_root (path resolve "$script_dir/..")

source "$script_dir/lib/ui.fish"
source "$script_dir/lib/packages.fish"

set -l fisher_version '4.4.8'
set -l fisher_commit 'a04308be92daa6cfecdbb0ca58b1e8508664cff2'
set -l fzf_fish_version 'v11.0'

ui_section '🧩' 'Shell & terminal packages'
install_manifest "$repo_root/packages/plugins.txt" 'Shell & terminal packages'
set -l package_status $status
if test $package_status -ne 0
    exit $package_status
end

ui_section '🏠' 'Portable terminal configuration'
if not command -q chezmoi
    ui_error 'chezmoi is required to apply the tracked shell/terminal configuration'
    exit 1
end

ui_spinner 'Applying tracked shell and terminal configuration' chezmoi apply
if test $status -ne 0
    exit $status
end

ui_success 'Starship, Ghostty, Kitty and Fisher manifests applied'

ui_section '🐟' 'Fisher plugin manager'

if not functions -q fisher
    if test -f "$HOME/.config/fish/functions/fisher.fish"
        source "$HOME/.config/fish/functions/fisher.fish"
    end
end

if not functions -q fisher
    set -l bootstrap_url "https://raw.githubusercontent.com/jorgebucaran/fisher/$fisher_commit/functions/fisher.fish"
    set -l bootstrap_file (mktemp)

    ui_step "Bootstrapping Fisher $fisher_version from pinned commit"
    curl --fail --location --silent --show-error "$bootstrap_url" --output "$bootstrap_file"; or begin
        rm -f "$bootstrap_file"
        ui_error 'Could not download Fisher bootstrap function'
        exit 1
    end

    source "$bootstrap_file"
    rm -f "$bootstrap_file"
end

if not functions -q fisher
    ui_error 'Fisher bootstrap completed but the fisher function is unavailable'
    exit 1
end

ui_step 'Reconciling pinned Fish plugins from fish_plugins'
fisher update; or begin
    ui_error 'Fisher plugin reconciliation failed'
    exit 1
end

ui_success 'Fisher plugin set reconciled'

ui_section '⭐' 'Starship validation'
if not command -q starship
    ui_error 'starship is not available after package installation'
    exit 1
end

set -lx STARSHIP_CONFIG "$HOME/.config/starship.toml"
starship prompt >/dev/null; or begin
    ui_error 'Starship could not render the Panda prompt configuration'
    exit 1
end
ui_success 'Starship Panda prompt rendered successfully'

ui_section '🔤' 'Font validation'
set -l font_match (fc-match 'JetBrainsMono Nerd Font Mono' family 2>/dev/null | string collect)
if string match -qi '*JetBrainsMono*' -- "$font_match"
    ui_success "JetBrainsMono Nerd Font available: $font_match"
else
    ui_error 'JetBrainsMono Nerd Font Mono was not resolved by fontconfig'
    exit 1
end

ui_section '👻' 'Ghostty validation'
if not command -q ghostty
    ui_error 'ghostty is not available after package installation'
    exit 1
end

ghostty +show-config >/dev/null 2>&1; or begin
    ui_error 'Ghostty rejected its configuration'
    exit 1
end
ui_success 'Ghostty configuration parsed successfully'

ui_section '🐱' 'Kitty validation'
if not command -q kitty
    ui_error 'kitty is not available after package installation'
    exit 1
end

if not test -s "$HOME/.config/kitty/kitty.conf"
    ui_error 'Kitty configuration is missing'
    exit 1
end
ui_success 'Kitty executable and configuration detected'

ui_section '🔍' 'Integration verification'
set -l failed 0

for command_name in starship ghostty kitty fzf
    if command -q "$command_name"
        ui_success "$command_name · "(command -v "$command_name")
    else
        ui_error "$command_name is missing from PATH"
        set failed (math "$failed + 1")
    end
end

set -l fisher_version_output (fisher --version 2>/dev/null | string collect)
if string match -q "*version $fisher_version*" -- "$fisher_version_output"
    ui_success "Fisher $fisher_version available"
else
    ui_error "Unexpected Fisher version: $fisher_version_output"
    set failed (math "$failed + 1")
end

set -l fisher_plugins (fisher list 2>/dev/null | string join ' ')
if string match -qi '*patrickf1/fzf.fish@v11.0*' -- "$fisher_plugins"
    ui_success "fzf.fish $fzf_fish_version installed"
else
    ui_error "fzf.fish $fzf_fish_version not reported by Fisher"
    set failed (math "$failed + 1")
end

if test $failed -gt 0
    ui_error "Shell/terminal integration validation failed with $failed problem(s)"
    exit 1
end

ui_info 'Konsole remains installed as the known-safe KDE fallback'
ui_info 'Ghostty and Kitty are both configured for an equal trial'
ui_info 'Trial checklist: docs/terminal-trial.md'

ui_done
exit 0
