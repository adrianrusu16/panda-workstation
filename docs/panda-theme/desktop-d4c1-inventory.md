# D4C1 — sanitized saved-file host inventory

Status: **read-only saved-file inventory; no live-session verification**.
Prepared 2026-10-26; final review completed 2026-10-27. Base: 215522fb36d9f4f29922fed83bd568bf7aa6a442.
Branch: feat/panda-desktop-d4c1. The observations below are the accepted offline
review snapshot; publication is separately authorized. No new host observation
was made during finalization. Timestamp drift and runtime pins remain unresolved.

## Collection boundary

Seven exact user configuration files were opened using O_RDONLY, O_NOFOLLOW,
O_NOATIME and a bounded regular-file reader. Every path component was bound
through directory descriptors; files required safe ownership, no group/world
write and one hard link. Before/after receipts include inode/device, owner/group,
mode, link count, size, atime/mtime/ctime, SHA256 and supported xattr hashes.
There is no timestamp reset, permission change, lock acquisition or plain-read
fallback. Raw configuration was held in memory only and was never saved.

Allowlist: plasma-org.kde.plasma.desktop-appletsrc, plasmashellrc, kwinrc,
kdeglobals, plasmarc, kactivitymanagerdrc and kwinoutputconfig.json under
the user's configuration root. No unrelated home data, historical rehearsal
tree, activity-history database, hardware/sysfs interface or session bus was read.

Relevant package versions/file ownership lists came only from pacman -Q/-Ql.
These do not run package scripts or services. The ksystemstats entry is package
metadata only; neither the program nor its backend was queried or activated.

Private evidence lives in this worktree's ignored .local-ai/d4c1 directory:
new directories mode 0700, files 0600. Real IDs, parent paths, saved order,
output identifiers and file fingerprints stay private. Activity labels are
hashed, and credential-like launcher values would be withheld. Public fixtures
use synthetic IDs/pins and are not host-operable inventories.

## Fresh observations

| Area | Saved-file / installed-package observation | Limitation |
| --- | --- | --- |
| Desktop | One folder-view desktop containment; virtual desktop count 1 | Current activity and runtime output mapping unobserved; do not force the specification's initial three-desktop goal |
| Panel | One horizontal bottom-panel containment | Saved panel profiles include floating=true and thickness 46/44; which profile is current was not established |
| Panel order | Seven ordered slots: launcher, pager, icons-only tasks, margins separator, tray, digital clock, show desktop | All existing identities/order/settings are preserved; no top bar or new dock is created |
| Desktop clock | Absent on saved target desktop; one clock belongs to panel | Panel clock is ineligible for repurposing as the independent desktop clock |
| Media | No saved instance found | Any first desktop media instance would be a separately authorized addition |
| Weather | One nested tray instance, no desktop instance | Preserve tray ownership; do not reparent or activate it |
| CPU / RAM | No saved dedicated desktop instance found | No sensor/backend query, so this is not a data-availability claim |
| Tray | 16 nested applet identities under the existing tray applet | Exact IDs/configuration remain private; no flattening or container reconstruction |
| Task pins | No launcher list is serialized for the saved task-manager instance | **Unknown, not zero.** Runtime ordered pins were not queried or synthesized from the D4B sample |
| Activities | One saved registry entry; label retained only as a hash | Current activity is not established from the selected saved fields |
| Outputs | Saved mode describes 1920×1080, scale 1, normal transform; historical setup records also exist | This is configuration evidence, not a fresh scanout/hotplug/current-topology observation |
| Style | Packaged default, breeze-dark and breeze-light resources are listed | No explicit style override or active font/icon selection was found in the selected globals; actual runtime defaults remain unverified |
| Font | Noto package and native file path are present; vendored D4B font remains hash-verified | Native root-owned font read with O_NOATIME was refused; no fallback or permission workaround |
| Geometry | Saved layout fields/relationships are retained privately where available | No desktop cards exist to measure; no live scene geometry was queried |

Nested applets are stored under Containments / panel / Applets / tray / Applets /
child in this saved configuration. They are not extra desktop widgets. The
assessment classifier includes them as non-reusable nested instances.

## Installed versions

| Component | Version |
| --- | --- |
| plasma-workspace, plasma-desktop, libplasma, kdeplasma-addons | 6.8.1-1.1 |
| plasma-nm, plasma-pa, ksystemstats | 6.8.1-1.1 |
| libksysguard | 6.8.1-1 |
| Qt base | 6.12.0-3.1 |
| Qt declarative | 6.12.0-2.1 |
| Qt SVG | 6.12.0-1.1 |
| KConfig, KCoreAddons, KPackage, KColorScheme, KIconThemes | 6.31.0-1.1 |
| Kirigami | 6.31.0-1 |
| Breeze | 6.8.1-1.1 |
| Breeze icons | 6.31.0-1.1 |
| Noto fonts | 1:2026.10.01-1 |
| Fontconfig | 2:2.18.3-2.1 |
| Pango | 1:1.58.2-1.1 |

The package database reports 25 relevant installed packages and one optional
queried name absent (ttf-noto; noto-fonts is installed). Packages do not prove
loaded process versions: the daily session may predate an upgrade. No Plasma
GUI, qtdiag, widget loader, compositor, D-Bus interface or sensor command ran.

## Preservation and access limitations

Per-read before/after fingerprints matched for all seven configuration files.
The final whole-assessment recheck matched complete initial receipts for six.
For kwinoutputconfig.json, **mtime and ctime changed between observations**;
bytes/SHA256, inode/device, owner/mode/link count, size, atime, parent bindings and
xattrs still matched. Each individual read was metadata-stable. The actor and
reason for the intervening timestamp changes were not established; identical
bytes do not justify claiming whole-assessment metadata preservation.

Host collection stopped on that mismatch, and both receipts remain in private
preservation-final.json. No timestamp reset, further host-config read or
workaround followed. Saved output facts are provisional; a separately authorized
fresh, stable inventory is required before native planning can use them.

The original canary index and four untracked-file hashes match their recorded
historical fingerprints. Four prior checkout HEAD/branch/status records and
seven known repository-file receipts also matched a second D4C1 observation.
Those checkout observations were collected late in this task, so their complete
metadata stability claim covers that interval; it is not a fabricated start-of-task
metadata baseline. All previous checkouts remain untouched.

One attempted read in the sandbox refused unexpected parent ownership. Metadata
inspection established that sandbox / and /home were mapped to UID 65534,
while trusted-host ownership was UID 0. The guard was not relaxed. All successful
host reads used the original trusted-host context with verified 0/1000 ownership.
The unsupported sandbox read and root-owned native-font read stopped without
plain-read fallback or changes to permissions/timestamps.

The reader fingerprints POSIX metadata and supported xattrs, including an ACL
xattr if exposed. It does not independently inspect filesystem-specific flags,
other ACL mechanisms or in-memory unsaved KDE state. The strict KConfig subset
does not evaluate expansions, flags, includes or unknown fields. Identity
classification refuses flagged/escaped containment or plugin identities rather
than treating unevaluated identity syntax as absence. Other raw values remain
unassessed, never expanded into defaults or executable expressions.

The approved theme specification is local and Git-ignored, absent from main.
It was read with O_NOATIME and an unchanged before/after stat record; its hash
is in the plan. It was not copied into tracked source.

No D3B1A roots were accessed. No config restoration, desktop change, installation,
service activation, GPU probe, theme-manager change, commit, push or merge occurred.

## Private evidence available for local review

- config-initial-receipts.json: seven file/parent fingerprints; no raw configs.
- preservation-final.json: six exact matches and the output-config timestamp mismatch.
- checkout-preservation-initial.json / checkout-preservation-final.json: known
  repository fingerprints, prior checkout status and preservation comparison.
- selected-host-facts.json: filtered relevant saved fields.
- role-bindings-private.json: exact IDs, parent paths and binding classification.
- package-versions.json and relevant-package-resources.json.
- resource-receipts.json and collection-status.json: supported/refused resource reads.
- saved-output-modes.json: selected saved mode facts, not hardware probes.
- clock-media-candidate-private.json: exact saved parent/role references and gated proposal.
- upstream/: original source receipts, pin investigation and immutable source evidence.

These are inventory receipts, **not a complete configuration backup or a proven
recovery mechanism**. They must not be used for restoration.

## Final verification

- Complete post-review Python suite: **314 tests passed** (68.375 seconds);
  17 D4C1 reader/parser/candidate regressions pass. No skipped tests were reported.
- The preceding full run passed 313 tests before the final refusal regression.
- Fish syntax: three applicable desktop/bootstrap scripts pass fish -n.
  bootstrap/validate.fish also passes all 13 Fish scripts and 54 package entries.
- Candidate schema/model validation and published-fixture regeneration match
  exactly; Python compilation performed in memory, without cache files.
- All 20 source lengths, SHA256 hashes, Git blob hashes and immutable-tree
  memberships verified; independently checked by the fresh final reviewer.
- git diff --check passes. All nine untracked files additionally pass explicit
  no-index whitespace checks; local Markdown links resolve.
- HEAD stays at the integrated main base; index and tracked diff are empty.
  Nine intended new files comprised the original untracked review set.
- Private evidence ownership/modes checked: UID/GID 1000:1000, directories 0700,
  files 0600; ignored from Git. Evidence is retained, with no historical cleanup.
- Final protected-file status: **7/7 content hashes match, 6/7 complete receipts
  match**. Output-config mtime/ctime drift stops host collection and blocks use of
  that snapshot as a fresh stable native baseline.
- Original canary index/four untracked historical hashes match; prior checkout
  status/HEAD and seven known repository-file receipts match the recorded interval.

No native visuals, live geometry, unsaved task pins, provider availability or
recovery mechanics were tested. D3B1A remains unresolved and untouched.

## Complete public changed-file inventory

All nine are new files in the separate D4C1 worktree:

1. docs/panda-theme/desktop-d4c1-plan.md — scope, decisions and verification ledger.
2. docs/panda-theme/desktop-d4c1-compatibility.md — five-role and panel API matrix.
3. docs/panda-theme/desktop-d4c1-inventory.md — this sanitized preservation report.
4. docs/panda-theme/desktop-d4c1-candidate.md — future clock/media changes and gates.
5. docs/panda-theme/d4c1/kde-source-references.json — immutable source provenance.
6. docs/panda-theme/d4c1/clock-media-candidate.json — non-executable synthetic plan.
7. tests/fixtures/desktop/assessment/sanitized-shape.json — synthetic saved layout.
8. tests/test_desktop_assessment.py — read/refusal/identity/schema regressions.
9. theme/panda/common/desktop_assessment.py — pure reader/parser/fixture helpers.

Existing D4A/D4B layout, installer, assets, palettes, source and fixtures are
unchanged. Private local evidence is additional ignored material, not PR content.
Its final public hashes/private object inventory is in
.local-ai/d4c1/final-review-manifest.json; scope-validation.json retains the
earlier scope check. verification-final.log is the final 314-test run;
verification.log and verification-after-review.log preserve earlier runs.

## Publication verification

The accepted nine-file manifest matched exactly before finalization. A fresh
314-test run passed (73.663 seconds), along with the applicable Fish checks,
all 13 Fish scripts and 54 package entries. Publication changes only clarify
the report's historical review state; source, tests, fixtures and source pins
are unchanged. New private logs are retained separately under the ignored
.local-ai/d4c1-finalization directory, outside the PR.

No fresh protected-host read was attempted. The qualified original preservation
result, unknown runtime pins and every native/recovery authorization gate stand.
