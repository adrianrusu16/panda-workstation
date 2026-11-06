# Opt in once with: set -Ux PANDA_ANDROID 1
# This file only changes the current Fish environment; it never installs tools.
if test "$PANDA_ANDROID" != 1
    return
end

function __panda_android_has_jdk --argument-names root
    test -n "$root"; and test -f "$root/release"; and \
        test -x "$root/bin/java"; and test -x "$root/bin/javac"
end

function __panda_android_sdkmanager --argument-names root
    test -n "$root"; or return 1
    if test -x "$root/cmdline-tools/latest/bin/sdkmanager"
        printf '%s\n' "$root/cmdline-tools/latest/bin/sdkmanager"
        return
    end
    # Prefer the highest installed version when Studio has no 'latest' folder.
    path filter -xf "$root"/cmdline-tools/*/bin/sdkmanager | sort -Vr | head -n 1
end

function __panda_android_has_sdk --argument-names root
    test -n "$root"; and test -d "$root"; or return 1
    set -l manager (__panda_android_sdkmanager "$root" | string collect)
    test -x "$root/platform-tools/adb"; or \
        test -f "$root/platforms/android-36.1/android.jar"; or \
        test -n "$manager"
end

function __panda_android_cli --argument-names root
    # Reject symlinked path components rather than exposing an external launcher.
    set -l candidates "$root/cmdline-tools/22.0/bin/android" \
        (path filter -xf "$root"/cmdline-tools/*/bin/android | sort -Vr)
    for candidate in $candidates
        if test -x "$candidate"; and test -f "$candidate"; and test (path resolve "$candidate") = "$candidate"
            printf '%s\n' "$candidate"
            return
        end
    end
end

# Keep a valid explicit JDK, including a different major. --check diagnoses that
# choice against PandaWave's JDK 21 requirement instead of changing user intent.
if not __panda_android_has_jdk "$JAVA_HOME"
    # Resolve alternatives/symlinks without executing Java. A coherent PATH JDK
    # is also an intentional choice, even when JAVA_HOME has not been exported.
    set -l path_java (command -s java)
    set -l path_javac (command -s javac)
    if test -n "$path_java"; and test -n "$path_javac"
        set -l java_bin (path dirname (path resolve "$path_java"))
        set -l javac_bin (path dirname (path resolve "$path_javac"))
        set -l path_jdk (path dirname "$java_bin")
        if test "$java_bin" = "$javac_bin"; and __panda_android_has_jdk "$path_jdk"
            set -gx JAVA_HOME "$path_jdk"
        end
    end
    if not __panda_android_has_jdk "$JAVA_HOME"; and __panda_android_has_jdk /usr/lib/jvm/java-21-openjdk
        if string match -qr '^JAVA_VERSION="21([.+"-]|$)' < /usr/lib/jvm/java-21-openjdk/release
            set -gx JAVA_HOME /usr/lib/jvm/java-21-openjdk
        end
    end
end

if not __panda_android_has_sdk "$ANDROID_HOME"
    if __panda_android_has_sdk "$HOME/Android/Sdk"
        set -gx ANDROID_HOME "$HOME/Android/Sdk"
    end
end

if __panda_android_has_sdk "$ANDROID_HOME"
    set -gx ANDROID_HOME "$ANDROID_HOME"
    set -l android_bins
    if test -x "$ANDROID_HOME/platform-tools/adb"
        set -a android_bins "$ANDROID_HOME/platform-tools"
    end
    set -l manager (__panda_android_sdkmanager "$ANDROID_HOME" | string collect)
    # Prefer the existing bundled launcher; this only exposes a process PATH.
    # Discovery is not product-version or runtime capability verification.
    set -l android_cli (__panda_android_cli "$ANDROID_HOME" | string collect)
    if test -n "$android_cli"
        set android_bins (path dirname "$android_cli") $android_bins
    end
    if test -n "$manager"
        set -a android_bins (path dirname "$manager")
    end
    if test (count $android_bins) -gt 0
        fish_add_path --global --path --move $android_bins
    end
end

if __panda_android_has_jdk "$JAVA_HOME"
    set -gx JAVA_HOME "$JAVA_HOME"
    fish_add_path --global --path --move "$JAVA_HOME/bin"
end

functions --erase __panda_android_has_jdk __panda_android_has_sdk __panda_android_sdkmanager __panda_android_cli
