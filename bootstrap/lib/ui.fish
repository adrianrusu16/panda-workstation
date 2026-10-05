#!/usr/bin/env fish

# 🐼 Panda Workstation — shared terminal UI helpers.

function ui_line
    set_color brblack
    printf '%s\n' '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━'
    set_color normal
end

function ui_banner
    echo
    set_color --bold cyan
    printf '%s\n' \
        '╭──────────────────────────────────────────────────────────╮' \
        '│                    🐼 PANDA WORKSTATION                  │' \
        '│             CachyOS · Development · Gaming               │' \
        '╰──────────────────────────────────────────────────────────╯'
    set_color normal
    echo
end

function ui_chapter --argument-names icon title
    echo
    ui_line
    set_color --bold cyan
    printf '%s %s\n' "$icon" (string upper -- "$title")
    set_color normal
    ui_line
    echo
end

function ui_section --argument-names icon title
    echo
    set_color --bold brcyan
    printf '┌─ %s %s\n' "$icon" "$title"
    set_color normal
end

function ui_step
    set_color blue
    printf '  ➜ '
    set_color normal
    printf '%s\n' (string join ' ' $argv)
end

function ui_success
    set_color green
    printf '  ✅ '
    set_color normal
    printf '%s\n' (string join ' ' $argv)
end

function ui_info
    set_color cyan
    printf '  ℹ️  '
    set_color normal
    printf '%s\n' (string join ' ' $argv)
end

function ui_warn
    set_color yellow
    printf '  ⚠️  '
    set_color normal
    printf '%s\n' (string join ' ' $argv)
end

function ui_error
    set_color red
    printf '  ❌ '
    set_color normal
    printf '%s\n' (string join ' ' $argv)
end

function ui_skip
    set_color brblack
    printf '  ⏭️  '
    set_color normal
    printf '%s\n' (string join ' ' $argv)
end

function ui_progress --argument-names current total label
    if test "$total" -le 0
        return
    end

    set -l width 24
    set -l filled (math --scale=0 "floor(($current * $width) / $total)")
    set -l empty (math "$width - $filled")
    set -l percent (math --scale=0 "floor(($current * 100) / $total)")

    set -l filled_bar (string repeat -n $filled '█')
    set -l empty_bar (string repeat -n $empty '░')

    echo
    set_color --bold cyan
    printf 'Progress  '
    set_color green
    printf '%s' "$filled_bar"
    set_color brblack
    printf '%s' "$empty_bar"
    set_color normal
    printf '  %d/%d · %d%%' $current $total $percent

    if test -n "$label"
        printf ' · %s' "$label"
    end

    echo
end

function ui_spinner --argument-names message
    set -e argv[1]

    if test (count $argv) -eq 0
        ui_error 'Spinner called without a command'
        return 2
    end

    set -l logfile (mktemp)
    set -l frames '⠋' '⠙' '⠹' '⠸' '⠼' '⠴' '⠦' '⠧' '⠇' '⠏'

    command $argv >$logfile 2>&1 &
    set -l pid $last_pid
    set -l frame 1

    while kill -0 $pid 2>/dev/null
        set_color cyan
        printf '\r  %s ' $frames[$frame]
        set_color normal
        printf '%s' "$message"

        set frame (math "$frame + 1")
        if test $frame -gt (count $frames)
            set frame 1
        end

        sleep 0.08
    end

    wait $pid
    set -l code $status
    printf '\r\033[K'

    if test $code -eq 0
        ui_success "$message"
    else
        ui_error "$message"
        echo
        set_color brblack
        cat $logfile
        set_color normal
    end

    rm -f $logfile
    return $code
end

function ui_done
    echo
    ui_line
    set_color --bold green
    echo '🎉 Panda Workstation stage completed successfully.'
    set_color normal
    ui_line
    echo
end
