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
    echo '  fish bootstrap/panda-setup.fish [--interactive] [--modules '(string join ',' -- (panda_setup_module_ids))']'
    echo '                                 [--stores steam,gog,epic,other] [--gpu auto|intel|amd]'
    echo '                                 [--enable-flathub] [--with-shell-tools] [--dry-run | --check | --verify | --apply [--yes]]'
    echo '  fish bootstrap/panda-gaming.fish [--stores steam,gog,epic,other] [--gpu auto|intel|amd] [--dry-run | --check | --verify | --apply]'
    echo 'Without --apply, all selections are READ-ONLY preview operations.'
    echo 'In a terminal type APPLY; without a terminal use --apply --yes.'
    echo '--check validates readiness; --verify checks installed components. Neither writes.'
end

argparse 'help' 'interactive' 'modules=' 'only=' 'stores=' 'gpu=' 'dry-run' 'check' 'verify' 'apply' 'yes' 'enable-flathub' 'with-shell-tools' -- $argv
or exit 2
if test "$PANDA_SETUP_READ_ONLY" = 1; and set -q _flag_apply
    ui_error 'Use fish bootstrap/panda-setup.fish directly to apply a module plan.'
    exit 2
end

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
set -l shell_tools 0
set -l module_menu 0
set -l stores
set -l gpu auto
set -l apply 0
set -l check 0
set -l verify 0
set -l enable_flathub 0
set -l apply_started 0
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
    set module_menu 1
    fish_default_key_bindings
    ui_banner
    echo 'Select modules (comma-separated numbers):'
    set -l available_modules (panda_setup_module_ids)
    set -l module_numbers
    set -l index 1
    for module in $available_modules
        printf '  %s. %s (%s)\n' "$index" (panda_setup_module_get "$module" name) (panda_setup_module_get "$module" menu)
        set -a module_numbers "$index"
        set index (math $index + 1)
    end
    read -l -P 'Modules [3]: ' selection
    if test -z "$selection"
        set selection 3
    end
    for n in (panda_setup_csv "$selection")
        set -l selected_index (contains -i -- "$n" $module_numbers)
        if test -z "$selected_index"
            ui_error "Unknown module selection: $n"
            exit 2
        end
        set -a modules "$available_modules[$selected_index]"
    end
end
if test (count $modules) -eq 0
    ui_error 'Choose at least one module'
    exit 2
end

set -l unique_modules
for mod in $modules
    if not contains -- "$mod" (panda_setup_module_ids)
        ui_error "Unknown module: $mod"
        exit 2
    end
    if not contains -- "$mod" $unique_modules
        set -a unique_modules "$mod"
    end
end
set -l modules_in_order
for module in (panda_setup_module_ids)
    if contains -- "$module" $unique_modules
        set -a modules_in_order "$module"
    end
end
set modules $modules_in_order
if test "$PANDA_SETUP_GAMING_ONLY" = 1; and test (string join ',' -- $modules) != gaming
    ui_error 'The gaming shortcut only supports the gaming module.'
    exit 2
end

if set -q _flag_with_shell_tools
    if not contains -- workspace $modules
        ui_error '--with-shell-tools requires Workspace'
        exit 2
    end
    set shell_tools 1
else if contains -- workspace $modules; and begin
        test $module_menu -eq 1; or set -q _flag_interactive
    end
    fish_default_key_bindings
    read -l -P 'Include optional Workspace shell tools? [y/N] ' answer
    if contains -- "$answer" y Y yes YES
        set shell_tools 1
    end
end
if test $shell_tools -eq 1
    source "$script_dir/lib/shell-tools.fish"
    or exit $status
end

if set -q _flag_stores
    set stores (panda_setup_csv "$_flag_stores")
else if contains gaming $modules
    if set -q _flag_interactive
        fish_default_key_bindings
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
if set -q _flag_enable_flathub; and test $heroic -eq 0
    ui_error '--enable-flathub requires the GOG or Epic gaming selection'
    exit 2
end
if contains gaming $modules
    set gpu (panda_setup_gpu_profile "$gpu")
    or exit $status
end
set -l transaction_manifests
for module in gaming virtualization workspace desktop
    if contains -- "$module" $modules
        for manifest in (panda_setup_module_manifests "$module" "$gpu" $stores)
            set -a transaction_manifests "$repo_root/$manifest"
        end
    end
end

set -l shell_manifest "$repo_root/packages/plugins.txt"
if test $shell_tools -eq 1
    set -a transaction_manifests "$shell_manifest"
end

# This list is also the source of the final report. Unreached operations stay
# blocked, including after a preflight refusal or a partial apply.
set -g panda_setup_operations
set -g panda_setup_outcomes
set -g panda_setup_details
set -l preview_inventory
set -l inventory_known 0
if test (count $transaction_manifests) -gt 0
    set preview_inventory (panda_installed_inventory 2>/dev/null)
    if test $status -eq 0
        set inventory_known 1
    else
        ui_warn 'Pacman inventory unavailable; listing desired packages with unknown installed status.'
    end
end
for module in $modules
    ui_section '🧭' (panda_setup_module_get "$module" name)
    for field in step info warning
        for message in (panda_setup_module_get "$module" "$field")
            ui_info "$message"
        end
    end
    ui_info (panda_setup_module_get "$module" limitations)
    if test (panda_setup_module_get "$module" status) = preview-only
        panda_setup_add_result "$module/apply" 'Unsupported or deferred' 'Android runtime acceptance is pending'
        continue
    end
    panda_setup_add_result "$module/packages" Blocked 'transaction or verification not reached'
    ui_step 'Package installation / network: official pacman packages and dependencies via sudo, with native pacman prompts'
    for manifest in (panda_setup_module_manifests "$module" "$gpu" $stores)
        panda_setup_show_manifest "$repo_root/$manifest" "$inventory_known" $preview_inventory
        or exit $status
    end
    for script in (panda_setup_module_get "$module" scripts)
        panda_setup_add_result "$module/"(path basename -- "$script") Blocked 'stage not run'
    end
    switch "$module"
        case workspace
            ui_step 'User configuration / interactive: review and approve the chezmoi changes, then configure Git identity'
            ui_step 'Authentication / external service: GitHub CLI may contact GitHub, open browser login and prompt about SSH keys'
            ui_step 'Network / development: Rust toolchain and components, pinned fish-lsp (sudo install), and uv tools'
            ui_info 'Codex CLI is a manual prerequisite for the development stage. Dotfiles and GitHub require a terminal.'
        case desktop
            panda_setup_add_result desktop/native 'Unsupported or deferred' 'separate native Panda Desktop deployment gate'
        case gaming
            ui_step "Hardware: verify the active $gpu driver and check free space"
            if test $heroic -eq 1
                panda_setup_add_result gaming/flathub Blocked 'user remote not checked'
                panda_setup_add_result gaming/heroic Blocked 'user Flatpak not checked'
                ui_step 'User configuration / network: install Heroic from user Flathub once for GOG or Epic'
                if test $enable_flathub -eq 1
                    ui_info 'With --enable-flathub: add the official user-scoped Flathub remote if needed.'
                else
                    ui_info 'A user Flathub remote or existing Heroic install is required without --enable-flathub.'
                end
            end
            panda_setup_add_result gaming/first-run 'Pending manual action' 'after installing, launch selected clients, sign in, and choose runners or game downloads'
    end
end
if test $shell_tools -eq 1
    panda_setup_add_result workspace/shell-packages Blocked 'transaction or verification not reached'
    panda_shell_add_results
    ui_info "Optional Workspace shell manifest: $shell_manifest"
    panda_setup_show_manifest "$shell_manifest" "$inventory_known" $preview_inventory
    or panda_setup_finish $status 'Restore the shell package manifest.'
end
set -l execution_order 'combined pacman transaction'
if test $heroic -eq 1
    set -a execution_order 'user Flathub/Heroic'
end
for module in $modules
    for script in (panda_setup_module_get "$module" scripts)
        set -a execution_order (path basename -- "$script")
    end
end
if test $shell_tools -eq 1
    set -a execution_order 'scoped shell configuration and readiness'
end
set -a execution_order 'installed component verification'
if test (count $transaction_manifests) -gt 0
    ui_info 'Apply order: '(string join ' → ' -- $execution_order)
end
if test $apply -eq 1
    panda_setup_add_result setup/final-verification Blocked 'verification not reached'
end
ui_info 'Hardware: strict modes check Helios safety. Pacman hooks may regenerate boot artifacts during apply.'

set -l mode dry-run
if test $apply -eq 1
    set mode apply
else if test $check -eq 1
    set mode check
else if test $verify -eq 1
    set mode verify
end

# Refuse unsupported selections before strict safety checks or writes.
for module in $modules
    if not contains -- "$mode" (panda_setup_module_get "$module" operations)
        ui_error 'Android / AOSP implementation is pending; no selected modules were applied.'
        panda_setup_finish 1
    end
end

ui_section '🔍' 'Safety checks'
set -l strict 0
if test "$mode" != dry-run
    set strict 1
end
if contains gaming $modules
    panda_setup_check_gpu_safety "$gpu" "$strict"
    or panda_setup_finish $status 'Resolve the selected GPU/driver safety check.'
end
if test $strict -eq 1
    panda_setup_helios_validate "$repo_root"
    or panda_setup_finish $status 'Resolve the Helios safety validation before rerunning.'
end

if test $shell_tools -eq 1; and test "$mode" != verify
    panda_shell_stage "$repo_root" plan
    or panda_setup_finish $status 'Resolve the shell configuration preflight error.'
end

if test $apply -eq 0; and test $check -eq 0; and test $verify -eq 0
    ui_success 'DRY RUN COMPLETE: the manager performed read-only checks.'
    exit 0
end

if test $verify -eq 1
    ui_section '🔍' 'Installed component verification'
    set -l verify_status 0
    for module in $modules
        set -l manifests
        for manifest in (panda_setup_module_manifests "$module" "$gpu" $stores)
            set -a manifests "$repo_root/$manifest"
        end
        panda_setup_package_result "$module" 0 verify $manifests
        set -l module_status $status
        if test $verify_status -eq 0
            set verify_status $module_status
        end
        for script in (panda_setup_module_get "$module" scripts)
            set -l stage (path basename -- "$script")
            switch "$stage"
                case install-core.fish install-desktop.fish
                    panda_setup_set_result "$module/$stage" (panda_setup_result_status "$module/packages") 'checked via package inventory'
                case '*'
                    panda_setup_set_result "$module/$stage" 'Pending manual action' 'verify this stage separately; package presence does not verify user configuration or authentication'
            end
        end
    end
    if test $heroic -eq 1
        command -sq flatpak; and flatpak info --user com.heroicgameslauncher.hgl >/dev/null
        set -l heroic_status $status
        if test $heroic_status -eq 0
            panda_setup_set_result gaming/heroic 'Already satisfied' 'user Flatpak verified'
            panda_setup_set_result gaming/flathub 'Already satisfied' 'Heroic is installed; remote setup is unnecessary'
        else
            panda_setup_set_result gaming/heroic Failed "(exit $heroic_status) user Flatpak is missing or could not be queried"
            if command -sq flatpak
                set -l remote_state (panda_setup_flathub_state)
                set -l remote_status $status
                if test $remote_status -ne 0
                    panda_setup_set_result gaming/flathub Failed "(exit $remote_status) user remote query failed"
                else if test "$remote_state" = configured
                    panda_setup_set_result gaming/flathub 'Already satisfied' 'user remote available'
                else
                    panda_setup_set_result gaming/flathub 'Pending manual action' 'user remote missing; review --enable-flathub'
                end
            end
            if test $verify_status -eq 0
                set verify_status $heroic_status
            end
        end
    end
    if test $shell_tools -eq 1
        panda_setup_package_result workspace 0 verify --operation workspace/shell-packages "$shell_manifest"
        or begin
            set -l shell_package_status $status
            if test $verify_status -eq 0
                set verify_status $shell_package_status
            end
        end
        panda_shell_stage "$repo_root" verify
        or begin
            set -l shell_status $status
            if test $verify_status -eq 0
                set verify_status $shell_status
            end
        end
    end
    if test $verify_status -ne 0
        panda_setup_finish $verify_status 'Review missing components with the same selection in --check before applying.'
    end
    if contains gaming $modules
        panda_setup_smoke_gaming "$gpu" $stores
    end
    ui_success 'VERIFICATION COMPLETE: no installations or configuration changes made.'
    panda_setup_finish 0
end
# These preflights are shared by --check and --apply. They do not write.
if not command -sq pacman; or not command -sq sudo
    ui_error 'pacman and sudo are required for an executable plan'
    panda_setup_finish 1 'Install the base package tools through your distribution before rerunning.'
end
ui_section '🔎' 'Read-only execution preflight'
panda_setup_preflight_scripts "$script_dir" $modules
or panda_setup_finish $status 'Restore the selected stage from a complete checkout.'
panda_setup_preflight_packages $transaction_manifests
or panda_setup_finish $status 'Resolve the package inventory, conflict, or repository error above.'
# Check the complete selected transaction against cached pacman databases.
panda_setup_guard_transaction $transaction_manifests
or panda_setup_finish $status 'Resolve the cached pacman transaction error above, then rerun --check.'
if contains gaming $modules
    panda_setup_check_disk_space
    or panda_setup_finish $status 'Check free space on the reported volumes.'
end
if contains gaming $modules
    panda_setup_multilib_check
    or panda_setup_finish $status 'Review multilib configuration before rerunning the Gaming check.'
    if test $heroic -eq 1
        panda_setup_preflight_heroic "$enable_flathub"
        or panda_setup_finish $status 'Review user Flathub readiness or pass --enable-flathub to authorize adding it.'
    end
end
if test $check -eq 1
    if test $shell_tools -eq 1
        set -l missing (panda_setup_missing_targets "$shell_manifest")
        or panda_setup_finish $status 'Could not read shell package inventory.'
        if set -q missing[1]
            panda_setup_set_result workspace/shell-packages 'Pending manual action' 'cached package preflight passed; packages missing'
        else
            panda_setup_set_result workspace/shell-packages 'Already satisfied' 'selected packages verified'
        end
        panda_shell_stage "$repo_root" check
        or panda_setup_finish $status 'Resolve the shell configuration preflight error.'
    end
    for operation in $panda_setup_operations
        if test (panda_setup_result_status "$operation") != Blocked
            continue
        end
        if string match -q 'workspace/shell-*' -- "$operation"
            panda_setup_set_result "$operation" 'Pending manual action' 'run the selected apply or verification to check readiness'
            continue
        end
        set -l manual_reason (panda_setup_stage_manual_reason (path basename -- "$operation"))
        if test -n "$manual_reason"
            panda_setup_set_result "$operation" 'Pending manual action' "$manual_reason"
        else
            panda_setup_set_result "$operation" Ready 'offline preflight passed; execution pending'
        end
    end
    ui_success 'READINESS CHECK PASSED: the manager performed read-only checks.'
    panda_setup_finish 0
end

# Terminal apply always asks, even if --yes was supplied.
if isatty stdin
    # Fish can omit the reader's Enter binding when launched with --no-config.
    fish_default_key_bindings
    read -l -P 'Type APPLY to execute this plan: ' confirmation
    if test "$confirmation" != APPLY
        ui_warn 'Cancelled. No changes applied.'
        for operation in $panda_setup_operations
            if test (panda_setup_result_status "$operation") = Blocked
                panda_setup_set_result "$operation" 'Skipped by user' 'apply confirmation declined'
            end
        end
        panda_setup_finish 1
    end
else if not set -q _flag_yes
    ui_error '--apply needs an interactive terminal or an explicit --yes'
    panda_setup_finish 1 'Review the plan and confirm in a terminal or use --apply --yes for noninteractive execution.'
end

# Re-check immediately before writes: the operator may have spent time at the
# confirmation prompt, and another package manager could have changed state.
if contains gaming $modules
    panda_setup_check_disk_space
    or panda_setup_finish $status 'Check free space on the reported volumes.'
end

# Record boot configuration before package hooks; this is read-only. A
# pacman transaction may indirectly regenerate Limine or initramfs files.
set -l limine_before
if test (hostname) = panda-helios
    panda_setup_helios_limine_lts
    or panda_setup_finish $status 'Inspect the first generated Limine LTS entry.'
    set limine_before (panda_setup_limine_hash)
    or panda_setup_finish $status 'Inspect the generated Limine configuration permissions.'
end

# Snapshot missing targets per module to distinguish newly installed packages
# from existing state. The combined transaction remains the only installer.
for module in $modules
    set -l manifests
    for manifest in (panda_setup_module_manifests "$module" "$gpu" $stores)
        set -a manifests "$repo_root/$manifest"
    end
    set -l missing (panda_setup_missing_targets $manifests)
    or panda_setup_finish $status 'Could not read package inventory before applying.'
    if test (count $missing) -eq 0
        panda_setup_set_result "$module/packages" 'Already satisfied' 'all selected packages present before apply'
    end
end

if test $shell_tools -eq 1
    set -l missing (panda_setup_missing_targets "$shell_manifest")
    or panda_setup_finish $status 'Could not read shell package inventory before applying.'
    if not set -q missing[1]
        panda_setup_set_result workspace/shell-packages 'Already satisfied' 'all selected packages present before apply'
    end
end

# One pacman transaction across ALL selected package manifests. Existing
# workspace/desktop setup scripts still run afterward for non-package tasks;
# their install_manifest calls become no-ops for already-installed packages.
# Capture its exit status BEFORE running any other command. Even on failure,
# pacman may already have run hooks or changed system/boot state.
panda_setup_guard_transaction $transaction_manifests
or panda_setup_finish $status 'Resolve the cached pacman transaction error above, then rerun --check.'
set apply_started 1
panda_setup_install_selected $transaction_manifests
set -l package_status $status

# ALWAYS perform read-only post-transaction checks on Helios, even if pacman
# failed. Collect failures instead of short-circuiting: a failed machine check
# must not prevent examining the generated Limine entry and its fingerprint.
set -l post_safety_failed 0
panda_setup_helios_validate "$repo_root"
or set post_safety_failed $status
if test (hostname) = panda-helios
    panda_setup_helios_limine_lts
    set -l lts_status $status
    if test $post_safety_failed -eq 0
        set post_safety_failed $lts_status
    end
    set -l limine_after (panda_setup_limine_hash)
    set -l hash_status $status
    if test $hash_status -ne 0
        if test $post_safety_failed -eq 0
            set post_safety_failed $hash_status
        end
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

# Check observed package state even on partial transaction failure. Always
# preserve the original transaction status as the primary failure.
set -l package_verification 0
for module in $modules
    set -l manifests
    for manifest in (panda_setup_module_manifests "$module" "$gpu" $stores)
        set -a manifests "$repo_root/$manifest"
    end
    panda_setup_package_result "$module" "$package_status" apply $manifests
    or set package_verification $status
end
if test $shell_tools -eq 1
    panda_setup_package_result workspace "$package_status" apply --operation workspace/shell-packages "$shell_manifest"
    or set package_verification $status
end
if test $post_safety_failed -ne 0
    ui_error 'Post-transaction safety validation failed; refusing remaining setup stages. Do not reboot until investigated.'
end
if test $package_status -ne 0
    ui_error "Package transaction failed (exit $package_status); post-transaction safety checks completed."
    panda_setup_finish $package_status 'Inspect pacman output and existing state. Resolve any Helios safety failure before rebooting or retrying.'
end
if test $post_safety_failed -ne 0
    panda_setup_finish $post_safety_failed 'Resolve the Helios safety failure before rebooting or retrying.'
end
if test $package_verification -ne 0
    panda_setup_finish $package_verification 'Inspect the package inventory and resolve missing packages before retrying.'
end

if test $heroic -eq 1
    panda_setup_apply_heroic "$enable_flathub"
    or panda_setup_finish $status 'Inspect the user Flathub/Heroic error, then rerun the Gaming selection.' gaming
end
for module in $modules
    set -l stage_arguments (panda_setup_module_get "$module" arguments)
    for script in (panda_setup_module_get "$module" scripts)
        set -l stage (path basename -- "$script")
        set -l operation "$module/$stage"
        set -l manual_reason (panda_setup_stage_manual_reason "$stage")
        if test -n "$manual_reason"
            panda_setup_set_result "$operation" 'Pending manual action' "$manual_reason"
            continue
        end
        # Stages may recheck their package layer, but never start another
        # package transaction outside the combined transaction guard.
        set -lx PANDA_SETUP_PACKAGE_MODE --verify-only
        set -lx PANDA_SETUP_SHELL_TOOLS "$shell_tools"
        set -l stage_report
        set -l stage_status
        if contains -- "$stage" setup-chezmoi.fish setup-github.fish
            # Stream stage output to the terminal and capture only the small
            # result marker on a separate descriptor. Preserve every exit code.
            set -lx PANDA_SETUP_STAGE_REPORT 1
            set stage_report (fish --no-config "$repo_root/$script" $stage_arguments 3>&1 1>&2)
            set stage_status $status
        else
            fish --no-config "$repo_root/$script" $stage_arguments
            set stage_status $status
        end
        if test $stage_status -eq 0
            if test "$stage_report" = skipped
                panda_setup_set_result "$operation" 'Skipped by user' 'rerun Workspace in a terminal to review the dotfile changes again'
            else if test "$stage_report" = needs-git-identity
                panda_setup_set_result "$operation" 'Pending manual action' 'apply the portable Git config or configure a global identity, then rerun Workspace'
            else if test "$stage_report" = already-satisfied
                panda_setup_set_result "$operation" 'Already satisfied'
            else if contains -- "$stage" install-core.fish install-desktop.fish
                panda_setup_set_result "$operation" (panda_setup_result_status "$module/packages") 'package layer verified'
            else
                panda_setup_set_result "$operation" Completed
            end
        else
            panda_setup_set_result "$operation" Failed "(exit $stage_status)"
            panda_setup_finish $stage_status "Review the $stage error and any changes it made, then rerun the affected module." "$module"
        end
    end
end
if test $shell_tools -eq 1
    panda_shell_stage "$repo_root" apply
    or panda_setup_finish $status 'Review the shell stage error and any completed operations before retrying.' workspace
end
ui_section '🔍' 'Automatic installation verification'
panda_setup_verify_installation "$heroic" $transaction_manifests
or begin
    set -l verify_status $status
    panda_setup_set_result setup/final-verification Failed "(exit $verify_status) installed component verification failed"
    panda_setup_finish $verify_status 'Inspect the package and Heroic inventory before retrying.'
end
panda_setup_helios_validate "$repo_root"
or begin
    set -l verify_status $status
    panda_setup_set_result setup/final-verification Failed "(exit $verify_status) Helios safety verification failed"
    panda_setup_finish $verify_status 'Resolve the Helios safety failure before rebooting or retrying.'
end
panda_setup_set_result setup/final-verification Completed
if contains gaming $modules
    panda_setup_smoke_gaming "$gpu" $stores
end
panda_setup_finish 0
