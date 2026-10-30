# Ubuntu authentication authorization readiness

Source-only review prepared on 2026-10-30. **This document and its PR do not
authorize authentication.** No workflow activation or dispatch is part of this
change. The existing [S4 restrictions](README.md#execution-restrictions) apply.

The subsequent [external single-use architecture](ubuntu-single-use-authorization.md)
extends this review with a transactional offline reference and explicit production
blockers. The pure model and sealed runner remain unchanged and disconnected.

## Reviewed baseline

Remote `main` was fetched before this hardening work and exactly matched
`0f604ed3cbdf52c7be6ed6805270f9f8cd4eafcc`, the integration of
[PR #22](https://github.com/adrianrusu16/panda-workstation/pull/22).
There were no intervening changes. This supersedes that PR's source-admission
findings where explicitly stated below. Unrelated canary work remains in the
original checkout; this change uses an isolated feature-branch worktree.

Reviewed sources include the [disabled workflow](../../../../.github/workflows/panda-ubuntu-bootstrap-verification.yml.disabled),
[runner](ubuntu_bootstrap_runner.py), [verification protocol](ubuntu_verification.py),
[packet publisher and upload gate](ubuntu_packets.py), [archive/ELF readers](ubuntu_artifacts.py),
both provenance pin files, [pending policy](trust-policy.json), S4/provenance tests
and Ubuntu protocol/status/adapter/packet tests. The new
[authorization model](ubuntu_authorization.py) is pure and disconnected from the
runner and workflow. All new validation uses synthetic data.

Protected baseline digests:

| Input | SHA-256 |
| --- | --- |
| `trust-policy.json` | `7c43bbbf0fc1ca9ba9450121402fe8e07c2aa851aaf6fc49bd01933f9f713c2b` |
| `ubuntu-verification.pins.json` | `582c784e1fac0c6cbe013b64885b718a2443ef6d456ff020f5c0607a79629b4f` |
| `../packages.lock.json` | `f4034660aa04de28123ccaf80fd6d12d2d7eb9c8f2d29e5043f1f4511fe16618` |

The policy remains byte-for-byte unchanged with `status=pending-review`, empty
signers/tools and null approval fields. Neither observations nor synthetic
fixtures supply missing trust approvals.

## Proposed future activation diff

**NOT AUTHORIZED — DO NOT APPLY.** These are the three necessary seal changes
for a separate activation review, not a sufficient authorization package:

```diff
rename .github/workflows/panda-ubuntu-bootstrap-verification.yml.disabled
    to .github/workflows/panda-ubuntu-bootstrap-verification.yml
@@ jobs.verify
-    if: ${{ false }}
+    if: ${{ github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main' }}
@@ tests/native/external_vm/s4/ubuntu_bootstrap_runner.py
-AUTHENTICATION_ENABLED = False  # Source seal; never controlled by argv or environment.
+AUTHENTICATION_ENABLED = True  # Source seal; never controlled by argv or environment.
```

This proposal does not alter pins, locks, policy or other S4 execution seals.
Any prerequisite hardening, changed seal tests, protected-environment binding or
one-shot enforcement must receive its own explicit review in the future diff.
Do not remove assertions merely to make an activation change pass tests.

The future approval must identify the **complete final activation commit `A`**,
including any prerequisite changes. `A` must already be the reviewed commit on
`main` when dispatch is considered. With squash/rebase/merge integration, review
the actual resulting commit and tree; a PR head or earlier base is insufficient.
An approval record outside that commit can bind `A` without a self-referential
embedded commit hash. Any subsequent source change requires renewed review.

| Source identity | Required relationship and limitation |
| --- | --- |
| `GITHUB_SHA` | Exactly `A`, 40 lowercase hexadecimal characters. The checkout action uses `${{ github.sha }}`, not an independent moving branch checkout. |
| `REVIEWED_SOURCE_SHA` | Dispatch input exactly equal to `A` and `GITHUB_SHA`. It is operator input, not evidence of approval by itself. |
| `GITHUB_REF` | Exactly `refs/heads/main`; a feature branch, tag or PR merge ref is rejected even if its tree matches. |
| Detached `.git/HEAD` | The runner reads this ordinary checkout file and requires its stripped contents to equal `GITHUB_SHA`. A symbolic HEAD or linked-worktree `.git` indirection fails. |
| Workflow and working files | Review the workflow at `A`, pinned action commits and complete executed tree. HEAD equality alone does not prove working files are unmodified. Source hashes are observations, not independent Git-object verification. |

[GitHub's dispatch contract](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_dispatch)
requires the workflow to exist on the default branch and binds the run to the
selected branch/tag. A disabled filename is not a registered runnable workflow.
Do not probe registration by dispatching or rename the file in this preparation
PR. Future reviewers must check default-branch registration and the actual run
revision. If `main` moves between approval and dispatch, the SHA equality must
abort rather than silently approve its replacement. Branch protection, access
to dispatch/rerun, action supply chains and GitHub's control plane remain trust
dependencies. The template uses pinned checkout/upload actions, read-only
contents permission, no persisted checkout credentials, no submodules or LFS.

## One-shot execution scope

If separately approved, admit one new standard GitHub-hosted Ubuntu job for one
reviewed `A`, run ID and **attempt 1**. Admission failure, cancellation, timeout,
missing evidence or image mismatch consumes that authorization; there is no
automatic retry, rerun or second dispatch. The approval must name its operator,
validity window, scope, durable review reference and how the authorization is
consumed. These fields are requirements for future approval, not filled-in
approvals in this document.

The concurrency group serializes runs and can queue another run. It does not
enforce one shot. The protocol now rejects `GITHUB_RUN_ATTEMPT != "1"`, which
blocks reruns but still permits independent first-attempt dispatches.
`REVIEWED_SOURCE_SHA`, an environment variable, an input, a repository file,
a local token and a concurrency group cannot establish an external approval or
durably consume one.

### Mechanisms considered

| Mechanism | Useful control | Single-use limit / trust requirement |
| --- | --- | --- |
| [Protected environments](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments) | Required independent reviewer, prevent self-review, main-only deployment rules; disallow administrative bypass where supported. | Gate each deployment, but do not constitute a global consumed-approval ledger across dispatches. Availability depends on repository/plan settings, which this task does not configure. |
| Branch protection and restricted dispatch/rerun access | Protect the reviewed workflow/tree and limit operators. | Permissions and procedures are defense in depth, not an atomic consumption primitive. Privileged repository administrators remain trusted. |
| GitHub API-backed approval/reservation | Run/job/environment APIs can independently corroborate run, actor, workflow revision and approval. A separately controlled Git ref with conditional non-forced updates could represent a reservation. | Ordinary issue/comment/status writes are not CAS. A ref scheme needs a unique immutable approval namespace, create-once/no-delete rules, race/crash handling, revoked-state rules and an independent state owner; same-runner write credentials undermine separation. No such scheme is implemented or approved. |
| External durable record with atomic CAS | One transaction can check state, revision, revocation, expiry and exact run/source/operator binding, then irreversibly consume. | Requires a trusted owner, persistent store, authenticated caller, trusted clock and no rollback/reset of consumed tombstones. |
| Independently operated authorization service / GitHub App | A small service with one transactional store can combine the prior control with independently verified GitHub identity. | Adds a narrow service and operational ownership; compromise of that owner/control plane defeats the gate. No machine attestation follows. |

**Selected design proposal:** one independently administered owner with a small
durable transactional store, optionally exposed through a GitHub App/protected
environment gate. This is the minimal technical single-use boundary considered
defensible here. It is **blocked pending owner, store, identity and operator-policy
decisions**. No service, secret, permission or live connection is provisioned.

### Exact proposed authority contract

`consume_approval(record, claim, now, source_files)` validates an in-memory
transition proposal and returns a *new* consumed record. It performs no I/O,
authenticates nobody and persists nothing. Calling it twice on the old approved
record returns two proposals; tests demonstrate this limitation explicitly.
Its output is not a grant and has no execution-authority flag. It is not imported
by the runner. Synthetic CAS tests exercise a test-only state owner, not a
deployed authority.

The future trusted owner must implement the following contract:

1. Reviewers create one external record after the complete final activation
   commit `A` is integrated. Do not embed `A` inside itself. Bind a single
   pending run ID before releasing a protected job; never let the first claimant
   choose a run. The issuer controls uniqueness of the approval scope and must
   not silently mint replacement approvals after failure.
2. Proposed endpoint: `POST /v1/approvals/{approval_id}/consume`, authenticated
   with a separately approved GitHub workload-identity mechanism. Request body:
   `{"expected_revision": <positive integer>}`. The client supplies neither
   the record nor trusted claims/time/file hashes. Invalid authentication is
   denied before lookup; an ID is a label, never a bearer credential.
3. The owner verifies issuer, audience, expiry and job/run identity of the
   workload assertion, then independently queries GitHub for canonical numeric
   repository ID, run ID, original and triggering numeric actor IDs, event,
   ref, workflow path/revision, attempt and current main SHA. Do not assume a
   token exposes every field: retrieve and cross-check missing fields through
   authenticated provider APIs. Conflicts, missing data, unknown identity,
   revocation or control-plane failure deny admission. Workload-identity setup
   and required API permissions remain undecided.
4. Exact record fields are `schema_version=1`, `approval_id` (16–64 ASCII
   alphanumeric/underscore/hyphen characters), positive `revision`,
   `state="approved"`, lowercase 40-hex `source_sha`, decimal-string
   `repository_id`, `operator_id`, `run_id`, positive integer epoch seconds
   `not_before` / `expires_at`, bounded nonempty `review_reference`,
   `source_hashes` and `consumed_at=null`. Unknown fields fail. Revisions
   and times are below 2^53; identities are at most 20 digits without leading
   zeros. The owner obtains `now` from its separately approved trusted clock;
   the model only checks its type/range and `not_before <= now < expires_at`.
5. Exact verified-claim fields are `repository`, `repository_id`,
   `source_sha`, `reviewed_source_sha`, `checkout_sha`, `workflow_sha`,
   `main_sha`, `ref`, `event_name`, `workflow_path`, `run_id`,
   `run_attempt`, `actor_id`, `triggering_actor_id`. All are nonempty
   strings of at most 256 characters. Repository is exactly
   `adrianrusu16/panda-workstation`, ref `refs/heads/main`, event
   `workflow_dispatch`, future workflow path
   `.github/workflows/panda-ubuntu-bootstrap-verification.yml`, attempt
   `"1"`. All five source SHA fields equal approved `A`; both actors equal
   the approved operator; run/repository IDs equal the external record.
6. `source_hashes` has exactly the paths in the model's `SOURCE_FILES` and
   lowercase SHA-256 values. It covers the future enabled workflow, runner,
   protocol, packet/archive readers, authorization model, common/provenance
   modules, both pins, pending policy and package lock. The separately reviewed
   observer supplies held bytes for exactly those files (1–131072 bytes each,
   at most 2 MiB total); every digest must match. The final activation review
   must re-audit this list for additional imports/configuration. This scoped
   byte contract does not cover the complete Git tree, stdlib or actions.
7. Inside one serializable transaction, load the authoritative record, verify
   expected revision, approval/revocation state, deadline and verified claims,
   validate the model, then CAS original state/revision to `consumed` with
   revision incremented and `consumed_at=now`. Revocation must use the same
   serialization boundary. Re-evaluate validity at the commit/linearization
   point, not after an arbitrarily long queued observation. Exactly one CAS
   succeeds; no upsert, overwrite, lease expiry, refund, resume or delete/recreate.
   Durable consumption must commit before releasing any candidate acquisition
   or verifier operation. Approval issuance, revocation, source observations,
   consumption and denied attempts require an owner-controlled audit record.
8. A single authenticated `201` response contains exactly `approval_id`,
   `revision`, `state="consumed"`, `consumed_at`, `run_id`, `source_sha`.
   It is delivered only to the bound current job after the durable commit;
   it is not a reusable bearer grant. Conflict/reuse returns `409`; missing,
   revoked or expired approval returns `403`; malformed request `400`;
   unavailable/ambiguous state `503` or transport failure. No non-201 response
   admits execution. Timeouts/lost responses have no retry or recovery grant.
9. Cancellation, timeout, missing evidence and any local admission failure after
   consumption leave the record consumed. Denial before a successful transaction
   grants nothing; the owner must revoke any still-pending approval when its
   prebound run terminates, including when the response/state is uncertain.
   There is no automatic retry under that run/approval. An unauthorized request
   alone must not create a new authorization. Any replacement requires a fresh
   explicit decision with the failed outcome visible.
10. The runner cannot write/reset this store. Administrative backup restore,
    record deletion, ledger rollback, a second issuer or recreation of the same
    scope must not resurrect consumption. The trusted executor must obey the
    live gate and not cache/replay its response. This provides at-most-one
    admitted invocation under those assumptions, never exactly-once completion,
    malicious-host containment or proof that any evidence will survive.

The pure model does not implement the endpoint, API/OIDC verification, trusted
clock, source observer, durable CAS, revocation transaction or pending-run
reconciliation. All are mandatory before claiming production enforcement.
Supplied input alone cannot bypass the three existing execution seals. Removing
only those seals in a future change would still lack this external gate and is
**not a sufficient activation change**.

### Source identity and byte-integrity boundary

The model checks approved/executed/reviewed/checkout/workflow/current-main SHA
agreement and externally approved file-byte hashes. Its synthetic tests reject
each mismatched SHA, changed observed file, missing/extra file, wrong branch/tag,
PR event, absent approval, rerun, unauthorized actor and malformed metadata.
These are implemented checks of *supplied observations*, not deployment of a
trustworthy observer. The sealed adapter still checks detached `.git/HEAD`
only; its local source hashes are observations, not approved comparisons.

An honest observer can detect modifications in the scoped held bytes; an
attacker who controls both files and claimed observations can lie. Imports have
already executed before an in-process checker runs. Neither Git HEAD text nor
matching supplied hashes authenticates the actual executed bytes, process,
Python stdlib, pinned actions or provider. A separately trusted observer must
bind the measured checkout to execution and constrain mutation afterward, or
reviewers must explicitly accept the runner-integrity boundary. Source/action
review at `A` and a pinned checkout are still required.

The owner checks current-main identity at consumption. This does not atomically
lock GitHub's branch together with an external database. A later branch move
cannot change a checkout pinned to `A`, but policy requiring main to stay at
`A` until execution additionally needs an approved branch-freeze/control-plane
boundary. Queue time does not extend expiry. The future workflow must be
registered on default main before dispatch; this task does not probe that by
dispatching. Pinned checkout/upload action commits remain byte-identical.

Permitted work in that future job is inventory of preinstalled inputs, three
InRelease checks plus six negative probes, four index checks, and bounded
data-only inspection of the exact 13 pinned Ubuntu packages and 13 selected
ELFs/aliases. `/usr/bin/vercmp` is a candidate member inspected as bytes, never
an executed verification tool. Network acquisition is confined to
`https://snapshot.ubuntu.com/ubuntu/20261029T000000Z/`, including redirects;
queries, fragments, credentials, traversal and other hosts/snapshots fail.
Individual responses require exact expected sizes and hashes; the transport
limits requests to 32 MiB each and an aggregate expected 64 MiB.

The job timeout is 10 minutes. The adapter applies a 2 GiB address-space limit;
preinstalled tool children have 20 CPU seconds, 25 seconds wall time, 512 MiB
address space, bounded output, no core dumps and 32 descriptors. These limits
are not a network namespace, whole-host sandbox or proof against a malicious
runner. Timeout/termination can prevent any diagnostic packet from being made.

No APT/install/update, keyserver, downloaded verifier/keyring substitution,
candidate invocation, rootfs assembly, native build/render, Arch authentication,
S4 activation, external-VM preparation or Helios desktop changes are in scope.
The preparation task itself retrieves no candidate package or release/index
data; its validation uses fictional in-memory fixtures and temporary files.

## Required runner admission

All current runner checks must pass before inventory, candidate acquisition or
tool invocation:

- `GITHUB_ACTIONS=true`, `RUNNER_ENVIRONMENT=github-hosted`, `RUNNER_OS=Linux`,
  `RUNNER_ARCH=X64`, actual `platform.machine()=x86_64`.
- `ImageOS=ubuntu24`, `ImageVersion=20261026.354.1`, Ubuntu `ID=ubuntu` and
  `VERSION_ID=24.04` from the bounded root-owned OS release file.
- Exact repository, `workflow_dispatch`, main ref, source identities above,
  bounded nonempty job/runner names and positive run ID and attempt exactly `1`.
- Observable, nonconflicting runner-application version from a bounded process
  ancestry matching `/home/runner/runners/<version>/bin/Runner.Worker` or
  `Runner.Listener`; later corroborate it against the provider's Set up job log.
  A different path layout or inaccessible ancestry is an abort, not permission
  to guess a version.
- Observed `sys.version_info` must be a well-formed final Python 3.12 tuple;
  the executable must be `/usr/bin/python3` or `/usr/bin/python3.12` and resolve
  exactly to `/usr/bin/python3.12`. This is checked before host inventory, TLS
  setup, tool invocation or candidate acquisition, and again at inventory entry.
  Missing/malformed runtime data or another path/version fails; no auto-repair.
- No nonempty `LD_*`, `GCONV_PATH`, `PYTHONPATH`, `PYTHONHOME` or `GNUPGHOME`
  influencing variables. The workflow uses `/usr/bin/python3 -I -S -B`.

The official [pinned image README](https://github.com/actions/runner-images/blob/ac85c71971895cd6234578d6b11f49f7c27ff0c4/images/ubuntu/Ubuntu2404-Readme.md)
was fetched as source text through GitHub's contents API. Its returned blob SHA
and recomputed Git blob identity both equal
`97e7ec74186bddefe5bb53c8d3e573955364d89c`, matching the pin. At that commit it
documents image `20261026.354.1`, Ubuntu 24.04.5, Python 3.12.3, gnupg2
`2.4.4-2ubuntu17.6`, and zstd 1.5.7. It does not prove `/usr/bin/gpgv` or
`/usr/bin/zstd` file bytes, keyring bytes, process mappings or a future VM's
inventory. The zstd summary differs from the reviewed `zstd` package
`1.5.5+dfsg2-2build1.1`; different installed paths could explain it, but this
has not been established. Do not claim either a proven runtime match or a
proven `/usr/bin/zstd` mismatch from that summary.

[Runner images roll regularly](https://github.com/actions/runner-images#image-releases).
`runs-on: ubuntu-24.04` selects an OS family, not an immutable image build.
Neither the pinned README nor `EXPECTED_IMAGE_VERSION` reserves this image.
The actual enforcement uses the protocol's `IMAGE_VERSION` constant, not that
workflow environment variable. Missing, newer or conflicting image evidence
must abort before candidate work, with no retry-until-match, fallback label,
installation, self-hosted substitution or automatic repin. Availability and
provider-log corroboration remain unresolved until a separately approved run.

## Toolchain and keyring admission

| Input | Current enforced contract | Interpretation / remaining requirement |
| --- | --- | --- |
| `/usr/bin/gpgv` | Pinned 310416 bytes, SHA-256 `f14d026b9eae172c432e015bce227483293b4966f2f3fdcfa582f71d3dbb2ae8`, installed `gpgv=2.4.4-2ubuntu17.6`, amd64. | Root-owned preinstalled verifier only. Hash is rechecked before invocation. |
| `/usr/bin/zstd` | Pinned 1022760 bytes, SHA-256 `7c5468b370f7c47eda07281e3437fafc568f95d10420051e3aa522709f9342c5`, installed `zstd=1.5.5+dfsg2-2build1.1`, amd64. | No PATH-selected or downloaded replacement. Resolve image-source ambiguity without weakening admission. |
| System Python | Explicit observed final Python 3.12 admission and exact resolved `/usr/bin/python3.12`; receipt validator also rejects prefix lookalikes. Loaded native extensions must resolve under `/usr/lib/python3.12/`, at most 32. Installed Python packages remain required. | Version/path gap is closed in the sealed adapter. Interpreter/package hashes and versions remain observations, not independently authenticated provenance. Development-host Python is not Ubuntu runtime evidence. |
| ELF closure | At most 128 files / 64 MiB; ELF64 little-endian x86-64, PT_INTERP, unique library resolution in fixed directories, SONAME and required/provided symbol versions. Unsafe search overrides or populated glibc-hwcaps trees fail. | Static resolution is not the actual loader's mapping. Host libraries need not match all candidate-library pins: same-content metadata is cross-checked, while other bytes are observed. |
| dpkg | Bounded installed status and file-list records; exactly one installed owner per inventoried ELF/keyring; architecture/version metadata retained. | A root-controlled database is local evidence, not independent authenticated package-to-file provenance. Python, extensions and most host libraries are not independently authenticated by these records. |
| Archive keyring | `/usr/share/keyrings/ubuntu-archive-keyring.gpg`, root owned, safe mode, bounded 128 KiB, owner `ubuntu-keyring`, installed `2023.11.28.1` / `all`; SHA-256 `80a36b0a6de2f69f49d2df75ef473ccde121e9e190b9ea01d20a4f63778d5c31`. | Preinstalled bytes only; never replace from a candidate package. Full anchor fingerprint is checked separately below. |
| Loader / TLS | Root-owned bounded `/etc/ld.so.cache`, `/etc/ld.so.conf`, matching `ld.so.conf.d/*.conf`, and `/etc/ssl/certs/ca-certificates.crt` are hashed. System preload must be absent/empty. TLS uses that explicit CA file and disables proxies. | Hashing is not approval of CA contents, cache interpretation, all transitive configuration or actual loader selection. TLS/DNS/platform integrity are delegated. |

System reads check regular files, root ownership, non-writable ancestors, no
set-id/unsafe modes or file capabilities, sizes and stable descriptor identity
while reading. The keyring records resolved path, mode, owner, size and hash.
Eight S4 source/reference hashes are recorded. All inventoried ELF hashes are
rechecked after verification, but this is not a held-executable descriptor or
an atomic whole-machine snapshot.

Native modules include `_ctypes` loaded by the packet module before inventory,
and its ELF dependencies; publication uses preinstalled libc, not a candidate.
The inventory is of **already loaded** extensions. It does not prove no later
extension, NSS/OpenSSL provider or other dynamically loaded object is used;
pure Python stdlib source and all possible configuration inputs are not a
fully authenticated closure. The Python interpreter and loader have already
executed before inventory. Current checks reject unreviewed ELF search behavior
they model, not all possible host behavior. Future approval must explicitly
accept these delegated boundaries for evidence gathering or require further
source-only hardening first. Real compatibility is untested here.

## Signature verification acceptance

The actual adapter remeasures preinstalled gpgv, creates a fresh private temporary
directory, writes held input and keyring bytes exclusively, and invokes:

```text
/usr/bin/gpgv --homedir <private-directory> --keyring ./keyring.gpg --status-fd 1 --output plain input
```

The subprocess has a minimal fixed environment and bounded files/status/stderr.
Only its dedicated status stream, exit code and extracted plaintext feed the
protocol; human-readable stderr is not proof. Explicit keyring selection prevents
default-keyring fallback; the negative empty ring is likewise isolated.

For each of `noble`, `noble-security`, `noble-updates`, require:

1. Exact pinned InRelease size/hash and a zero verifier return code. Status is
   UTF-8, at most 16384 bytes / 64 records, newline terminated, strictly prefixed
   `[GNUPG:] `, with forbidden controls and unknown/failure statuses rejected.
2. Exactly one NEWSIG, SIG_ID, GOODSIG and VALIDSIG, one to eight KEY_CONSIDERED
   records with the reviewed fingerprint and zero flags, and at most one SIGINFO.
   GOODSIG's long key ID is insufficient alone. VALIDSIG's full signing **and
   primary** fingerprints must both be
   `F6ECB3762474EDA9D21B7022871920D1991BC93C`; a different subkey is not admitted.
3. OpenPGP v4, RSA algorithm 1, SHA-512 algorithm 10, class `01`, reserved field
   zero. The measured anchor is v4 RSA-4096 with exponent 65537; packet bounds,
   unique primary identity, creation time and an observed anchor key-revocation
   packet are checked. Parsing its packet fingerprint is not lifecycle proof.
4. Positive creation time no later than assessment time, not before key creation;
   expiration zero or later than both assessment and creation; matching UTC date,
   SIG_ID timestamps and optional SIGINFO. Release identity must be Ubuntu/noble,
   correct suite and amd64; Date cannot be future and present Valid-Until must
   be later than assessment time. Missing Valid-Until remains explicit.
5. A first-cleartext-byte mutation must return 1 or 2 with the expected BADSIG
   identity and no ERRSIG/NO_PUBKEY. The unchanged input with an empty ring must
   return 1 or 2 with matching NO_PUBKEY and ERRSIG, full fingerprint, algorithms,
   class and missing-key reason 9, with no BADSIG. A timeout, absent executable,
   blank status, unrelated error or accidental positive result fails the probe.
   All six negatives are required, not substituted by a general error.

[GnuPG 2.4.4 DETAILS](https://raw.githubusercontent.com/gpg/gnupg/gnupg-2.4.4/doc/DETAILS)
defines the informational PLAINTEXT and PLAINTEXT_LENGTH records. The parser
allows at most one each; length requires an earlier PLAINTEXT. Formats `62`,
`74`, `75` and bounded unsigned timestamps are admitted. Filenames are bounded,
percent-escaped opaque metadata, never paths; malformed escapes, ambiguity or
unsupported formats fail. Binary length must match supplied extracted bytes;
text/UTF-8 length may differ after line-ending conversion, and length may be
absent for partial-length encoding. These records supply no signature authority.
The receipt validator re-parses recorded statuses for consistency without
rerunning gpgv, receiving original plaintext or proving assessment-time freshness.

[gpgv trusts its keyring and does not check key expiry/revocation](https://www.gnupg.org/documentation/manuals/gnupg/gpgv.html).
Rejecting expired/revoked statuses **if emitted**, or spotting one revocation
packet, cannot establish complete current lifecycle. The runner's `time.time()`
is not a trusted-clock proof. A frozen historical snapshot and nonexpiring
signature can verify long after publication. Current lifecycle, assessment clock
and acceptable historical replay window need explicit decisions at activation
review; keep `key_lifecycle_verified=false` and
`freshness_policy_established=false`. Cryptographic success cannot resolve them.

## Artifact and packet acceptance

Require the signature-authenticated SHA-256 tables to bind both compressed and
plain forms of all four indexes. Require exact Package, Version, Architecture,
Filename, SHA256 and Size for all 13 pinned packages, control/index agreement,
bounded decompression/archive paths, collision/link checks and exact selected
member hashes. All 13 ELFs and all required aliases must form the recomputed
static PT_INTERP/DT_NEEDED/SONAME/symbol-version graph. This does not authenticate
all installation dependencies or establish executable compatibility.

The success packet has exactly these nine receipt files:

```text
runner-environment.json
verification-toolchain.json
archive-anchor.json
inrelease-signatures.json
index-hash-chain.json
package-membership.json
elf-closure.json
consistency-review.json
authorization-state.json
```

Both packet kinds additionally require `SHA256SUMS`, `run-context.json`,
`context-binding.json`, `completion.json`. A failure packet contains exactly
`failure.json` and `authorization-state.json` instead of the nine receipts:
**13 total files for success; six for failure; never a mixture.** Failure means
`status=failed-closed`, `evidence_complete=false`, a bounded phase/error class
and every authority flag false. No raw package, keyring, rootfs or logs are
allowed packet members.

Preserve the current publication and upload contracts:

- Canonical sorted compact JSON with a final newline, strict JSON parsing,
  per-document budgets, at most 1 MiB receipt content and a 2 MiB packet.
- Sorted SHA256SUMS covers receipt/diagnostic content. Context binding separately
  hashes checksums and run context; versioned completion binds all other files'
  digests, sizes and local device/inode/mtime/ctime, and the directory identity.
- A fresh unpredictable sibling staging directory, mode 0700, exclusive files
  mode 0600, complete writes and fsync of members/staging/parent before rename.
  Linux libc `renameat2(RENAME_NOREPLACE)` atomically publishes without replacing
  an existing destination; no replacing fallback is allowed.
- Publication failure discards incomplete staging and attempts an independently
  complete failure packet. If that fails, exit 78 with no token. Existing output
  is never replaced or resumed. Preflight errors outside the runner's try block,
  imports, process termination and timeout may yield no packet at all.
- The token hashes the current completion-file content/identity record. Only
  this invocation's successful publication hands it to the next step. It is a
  local handoff binding, not a secret, signature or externally issued approval.
- The read-only upload gate must validate token, exact membership, canonical
  JSON, content/semantics, context binding, budgets, ownership/modes, regular
  types, single links and final local member identities. Only its explicit
  validated path list reaches upload. Both `steps.packet.outcome == 'success'`
  and `steps.packet.outputs.complete == 'true'` are required; `always()` alone
  grants nothing. `if-no-files-found: error` remains required.

A complete failure packet may upload for diagnosis even when authentication
fails. A successful upload or successful packet gate does not mean signatures
passed: inspect packet type and authentication step outcome. Preserve provider
run/job identity, input SHA, Set up job image/application details and upload
artifact identity/digest alongside the packet; compare them independently.
Retention is seven days, so any approved evidence retention must occur in time.

Remaining packet boundaries: renameat2/filesystem support is environmental;
there is no post-rename parent fsync, so atomic visibility is not a crash/VM-loss
durability promise. Same-user/root mutation after final validation and before
the uploader reads paths remains possible. Parent/working-file replacement,
tool remeasurement versus actual execution, and later dynamic loads are not
eliminated by local inode checks. The separate uploader/control plane is trusted.
Source-only review found no
small change that binds the uploader's later path reads to the validated open
descriptors: another copy/archive/chmod would itself remain same-user/root
mutable. The packet publisher, manifest version and workflow handoff are
therefore unchanged. Closing this gap requires a separately reviewed trusted
uploader that hashes the exact uploaded bytes or an accepted runner-integrity
boundary; an after-upload hash alone cannot prevent an earlier disclosure or
prove the producer.
Local identity checks cannot be reproduced from a downloaded archive's newly
created inodes; offline reviewers check content/semantics and provider context,
not pretend the original filesystem identities were independently attested.

## Abort and failure matrix

| Condition | Required disposition |
| --- | --- |
| Missing approval, wrong/finally changed source SHA, wrong ref/event/repository, unregistered workflow | No dispatch; if encountered during an approved run, fail closed. Never substitute PR #21's SHA for `A`. |
| Second dispatch, rerun, queued duplicate, expired approval or attempt other than 1 | No-go; no retry under the same authorization. Attempt 1 is enforced; durable consumption remains a disconnected design. |
| Missing/mismatched image, OS/CPU, application ancestry or conflicting provider logs | Abort; no fallback or automatic repin. Image identity fails before inventory/download/verifier. |
| Unsafe environment, unowned/changed tool/keyring, dpkg mismatch, missing/ambiguous ELF, preload/hwcaps, incomplete inventory | Abort; no repair/install or relaxed allowlist. |
| Unresolved lifecycle/clock/replay decision or missing delegated-assumption approval | No activation approval. Verification cannot supply the missing policy decision. |
| Redirect, TLS, exact-size/hash, index/member/ELF or budget violation | Stop; bounded failure diagnostics only, never candidate execution. |
| Positive signature or any negative probe fails, malformed/unknown status, future/expired time | Reject authentication; no algorithm/status broadening or weaker probe. |
| Existing destination, partial write/fsync, missing renameat2, incomplete/failing fallback | Never replace; no token unless a complete diagnostic packet was published. |
| Token conflict, changed/extra/missing file, invalid context or upload-gate failure | No upload; do not manually upload a glob or repair the packet. |
| Timeout, cancellation, absent artifact or upload error | Attempt consumed, evidence incomplete; no success inference from logs or surviving staging. |
| Lock/pin/policy/seal drift or proposed work beyond Ubuntu authentication/static inspection | Stop for separate review; preserve all other S4 and Helios boundaries. |

## Evidence interpretation and open findings

`cryptographic_result` records the adapter's signature/probe outcomes;
`hash_membership_result` binds authenticated metadata to inspected bytes;
`local_observation` records host/toolchain/checker state; `policy_assumption`
records delegated trust and unresolved questions. Unsigned canonical receipts
and hashes detect inconsistency; they do not authenticate the producer.

The integrated consistency checker deliberately rejects the empty Arch section
with exactly `arch fields`. That expected boundary is neither Ubuntu signature
failure nor Arch approval. Its authority flags remain false. The receipt
validator checks data consistency and reports cryptographic verification was
not performed by that validator. Success never means S4 is accepted, execution
is authorized, hardware is attested or trust-policy activation is permitted.

| Finding | Classification | Needed at separate activation review |
| --- | --- | --- |
| Final activation SHA and default-branch workflow registration | Future approval blocker | Review resulting `A`, source tree/actions and registration; bind external approval to it. |
| No connected durable consumed-approval authority | Future approval blocker | Implement and independently review the external contract above; the pure model and synthetic CAS are not production enforcement. |
| Rolling image availability and zstd summary/path ambiguity | Availability / compatibility unresolved | Retain strict admission; explain source observations without claiming unobserved bytes; no automatic repin. |
| Python version/path gap closed; inventory is not complete runtime provenance | Implemented admission / delegated-host decision | Preserve explicit 3.12 check; assess already-loaded extensions, late OpenSSL providers/NSS modules, dlopen, Python stdlib and unpinned Python/library/CA/config observations. |
| Key lifecycle, trusted assessment time and historical replay | Policy unresolved | Record reviewed lifecycle/time/replay decisions or explicitly limit separately authorized evidence gathering to unverified lifecycle/freshness. Do not claim these checks passed. |
| GitHub image/provisioning/control plane and Canonical authority | Delegated assumptions | Name the accepted trust basis; no hardware attestation or independent root of trust is established. |
| Local source/tool/packet TOCTOU and uploader handoff | Delegated runner-integrity limitation | Accept the bounded evidence model explicitly or require further hardening; do not equate atomic publication with immutable upload bytes. |
| Real Ubuntu behavior not exercised in this preparation | Validation limitation | Synthetic success is not real authentication, compatibility or containment evidence. |
| Arch trust, assembly/build/capture/export lifecycle | Outside scope, still blocked | Separate future stages and approvals; no inference from Ubuntu packets. |

## Final approval checklist and no-go decision

Every item below is for a **separate** approval; none is checked here:

- [ ] Reviewer identifies final `A`, exact activation diff, unchanged policy,
  protected pins/locks and all other source seals; source drift has no waiver.
- [ ] Authorized operator, approval window, scope, consumed-authorization record,
  single run/attempt, queue checks and dispatch/rerun restrictions are established.
- [ ] Default-branch registration and checkout/workflow identity are reviewed
  without performing an unauthorized test dispatch.
- [ ] Exact hosted runner image/architecture/application conditions remain
  mandatory, with no substitution and a defined admission-failure response.
- [ ] Tool/keyring identities and Python 3.12 admission are resolved; remaining
  host inventory, dynamic-loading, TLS and provider assumptions are explicit.
- [ ] Key lifecycle, trusted-time basis and historical replay treatment are
  decided and reflected honestly in evidence limitations.
- [ ] Positive/negative signature criteria, exact package/ELF graph and bounded
  data-only scope are accepted without broadening algorithms or status parsing.
- [ ] Success/failure packet semantics, no-replace publication, current-token
  upload gate, provider-log comparison and timely evidence retention are agreed.
- [ ] Failure consumes the attempt; no rerun, repair, repin, policy activation,
  package installation, rootfs/native/desktop activity is implicitly authorized.

**Merge decision:** GO for review/merge of this source-only hardening after
the recorded checks and independent review pass. Merge grants no execution
authority. **Activation decision:** NO-GO to advancing an activation package
while the external authority/observer, runner/toolchain admission and
lifecycle/time/replay decisions remain unresolved. A separate design review may
resolve those blockers; no successful synthetic test is real Ubuntu admission.
This task stops after PR publication.

## Local validation record

The final compatible full suite used the pre-existing environment at
`/home/adrian/Workspace/system/panda-workstation/tmp/s3-integration-review/venv`.
Both it and system Python report **3.14.8**; positive Python 3.12 tests substitute
observations and do not claim Ubuntu runtime evidence. No packages were installed.

| Check | Observed result |
| --- | --- |
| Ubuntu protocol/adapter/artifacts/status/packet/authorization tests | 75 passed; 0 failures/errors/skips. Baseline: 60 passed. |
| S4 external VM stage tests | 21 passed; 0 failures/errors/skips. |
| Bootstrap-provenance tests | 44 passed; 0 failures/errors/skips. |
| Initial full suite, system Python in sandbox, intermediate test tree | 597 run in 135.601 s: 543 passed, 2 failures, 51 errors, 1 skip. This was not a passing run. |
| Final full suite, existing compatible environment outside sandbox | 599 passed in 140.514 s; 0 failures/errors/skips. |
| JSON Schema validation with existing pinned `jsonschema==4.25.1` | Four schemas valid; all 13 existing regressions passed, 0 skips. |
| AST parsing | All six modified/new Python files parse without executing them. |
| Whitespace | `git diff --check` passed. |
| Independent read-only source review | No critical, important or minor actionable findings; Ubuntu 75-test suite independently passed. |

The initial sandbox errors were 48 `test_sandbox_supervisor` setup errors,
two `test_desktop_assessment` preserved-read errors and one
`test_plasma_style` writer error. Sandbox ancestor ownership appears as
UID 65534 instead of root/current UID, triggering the existing fail-closed
ownership rules. The two failures were
`test_permission_failure_never_falls_back_to_plain_read` (earlier ancestor
refusal prevented the expected probe) and `test_android_apply_refused`
(read-only systemctl mask observations were empty, causing an earlier Helios
safety refusal). The skip was
`test_capture_sections_require_each_named_section_once` because system Python
lacks jsonschema. No assertions, safety checks or host policy were changed.
The compatible run removes these environment-specific conditions and uses the
already installed pinned validator; it passed without skips.

Representative verification commands (Fish-compatible, from the feature worktree):

```fish
python3 -B -m unittest discover -s tests -p 'test_ubuntu*.py'
python3 -B -m unittest discover -s tests -p test_external_vm_s4.py
python3 -B -m unittest discover -s tests -p test_bootstrap_provenance.py
python3 -B -m unittest discover -s tests -v
/home/adrian/Workspace/system/panda-workstation/tmp/s3-integration-review/venv/bin/python -B -m unittest discover -s tests -v
git diff --check
```

Schema validation used the existing CI body without its installation step:
assert validator version 4.25.1, call `Draft202012Validator.check_schema` for
every `tests/native/**/*.schema.json`, then discover
`test_external_vm_preparation.py` and require success with no skips.

A Git-object byte comparison against the verified baseline found **330 baseline
files unchanged**, with exactly six modified tracked paths and two new paths.
The policy, both provenance pin files, package lock and disabled workflow are
byte-identical; all other protected inputs are among the unchanged files.
The trust-policy SHA-256 and both provenance-pin SHA-256 values match the
baseline; policy remains `pending-review`. AST comparison additionally
confirmed strict GnuPG status/negative-probe/keyring/protocol functions and the
runner's authentication/invocation/CLI functions are unchanged. The packet
publisher and workflow upload handoff remain byte-identical.

The workflow still has its `.yml.disabled` suffix and exact unconditional
`if: ${{ false }}`; no enabled counterpart exists. AST inspection confirms
`AUTHENTICATION_ENABLED = False`. New model calls occur only in synthetic
tests. No native build/render, rootfs or candidate-execution path was introduced.
No workflow dispatch/rerun or live authority operation was issued during this
task. Remote main was re-fetched before publication and still matched the
baseline. Merge eligibility and authentication authority remain separate.
