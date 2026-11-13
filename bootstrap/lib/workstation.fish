function panda_setup_chatgpt_inventory
    command -sq pacman; and pacman -Q chatgpt-bin
    and test -x /usr/bin/chatgpt
    and test -r /usr/share/applications/chatgpt.desktop
    or begin
        ui_info 'ChatGPT Desktop inventory incomplete. See docs/chatgpt-desktop.md for the separate manual installation workflow.'
        return 1
    end
    ui_success 'ChatGPT Desktop package, executable and KDE entry found.'
end

function panda_setup_gog_launchers --argument-names assets mode
    set -l config "$HOME/.config"
    set -l data "$HOME/.local/share"
    test -n "$XDG_CONFIG_HOME"; and set config "$XDG_CONFIG_HOME"
    test -n "$XDG_DATA_HOME"; and set data "$XDG_DATA_HOME"
    set data (string replace -r '/+$' '' -- "$data")
    set config (string replace -r '/+$' '' -- "$config")
    if not string match -q '/*' -- "$config"; or not string match -q '/*' -- "$data"
        ui_error 'Launcher roots must be absolute, non-root paths and require manual review.'
        return 1
    end
    set -l desktop "$data/applications/panda-gog-heroic.desktop"
    set -l shortcut "$config/fish/functions/gog.fish"

    set -l result 0
    for target in "$desktop" "$shortcut"
        set -l directory (path dirname -- "$target")
        if not panda_setup_launcher_directory_safe "$directory"
            ui_error "Launcher directory requires manual review: $directory"
            set result 1
            continue
        end
        set -l source "$assets/"(path basename -- "$target")
        if test "$target" = "$shortcut"
            set -l executable (command -s gog)
            if set -q executable[1]
                ui_error "Conflicting gog command requires manual review: $executable"
                set result 1
                continue
            end
            if functions -q gog
                set -l origin (functions --details gog)
                if test "$origin" != "$shortcut"
                    ui_error "Conflicting gog function requires manual review: $origin (expected $shortcut)"
                    set result 1
                    continue
                end
            end
        end
        if test -e "$target"; or test -L "$target"
            if not panda_setup_launcher_matches "$source" "$target"
                ui_error "Launcher requires manual review: $target"
                set result 1
            end
            continue
        end
        if test "$mode" = verify
            ui_error "Missing launcher: $target"
            set result 1
            continue
        end
        mkdir -p -- "$directory"; or return $status
        if not panda_setup_launcher_directory_safe "$directory"
            ui_error "Launcher directory requires manual review: $directory"
            set result 1
            continue
        end
        set -l temporary (mktemp -- "$directory/.panda-gog.XXXXXXXX"); or return $status
        cp -- "$source" "$temporary"; and ln -T -- "$temporary" "$target" 2>/dev/null
        set -l publish_status $status
        rm -- "$temporary"; or return $status
        if test $publish_status -ne 0; and not panda_setup_launcher_matches "$source" "$target"
            ui_error "Could not publish launcher. Destination requires manual review: $target"
            set result 1
        end
    end
    return $result
end

function panda_setup_launcher_matches --argument-names source target
    test ! -L "$target"; and test -f "$target"; and cmp -s -- "$source" "$target"
end

function panda_setup_launcher_directory_safe --argument-names directory
    set -l lexical (realpath -ms -- "$directory"); or return 1
    set -l resolved (realpath -m -- "$directory"); or return 1
    test "$directory" = "$lexical"; and test "$resolved" = "$lexical"
end
