#!/usr/bin/env fish
# Panda Setup Manager — explicit opt-in, default plan-only.
# Never calls setup-workstation.fish or setup-machine.fish.
set -l script_dir (path resolve (path dirname (status filename)))
set -l repo_root (path resolve "$script_dir/..")
source "$script_dir/lib/ui.fish"
source "$script_dir/lib/packages.fish"
source "$script_dir/lib/panda-setup.fish"

function panda_setup_usage
    echo 'Panda Setup Manager'
    echo 'Usage:'
    echo '  fish bootstrap/panda-setup.fish [--interactive] [--modules workspace,desktop,gaming,android,virtualization]'
    echo '                                 [--stores steam,gog,epic,other] [--gpu auto|intel|amd]'
    echo '                                 [--enable-flathub] [--dry-run | --check | --verify | --apply [--yes]]'
    echo '  fish bootstrap/panda-gaming.fish [--stores steam,gog,epic,other] [--gpu auto|intel|amd] [--dry-run | --check | --verify | --apply]'
    echo 'Without --apply, all selections are READ-ONLY preview operations.'
    echo '--check validates readiness; --verify checks installed components. Neither writes.'
end

argparse 'help' 'interactive' 'modules=' 'only=' 'stores=' 'gpu=' 'dry-run' 'check' 'verify' 'apply' 'yes' 'enable-flathub' -- $argv
or exit 2
if test (count $argv) -gt 0
    ui_error 'Unexpected positional arguments'
    panda_setup_usage
    exit 2
end
if set -q _flag_interactive; and not isatty stdin
    ui_error '--interactive requires a terminal'
    exit 2
end
if set -q _flag_help
    panda_setup_usage
    exit 0
end
set -l selected_modes 0
for mode in _flag_dry_run _flag_check _flag_verify _flag_apply
    if set -q $mode
        set selected_modes (math $selected_modes + 1)
    end
end
if test $selected_modes -gt 1
    ui_error 'Choose only one of --dry-run, --check, --verify, or --apply'
    exit 2
end
if set -q _flag_only; and set -q _flag_modules
    ui_error 'Use --modules OR --only, not both'
    exit 2
end
if set -q _flag_yes; and not set -q _flag_apply
    ui_error '--yes is only valid with --apply'
    exit 2
end

set -l modules
set -l stores
set -l gpu auto
set -l apply 0
set -l check 0
set -l verify 0
set -l enable_flathub 0
if set -q _flag_apply
    set apply 1
end
if set -q _flag_check
    set check 1
end
if set -q _flag_verify
    set verify 1
end
if set -q _flag_enable_flathub
    set enable_flathub 1
end
if set -q _flag_gpu
    set gpu "$_flag_gpu"
end
if not contains -- "$gpu" auto intel amd
    ui_error "Invalid GPU profile: $gpu (supported: auto, intel, amd)"
    exit 2
end

if set -q _flag_modules
    set modules (panda_setup_csv "$_flag_modules")
else if set -q _flag_only
    set modules (panda_setup_csv "$_flag_only")
else
    # Interactive only when running in a terminal; no surprise selection in CI.
    if not isatty stdin
        ui_error 'No modules supplied on non-interactive input; use --modules'
        exit 2
    end
    ui_banner
    echo 'Select modules (comma-separated numbers):'
    echo '  1. Workspace (core tools, chezmoi, Git, development; no boot changes)'
    echo '  2. Panda Desktop (Plasma packages only; no theme activation)'
    echo '  3. Gaming (multi-store gaming stack)'
    echo '  4. Android / AOSP (planning only, not deployable yet)'
    echo '  5. Virtualization (packages only; never creates/boots a VM)'
    read -l -P 'Modules [3]: ' selection
    if test -z "$selection"
        set selection 3
    end
    for n in (panda_setup_csv "$selection")
        switch "$n"
            case 1
                set -a modules workspace
            case 2
                set -a modules desktop
            case 3
                set -a modules gaming
            case 4
                set -a modules android
            case 5
                set -a modules virtualization
            case '*'
                ui_error "Unknown module selection: $n"
                exit 2
        end
    end
end
if test (count $modules) -eq 0
    ui_error 'Choose at least one module'
    exit 2
end

set -l unique_modules
for mod in $modules
    if not contains -- "$mod" workspace desktop gaming android virtualization
        ui_error "Unknown module: $mod"
        exit 2
    end
    if not contains -- "$mod" $unique_modules
        set -a unique_modules "$mod"
    end
end
set modules $unique_modules

if set -q _flag_stores
    set stores (panda_setup_csv "$_flag_stores")
else if contains gaming $modules
    if set -q _flag_interactive
        read -l -P 'Gaming stores [steam,gog,epic,other]: ' answer
        if test -z "$answer"
            set answer steam,gog,epic,other
        end
        set stores (panda_setup_csv "$answer")
    else
        set stores steam gog epic other
    end
end
if test (count $stores) -gt 0; and not contains gaming $modules
    ui_error '--stores only applies when the gaming module is selected'
    exit 2
end
if contains gaming $modules; and test (count $stores) -eq 0
    ui_error 'Gaming requires at least one store'
    exit 2
end
set -l unique_stores
for store in $stores
    if not contains -- "$store" steam gog epic other
        ui_error "Unknown gaming store: $store"
        exit 2
    end
    if not contains -- "$store" $unique_stores
        set -a unique_stores "$store"
    end
end
set stores $unique_stores

# A separate return code from each action is checked. Never continue on failures.
ui_banner
ui_section '🧭' 'Selected setup plan'
ui_info "Modules: "(string join ', ' -- $modules)
if contains gaming $modules
    ui_info "Stores: "(string join ', ' -- $stores)
    ui_info "Requested GPU: $gpu"
end
ui_info 'This manager never runs the machine/boot setup stage.'

set -l heroic 0
if contains gog $stores; or contains epic $stores
    set heroic 1
end
set -l manifest_names
if contains gaming $modules
    set -a manifest_names gaming-base
    if contains steam $stores
        set -a manifest_names gaming-steam
    end
    if test $heroic -eq 1
        set -a manifest_names gaming-heroic
    end
    if contains other $stores
        set -a manifest_names gaming-other
    end
    # GPU-specific packages will be added after safety checks.
    set gpu (panda_setup_gpu_profile "$gpu")
    or exit 1
    set -a manifest_names "gaming-$gpu"
end
if contains virtualization $modules
    set -a manifest_names virtualization-base
end
if contains workspace $modules
    ui_step 'Workspace: install-core → setup-chezmoi → setup-github → setup-development'
    ui_info 'Existing workstation scripts may change user configuration and install dev tools on --apply.'
    panda_setup_show_manifest "$repo_root/packages/core.txt"
    or exit 1
    panda_setup_show_manifest "$repo_root/packages/development.txt"
    or exit 1
end
if contains desktop $modules
    ui_step 'Panda Desktop: install-desktop.fish --profile plasma (packages only)'
    ui_info 'Panda theme/layout activation is not part of this release.'
    panda_setup_show_manifest "$repo_root/packages/desktop.txt"
    or exit 1
end
if contains android $modules
    ui_warn 'Android / AOSP is NOT IMPLEMENTED; --apply will refuse the entire selection.'
end
if contains virtualization $modules
    ui_step 'Virtualization: QEMU/libvirt/virt-manager/OVMF package layer only'
    ui_info 'No libvirt service configuration, VM disk, firmware changes, or guest startup.'
end
if test $heroic -eq 1
    ui_step 'GOG + Epic: install Heroic Flatpak once (user scope)'
    if test $enable_flathub -eq 1
        ui_info 'With --enable-flathub: would add the official user-scoped Flathub remote if missing.'
    else if command -sq flatpak; and flatpak info --user com.heroicgameslauncher.hgl >/dev/null 2>&1
        ui_info 'Heroic is already installed for this user; Flathub setup not needed.'
    else
        ui_warn 'If Flathub is missing, --apply requires --enable-flathub.'
    end
end
for name in $manifest_names
    set -l manifest "$repo_root/setup/manifests/$name.txt"
    panda_setup_show_manifest "$manifest"
    or exit 1
end

# Use one selected manifest list for preflight and final verification.
set -l transaction_manifests
for name in $manifest_names
    set -a transaction_manifests "$repo_root/setup/manifests/$name.txt"
end
if contains workspace $modules
    set -a transaction_manifests "$repo_root/packages/core.txt" "$repo_root/packages/development.txt"
end
if contains desktop $modules
    set -a transaction_manifests "$repo_root/packages/desktop.txt"
end

ui_section '🔍' 'Safety checks'
# Read-only checks in both plan and apply modes. A failed plan explains blockers,
# but only --apply performs strict eligibility enforcement.
set -l strict 0
if test $apply -eq 1; or test $check -eq 1; or test $verify -eq 1
    set strict 1
end
if contains gaming $modules
    panda_setup_check_gpu_safety "$gpu" "$strict"
    or exit 1
end
if test $strict -eq 1
    panda_setup_helios_validate "$repo_root"
    or exit 1
end

if test $apply -eq 0; and test $check -eq 0; and test $verify -eq 0
    ui_success 'DRY RUN COMPLETE: no packages, repos, files, services, VMs, or boot settings changed.'
    exit 0
end

# Preflight the complete selection before any writes or privileged commands.
if contains android $modules
    ui_error 'Android / AOSP implementation is pending; no selected modules were applied.'
    exit 1
end
if test $verify -eq 1
    ui_section '🔍' 'Installed component verification'
    panda_setup_verify_installation "$heroic" $transaction_manifests
    or exit 1
    if contains gaming $modules
        panda_setup_smoke_gaming "$gpu" $stores
    end
    ui_success 'VERIFICATION COMPLETE: no installations or configuration changes made.'
    exit 0
end
# These preflights are shared by --check and --apply. They do not write.
if not command -sq pacman; or not command -sq sudo
    ui_error 'pacman and sudo are required for an executable plan'
    exit 1
end
ui_section '🔎' 'Read-only execution preflight'
panda_setup_preflight_scripts "$script_dir" $modules
or exit 1
panda_setup_preflight_packages "$repo_root" $modules -- $manifest_names
or exit 1
# Check the complete selected transaction against cached pacman databases.
panda_setup_guard_transaction $transaction_manifests
or exit 1
if contains gaming $modules
    panda_setup_check_disk_space
    or exit 1
end
if contains gaming $modules
    panda_setup_multilib_check
    or exit 1
    if test $heroic -eq 1
        panda_setup_preflight_heroic "$enable_flathub"
        or exit 1
    end
end
if test $check -eq 1
    ui_success 'READINESS CHECK PASSED: no packages, repos, files, services, VMs, or boot settings changed.'
    exit 0
end

# An explicit apply invocation is required; for terminal use we additionally ask.
if not set -q _flag_yes
    if not isatty stdin
        ui_error '--apply needs an interactive terminal or an explicit --yes'
        exit 1
    end
    read -l -P 'Type APPLY to execute this plan: ' confirmation
    if test "$confirmation" != APPLY
        ui_warn 'Cancelled. No changes applied.'
        exit 1
    end
end

# Re-check immediately before writes: the operator may have spent time at the
# confirmation prompt, and another package manager could have changed state.
panda_setup_guard_transaction $transaction_manifests
or exit 1
if contains gaming $modules
    panda_setup_check_disk_space
    or exit 1
end

# Record boot configuration before package hooks; this is read-only. A
# pacman transaction may indirectly regenerate Limine or initramfs files.
set -l limine_before
if test (hostname) = panda-helios
    panda_setup_helios_limine_lts
    or exit 1
    set limine_before (panda_setup_limine_hash)
    or exit 1
end

# One pacman transaction across ALL selected package manifests. Existing
# workspace/desktop setup scripts still run afterward for non-package tasks;
# their install_manifest calls become no-ops for already-installed packages.
# Capture its exit status BEFORE running any other command. Even on failure,
# pacman may already have run hooks or changed system/boot state.
panda_setup_install_selected $transaction_manifests
set -l package_status $status

# ALWAYS perform read-only post-transaction checks on Helios, even if pacman
# failed. Collect failures instead of short-circuiting: a failed machine check
# must not prevent examining the generated Limine entry and its fingerprint.
set -l post_safety_failed 0
panda_setup_helios_validate "$repo_root"
or set post_safety_failed 1
if test (hostname) = panda-helios
    panda_setup_helios_limine_lts
    or set post_safety_failed 1
    set -l limine_after (panda_setup_limine_hash)
    if test $status -ne 0
        set post_safety_failed 1
    else if test "$limine_before" != "$limine_after"
        if test $post_safety_failed -eq 0
            ui_warn 'Pacman hooks changed /boot/limine.conf; verified LTS NVIDIA blacklist remains intact.'
        else
            ui_warn 'Pacman hooks changed /boot/limine.conf; LTS safety validation did not pass.'
        end
    else
        ui_success 'Generated Limine configuration unchanged by package transaction.'
    end
end

# Preserve pacman's original nonzero status despite subsequent safety checks.
# No Flatpak, development, or desktop stages may follow either failure.
if test $package_status -ne 0
    if test $post_safety_failed -ne 0
        ui_error 'Post-transaction safety validation failed; do not reboot until investigated.'
    end
    ui_error "Package transaction failed (exit $package_status); post-transaction safety checks completed."
    exit $package_status
end
if test $post_safety_failed -ne 0
    ui_error 'Post-transaction safety validation failed; refusing remaining setup stages. Do not reboot until investigated.'
    exit 1
end

if test $heroic -eq 1
    if not command -sq flatpak
        ui_error 'flatpak was not installed as expected'
        exit 1
    end
    if flatpak info --user com.heroicgameslauncher.hgl >/dev/null 2>&1
        ui_success 'Heroic already installed'
    else
        if not panda_setup_has_flathub
            if test $enable_flathub -eq 0
                ui_error 'User Flathub remote is unavailable'
                exit 1
            end
            flatpak remote-add --user --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
            or exit $status
        end
        flatpak install --user --noninteractive -y flathub com.heroicgameslauncher.hgl
        or exit $status
    end
    flatpak info --user com.heroicgameslauncher.hgl >/dev/null 2>&1
    or begin
        ui_error 'Heroic post-install validation failed'
        exit 1
    end
end
if contains workspace $modules
    for script in install-core.fish setup-chezmoi.fish setup-github.fish setup-development.fish
        fish "$script_dir/$script"
        or exit $status
    end
end
if contains desktop $modules
    fish "$script_dir/install-desktop.fish" --profile plasma
    or exit $status
end
ui_section '🔍' 'Automatic installation verification'
panda_setup_verify_installation "$heroic" $transaction_manifests
or exit 1
panda_setup_helios_validate "$repo_root"
or exit 1
if contains gaming $modules
    panda_setup_smoke_gaming "$gpu" $stores

    ui_info 'Launch Steam/Heroic/Lutris normally to sign in and complete their first-run setup.'
    ui_info 'Proton/game downloads and store authentication require user actions; nothing is enabled in the GPU/boot configuration.'
end
ui_success 'Selected implemented modules completed; package-hook boot effects were checked on Helios.'
