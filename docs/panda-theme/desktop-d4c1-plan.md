# D4C1 compatibility and read-only inventory plan

Authority: current D4C1 user request, AGENTS.md, approved Panda specification,
and merged desktop-d4c-proposal.md. Base: 215522fb36d9f4f29922fed83bd568bf7aa6a442.
This plan is executed inline under the user's supplied three phases.
Original D4C1 work was left uncommitted for review. Publication is now separately
authorized; no applicator, plasmoid or live service call is added.

- [x] Test a bounded O_NOATIME regular-file reader against disposable fixtures:
  byte/metadata preservation, symlink/hardlink/special-file refusal, identity
  drift and permission failure with no fallback.
- [x] Prepare the static configuration-subset parser and explicit role-binding
  classification. Preserve raw values without expanding KConfig expressions.
- [x] Read only the allowlisted Plasma configuration files; retain selected
  inventory facts and complete fingerprints in a new private ignored evidence
  directory. Never save raw configuration or credential fields.
- [x] Record relevant package versions and installed resources without executing
  Plasma/Qt GUI programs, contacting D-Bus, querying sensors or probing hardware.
- [x] Build a version-pinned compatibility matrix and sanitized fixture-based
  clock/media candidate. Native instance IDs/private values remain private.
- [x] Recheck every protected file and original checkout fingerprint; stop any
  unsafe portion, report saved-file versus runtime limits. Qualified outcome:
  7/7 bytes match, 6/7 full receipts; output-config timestamp drift stopped
  host collection. No native readiness or recovery success is claimed.
- [x] Run full repository tests, candidate/schema checks, applicable Fish/package
  checks, whitespace checks, and a read-only final review. Stop for user review.

Review focus: no silent read fallback; no raw secrets/pins/UUIDs in public output;
panel clocks never repurposed as desktop clocks; ambiguous/absent bindings gated;
saved geometry and output settings never claimed as current native observations.

Tracked scope: assessment helper/tests, sanitized fixtures/candidate, compatibility
and inventory reports, this plan. Private collector scripts and upstream source
receipts remain ignored; no existing D4A/D4B code or assets need modification.

Specification provenance: approved local ignored source
docs/superpowers/specs/2026-10-06-panda-theme-system-design.md,
SHA256 5904eb5532d5fc66d70918f959b499f3906bd20b0098c1a8fba5896eaad22db0.
It was read with O_NOATIME and unchanged metadata.

## Decisions and verification ledger

- Ruling: leave all work uncommitted and retain private evidence instead of
  following generic skill commit/scratch-cleanup steps — explicit D4C1 limits
  take precedence — cost if wrong: review artifacts persist rather than a commit.
- Ruling: use the approved local ignored specification with recorded hash,
  without copying it into the patch — it is absent from integrated main —
  cost if wrong: reviewers must obtain that authoritative local source.
- Ruling: keep the strict ownership guard and use trusted-host read-only context
  after sandbox ownership mapping refused access — no weaker fallback —
  cost if wrong: inventory is unavailable in the sandbox namespace.
- Ruling: retain the 6.7.5 source baseline and expose the installed 6.8.1 gap —
  no unmeasured version extrapolation — cost if wrong: native work stays blocked.
- Ruling: verify tag-response commit/tree identifiers against actual immutable
  tree membership — all 20 source blobs and tree entries matched —
  cost if wrong: static compatibility claims require a new provenance audit.
- Ruling: leave the root-owned native font unread after O_NOATIME refusal —
  no fallback — cost if wrong: active/native font evidence remains incomplete.
- Ruling: treat absent serialized launcher data as unknown runtime pins —
  synthetic examples are not host pins — cost if wrong: native planning needs
  another explicitly authorized observation.
- Ruling: stop host collection on final output-config mtime/ctime drift —
  bytes/identity/xattrs matched, actor unknown — cost if wrong: a harmless
  rewrite still requires fresh stable evidence; no native readiness claim.

TDD evidence: the reader/parser/candidate tests were introduced before their
implementation. A nested-tray classification regression and off-model rectangle
acceptance were observed failing and corrected. The fresh final reviewer found
flagged KConfig identity fields could silently become absent; its dedicated
regression failed for flagged groups/keys and escaped plugin values, then passed;
additional escaped-root/key cases also failed and passed after the same correction
was completed. Classification refuses unevaluated identity flags/escapes. No native behavior was inferred from these tests.

Final review: one fresh-context read-only reviewer independently verified all 20
source SHA256/Git blob hashes/lengths/tree memberships and reviewed the nine-file
scope. Its one P2 finding was fixed RED→GREEN. No deferred minor findings.
Host preservation remains a qualified result, not a passed recovery test.

Verification results are recorded in desktop-d4c1-inventory.md and private logs.

Task completion: 314/314 repository tests passed after the review fix; 17/17
D4C1 tests passed. Applicable Fish syntax, 13-script/54-package validation,
candidate schema/regeneration, all 20 source blob/tree checks, and tracked plus
nine-file whitespace checks passed. Index/HEAD and previous checkouts preserved.
D4C1 is complete for review with the explicit host metadata/freshness limitation.

Finalization authorization (2026-10-27): the user accepted this qualified offline
milestone and requested a focused PR. Preserve the original review ledger above.
Fresh verification passed 314 tests, 13 Fish scripts and 54 package entries;
stage only the nine reviewed public files. Publish using the configured user's
Git identity, without merge or deployment. D4C2 proposal work remains separate.
