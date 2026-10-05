#!/usr/bin/env fish

set -l script_dir (path resolve (path dirname (status filename)))
set -l repo_root (path resolve "$script_dir/..")
source "$script_dir/lib/ui.fish"

set -l expected_host 'panda-helios'
set -l safe_kernel 'linux-cachyos-lts'
set -l nvidia_modules 'nvidia,nvidia_drm,nvidia_modeset,nvidia_uvm,nouveau'
set -l module_arg "module_blacklist=$nvidia_modules"
set -l limine_file '/etc/default/limine'
set -l legacy_blacklist '/etc/modprobe.d/90-panda-nvidia-on-demand.conf'
set -l validator "$repo_root/machines/panda-helios/validate.fish"

ui_section '💻' 'Machine profile selection'

if test (hostname) != "$expected_host"
    ui_skip "No implemented machine profile for "(hostname)
    exit 20
end

ui_success 'Selected machines/panda-helios'

if not test -f "$limine_file"
    ui_error "$limine_file is missing; refusing to modify boot configuration"
    exit 1
end

set -l default_line (grep -F -m1 'KERNEL_CMDLINE[default]+=' "$limine_file" 2>/dev/null)
if test -z "$default_line"
    ui_error 'Could not locate the Limine default kernel command line'
    exit 1
end

if string match -q '*module_blacklist=*' -- "$default_line"
    ui_error 'Default Limine entry contains a module blacklist'
    ui_info 'Refusing automatic changes because the normal kernel must remain NVIDIA-capable'
    exit 1
end

set -l default_args (string replace -r '^KERNEL_CMDLINE\[default\]\+="(.*)"$' '$1' -- "$default_line")
if test "$default_args" = "$default_line" -o -z "$default_args"
    ui_error 'Could not parse the Limine default kernel command line safely'
    exit 1
end

set -l expected_lts_line "KERNEL_CMDLINE[\"$safe_kernel\"]=\"$default_args $module_arg\""
set -l current_lts_line (grep -F -m1 "KERNEL_CMDLINE[\"$safe_kernel\"]=" "$limine_file" 2>/dev/null)
set -l changed 0

ui_section '🧩' 'Legacy global NVIDIA policy'

if test -f "$legacy_blacklist"
    set -l disabled "$legacy_blacklist.disabled"
    ui_warn 'Old global NVIDIA blacklist would also block experimental mode'
    ui_step "Disabling "(path basename "$legacy_blacklist")
    sudo mv "$legacy_blacklist" "$disabled"; or begin
        ui_error 'Could not disable the legacy global NVIDIA blacklist'
        exit 1
    end
    set changed 1
    ui_success "Legacy policy disabled: $disabled"
else
    ui_success 'No active Panda global NVIDIA blacklist'
end

ui_section '🥾' 'Kernel boot policy'

if test "$current_lts_line" = "$expected_lts_line"
    ui_success 'LTS Intel-only Limine entry already matches policy'
else
    ui_warn 'LTS Intel-only Limine entry needs reconciliation'
    ui_step 'Creating /etc/default/limine backup'

    set -l stamp (date +%Y%m%d-%H%M%S)
    set -l backup "$limine_file.panda-backup-$stamp"
    sudo cp "$limine_file" "$backup"; or begin
        ui_error "Could not back up $limine_file"
        exit 1
    end
    ui_success "Backup: $backup"

    set -l tmp (mktemp)
    set -l replaced 0

    while read -l line
        if string match -q -r '^KERNEL_CMDLINE\["linux-cachyos-lts"\]' -- "$line"
            printf '%s\n' "$expected_lts_line" >> "$tmp"
            set replaced 1
        else
            printf '%s\n' "$line" >> "$tmp"
        end
    end < "$limine_file"

    if test $replaced -eq 0
        printf '%s\n' "$expected_lts_line" >> "$tmp"
    end

    ui_step 'Installing reconciled Limine configuration'
    sudo install -m 0644 "$tmp" "$limine_file"; or begin
        rm -f "$tmp"
        ui_error 'Could not install updated Limine configuration'
        exit 1
    end
    rm -f "$tmp"

    ui_step 'Rebuilding Limine/initramfs entries'
    sudo limine-mkinitcpio; or begin
        ui_error 'limine-mkinitcpio failed; restoring backup'
        sudo cp "$backup" "$limine_file"
        sudo limine-mkinitcpio >/dev/null 2>&1
        exit 1
    end

    set changed 1
    ui_success 'LTS Intel-only boot policy installed'
end

ui_section '🧪' 'Machine validation'

if test $changed -eq 1
    ui_warn 'Boot policy changed; runtime validation requires a fresh LTS boot'
    ui_info "Power off fully, boot $safe_kernel, then rerun this stage"
    exit 20
end

if not test -x "$validator"
    ui_error "Machine validator is missing or not executable: $validator"
    exit 1
end

"$validator"
set -l result $status

if test $result -eq 0
    ui_done
end

exit $result
