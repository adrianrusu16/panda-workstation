#!/usr/bin/env fish

set -l script_dir (path resolve (path dirname (status filename)))
set -l repo_root (path resolve "$script_dir/../..")
source "$repo_root/bootstrap/lib/ui.fish"

set -l expected_host 'panda-helios'
set -l safe_kernel 'linux-cachyos-lts'
set -l nvidia_modules 'nvidia,nvidia_drm,nvidia_modeset,nvidia_uvm,nouveau'
set -l module_arg "module_blacklist=$nvidia_modules"
set -l failed 0
set -l warnings 0

ui_section '💻' 'Panda Helios identity'

if test (hostname) != "$expected_host"
    ui_skip "This profile targets $expected_host; current host is "(hostname)
    exit 20
end

ui_success "Host: $expected_host"
ui_info "Kernel: "(uname -r)

ui_section '🥾' 'Limine kernel policy'

if not test -f /etc/default/limine
    ui_error '/etc/default/limine is missing'
    set failed (math "$failed + 1")
else
    set -l default_line (grep -F -m1 'KERNEL_CMDLINE[default]+=' /etc/default/limine 2>/dev/null)
    set -l lts_line (grep -F -m1 "KERNEL_CMDLINE[\"$safe_kernel\"]=" /etc/default/limine 2>/dev/null)

    if test -n "$lts_line"; and string match -q "*$module_arg*" -- "$lts_line"
        ui_success 'LTS entry hard-blocks NVIDIA modules'
    else
        ui_error 'LTS Intel-only kernel policy is missing or incomplete'
        set failed (math "$failed + 1")
    end

    if string match -q '*module_blacklist=*' -- "$default_line"
        ui_error 'Default kernel line contains a module blacklist; experimental NVIDIA mode would also be blocked'
        set failed (math "$failed + 1")
    else
        ui_success 'Default kernel line remains NVIDIA-capable'
    end
end

ui_section '🧩' 'Global modprobe policy'

set -l global_nvidia_blacklists
for conf in /etc/modprobe.d/*.conf
    if test -f "$conf"
        set -a global_nvidia_blacklists (grep -H -E '^[[:space:]]*blacklist[[:space:]]+(nvidia|nvidia_drm|nvidia_modeset|nvidia_uvm)([[:space:]]|$)' "$conf" 2>/dev/null)
    end
end

if test (count $global_nvidia_blacklists) -eq 0
    ui_success 'No active global blacklist blocks the proprietary NVIDIA modules'
else
    ui_error 'Active global NVIDIA blacklist would defeat experimental mode'
    printf '%s\n' $global_nvidia_blacklists
    set failed (math "$failed + 1")
end

ui_section '😴' 'Suspend safety'

for target in sleep.target suspend.target hibernate.target hybrid-sleep.target
    set -l state (systemctl is-enabled "$target" 2>/dev/null)

    if test "$state" = 'masked'
        ui_success "$target is masked"
    else
        ui_error "$target is not masked · state: "(string escape -- "$state")
        set failed (math "$failed + 1")
    end
end

ui_section '💾' 'Storage policy'

set -l root_source (findmnt -no SOURCE / 2>/dev/null)
if string match -q '/dev/sda2*' -- "$root_source"
    ui_success "Root filesystem is on Samsung SATA system partition: $root_source"
else
    ui_warn "Expected root on /dev/sda2; observed: $root_source"
    set warnings (math "$warnings + 1")
end

if test -b /dev/nvme0n1
    set -l nvme_mounts (lsblk -nrpo MOUNTPOINT /dev/nvme0n1 2>/dev/null | string trim | string match -rv '^$')

    if test (count $nvme_mounts) -eq 0
        ui_success 'Untrusted Intel NVMe has no mounted filesystems'
    else
        ui_error "Untrusted Intel NVMe is mounted: "(string join ', ' $nvme_mounts)
        set failed (math "$failed + 1")
    end
else
    ui_info 'Intel NVMe is not currently exposed as /dev/nvme0n1'
end

ui_section '🎮' 'Current GPU runtime'

if string match -q '*cachyos-lts*' -- (uname -r)
    ui_info 'Safe/dev kernel detected; enforcing Intel-only runtime checks'

    set -l cmdline (string collect < /proc/cmdline)
    if string match -q "*$module_arg*" -- "$cmdline"
        ui_success 'Kernel command line contains NVIDIA hard blacklist'
    else
        ui_error 'Running LTS kernel without NVIDIA hard blacklist'
        set failed (math "$failed + 1")
    end

    set -l loaded_nvidia (lsmod | string match -r '^nvidia')
    if test (count $loaded_nvidia) -eq 0
        ui_success 'No NVIDIA kernel modules are loaded'
    else
        ui_error 'NVIDIA modules are loaded in safe mode'
        printf '%s\n' $loaded_nvidia
        set failed (math "$failed + 1")
    end

    set -l dgpu (lspci -k -s 01:00.0 2>/dev/null)
    if string match -q '*Kernel driver in use: nvidia*' -- "$dgpu"
        ui_error 'GTX 1060 is bound to the NVIDIA driver in safe mode'
        set failed (math "$failed + 1")
    else
        ui_success 'GTX 1060 has no NVIDIA driver bound'
    end

    set -l igpu (lspci -k -s 00:02.0 2>/dev/null)
    if string match -q '*Kernel driver in use: i915*' -- "$igpu"
        ui_success 'Intel HD 630 is bound to i915'
    else
        ui_error 'Intel HD 630 is not bound to i915'
        set failed (math "$failed + 1")
    end

    set -l xids (journalctl -k -b --no-pager 2>/dev/null | string match -r 'NVRM: Xid')
    if test (count $xids) -eq 0
        ui_success 'No NVIDIA Xids in the current boot'
    else
        ui_error 'NVIDIA Xids detected in safe boot'
        printf '%s\n' $xids
        set failed (math "$failed + 1")
    end
else
    ui_warn 'Experimental/non-LTS kernel is running; Intel-only runtime checks were not applied'
    ui_info "Boot $safe_kernel to validate the safe/dev profile"
    set warnings (math "$warnings + 1")
end

echo

if test $failed -gt 0
    ui_error "Panda Helios validation failed with $failed problem(s)"
    exit 1
end

if test $warnings -gt 0
    ui_warn "Profile configuration passed with $warnings warning(s)"
end

ui_success 'Panda Helios machine profile validated'
exit 0
