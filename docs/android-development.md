# Optional Android workstation profile

The recovered profile provides JDK/SDK selection, metadata checks and an
interactive SDK installer. Source and fixture validation do not authorize live
installation or establish current host acceptance. Android Studio, plugins,
preferences, Gradle builds, devices, emulators and native development remain
separate operator tasks.

The separate [Panda Setup Manager](panda-setup-manager.md) Android/AOSP module
remains plan-only and blocks apply. The legacy workstation entrypoint supports
an independent `--android` route; Android is OFF during ordinary workstation and
development setup, even when the Fish environment profile is enabled.

## Commands and effects

```fish
fish --no-config bootstrap/setup-android.fish --plan
fish --no-config bootstrap/setup-workstation.fish --android --plan
```

| Mode | Contract |
|---|---|
| No argument / `--dry-run` | Read paths and metadata; report gaps; exit 0; execute no Java/SDK tools |
| `--plan` | Strict manifest, package/layout/revision inventory, candidate identity and manual IDE checklist; no vendor execution |
| `--check` | Execute selected Java/javac and check SDK presence; no Android/SDK/Studio execution; gaps return 1 |
| `--cli-check` | Interactive approval before Android version/help/root/inventory calls; possible network/cache/launcher writes |
| `--install` | Interactive approvals for missing baseline packages, archive acquisition/publication and terms; no healthy package reinstall |
| `--repair` | Same approvals, plus retain/restore specifically approved corrupt package directories |
| `--help` | Describe effects without running installation |

The legacy `--android` route runs only this stage, defaults to `--plan`, forwards
the selected mode and exit status, and rejects extra/mixed options. Do not run
the unqualified master bootstrap to inspect Android: other stages can change
packages, configuration and recovery-critical host policy.

## Managed baseline and selection

| Component | Profile |
|---|---|
| Terminal JDK | 21; Java default changes and JDK installation remain manual |
| Platform Tools | Existing compatible metadata/layout, or approved missing installation |
| Command-Line Tools | Existing compatible installation; bootstrap pin 22.0 |
| SDK platform | Exactly `platforms;android-36.1`, revision 1 |
| Build Tools | Exactly `build-tools;36.0.0` |

`config/android/toolchain.toml` defines the baseline. Platform metadata accepts
`AndroidVersion.ApiLevel=36.1`, or the older split `36` plus minor `1`; mixed,
missing, malformed and conflicting forms refuse. A regular `android.jar`,
numeric package revision and non-symlink paths are required. Revision 2 is not a
substitute for approved platform revision 1.

The Fish selector is disabled until `PANDA_ANDROID=1`. It preserves valid explicit
JDK/SDK choices, including a different JDK major that `--check` then diagnoses.
It can select a coherent PATH JDK or the existing system JDK 21 and defaults to
`$HOME/Android/Sdk` when appropriate. New automation modes preserve an explicit
empty SDK choice rather than switching roots. Conflicting `ANDROID_SDK_ROOT`
and `ANDROID_HOME` refuse. Repeated sourcing changes process PATH only; it does
not persist universal paths or change the machine's Java default.

Studio remains manually installed. Metadata detection considers
`ANDROID_STUDIO_HOME`, an explicitly configured preferred path,
`$HOME/Applications/android-studio`, and supported system locations. An empty
preferred path in the manifest avoids a machine-specific default.

## Before an approved installation

Use a user-local SDK in a trusted private directory and close concurrent Studio/
SDK installers. Inspect the exact source, SDK selection, metadata plan and
[CLI approval contract](android-cli.md). The path checks reject traversal and
symlinks; CLI candidate checks also enforce owner and group/other write limits
inside the SDK. Bootstrap/repair do **not** establish a uniform ownership or
permission boundary for all ancestors, especially before the SDK exists.
Shared/untrusted parent directories and concurrent or hostile writers are
unsupported. No atomic defense against same-UID substitution is claimed.

If JDK 21 is missing, review the standalone `packages/android.txt` recipe first.
It contains only `jdk21-openjdk`, not Studio or Google SDK package IDs. This
profile never installs OS packages or runs a system upgrade. On Arch, avoid
partial upgrades and never run `pacman -Sy` alone.

After reviewing the plan, the operator may separately authorize:

```fish
fish --no-config bootstrap/setup-android.fish --cli-check
fish --no-config bootstrap/setup-android.fish --install
# Only for specifically reviewed corrupt package directories:
fish --no-config bootstrap/setup-android.fish --repair
```

These commands are examples for a future authorized operator session, not steps
performed during recovery. Confirmations require a real terminal and exact `yes`.
Google licenses remain interactive; no `yes` pipe or automatic terms acceptance
is used. Existing extra SDK platforms, sources, emulators and system images are
preserved. No update/remove/downgrade or substitute package is implicit.

When Command-Line Tools are absent, bootstrap requires the exact reviewed Google
archive URL and SHA-256 in the [release receipt](android-command-line-tools-provenance.md).
Download and SDK publication have separate approvals. Every ZIP member is
inspected before extraction; links, traversal, unexpected executables and bad
digests refuse. Private staging and Linux atomic no-replace publication preserve
occupied slots. Corrupt occupied tool slots require manual recovery, not replacement.

## Failure and recovery

Plans are rechecked after approvals. Repair renames only approved corrupt package
directories to `.panda-android-backup-<id>` siblings. On an ordinary caught vendor
failure, the process group is stopped/reaped before rollback. Failed replacement
outputs are retained as `.panda-android-failed-<id>`; backups restore independently.
Successful repair keeps backups for operator review. Never follow untrusted links
inside retained failure output.

If process cleanup cannot be confirmed, the operation reports **manual recovery
required**, preserves backup/output entries and withholds rollback and fallback.
Stop the vendor process group before inspecting/restoring or retrying. A pipe-close
error cannot erase this cleanup-uncertainty gate.

Power loss/SIGKILL cannot run Python rollback. There is no durable transaction
journal across Google's package manager. New packages, licenses and caches may
remain after a partial operation; nothing automatically uninstalls or erases them.
Retain evidence and inspect before any retry. This is a cooperative, quiescent
installer contract, not a live-host rollback guarantee.

## Fish, IDE and project adoption

Preview only the Android Fish target before a separately approved chezmoi apply:

```fish
set target "$HOME/.config/fish/conf.d/panda-android.fish"
chezmoi --refresh-externals=never --no-pager diff -- "$target"
# Apply only after reviewing and approving that exact target:
chezmoi --refresh-externals=never apply -- "$target"
set -Ux PANDA_ANDROID 1
```

Use the reviewed repository as the existing chezmoi source; never run bulk apply
or repoint the user's configured source as a side effect. `PANDA_ANDROID` enables
environment selection, not workstation-stage execution.

`studio-plugins.toml` has an empty allowlist. No Studio-specific compatible plugin
installer was verified. Plugins, font/theme/keymap preferences and settings
export/import stay preview/manual; existing preferences and accounts are preserved.
Use project-owned formatting and the project's Gradle wrapper. The profile does
not install system Gradle/Kotlin or run PandaWave builds. NDK/Rust targets/AAOS,
devices and emulators require new, independent authorization.

## Verification scope

Named offline tests use synthetic SDK/JDK files, fake vendor boundaries and
disposable Fish stage copies. They do not establish actual SDK, Studio, device,
Gradle or native compatibility:

```fish
python3 -B -m unittest discover -s tests -p 'test_android*.py' -v
fish --no-config -n bootstrap/setup-android.fish
fish --no-config -n bootstrap/setup-workstation.fish
fish --no-config -n home/dot_config/fish/conf.d/panda-android.fish
git diff --check
```

Historical host acceptance and private recovery logs are not part of this guide.
Live vendor/license/provenance acceptance remains a separate operator gate.
