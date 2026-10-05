#!/usr/bin/env fish

set -l script_dir (path resolve (path dirname (status filename)))
set -l repo_root (path resolve "$script_dir/..")

source "$script_dir/lib/ui.fish"
source "$script_dir/lib/packages.fish"

set -l fish_lsp_version '1.1.5'
set -l fish_lsp_sha256 'b6bbe28d497b22abaad7a3ffe4e315a728bfd1a80c6c2d9ccbf444d2d1884529'
set -l fish_lsp_url "https://github.com/ndonfris/fish-lsp/releases/download/v$fish_lsp_version/fish-lsp.standalone"
set -l fish_lsp_path '/usr/local/bin/fish-lsp'
set -l completions_dir "$HOME/.config/fish/completions"
set -l completions_file "$completions_dir/fish-lsp.fish"

ui_section '🧪' 'Development package layer'

if pacman -Q rust >/dev/null 2>&1; and not pacman -Q rustup >/dev/null 2>&1
    ui_error 'The Arch rust package is installed, but Panda Workstation standardizes on rustup.'
    ui_info 'Resolve the rust/rustup package conflict before rerunning this stage.'
    exit 1
end

install_manifest "$repo_root/packages/development.txt" 'Development packages'
set -l package_status $status
if test $package_status -ne 0
    exit $package_status
end

ui_section '🦀' 'Rust toolchain'

if not command -q rustup
    ui_error 'rustup is not available after package installation'
    exit 1
end

set -l stable_installed 0
for toolchain in (rustup toolchain list 2>/dev/null)
    if string match -q 'stable-*' -- "$toolchain"; or string match -q 'stable*' -- "$toolchain"
        set stable_installed 1
        break
    end
end

if test $stable_installed -eq 0
    ui_step 'Installing Rust stable toolchain'
    rustup toolchain install stable; or begin
        ui_error 'Rust stable toolchain installation failed'
        exit 1
    end
else
    ui_success 'Rust stable toolchain already installed'
end

set -l default_toolchain (rustup default 2>/dev/null | string collect)
if not string match -q '*stable*' -- "$default_toolchain"
    ui_step 'Setting Rust stable as the default toolchain'
    rustup default stable; or begin
        ui_error 'Could not set the Rust default toolchain'
        exit 1
    end
else
    ui_success 'Rust stable is already the default toolchain'
end

ui_step 'Ensuring rustfmt and clippy are installed'
rustup component add rustfmt clippy --toolchain stable >/dev/null; or begin
    ui_error 'Could not install Rust components'
    exit 1
end
ui_success 'rustfmt + clippy ready'

ui_section '🐟' 'Fish language server'

set -l fish_lsp_current_ok 0
if test -x "$fish_lsp_path"
    set -l current_sha (sha256sum "$fish_lsp_path" 2>/dev/null | string split ' ' | head -n 1)

    if test "$current_sha" = "$fish_lsp_sha256"
        set fish_lsp_current_ok 1
        ui_success "fish-lsp v$fish_lsp_version already matches the pinned release"
    else
        ui_info 'Existing /usr/local/bin/fish-lsp differs from the pinned release'
    end
end

if test $fish_lsp_current_ok -eq 0
    set -l tmp (mktemp)

    ui_step "Downloading fish-lsp v$fish_lsp_version"
    curl --fail --location --silent --show-error "$fish_lsp_url" --output "$tmp"; or begin
        rm -f "$tmp"
        ui_error 'fish-lsp download failed'
        exit 1
    end

    set -l downloaded_sha (sha256sum "$tmp" | string split ' ' | head -n 1)
    if test "$downloaded_sha" != "$fish_lsp_sha256"
        rm -f "$tmp"
        ui_error 'fish-lsp checksum verification failed'
        ui_info "Expected: $fish_lsp_sha256"
        ui_info "Actual:   $downloaded_sha"
        exit 1
    end

    ui_success 'fish-lsp checksum verified'

    sudo install -m 0755 "$tmp" "$fish_lsp_path"; or begin
        rm -f "$tmp"
        ui_error "Could not install $fish_lsp_path"
        exit 1
    end

    rm -f "$tmp"
    ui_success "fish-lsp installed to $fish_lsp_path"
end

if not "$fish_lsp_path" --help >/dev/null 2>&1
    ui_error 'fish-lsp exists but cannot execute successfully'
    exit 1
end
ui_success 'fish-lsp execution verified'

mkdir -p "$completions_dir"

set -l completion_tmp (mktemp)
"$fish_lsp_path" complete > "$completion_tmp"; or begin
    rm -f "$completion_tmp"
    ui_error 'Could not generate fish-lsp completions'
    exit 1
end

if not test -s "$completion_tmp"
    rm -f "$completion_tmp"
    ui_error 'fish-lsp generated an empty completion file'
    exit 1
end

if test -f "$completions_file"; and cmp -s "$completion_tmp" "$completions_file"
    rm -f "$completion_tmp"
    ui_success 'fish-lsp completions already current'
else
    mv "$completion_tmp" "$completions_file"
    ui_success "fish-lsp completions written to $completions_file"
end

ui_section '🔍' 'Development verification'

set -l failed 0

for command_name in gcc g++ clang cmake ninja gdb lldb ccache valgrind perf python node npm rustup rustc cargo rustfmt fish-lsp
    if command -q "$command_name"
        ui_success "$command_name · "(command -v "$command_name")
    else
        ui_error "$command_name is missing from PATH"
        set failed (math "$failed + 1")
    end
end

if command -q cargo
    if cargo clippy --version >/dev/null 2>&1
        ui_success 'cargo clippy available'
    else
        ui_error 'cargo clippy is unavailable'
        set failed (math "$failed + 1")
    end
end

echo
ui_info "GCC: "(gcc --version | head -n 1)
ui_info "Clang: "(clang --version | head -n 1)
ui_info "CMake: "(cmake --version | head -n 1)
ui_info "Node: "(node --version)
ui_info "npm: "(npm --version)
ui_info "Rust: "(rustc --version)
ui_info "Cargo: "(cargo --version)

set -l completion_lines (wc -l < "$completions_file" | string trim)
ui_info "fish-lsp completions: $completion_lines lines"

if test $failed -gt 0
    ui_error "Development verification failed with $failed missing tool(s)"
    exit 1
end

ui_done
exit 0
