# Official Media Controller: offline candidate and native trial proposal

D2b prepares the official `org.kde.plasma.mediacontroller` for issue #34 and a
future clean workstation. Laptop-specific D2a live acceptance is deferred; its
deleted-wrapper and denied-access findings do not demonstrate failure of Digital
Clock or D1. Preserve that evidence and its unresolved findings. No additional
laptop observation, package-history probe or executable exception is included.

This candidate runs without Plasma, MPRIS, Qt or network providers. It creates
no widget, plays no media and reads no host configuration. Existing clock and
historical clock/media candidate APIs, synthetic visual fixtures and preview
assets remain unchanged. No custom media plasmoid is introduced.

## Explicit offline inputs

Run from the repository:

    python3 -B theme/panda/common/desktop_cli.py media-candidate --fixture tests/fixtures/desktop/assessment/sanitized-shape.json --plasma-version 6.8.2 --media-contract theme/panda/common/desktop/media-6.8.2.json --media-fixture tests/fixtures/desktop/media/playing.json

The existing Fish wrapper accepts the same arguments. Substitute `paused.json`,
`no-player.json` or `unavailable.json` for the other shipped scenarios. Output is
stdout-only JSON. The pure builder/validator is `desktop_media_candidate.py`.
Version is an explicit upstream-source claim, not installed/runtime discovery.

The source contract is byte-pinned to SHA-256
`6c0104340b7b4e448ea0cb0228f15ce2fb9aedc60ccbf367784cd0a125cb45a7`.
It retains the exact source tree inventory and selected blob/SHA-256/size receipts
for plasma-workspace commit `30beb0095873364c6b34ebcfd292ecafd4db7f61` (`v6.8.2`).
The checked source inventory has no per-instance `main.xml`; the contract is not
a fabricated native configuration schema. New releases require separate source
review, contract update and tests. Future AMD hardware does not validate this pin.

Only one additive desktop instance is proposed, with a **null ID**, empty native
settings and zero executable operations. Existing or ambiguous desktop media
instances are refused. Panel/tray media is preserved, never reused or reparented.
The complete input fixture and synthetic media state are copied and fingerprinted;
repeated planning changes neither and allocates nothing. Candidate validation
rejects forged native claims, actions, settings or unknown fields.

No-player/unavailable fixtures have zero players, empty metadata, no artwork,
unknown time values and all capabilities false. Active fixtures require a player.
`stopped` is also supported because a present MPRIS player can be stopped; it is
not silently treated as absent. Fixtures contain no bus name, PID, artwork URI
or host path. `players` is a synthetic count (0–16), not a player-selection rule.

## Verified 6.8.2 source contract and limits

| Area | Reviewed behavior | Candidate/native distinction |
| --- | --- | --- |
| Plugin/package | CMake registers `org.kde.plasma.mediacontroller` in plasma-workspace | No installed binary or current player is attested |
| Configuration | No per-instance XML; main removes the Configure action | Native settings are strictly `{}`; unknown settings are refused |
| Global audio | GlobalConfig watches `plasmaparc`, General/VolumeStep, default 5 | Never read or write it during offline planning; preserve it in a future trial |
| Capabilities | libkmpris effective play/pause/previous/next/seek values include CanControl | Synthetic raw booleans are projected through the same conjunction |
| Primary control | Full UI chooses pause while playing, otherwise play | Candidate exposes the relevant enabled action, not an invocation |
| Missing player | Main uses null-safe defaults and guarded dispatch wrappers | `unavailable` is an explicit synthetic uncertainty state; stock may show the same empty UI as no-player |
| Track metadata | Compact view selects an icon when track is empty or in tray, otherwise adapts | Empty titles stay empty; a playing state does not guarantee a desktop row/control layout |
| Duration/position | Native lengths and positions are microseconds | Candidate converts to seconds once; unknown values stay null, with no invented percentage |
| Artwork | Stock QML dynamically loads the reported image URL and handles loading/error | Fixtures accept only sample/none/unavailable, emit no URI and never load an image |
| Full representation | Minimum 14×10, preferred 20×20, maximum 40×40 Kirigami grid units | Pixel size, margins, font metrics and actual fit remain unverified |
| Compact representation | Content/form-factor dependent row, icon or tray view; no fixed numeric minimum established | Do not infer a universal compact minimum or guaranteed visible controls |

Source references are in the [reviewed contract](../../theme/panda/common/desktop/media-6.8.2.json).
The UI and C++ capability bindings were inspected together: the QML control's
`canPlay` etc. are effective values, not independent raw MPRIS flags. Main wrappers
also check for a current player. This is not proof that every native shortcut,
gesture or changing-player race satisfies the same predicate; those need native
tests. D2b contains no custom dispatch layer or change to KDE behavior.

For synthetic states, play requires a present paused/stopped player, CanControl
and CanPlay; pause requires playing, CanControl and CanPause. Previous/next require
a present player, CanControl and their respective capability. Seek possibility
is reported only with CanControl, CanSeek and known duration; seeking is not an
operation in this candidate or an approved trial action by default.

Fixture microsecond values are bounded to one day solely to keep test inputs
small and explicit; that is not an MPRIS protocol limit. Duration zero, booleans,
NaN, negative or inconsistent time values are refused. Unknown length and known
position are allowed but produce no progress fraction. The model does not parse
arbitrary MPRIS wire data or promise how stock native widgets handle bad metadata.

## Geometry and five-flavor consistency

Shared Panda design preferences are compact **288×120** and expanded **352×168**
logical pixels, identical for Minimal, Cyber, Gothic, Hybrid and PandaWave.
`wave` remains an alias for PandaWave. They do not request native representation
switching or establish that the full 14×10-grid-unit minimum fits. Measure native
units/margins and available space; never assume an 18-pixel grid unit or force
full controls into a short card. Do not use the no-op Widget.setGeometry setter.

The baseline inherits the current stock Plasma style. No global theme, font,
palette, blur or shader is enabled. Existing five-flavor D4B previews are synthetic
design samples, not capability-aware native screenshots. Their prior control
drawings are not changed or presented as runtime evidence by this slice. Exact
Panda framing, typography, artwork crop, focus/disabled contrast and spacing
parity remain later appearance work. Opaque-first remains the Panda default.

## Separate native trial specification — not current authorization

1. **Scope and source.** On the separately approved target host/session, verify
   actual installed and running Plasma/Qt/plugin identities and revalidate this
   plugin/configuration against that release. A different version blocks use of
   this 6.8.2 contract. Do not transfer laptop IDs, output ordinals or receipts.
2. **Per-operation gate decision.** Review whether strict compositor executable
   attestation is necessary for the specific attended UI-only operation and what
   equivalent evidence would suffice. Any change to existing gates needs explicit
   owner approval before execution. This document changes none. AMD does not
   remove procfs/capability restrictions or establish trust, opacity or fit.
3. **Target and preservation.** Identify the real output/scale/activity and desktop
   containment D, existing desktop media and every panel/tray instance, pins,
   wallpaper/style and desktop count. Refuse ambiguity/duplicates. Prepare fresh
   private copies and stable before/quiet/final receipts for the seven existing
   protected files and propose adding `plasmaparc` to the media preservation scope.
   Approval must cover the exact protected keys/files, allowed new-instance
   persistence and disclosed cache effects. Do not assume whole-session atomicity.
4. **Player/privacy scope.** Native creation will instantiate the MPRIS model and
   read player metadata; opening full view may request position updates. Stock
   artwork can read local files or fetch remote URLs from player metadata. Owner
   approval must identify permitted players/artwork/network/cache effects first.
   Prefer an attended disposable test user/session with no private players and
   a reviewed local-only test source. Do not claim that empty artwork in this
   offline fixture disables native retrieval. If effects cannot be bounded,
   defer rather than substitute a custom widget or unreviewed loader.
5. **Creation.** Only after approval, add one official media widget through Plasma
   UI on D and record the allocated N, plugin and parent. Never invent N, reuse a
   tray instance, change panel membership, reset layouts or call scripting APIs.
   Preserve all per-instance defaults and global audio settings. There are no
   proposed media configuration keys to write. Place via operator edit-mode
   handles in an unoccupied area; record actual size and representation. A larger
   fit decision is separate from the compact/expanded design labels.
6. **Acceptance matrix.** Observe no-player, playing, paused, stopped, disappearing
   player and unavailable-metadata cases. Verify accessible labels, keyboard/focus,
   supported/disabled controls, multi-player selection, missing/failed artwork,
   unknown/zero duration, position updates and actual native minimum dimensions.
   Owner must separately permit play/pause/next/previous on the identified test
   player before any control interaction. No default permission for seek, volume,
   shuffle, repeat, rate, raise, quit, accounts or network playback. Operator
   gestures can invoke these too; do not scroll/middle-click merely to inspect.
7. **Persistence.** Expected additions are N's applet subtree and its exact new
   membership/layout/background entry. Resolve actual serialization from reviewed
   source/UI and the fresh target baseline before approval; no raw placement key
   is invented. All existing appletsrc entries and the other protected files must
   retain their approved state. Stop on unexpected writes, player/root changes,
   network/artwork effects, unsafe baseline, poor fit or uncertain cleanup.
8. **Recovery.** If separately approved, remove only N after rechecking its plugin
   and parent; verify preservation again. Copies are evidence, not permission to
   overwrite live files. No full appletsrc restore, timestamp repair, restart,
   desktop recreation, automatic retry or whole-system rollback claim.

Laptop D2a evidence remains preserved and deferred. It need not be resolved to
develop offline candidates. A future native gate is still a separate decision;
the latest owner scope governs whether historical laptop-specific requirements
apply to a new clean-host trial. No gate is bypassed by this implementation.

## Remaining offline work — planning only

| Slice | Small separately reviewable task | Hermetic/native boundary |
| --- | --- | --- |
| CPU | Pin official CPU preset and face/provider contracts; model unknown units, missing/stale sensors and history gaps | Fake samples only; no ksystemstats/service queries |
| RAM | Pin memory preset/face; define used versus available/cached/total and unknown-total display | No fabricated denominator/fill; no real sensor reads |
| Weather | Review official providers, attribution, location/privacy and network/cache contract; model unconfigured/offline/stale | Provider/data use and location selection need separate approval; no API keys |
| Panel/dock visuals | Reconcile target top bar/dock with identity-preserving existing layouts; offline reservations/spacing/floating/scaling and task growth | No panel recreation, pin changes, output or desktop-count migration |
| Five flavors | Measure type, opaque frames, artwork crop, contrast/focus/disabled states and localization parity across one shared geometry | Existing semantic tokens/spec remain authoritative; no native style activation |
| Clean AMD acceptance | Review actual release/schema, operation-specific gates, privacy and persistence scope, then one useful widget at a time | Separate owner approval for each live creation and theme activation; no assumption about hardware or compositor permissions |

W2–W6, Android, Audit Lab and Host Canary remain outside these slices. No new
Setup Manager architecture is a prerequisite for a useful offline media model.
