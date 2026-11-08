# Optional Workspace operations share the manager's result table.
function panda_shell_add_results
    for operation in configuration fisher fzf-fish ghostty kitty starship font fish-startup
        panda_setup_add_result "workspace/shell-$operation" Blocked 'stage not reached'
    end
end

function panda_shell_stage --argument-names repo_root mode
    if not command -sq python3
        if test "$mode" = plan
            ui_error 'Python 3 is required for safe shell path inspection before apply.'
        else
            ui_error 'Python 3 is required for shell-tools verification.'
        end
        return 127
    end
    if test "$mode" = plan
        set -g panda_shell_approved_plan (python3 -B "$repo_root/bootstrap/lib/shell_tools.py" plan 3>&1 1>&2)
        return $status
    end
    set -l results (python3 -B "$repo_root/bootstrap/lib/shell_tools.py" "$mode" "$panda_shell_approved_plan" 3>&1 1>&2)
    set -l result $status
    for record in $results
        set -l fields (string split -m 2 \t -- "$record")
        panda_setup_set_result "workspace/shell-$fields[1]" "$fields[2]" "$fields[3]"
    end
    return $result
end
