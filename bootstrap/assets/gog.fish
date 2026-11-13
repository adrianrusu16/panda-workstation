function gog --description 'Open Heroic Games Launcher'
    if not command -sq flatpak
        echo 'GOG requires Flatpak and the user-scoped Heroic Flatpak.' >&2
        return 1
    end
    if not command flatpak info --user com.heroicgameslauncher.hgl >/dev/null 2>&1
        echo 'GOG requires the user-scoped Heroic Flatpak.' >&2
        return 1
    end
    if not command -sq nohup; or not command -sq sh
        echo 'GOG requires nohup and sh to launch Heroic in the background.' >&2
        return 1
    end
    # Keep a diagnostic descriptor even when nohup redirects terminal stderr.
    command nohup sh -c '
        flatpak run --user com.heroicgameslauncher.hgl
        result=$?
        if [ "$result" -ne 0 ]; then
            printf "Heroic Flatpak exited with status %s. Diagnose with: flatpak run --user com.heroicgameslauncher.hgl\n" "$result" >&3
        fi
    ' </dev/null >/dev/null 3>&2 &
    set -l launcher $last_pid
    if not disown "$launcher" 2>/dev/null; and jobs -q "$launcher"
        echo 'Could not detach the Heroic launcher.' >&2
        return 1
    end
    return 0
end
