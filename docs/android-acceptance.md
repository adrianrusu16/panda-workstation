# Android live acceptance gates

This is a preparation checklist for the optional Android profile, reviewed against
official documentation on 2026-11-01. **No live stage below has been accepted.**
Source review, synthetic tests and green CI support a draft; they do not establish
JDK, SDK, license, network, Studio or project acceptance on a machine.

Each stage needs a separate future authorization naming the machine, selected
paths, permitted execution/writes/network and evidence destination. Approval of
one stage does not authorize the next. Package/license, fallback, IDE, project,
device and emulator authority are distinct. Do not run this as one pasted script.
Keep machine paths, inventory, logs, account data and license decisions private;
publish only a sanitized outcome and source identity.

## Fixed source contract and current vendor guidance

| Item | Acceptance target |
|---|---|
| Terminal JDK | Existing, independently reviewed JDK 21 with `java` and `javac`; no system Java default change |
| SDK | One explicitly selected absolute user-local root in trusted private parents; quiescent, no concurrent Studio/SDK installer |
| Baseline | `platform-tools`; `cmdline-tools;latest`; `platforms;android-36.1` revision **1**; `build-tools;36.0.0` |
| Bootstrap | Google Linux `commandlinetools-linux-15859902_latest.zip`, package revision **22.0** |
| Archive SHA-256 | `4e4c464f145a7512b57d088ac6c278c03c9eea610886b35a5e0804e74eedf583` |
| Bundled launcher SHA-256 | `24ff3bac5db16e5bcc5fd2a54dc58041fd06db373389cd6442dedb004fe092be` |
| Launcher/application identities | Embedded launcher `1.0.15498356`; application version and capabilities **not established** until approved runtime checks |

The [Google download table](https://developer.android.com/studio) still lists
the exact Linux filename and archive digest above (181.8 MB). This HTML check
acquired no archive and does not attest to an existing installed tree. Preserve
the [source receipt](android-command-line-tools-provenance.md) and
[`toolchain.toml`](../config/android/toolchain.toml); a changed publisher page
requires renewed review, not an automatic pin update.

Google distinguishes the [IDE runtime, Gradle runtime and Java toolchain](https://developer.android.com/build/jdks).
JDK 21 is this profile's terminal target, not a claim that every Android project
or Studio needs 21. Review the project's AGP requirements and its pinned Gradle
version's [Java compatibility](https://docs.gradle.org/current/userguide/compatibility.html).
Keep Studio's bundled JBR and existing project settings unless separately approved.

Current [CLI guidance](https://developer.android.com/tools/agents/android-cli)
documents `--no-metrics` and Linux `~/.androidrc` configuration. The profile does
not add either: exact-release support and placement must first be established.
Before the first invocation, decide whether its disclosed network/cache/privacy
effects are acceptable. If opt-out must precede any execution and cannot be
verified without execution, stop; do not guess a flag or create configuration.
An update recommendation in moving vendor documentation does not authorize
`android update`, init, skills, auth or completion installation.

## Dependencies, resources and command context

Source checks need Git, Fish and Python 3.11+. Live stages additionally need a
reviewed Linux JDK and, as applicable, the selected SDK-local tools, a real
terminal, permitted Google HTTPS access and sufficient private staging/SDK/cache
space. Record a storage budget before acquisition; package sizes, extracted
size and launcher/application downloads are additional to the 181.8 MB archive.
Do not install dependencies as an implicit preflight action.

| Stage resources | Permitted effect only after that stage's approval |
|---|---|
| A | Read selected metadata and repository files; no Java/vendor execution |
| B | Execute the reviewed JDK as the user; no installation/default change |
| C | Google HTTPS, archive/staging space and one previously absent SDK tools slot |
| D | User process, Google network/application download, `~/.android/cache`, reads of `~/.androidrc`; actual vendor effects still require observation |
| E/F | Real terminal, interactive terms, selected SDK/package/license files and vendor caches/network; no account authentication |
| G | Same as F plus retained backup/failed-output sibling space for named corrupt directories |
| H | Selected Studio/JBR, GUI session, settings/project/cache paths and separately approved network; no device/emulator |
| I | Reviewed wrapper/JDK/build code, project outputs, Gradle caches and approved dependency/distribution/toolchain network |

[Studio's Linux requirements](https://developer.android.com/studio/install)
currently list glibc 2.31+, 8 GB RAM and 8 GB free space for Studio alone, with
additional resources for an emulator. Check the complete current CPU/OS/resource
requirements before approving IDE execution; these figures are not a host
compatibility result. No boot, GPU, virtualization, kernel or system-package
change is authorized by this guide. Devices and emulators are excluded.

All commands below are **future operator commands**, from the reviewed repository
root in Fish. Replace the two example paths with independently reviewed absolute
paths as part of the approved metadata inventory gate A; these are process-local
selections:

```fish
set -gx JAVA_HOME /absolute/reviewed/jdk-21
fish_add_path --global --path --move "$JAVA_HOME/bin"
set -gx ANDROID_HOME /absolute/private/Android/Sdk
```

Quote replacement paths containing spaces. `fish_add_path --global --path`
changes this process PATH only; it does not persist universal paths, edit
configuration or change system Java defaults. Before B, `command -s java`
and `command -s javac` must name the reviewed JDK bin paths.

Inspect any inherited `ANDROID_SDK_ROOT` separately. A conflict must stop rather
than be silently unset or redirected. Do not publish environment dumps. Do not
run the unqualified master bootstrap, bulk chezmoi apply, `yes` pipes, system
Java switches or a vendor command copied from documentation to bypass approvals.

## Ordered acceptance matrix

| Gate | Separate authorization and prerequisites | Exact future command or controlled step | Success evidence; failure stop |
|---|---|---|---|
| A — source and metadata inventory | Read the chosen JDK/SDK metadata and paths; approve the checkout and quiescent private root first. No vendor execution. | `git rev-parse HEAD`, `git diff --check`, then `fish --no-config bootstrap/setup-android.fish --plan` | Record source SHA and sanitized plan. All four baseline IDs, selected root, candidate path/hash and gaps must be understood. Exit 0 is a plan, not healthy/runtime acceptance. Stop on conflicting roots, unsafe paths, malformed metadata or an unexplained selected tool. |
| B — JDK execution | Independently review the selected JDK and authorize its code to run with this account. No JDK installation or global default change. | `"$JAVA_HOME/bin/java" -version` and `"$JAVA_HOME/bin/javac" -version`; then `fish --no-config bootstrap/setup-android.fish --check` | Both report major 21 and match the selected process PATH. `--check` also requires SDK presence, so an incomplete SDK may still exit 1 after successful JDK checks; retain those as separate results. Stop on unexpected code, version, path or startup behavior. |
| C — archive acquisition/publication, only if absent | Review exact Google URL/digest, applicable terms, network destination, staging/cache budget and target slot. JDK and SDK selection must already be approved. | `fish --no-config bootstrap/setup-android.fish --install`; authorize **only** the download and publication prompts at this gate, then decline any further runtime/package prompts. | Archive digest and validated member layout match; revision 22.0 slot publishes without replacing an occupied entry. If no other baseline gaps remain, the helper returns after bootstrap without runtime checks. Declining later prompts is an intentional stopped run, not full install success. A digest/member mismatch or occupied/corrupt tool slot stops for manual review; never overwrite it. If tools already exist, skip acquisition and review their identity instead. |
| D — preferred launcher, capabilities and inventory | Approve the exact SDK-local launcher/hash, reviewed JDK and disclosed network/application/cache effects for this invocation. Existing supporting code still requires review; a launcher hash is not whole-tree authentication. | `fish --no-config bootstrap/setup-android.fish --cli-check` on a complete baseline. For an incomplete baseline, `--install` performs the same runtime verification and additionally lists available versions; decline package/terms prompts until E/F. | Capture actual application version, exact SDK root, supported commands/options and installed/available revisions separately. A full `--cli-check` needs healthy local baseline metadata. Stop on unsupported output/options, root mismatch, unknown required revisions outside the documented pinned 22.0 exception, or unexpected network/config effects; do not convert an arrow target into installed evidence. |
| E — licenses | Review the exact proposed missing package set and applicable terms in a real terminal. Approval to display terms is not acceptance of them. | Continue an independently authorized `--install`/`--repair` session through its license-review prompt; legacy `--licenses` remains interactive inside that approved route. Preferred CLI may present terms during package execution after F. | The operator personally accepts only wanted terms or declines. Legacy review may enumerate all outstanding SDK licenses; decline anything outside this authorization. No `yes` pipe, fabricated acceptance or license-file copying. If the vendor cannot present enough terms before an unacceptable write, decline/stop; prior network/cache/license effects may remain. A separate standalone license invocation is not required or implicitly authorized. |
| F — exact missing-package install | Authorize the listed package changes separately after D/E, including further interactive terms. No healthy package reinstall or extra package authority. | `fish --no-config bootstrap/setup-android.fish --install`, answering each current prompt only after rechecking its proposal. | Only missing baseline IDs requested; platform 36.1 revision 1 and Build Tools 36.0.0 pass post-install metadata/layout. Repeat `--plan`; then separately approve `--cli-check` for runtime inventory. A healthy repeat `--install` is a no-op without vendor execution. Stop on unavailable exact revisions, changed SDK state, extra changes, timeout, refusal or unconfirmed cleanup. |
| G — repair, only when needed | Explicitly name corrupt package directories, retained backup locations, space budget and restoration authority. Do not damage a real SDK to manufacture a test. A destructive failure drill needs a separately authorized disposable SDK. | `fish --no-config bootstrap/setup-android.fish --repair` | Only approved corrupt baseline directories are retained as backups; healthy/extras stay untouched; post-checks pass. Successful repair keeps backups for separate review. On any failure preserve backups/output and stop. Uncertain cleanup forbids rollback, fallback and retry; partial vendor changes are not automatically undone. |
| H — IDE | Separately approve one installed Studio distribution, launch identity, existing settings/import decision, project, caches/network and resource budget. Do not install Studio or plugins as part of this gate. | Use the explicit absolute launcher selection and validation block below; do not derive execution from inherited `ANDROID_STUDIO_HOME` or PATH. | Manually confirm About/build/runtime, selected SDK and project Gradle JDK; preserve settings. Decline unsolicited setup-wizard downloads/updates/imports until separately approved. No CLI Studio dispatch, account login, plugin install, emulator/device or GPU workaround. GUI launch alone is not project acceptance. |
| I — project verification | Select one reviewed project and exact existing task; approve its Gradle wrapper, build/plugin code, distribution/dependency/toolchain downloads, caches, writes and licenses. Review compatibility before execution. | Use the project commands below, one at a time. | Wrapper/JDK match the reviewed project; the authorized task succeeds with expected outputs. Stop on a version mismatch, unapproved download/task/device access, terms, unexpected writes or failure. No automatic project migration, wrapper upgrade or fallback to system Gradle. A build does not prove device/emulator/runtime behavior. |

The install verifier uses the selected absolute launcher with `--sdk=<root>` for
`-V`, `--help`, `info sdk`, `sdk --help`, `sdk install --help`, and `sdk list`;
install planning adds `--all --all-versions`. Required help includes
`--ignore-outdated-xmls` and `--no-downgrade`. These are the helper's internal
sequence, not additional commands to run outside its approval boundary.
Current [list](https://developer.android.com/tools/agents/android-cli/commands/sdk_list)
and [install](https://developer.android.com/tools/agents/android-cli/commands/sdk_install)
references document these flags, slash package IDs and `package@version`.
The profile requests `platforms/android-36.1@1` and
`build-tools/36.0.0@36.0.0`; moving documentation does not relax those pins.
The narrow [unknown Command-Line Tools exception](android-cli.md#installed-revisions-and-suggestions)
requires matching healthy 22.0 metadata, source archive/candidate identity and exact
launcher digest. Its warning retains an unknown CLI revision; it is not an
authenticated whole-tree result or a numerical installed version.

For H, independently review the installed distribution and actual launcher,
including any symlink targets, then replace this example with its approved
absolute executable path. Google's Linux layout uses `bin/studio`; another layout
needs its own review. File/executable checks are selection checks, not publisher
authentication. This block deliberately replaces inherited selection and has no
PATH fallback; an invalid path produces a nonzero STOP without launching anything.

```fish
set -l reviewed_studio_launcher /absolute/reviewed/android-studio/bin/studio
if not string match -q '/*' -- "$reviewed_studio_launcher"; or not test -f "$reviewed_studio_launcher"; or not test -x "$reviewed_studio_launcher"
    printf 'STOP: select the reviewed absolute Studio executable before launching.\n' >&2
    false
else
    "$reviewed_studio_launcher"
end
```

For I, replace both example values with the approved absolute project path and
one task already defined/reviewed there. The example task is not a promise that
every project contains it. Review wrapper scripts/JAR, distribution URL and
checksum, settings/build scripts, plugins, repositories and toolchain resolvers
first: even `--version` executes project-supplied code and may download Gradle.

```fish
set -l reviewed_project /absolute/reviewed/project
set -l reviewed_task :app:assembleDebug
cd -- "$reviewed_project"
./gradlew --version
# Stop and assess that result before separately approving the build:
./gradlew --no-daemon --console=plain "$reviewed_task"
```

## Fallback and failure custody

Legacy SDK Manager is [deprecated by Google](https://developer.android.com/tools/sdkmanager),
but remains an explicitly reviewed compatibility route. If the preferred CLI
contract fails, approve or decline **unverified SDK-local code running with the
account's privileges** separately from network/cache, packages and licenses.
The prompt's slot/tree SHA-256 records local entries, modes and content; ownership
and stability establish no publisher provenance. Independently review the
launcher, supporting tree and JDK. A changed tree refuses before listing,
licenses or install. Timeout, interruption, refusal or uncertain cleanup must
never silently choose fallback. Do not bypass this with a direct PATH command.

The runner assumes it is the sole child reaper. Linux `waitid(WNOWAIT)` retains
the leader until the final process-group signal, then performs a bounded reap.
Lost/reaped child custody requires manual recovery without signaling a possibly
reused group ID. The TERM grace is bounded; an observed leader exit escalates
immediately. Post-reap I/O failures preserve uncertainty. External reapers,
detached sessions, hostile same-UID writers and descendants left after an
otherwise successful command are outside this cooperative contract. Launcher
success is not proof that descendants stopped.

If cleanup is unconfirmed, preserve the reported backup/output locations and
private evidence. Do not restore, signal a guessed PID/group, retry or select
fallback; separately authorize inspection and establish process custody first.
Even ordinary caught failures can leave new packages, licenses and caches.
SIGKILL/power loss cannot run rollback; no durable cross-vendor transaction or
whole-SDK restoration is claimed. Shared/untrusted parents and concurrent writers
remain unsupported. See [recovery details](android-development.md#failure-and-recovery).

## Acceptance record and retained gates

For each authorized stage, privately record source SHA, reviewed tool identities,
selected paths, authorization scope, actual command, exit status, bounded output,
observed writes/network and any leftover processes/entries. Do not record secrets
or publish local machine inventory. Unobserved effects stay **unknown**; a fake
test is not a measurement of Google's real launcher or descendants.

Report each stage as not authorized, blocked, declined, failed or observed passed.
A declined later prompt may leave an earlier acquisition stage complete; it does
not pass the whole command. Keep PR/runtime readiness draft until the required
live stages have independent review and explicit operator acceptance. Devices,
emulators, auth, NDK/Rust/AAOS, automatic metrics configuration, plugin/settings
apply and Setup Manager Android apply remain outside this acceptance scope.
