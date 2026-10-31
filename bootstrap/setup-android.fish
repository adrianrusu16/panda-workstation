#!/usr/bin/env fish
# Legacy review/check plus separately approved Android CLI/SDK automation.
set -l script_dir (path resolve (path dirname (status filename)))
set -l repo_root (path resolve "$script_dir/..")
source "$script_dir/lib/ui.fish"

set -l mode --dry-run
if test (count $argv) -gt 1
    echo 'Usage: fish bootstrap/setup-android.fish [--dry-run | --check | --plan | --cli-check | --install | --repair | --help]' >&2
    exit 2
end
if test (count $argv) -eq 1
    set mode "$argv[1]"
end
switch "$mode"
    case --help -h
        echo 'Usage: fish bootstrap/setup-android.fish [--dry-run | --check | --plan | --cli-check | --install | --repair | --help]'
        echo 'Default/--dry-run: review paths and gaps without executing vendor tools.'
        echo '--check: also execute selected java/javac versions; never install or apply.'
        echo '--plan: read-only manifest, metadata inventory, exact actions and manual IDE checklist.'
        echo '--cli-check: separately approved vendor version/help/root/inventory; may download launcher payload and write caches.'
        echo '--install: interactive approvals for missing SDK components, downloads and Google terms.'
        echo '--repair: same approvals; retain/restore corrupt package directories; never replace CLI slots.'
        echo 'New modes require Python 3.11+. Unconfigured publisher metadata blocks CLI bootstrap.'
        echo 'Android CLI is preferred after runtime verification; deprecated SDK Manager fallback requires explicit approval.'
        echo 'No Java/Studio/plugin/dotfile installation. Master Android dispatch is optional and OFF by default.'
        echo 'See docs/android-development.md for effects, recovery and manual checkpoints.'
        exit 0
    case --dry-run --check --plan --cli-check --install --repair
    case '*'
        ui_error "Unknown argument: $mode"
        exit 2
end

# Enable only this child process, including when the deployed profile is disabled.
set -gx PANDA_ANDROID 1
set -l requested_sdk "$ANDROID_HOME"
source "$repo_root/home/dot_config/fish/conf.d/panda-android.fish"
if contains -- "$mode" --plan --cli-check --install --repair
    # New installs may select an empty/nonexistent custom SDK; do not switch roots.
    if test -n "$requested_sdk"
        set -gx ANDROID_HOME "$requested_sdk"
    end
    if not command -q python3
        ui_error 'Python 3.11+ is required for Android automation; no installation attempted.'
        exit 1
    end
    python3 -B "$script_dir/lib/android/automation.py" "$mode"
    exit $status
end
set -g android_problems 0
function android_missing --argument-names message
    ui_warn "$message"
    set -g android_problems (math "$android_problems + 1")
end

ui_section '🤖' "Opt-in Android profile · $mode"
ui_info 'No packages, SDK licenses, dotfiles or system policy will be changed.'
ui_info 'Host package recipe (approval required): sudo pacman -S --needed jdk21-openjdk'
ui_info 'Use only an up-to-date synchronized package database; approve any full upgrade separately.'

set -l jdk_ok 0
if test -n "$JAVA_HOME"; and test -f "$JAVA_HOME/release"; and \
        test -x "$JAVA_HOME/bin/java"; and test -x "$JAVA_HOME/bin/javac"
    ui_info "JAVA_HOME: $JAVA_HOME"
    if string match -qr '^JAVA_VERSION="21([.+"-]|$)' < "$JAVA_HOME/release"
        set jdk_ok 1
        ui_success 'JDK 21 metadata and java/javac executables found'
    else
        android_missing 'Selected JAVA_HOME is not JDK 21; select JDK 21 explicitly for PandaWave.'
    end
else
    android_missing 'JDK missing: install jdk21-openjdk; JAVA_HOME must name a complete JDK 21.'
end

if test "$mode" = --check; and test $jdk_ok -eq 1
    for tool in java javac
        set -l selected (path resolve "$JAVA_HOME/bin/$tool")
        set -l on_path (command -s "$tool")
        if test -z "$on_path"; or test (path resolve "$on_path") != "$selected"
            android_missing "$tool on PATH does not match JAVA_HOME"
            continue
        end
        set -l tool_version ("$JAVA_HOME/bin/$tool" -version 2>&1 | string collect)
        set -l version_status $pipestatus[1]
        ui_info "$tool_version"
        set -l pattern '^javac 21([.+ -]|$)'
        if test "$tool" = java
            set pattern 'version "21([.+"-]|$)'
        end
        if test "$version_status" != 0; or not string match -qr -- "$pattern" "$tool_version"
            android_missing "$tool did not execute successfully as version 21"
        end
    end
end

set -l sdkmanager
if test -n "$ANDROID_SDK_ROOT"
    if test -z "$ANDROID_HOME"; or test (path resolve "$ANDROID_SDK_ROOT") != (path resolve "$ANDROID_HOME")
        android_missing 'Legacy ANDROID_SDK_ROOT conflicts with ANDROID_HOME; review and remove the legacy setting.'
    end
end
if test -n "$ANDROID_HOME"; and test -d "$ANDROID_HOME"
    ui_info "ANDROID_HOME: $ANDROID_HOME"
    if test -x "$ANDROID_HOME/platform-tools/adb"
        ui_success 'Platform Tools found in selected SDK'
    else
        android_missing 'Missing Platform Tools: platform-tools (selected ANDROID_HOME)'
    end
    if test -x "$ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager"
        set sdkmanager "$ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager"
    else
        set sdkmanager (path filter -xf "$ANDROID_HOME"/cmdline-tools/*/bin/sdkmanager | sort -Vr | head -n 1 | string collect)
    end
    if test -n "$sdkmanager"
        ui_success "Command-Line Tools found: $sdkmanager"
        ui_info 'Deferred operator check: SDK Manager startup/cache writes are not assumed safe here.'
        printf '  %s --sdk_root=%s --list_installed\n' (string escape -- "$sdkmanager") (string escape -- "$ANDROID_HOME")
    else
        android_missing 'Missing Android SDK Command-Line Tools (sdkmanager inside ANDROID_HOME)'
    end
    if test -f "$ANDROID_HOME/platforms/android-36.1/android.jar"
        ui_success 'SDK platform found: platforms;android-36.1'
    else
        android_missing 'Missing SDK platform: platforms;android-36.1'
    end
    set -l build "$ANDROID_HOME/build-tools/36.0.0"
    if test -x "$build/aapt2"; and test -f "$build/source.properties"; and \
            string match -qr '^Pkg.Revision\s*=\s*36\.0\.0\s*$' < "$build/source.properties"
        ui_success 'SDK Build Tools found: build-tools;36.0.0'
    else
        android_missing 'Missing/inconsistent SDK Build Tools: build-tools;36.0.0'
    end
else
    android_missing 'ANDROID_HOME missing/invalid: choose an installed SDK, normally $HOME/Android/Sdk.'
    android_missing 'Install via Studio: Platform Tools, Command-Line Tools, platforms;android-36.1, build-tools;36.0.0'
end

ui_info 'Android Studio: use the official Linux archive or a separately reviewed AUR package.'
ui_info 'NDK, Rust Android targets, Canopy, AAOS, emulators, KVM/GPU and devices are deferred.'
ui_info 'These checks do not prove PandaWave builds; see docs/android-development.md.'
if test "$mode" = --dry-run
    ui_info "Review complete: $android_problems gap(s); no Java or SDK tools executed."
    exit 0
end
if test $android_problems -gt 0
    ui_error "Android checks failed: $android_problems gap(s)"
    exit 1
end
ui_success 'Local JDK checks and SDK presence checks passed; SDK Manager/Gradle remain unverified.'
