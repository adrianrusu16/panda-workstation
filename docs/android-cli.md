# Android CLI selection and approval contract

The profile prefers an existing SDK-local `android` candidate after explicit
per-invocation runtime approval. It never installs a separate unverified CLI,
persists a trust bypass or executes a PATH-shadowing candidate. Legacy SDK Manager
is an explicitly approved compatibility fallback.

## Three independent version identities

| Identity | Preserved evidence |
|---|---|
| Command-Line Tools package | Revision 22.0; Google archive build 15859902 |
| Bundled native launcher | Embedded version 1.0.15498356; SHA-256 `24ff3bac5db16e5bcc5fd2a54dc58041fd06db373389cd6442dedb004fe092be` |
| Android CLI application | Synthetic CLI 1.1 compatibility fixture; installed version/capabilities require a new approved check |

The [release receipt](android-command-line-tools-provenance.md) and metadata-only
ZIP fixture preserve source-review provenance, not current host observations.
The bundled launcher may download a separate application and write caches even
for version/help. Approval discloses network, launcher/cache writes and reads of
`~/.androidrc`; those commands are not offline metadata inspections.

## Selection and runtime checks

`--plan` discovers candidates without executing them. Preferred slot is
`cmdline-tools/22.0`, then supported existing versioned/latest slots. Candidate
and metadata paths must be SDK-local, user-owned, non-symlink and not group/other
writable. Slot/revision mismatch refuses; PATH shadows are reported and ignored.
The owned launcher digest is rechecked before each approved command. These are
cooperative path/content checks, not authentication against hostile same-UID peers.

`--cli-check` requests permission, then uses the exact SDK-local executable and
explicit `--sdk=<selected-root>` for version, help, `info sdk`, SDK help/install
help and package listing. Unsupported output or a different SDK root refuses.
Runtime environment forwards selected HOME/JAVA_HOME/locale/terminal values and
fixed JDK/SDK bins, excluding unrelated auth and launcher override variables.
It does not create an authentication home or change `CODEX_HOME`.

Captured stdout/stderr are bounded while the process runs. Timeout, interruption
and post-spawn setup/I/O failures stop/reap the process group before returning.
Interactive package/license operations inherit the real terminal. If cleanup
itself fails, **manual recovery is required**: no fallback or repair rollback
may proceed while the vendor may still be active. No fake test proves real
vendor process, license or cache behavior.

## Installed revisions and suggestions

The eight-row [synthetic text fixture](../tests/fixtures/android/cli-1.1-synthetic-installed.txt)
recreates CLI 1.1 layout and version syntax. Its extra package IDs, revisions and
descriptions are fictional; it contains no captured machine inventory. Parsing
keeps installed, available and arrow-suggested revisions distinct:

```text
cmdline-tools/22.0 unknown -> 22.0.0 Android SDK Command-line Tools
platforms/android-36.1 1.0.0 Android SDK Platform 36.1
```

`unknown` remains unverified. An arrow target never becomes installed-version
evidence. Numeric `1`, `1.0` and `1.0.0` may compare equal; nonzero components,
preview/rc syntax, unknown values, leading-zero ambiguities and malformed fields
are never discarded. Unsafe paths, duplicate installed IDs, unsupported sections,
pipe tables, controls and truncated output refuse.

Only the pinned 22.0 Command-Line Tools path may use the narrow unknown-revision
warning after matching healthy local metadata, package path, source archive pin,
candidate identity and exact launcher digest. The warning retains uncertainty;
it does not authenticate every installed archive byte or equate an update target
with the installed revision. Other unknown required packages fail closed.
Platform `android-36.1` still requires exact local API identity and revision 1.

## Package changes and fallback

Healthy metadata/layout produces a no-op without running vendor tools. Missing
components require separately approved runtime checks and exact package/terms
consent. CLI package IDs use slashes; platform and Build Tools revisions are
requested explicitly (`platforms/android-36.1@1`, `build-tools/36.0.0@36.0.0`) with
no-downgrade behavior. No unqualified update, removal or silent substitution runs.

If the CLI contract fails, legacy fallback needs its own approval for startup,
repository/network/cache effects. Available platform revision must be exactly 1;
post-install metadata checks apply to both routes. Refusal, timeout, interruption
or unconfirmed process cleanup never silently triggers fallback. Existing extra
SDK packages are preserved. See [installation and recovery](android-development.md).

## Optional capabilities remain gated

| Capability | Required independent review |
|---|---|
| SDK info/list | Runtime/network/cache approval; no package-change authority |
| Build/describe/analyze/preview | Project selection and write/dependency/build effects |
| Studio/device/emulator/screen/input/run/install | IDE, device and virtualization authorization |
| init/skills/auth/updates | Agent-directory, account, network and user-profile effects |
| Completion | Vendor documentation supports Bash/Zsh; no automatic Fish generation |

The metrics opt-out flag remains deferred until exact-version help establishes
its supported spelling/placement. No guessed `--no-metrics` or `.androidrc` write
is introduced. Review the selected release's privacy behavior before execution.
No CLI init, skill installation, update, auth, IDE or device operation is part of
automatic setup.

Official references: [CLI overview](https://developer.android.com/tools/agents/android-cli),
[SDK commands](https://developer.android.com/tools/agents/android-cli/commands/sdk),
[legacy SDK Manager](https://developer.android.com/tools/sdkmanager). Documentation
for another release does not establish current installed capabilities.
