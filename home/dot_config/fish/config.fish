# CachyOS defaults
if test -r /usr/share/cachyos-fish-config/cachyos-config.fish
    source /usr/share/cachyos-fish-config/cachyos-config.fish
end

# Panda Workstation customizations
if test -f "$__fish_config_dir/panda.fish"
    source "$__fish_config_dir/panda.fish"
else if test -f "$HOME/.config/fish/panda.fish"
    source "$HOME/.config/fish/panda.fish"
end
