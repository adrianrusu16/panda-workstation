# Android Command-Line Tools release verification

Preserved historical source receipt. Recovery did not refetch the archive or
revalidate publisher contents; future releases need new review and approval.

Verified on **2026-10-27** for source preparation and archive inspection only.
Live installation, SDK publication and vendor execution remain separately approved
actions. This record resolves the metadata blocker in the independent source
review dated 2026-10-26; it makes no SDK/Studio/Gradle runtime compatibility claim.

## Publisher and archive evidence

The official [Android Studio download page](https://developer.android.com/studio)
was inspected in the operator's browser. Its Linux Command-Line Tools row listed
the filename and SHA-256 below. Opening that exact row displayed the Linux SDK
download agreement dated April 28, 2026. After explicit operator confirmation for
this archive inspection, the dialog exposed the exact Google distribution URL.
No SDK license-acceptance files or credentials are included in source or fixtures.
This inspection's approval does not authorize future downloads or installation.

| Field | Verified value |
|---|---|
| Filename | `commandlinetools-linux-15859902_latest.zip` |
| Exact URL | `https://dl.google.com/android/repository/commandlinetools-linux-15859902_latest.zip` |
| Publisher page | `https://developer.android.com/studio` |
| Publisher row size | 181.8 MB |
| Downloaded size | 181833628 bytes |
| Publisher and independently computed SHA-256 | `4e4c464f145a7512b57d088ac6c278c03c9eea610886b35a5e0804e74eedf583` |
| Internal package revision | `22.0` |
| Internal package path | `cmdline-tools;22.0` |
| ZIP members | 141 regular files; only `cmdline-tools/` top-level tree |
| Total uncompressed bytes | 181805618 |
| ZIP compression method | Stored (0) |
| ZIP CRC validation | All 141 entries passed |

The authenticated archive's complete `source.properties` is:

```properties
Pkg.Revision=22.0
Pkg.Path=cmdline-tools;22.0
Pkg.Desc=Android SDK Command-line Tools
```

**15859902 is the filename build identifier, not the package revision.** The
future publication destination is `cmdline-tools/22.0`, under the explicitly
selected SDK root. `cmdline-tools;latest` remains the baseline management request;
the helper reports the resolved installed revision and reuses healthy versions.

## Observed layout and extraction safety

The archive contains 11 direct `bin/` launchers, including `sdkmanager` and the
newer `android` launcher, `lib/` JARs/classpaths, `source.properties`, `NOTICE.txt`
and `lib/README`. No absolute/traversal paths, links, special files, encrypted
entries or duplicate names were observed. All 141 regular entries have ZIP Unix
mode `0100755`, including JARs and metadata; reproducing this revealed the
previous synthetic fixture's narrower permissions assumption.

The extractor now accepts executable source modes for expected SDK data:
`lib/**/*.jar`, `source.properties`, `NOTICE.txt` and `lib/README`. It writes those
as **0644** and direct `bin/` files as **0755**. Unexpected executable locations,
such as `lib/install.sh`, remain rejected. Traversal, links, duplicate names,
special files, checksum validation, size limits and no-replace publication
controls are unchanged.

The real archive was safely extracted only into a private verification directory
under `/tmp`. All 141 extracted content hashes match their corresponding ZIP
members, and all resulting modes match the 0755/0644 policy. No extracted file
was executed, and `publish`, `--install`, `--repair`, SDK Manager, Java and Studio
were not run. The downloaded archive and real binaries are excluded from the
source tree and review patch.

`tests/fixtures/android/command-line-tools-22.0.json` records the observed member
names, sizes, CRCs, compression methods and Unix modes. It contains factual
metadata and the three-line package properties, with no vendor binaries. Tests
rebuild that layout using inert payloads to verify extraction and normalization
offline. Its filename/URL/hash fields describe the authenticated real archive;
generated synthetic ZIPs use their own computed checksum in tests.

## Limits and future release changes

HTTPS publisher provenance plus independent byte hashing establishes this pin's
integrity; this is not detached-signature verification. Repeating the page's hash
from the independent review alone was insufficient: the browser page, exact
download link, actual bytes, CRCs, layout and revision were checked in this run.
The first sandboxed download failed DNS resolution; the separately approved
network download to the verification directory succeeded. No network policy was
changed. Raw archive/evidence locations and verification results are recorded in
the parent handoff evidence directory, not installed SDK paths.

The included `sdkmanager` and `android` launchers were not executed. The independent
review flags SDK Manager deprecation; a separately approved controlled live pilot
must establish the pinned SDK Manager's actual behavior. This task does not swap
the CLI contract or claim that the newer CLI is compatible. Plugins, IDE settings,
master bootstrap integration and PandaWave builds remain outside this follow-up.

For a future release, independently recheck Google's Linux row and exact link,
download into private temporary storage after appropriate agreement approval,
verify the published SHA-256, inspect `source.properties` and all ZIP metadata,
and exercise safe extraction before changing the manifest pin and its fixture.
Keep fail-closed behavior when any publisher metadata or layout cannot be verified.
