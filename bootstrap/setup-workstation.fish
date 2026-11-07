#!/usr/bin/env fish

set -l script_dir (path resolve (path dirname (status filename)))
source "$script_dir/lib/ui.fish"

set -l stages \
    'core|install-core.fish|📦|Core packages|required' \
    'machine|setup-machine.fish|💻|Machine profile|gated' \
    'chezmoi|setup-chezmoi.fish|🏠|Portable configuration|required' \
    'github|setup-github.fish|🔐|Git & GitHub|required' \
    'desktop|install-desktop.fish|🖥️|Desktop & applications|required' \
    'plugins|setup-plugins.fish|🧩|Plugins & integrations|required' \
    'development|setup-development.fish|🧪|Development environment|required' \
    'gaming|setup-gaming.fish|🎮|Gaming|planned' \
    'panda|setup-panda.fish|🐼|Panda experience|planned' \
    'validate|validate.fish|✅|Final validation|required'

function print_stage_list
    set -l root "$argv[1]"
    set -e argv[1]

    set -l stage_rows $argv
    set -l stage_total (count $stage_rows)

    ui_banner
    ui_chapter '🧭' 'Declared workstation stages'

    for index in (seq $stage_total)
        set -l fields (string split '|' -- "$stage_rows[$index]")
        set -l script $fields[2]
        set -l icon $fields[3]
        set -l title $fields[4]
        set -l availability $fields[5]
        set -l path "$root/$script"

        if test "$availability" = gated
            ui_skip "$index. $icon $title · separate authorization required"
        else if test -f "$path"
            ui_success "$index. $icon $title · $script"
        else if test "$availability" = 'planned'
            ui_skip "$index. $icon $title · planned"
        else
            ui_error "$index. $icon $title · required module missing"
        end
    end
end

switch "$argv[1]"
    case --list
        if test (count $argv) -eq 1
            print_stage_list "$script_dir" $stages
            exit 0
        end
    case --help -h
        if test (count $argv) -eq 1
            echo 'Legacy entrypoint: --list, --help, or an explicit --dry-run, --check, or --verify followed by selection options.'
            echo 'For installation, review the plan with fish bootstrap/panda-setup.fish.'
            exit 0
        end
    case --dry-run --check --verify
        set -lx PANDA_SETUP_READ_ONLY 1
        exec fish --no-config "$script_dir/panda-setup.fish" $argv
end
ui_error 'Legacy execution is disabled. Use fish bootstrap/panda-setup.fish to review and apply a module plan.'
exit 2
