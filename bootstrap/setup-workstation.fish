#!/usr/bin/env fish

set -l script_dir (path resolve (path dirname (status filename)))
source "$script_dir/lib/ui.fish"

set -l stages \
    'core|install-core.fish|📦|Core packages|required' \
    'machine|setup-machine.fish|💻|Machine profile|required' \
    'chezmoi|setup-chezmoi.fish|🏠|Portable configuration|required' \
    'github|setup-github.fish|🔐|Git & GitHub|required' \
    'desktop|install-desktop.fish|🖥️|Desktop & applications|required' \
    'plugins|setup-plugins.fish|🧩|Plugins & integrations|required' \
    'development|setup-development.fish|🧪|Development environment|required' \
    'gaming|setup-gaming.fish|🎮|Gaming|planned' \
    'panda|setup-panda.fish|🐼|Panda experience|planned' \
    'validate|validate.fish|✅|Final validation|required'

set -l total (count $stages)

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

        if test -f "$path"
            ui_success "$index. $icon $title · $script"
        else if test "$availability" = 'planned'
            ui_skip "$index. $icon $title · planned"
        else
            ui_error "$index. $icon $title · required module missing"
        end
    end
end

if test (count $argv) -gt 0
    switch $argv[1]
        case '--list'
            print_stage_list "$script_dir" $stages
            exit 0

        case '--help' '-h'
            ui_banner
            echo 'Usage:'
            echo '  ./bootstrap/setup-workstation.fish'
            echo '  ./bootstrap/setup-workstation.fish --list'
            echo '  ./bootstrap/setup-workstation.fish --help'
            exit 0

        case '*'
            ui_error "Unknown argument: $argv[1]"
            exit 2
    end
end

ui_banner

set -l results
set -l durations

for index in (seq $total)
    set -a results 'PENDING'
    set -a durations '—'
end

ui_section '🧭' 'Environment'
ui_info "Host: "(hostname)
ui_info "User: "(whoami)
ui_info "Kernel: "(uname -r)
ui_info "Declared stages: $total"

ui_progress 0 $total 'Starting'

set -l stop_after_failure 0

for current in (seq $total)
    set -l fields (string split '|' -- "$stages[$current]")
    set -l script $fields[2]
    set -l icon $fields[3]
    set -l title $fields[4]
    set -l availability $fields[5]
    set -l path "$script_dir/$script"

    if test $stop_after_failure -eq 1
        if test -f "$path"
            set results[$current] 'BLOCKED'
        else
            set results[$current] 'PENDING'
        end
        continue
    end

    ui_chapter "$icon" "Chapter $current/$total · $title"

    if not test -f "$path"
        if test "$availability" = 'planned'
            ui_skip "$script has not been implemented yet"
            set results[$current] 'PENDING'
            continue
        end

        ui_error "Required setup module is missing: $script"
        set results[$current] 'FAILED'
        set stop_after_failure 1
        continue
    end

    if not test -x "$path"
        ui_warn "$script is not executable"
        ui_step 'Adding executable permission'
        chmod +x "$path"

        if test $status -eq 0
            ui_success 'Executable permission added'
        else
            ui_error "Could not make $script executable"
            set results[$current] 'FAILED'
            set stop_after_failure 1
            continue
        end
    end

    set -l started (date +%s)

    "$path"
    set -l result $status

    set -l ended (date +%s)
    set -l elapsed (math "$ended - $started")
    set durations[$current] "$elapsed"s

    switch $result
        case 0
            set results[$current] 'SUCCESS'
            ui_success "$title completed"

        case 20
            set results[$current] 'SKIPPED'
            ui_skip "$title skipped"

        case '*'
            set results[$current] 'FAILED'
            ui_error "$title failed with exit code $result"
            ui_warn 'Remaining implemented stages will be marked blocked.'
            set stop_after_failure 1
    end

    set -l success_now (count (string match 'SUCCESS' $results))
    ui_progress $success_now $total "$title"
end

set -l success_count (count (string match 'SUCCESS' $results))
set -l failed_count (count (string match 'FAILED' $results))
set -l skipped_count (count (string match 'SKIPPED' $results))
set -l pending_count (count (string match 'PENDING' $results))
set -l blocked_count (count (string match 'BLOCKED' $results))
set -l percent (math --scale=0 "floor(($success_count * 100) / $total)")

ui_chapter '📊' 'Final setup report'

set_color --bold cyan
printf '%s\n' \
    '╭────┬──────────────────────────────┬──────────────┬──────────╮' \
    '│ #  │ Stage                        │ Result       │ Time     │' \
    '├────┼──────────────────────────────┼──────────────┼──────────┤'
set_color normal

for index in (seq $total)
    set -l fields (string split '|' -- "$stages[$index]")
    set -l icon $fields[3]
    set -l title $fields[4]
    set -l result_label

    switch $results[$index]
        case SUCCESS
            set_color green
            set result_label '✅ done'
        case FAILED
            set_color red
            set result_label '❌ failed'
        case SKIPPED
            set_color yellow
            set result_label '⏭ skipped'
        case BLOCKED
            set_color red
            set result_label '🛑 blocked'
        case '*'
            set_color brblack
            set result_label '⏳ pending'
    end

    printf '│ %-2s │ %-28s │ %-12s │ %8s │\n' \
        "$index" \
        "$icon $title" \
        "$result_label" \
        "$durations[$index]"

    set_color normal
end

set_color --bold cyan
printf '%s\n' '╰────┴──────────────────────────────┴──────────────┴──────────╯'
set_color normal

ui_progress $success_count $total 'roadmap complete'

echo
set_color green
printf '  ✅ Done: %-2d' $success_count
set_color normal

set_color red
printf '   ❌ Failed: %-2d' $failed_count
set_color normal

set_color yellow
printf '   ⏭ Skipped: %-2d' $skipped_count
set_color normal

set_color brblack
printf '   ⏳ Pending: %-2d' $pending_count
set_color normal

set_color red
printf '   🛑 Blocked: %-2d\n' $blocked_count
set_color normal

echo

if test $failed_count -gt 0
    ui_line
    set_color --bold red
    echo '💥 PANDA WORKSTATION SETUP INCOMPLETE'
    set_color normal
    ui_line
    ui_error "$failed_count stage(s) failed"
    ui_info "$percent% of the declared workstation roadmap is complete"
    echo
    exit 1
end

if test $pending_count -gt 0 -o $skipped_count -gt 0
    ui_line
    set_color --bold yellow
    echo '🐼 PANDA WORKSTATION · CURRENT STAGE COMPLETE'
    set_color normal
    ui_line
    ui_success 'All currently implemented stages completed without failure'
    ui_info "$percent% of the declared workstation roadmap is complete"

    if test $pending_count -gt 0
        ui_info "$pending_count future stage(s) remain to be implemented"
    end

    echo
    exit 0
end

ui_line
set_color --bold green
echo '🎉 PANDA WORKSTATION SETUP COMPLETE'
set_color normal
ui_line
ui_success 'Every declared setup stage completed successfully'
ui_info '100% complete'
echo
