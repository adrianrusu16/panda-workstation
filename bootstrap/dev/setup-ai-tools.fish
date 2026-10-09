#!/usr/bin/env fish

set -l script_dir (path resolve (path dirname (status filename)))
set -l repo_root (path resolve "$script_dir/../..")
source "$script_dir/../lib/ui.fish"

ui_section '🤖' 'AI development tools'

for tool in uv python
    if not command -q "$tool"
        ui_error "$tool is required; run the Development package stage first"
        exit 1
    end
end
uv --version; or exit 1

# Do not change system Python or create a project .python-version file.
set -l user_bin "$HOME/.local/bin"
mkdir -p "$user_bin"; or exit 1
fish_add_path -g "$user_bin"
if not command -q codex
    ui_error 'Codex CLI is missing. Install the official standalone release into ~/.local/bin, then rerun.'
    ui_info 'https://github.com/openai/codex/releases/latest (Linux: extract the matching archive and rename the binary to codex)'
    exit 1
end
python -B "$script_dir/ai_tools.py" codex-version; or exit 1

set -l fish_config "$HOME/.config/fish"
if set -q XDG_CONFIG_HOME; and test -n "$XDG_CONFIG_HOME"
    set fish_config "$XDG_CONFIG_HOME/fish"
end
set -l path_source "$repo_root/home/dot_config/fish/conf.d/panda-user-path.fish"
set -l path_target "$fish_config/conf.d/panda-user-path.fish"
mkdir -p (path dirname "$path_target"); or exit 1
if not test -f "$path_target"; or not cmp -s "$path_source" "$path_target"
    install -m 0644 "$path_source" "$path_target"; or exit 1
    ui_success 'Installed reproducible Fish user tool PATH'
else
    ui_success 'Fish user tool PATH already current'
end

set -l tool_dir (uv tool dir); or exit 1
set -l serena_python "$tool_dir/serena-agent/bin/python"
set -l serena_runtime
if test -x "$serena_python"
    set serena_runtime ("$serena_python" -I -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null)
end

if not command -q serena; or test "$serena_runtime" != 3.14
    set -l reinstall
    if test -d "$tool_dir/serena-agent"
        set reinstall --reinstall
    end
    ui_step 'Installing Serena as a uv tool with Python 3.14'
    uv tool install $reinstall --python 3.14 serena-agent; or exit 1
else
    ui_success 'Serena uv environment already uses Python 3.14'
end

if not command -q serena
    ui_error 'Serena is missing from ~/.local/bin after installation; check UV_TOOL_BIN_DIR'
    exit 1
end
set serena_runtime ("$serena_python" -I -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")'); or exit 1
if test "$serena_runtime" != 3.14
    ui_error 'Serena runtime must be Python 3.14'
    exit 1
end
if test (path resolve (command -s serena)) != (path resolve "$tool_dir/serena-agent/bin/serena")
    ui_error 'Serena on PATH does not belong to the verified uv environment; resolve the shadowed command first'
    exit 1
end
serena --version; or exit 1

set -l serena_home "$HOME/.serena"
if set -q SERENA_HOME; and test -n (string trim -- "$SERENA_HOME")
    set serena_home (string trim -- "$SERENA_HOME")
end
if not test -f "$serena_home/serena_config.yml"
    serena init; or exit 1
else
    ui_success 'Existing Serena initialization preserved'
end
if not "$serena_python" -I -c 'from serena.config.serena_config import SerenaConfig; SerenaConfig.from_config_file(generate_if_missing=False)' >/dev/null 2>&1
    ui_error 'Serena configuration could not be loaded; repair it before rerunning setup'
    exit 1
end
ui_success 'Serena configuration load verified'
python -B "$script_dir/ai_tools.py" setup-codex; or exit 1
python -B "$script_dir/ai_tools.py" verify-mcp; or exit 1

if not command -q graphify
    ui_step 'Installing Graphify CLI through uv (graphifyy)'
    uv tool install graphifyy; or exit 1
else
    ui_success 'Graphify already installed'
end
graphify --version; or exit 1
graphify --help >/dev/null; or exit 1

ui_success 'uv, Codex CLI, Serena and Graphify execution verified'
ui_info 'Graphify project integration is deferred; no install/integration command was run.'
ui_info 'Existing Codex hooks are preserved and are not managed by this bootstrap.'
exit 0
