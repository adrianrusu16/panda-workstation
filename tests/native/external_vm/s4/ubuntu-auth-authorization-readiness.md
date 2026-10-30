# Ubuntu authentication authorization readiness

Source-only review prepared on 2026-10-30. **This document and its PR do not
authorize authentication.** No workflow activation or dispatch is part of this
change. The existing [S4 restrictions](README.md#execution-restrictions) apply.

## Reviewed baseline

GitHub's `main` branch was queried through the authenticated GitHub API before
work began and still resolved to
`626e38ed945bf898fbb4d0b7145f477a13676538`, the integration of
[PR #21](https://github.com/adrianrusu16/panda-workstation/pull/21).
The review branch starts at that commit; the previously cached local
`origin/main` was stale and was fetched before inspection. Unrelated work in
the original checkout was preserved in place; this review uses a separate
worktree. The implementation plan is documentation only: this file and an S4
README link. No production behavior or test expectations change.

Reviewed sources are the [disabled workflow](../../../../.github/workflows/panda-ubuntu-bootstrap-verification.yml.disabled),
[runner](ubuntu_bootstrap_runner.py), [verification protocol](ubuntu_verification.py),
[packet publisher and upload gate](ubuntu_packets.py),
[archive/ELF readers](ubuntu_artifacts.py), both adjacent provenance pin files,
the [pending policy](trust-policy.json), and the corresponding Ubuntu tests,
S4 stage tests and bootstrap-provenance contracts. All references below describe
this baseline, not demonstrated behavior on a real Ubuntu runner.

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

The present concurrency group has `cancel-in-progress: false`: it serializes
runs and can queue another run. It does **not** enforce one shot. The runner
accepts any positive `GITHUB_RUN_ATTEMPT` and has no consumed-authorization
ledger. A future review must establish an enforceable run/admission control
or explicitly approve a documented operator/control-plane boundary with a
single-use approval record, restricted dispatch/rerun access and queue checks.
No such boundary has been established here. An `attempt == 1` check alone
would still permit multiple independent dispatches.

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
  bounded nonempty job/runner names and positive run ID/attempt.
- Observable, nonconflicting runner-application version from a bounded process
  ancestry matching `/home/runner/runners/<version>/bin/Runner.Worker` or
  `Runner.Listener`; later corroborate it against the provider's Set up job log.
  A different path layout or inaccessible ancestry is an abort, not permission
  to guess a version.
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
| System Python | Resolved executable starts `/usr/bin/python3`; native extensions already in `sys.modules` must resolve under `/usr/lib/python3.12/`, at most 32. Inventory requires installed `python3.12-minimal` and `libpython3.12-stdlib`. | Intended interpreter is Python 3.12. The code does not explicitly assert `sys.version_info[:2] == (3,12)` or pin Python/package hashes/versions. The prefix and extension checks are not equivalent to that assertion. |
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
Local identity checks cannot be reproduced from a downloaded archive's newly
created inodes; offline reviewers check content/semantics and provider context,
not pretend the original filesystem identities were independently attested.

## Abort and failure matrix

| Condition | Required disposition |
| --- | --- |
| Missing approval, wrong/finally changed source SHA, wrong ref/event/repository, unregistered workflow | No dispatch; if encountered during an approved run, fail closed. Never substitute PR #21's SHA for `A`. |
| Second dispatch, rerun, queued duplicate, expired approval or attempt other than 1 | No-go; no retry under the same authorization. Existing code does not fully enforce this. |
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
| No technical one-shot/consumed-approval enforcement | Future approval blocker | Establish single-use run control, including queue/rerun handling and the limits of operator enforcement. |
| Rolling image availability and zstd summary/path ambiguity | Availability / compatibility unresolved | Retain strict admission; explain source observations without claiming unobserved bytes; no automatic repin. |
| Python 3.12 intention exceeds explicit version checks; inventory is not complete runtime provenance | Source admission gap / delegated-host decision | Require an explicit version check in a reviewed future change or document an approved equivalent provider boundary; assess late loads and unpinned Python/library/CA/config observations. |
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

**GO to a separate activation review as a source-only review package; NO-GO for
authentication now.** Any unchecked material decision, unresolved approval
blocker, failed admission condition or requested expansion of scope is an
explicit no-go for dispatch. Publication or merge of this documentation PR
cannot grant execution authority. This task stops after PR publication.

## Local validation record

Commands ran from the isolated worktree at the reviewed baseline plus these two
documentation changes. Both local interpreters report Python 3.14.8; this is
synthetic/static validation, not Ubuntu Python 3.12 runtime evidence. No dependency
was installed or downloaded. No new tests were added: existing tests cover the
source/protocol/packet invariants, and this change adds no production behavior.

```fish
python3 -B -m unittest discover -s tests -p 'test_ubuntu*.py' -v
python3 -B -m unittest discover -s tests -p test_external_vm_s4.py -v
python3 -B -m unittest discover -s tests -p test_bootstrap_provenance.py -v
python3 -B -m unittest discover -s tests -v
/home/adrian/Workspace/system/panda-workstation/tmp/s3-integration-review/venv/bin/python -B -m unittest discover -s tests -v
```

| Check | Observed result |
| --- | --- |
| Ubuntu protocol, adapter, artifacts, status and packet tests | 60 passed; 0 failures/errors/skips. |
| S4 stage tests | 21 passed; 0 failures/errors/skips. |
| Bootstrap-provenance tests | 44 passed; 0 failures/errors/skips. |
| Initial full suite, system Python inside sandbox | 584 run: 530 passed, 2 failures, 51 errors, 1 skip; not a passing run. |
| Full suite, existing pinned environment outside sandbox | All 584 passed in 126.533 seconds; 0 failures/errors/skips. |
| JSON Schema regressions using existing `jsonschema==4.25.1` | Four schema definitions valid; all 13 regressions passed, no skips. |

The initial errors were ancestor-owner refusals in desktop assessment, Plasma
artifact writing and sandbox-supervisor fixtures: the filesystem sandbox exposed
`/home` and temporary ancestors as UID 65534 rather than root/current UID. One
failure expected a permission probe that this earlier refusal prevented. The
Android refusal smoke test's expected message was preempted by its read-only
Helios safety check receiving empty systemctl mask states. The skip was the
system Python's absent jsonschema. No safety or test assertion was weakened.
The rerun uses normal host visibility (`/home` UID 0 / mode 0755 and `/tmp`
UID 0 / mode 01777) and a pre-existing environment containing the pinned
validator; it passes without changing host policy or installing packages.

Exact schema command (the existing CI validation body, without its install step):

```fish
/home/adrian/Workspace/system/panda-workstation/tmp/s3-integration-review/venv/bin/python -B -c 'import json,unittest; from importlib.metadata import version; from pathlib import Path; from jsonschema import Draft202012Validator; assert version("jsonschema") == "4.25.1"; paths=sorted(Path("tests/native").rglob("*.schema.json")); [(Draft202012Validator.check_schema(json.loads(p.read_text())), print("Schema valid:", p, flush=True)) for p in paths]; suite=unittest.defaultTestLoader.discover("tests",pattern="test_external_vm_preparation.py"); result=unittest.TextTestRunner(verbosity=2).run(suite); assert result.testsRun and not result.skipped and result.wasSuccessful()'
```

Additional static commands:

```fish
python3 -B -c 'import ast; from pathlib import Path; paths=sorted(Path("tests/native/external_vm/s4").glob("*.py"))+sorted(Path("tests").glob("test_ubuntu*.py")); [ast.parse(p.read_bytes(),filename=str(p)) for p in paths]; print("PASS:",len(paths),"Python sources parsed without execution")'
git diff --exit-code 626e38ed945bf898fbb4d0b7145f477a13676538 -- . ':(exclude)tests/native/external_vm/s4/README.md' ':(exclude)tests/native/external_vm/s4/ubuntu-auth-authorization-readiness.md'
sha256sum tests/native/external_vm/s4/trust-policy.json tests/native/external_vm/s4/ubuntu-verification.pins.json tests/native/external_vm/packages.lock.json
git diff --check
```

Observed: 14 Python sources parse; no diff outside the two intended documentation
paths; all three displayed digests match the baseline table; whitespace check
passes. A separate byte comparison against Git objects confirmed all 334 tracked
baseline files other than the edited README are identical, including all locks,
pins, native source seals, policy and workflow. AST inspection confirms the runner
constant is false; the disabled workflow retains its exact false job guard and
has no enabled filename counterpart. Status contains only the two intended files.

No real authentication, candidate download/install/decode, rootfs assembly,
native candidate execution, rendering, workflow dispatch/rerun/enablement, trust
activation or Helios configuration change occurred. An independent read-only
source-to-document review found no substantive inaccuracies or omissions.
