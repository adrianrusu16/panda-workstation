# 🐼 Panda Workstation — Fish configuration

# Workspace navigation
abbr -a ws "cd ~/Workspace"
abbr -a projects "cd ~/Workspace/projects"
abbr -a labs "cd ~/Workspace/labs"
abbr -a aosp "cd ~/Workspace/aosp"
abbr -a workstation "cd ~/Workspace/system/panda-workstation"

# Git
abbr -a g "git"
abbr -a gs "git status --short --branch"
abbr -a ga "git add"
abbr -a gc "git commit"
abbr -a gp "git push"
abbr -a gl "git log --oneline --graph --decorate -15"

# Useful CLI shortcuts
abbr -a ll "eza -lah --group-directories-first --icons=auto"
abbr -a lt "eza --tree --level=2 --group-directories-first --icons=auto"

# 🐼 Starship prompt — loaded after CachyOS defaults so it owns fish_prompt.
if status is-interactive; and command -q starship
    function starship_transient_prompt_func
        starship module character
    end

    starship init fish | source
    enable_transience
end
