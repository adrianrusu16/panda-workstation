# External single-use authorization for Ubuntu S4

Source-only architecture and offline reference, 2026-10-30. **Production
integration is blocked. This change authorizes no authentication.**

## Baseline and scope

Fetched `origin/main` equals `1c630e2c08dea0ede40fdc9adc9fc069d5961bc9`
(PR #23); no intervening commits were present. This extends the
[readiness review](ubuntu-auth-authorization-readiness.md) and preserves its
candidate restrictions, runtime admission requirements and three execution seals:

- Workflow remains `panda-ubuntu-bootstrap-verification.yml.disabled`.
- Its job retains unconditional `if: ${{ false }}`.
- Runner retains `AUTHENTICATION_ENABLED = False`.

The runner, pure model, policy, pins, locks and downstream seals are unchanged.
`trust-policy.json` remains byte-identical, `pending-review`, SHA-256
`7c43bbbf0fc1ca9ba9450121402fe8e07c2aa851aaf6fc49bd01933f9f713c2b`.
No candidate bytes, live authorization endpoints, OIDC credentials, infrastructure
or environment configuration are used. The supplied task text ends mid-sentence
in section 10; this milestone implements the complete requirements preceding it.

## Architecture choice

**Prefer A: a small independently administered authority with one transactional
relational store.** Use GitHub workload OIDC for caller authentication and,
if separately approved, an authority-owned GitHub App for API observations.
These are proposed production components, not provisioned dependencies.
The offline SQLite module models only the durable state owner.

The runner must have neither management credentials nor direct database access.
An independent reviewer approves the immutable source and run binding; a distinct
operator initiates the run. The existing model's `operator_id` names the run
operator, not the independent approving reviewer. Production management must
record the reviewer identity separately and prohibit self-approval.
Repository administrators, GitHub, the authority owner, trusted clock, database
administrators and storage remain trusted. This does not contain a malicious host.

| Criterion | A: small service + database | B: GitHub App + external state | C: separately controlled Git state | D: protected environment/manual approval |
| --- | --- | --- | --- | --- |
| Atomicity / linearizability | Single writer/serializable transaction with CAS | Same store needed; App is not a transaction engine | Conditional ref update requires strict ancestry and old-tip enforcement | Approval of one deployment is not a global CAS |
| Durable single use | Consumed tombstone, unique scope, no rollback | Same if backed by A's store | Possible only with immutable history, no delete/reset and exclusive state owner | No permanent execution-scope reservation |
| Separation of duties | Independent owner and reviewer; runner consume-only | Independent installation/operator administration needed | Independent state repo and sole writer, never runner write credentials | Independent reviewer, self-review and bypass restrictions |
| Operator identity | Verified workload + provider observations + approved numeric ID | Installation identity alone does not identify a human/job | Ref writer identity does not prove claimant identity | Reviewer identity is useful; run operator still needs corroboration |
| Run and attempt | Prebound run, exact attempt 1, job binding | Verify OIDC/API; installation token alone insufficient | Requires a separate identity adapter | Per-deployment checks, no cross-run single-use proof |
| Source revision | Approved commit + workflow + observed bytes | Same external observer required | Git objects can bind reviewed bytes, not executed checkout | Branch rules alone do not bind executed bytes |
| Replay | Terminal state + live delivery to one job | Same durable state and delivery rules | Competing sibling commits, no stale success reads | Can approve another deployment/run |
| Revocation | Same transaction boundary as consume | Same store; webhook delays cannot define revocation | Must compete on same ref/tip as consume | Rejecting one deployment is not a global revocation ledger |
| Trusted clock | Authority clock, rollback alarm, boundary checks | Host clock still required | Git author/committer timestamps are untrusted inputs | Wait timers do not supply an approval expiration protocol |
| Permissions | Runner future `id-token: write`; owner management; API read access | App install, key custody and minimal API permissions | State-repo write + anti-delete/force rules and independent administration | Environment configuration and reviewer permissions, plan dependent |
| Operational complexity | One service, one store, clock, audit/backup monitoring | A plus App lifecycle and possibly webhook verification | Ref policy, Git history, identity, clock and recovery logic | Low, but insufficient alone |
| Cost / maintenance | Small continuous hosting/storage; patches, backups, on-call ownership | Hosting plus App/key/permission maintenance | Low storage cost; higher bespoke protocol/policy maintenance | Existing platform controls; availability depends on repository plan |
| Failure recovery | Fail closed; no retry/refund; restore fenced until reconciled | Same; missed/duplicate webhooks never mint authority | Ambiguous push/read requires abort and owner reconciliation | Queue/reapproval can accidentally create another admission |
| Audit | Atomic transition/denial rows plus independent retention | Same, linked to provider event/job IDs | Git history covers transitions, not denied calls without another log | Platform review history, not a complete state-owner audit |
| Barrier before acquisition | Trusted bootstrap releases only after durable consumption | Possible with same explicit bootstrap barrier | Requires equivalent barrier and authenticated live result | Can gate job start, but needs A/B/C for durable single use |

B is a useful integration wrapper for A, not an alternative persistence primitive.
D is recommended defense in depth after a separate configuration review, not the
single-use authority. [GitHub environments](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments)
support reviewer and branch controls, including options against self-review and
administrator bypass; their availability varies by plan/repository.

C is plausible only with a deliberately restricted protocol: one independently
owned ref for the permanent scope, each state commit has exactly one parent equal
to the observed previous tip, and competing consume/revoke proposals are siblings.
A non-forced update to one sibling prevents fast-forward to the other. Never merge
or rebase the losing proposal onto the winner. This is an architectural inference,
not a GitHub REST expected-old-SHA guarantee: the
[update-ref API](https://docs.github.com/en/rest/git/refs#update-a-reference)
documents target `sha` and `force`, not an old-SHA CAS parameter. An ancestry check
alone permits later descendants and therefore needs state-transition enforcement.
An independently controlled receive boundary with expected-old semantics, strict
writer code and protected immutable history would need separate validation.
Trusted time, denied-call logging, rollback prevention and identity still need an
owner. **Environments or ordinary GitHub API writes alone do not enforce all the
required properties.** C adds complexity without removing the independent owner.

## State machine and invariants

The issuer reserves one permanent `(repository_id, ubuntu-s4-authentication-v1)`
scope at draft creation. This scope represents the intended S4 execution, not an
arbitrary client string, run ID or SHA. It is also unique by `(repository_id,
run_id)` and by `approval_id`. Changing the run, SHA, ID or client cannot create a
second approval for this scope. A draft mistake can be revoked, but cannot be
silently replaced. A genuinely different intended execution needs a separately
reviewed policy/version migration preserving the old reservation and history.
The reference intentionally provides no migration or replacement API.

| Current state | Operation | Result |
| --- | --- | --- |
| Absent | Independent owner creates valid template, reserves scope | `draft`, revision 1 |
| Draft | Independent approval of that exact template/revision within window | `approved`, revision +1 |
| Draft or approved | Owner revokes expected revision | `revoked`, revision +1 |
| Approved | Exact verified claim, expected revision, valid bytes/time; CAS commits | `consumed`, revision +1, consumed timestamp |
| Any | Request validation/identity/state/revision fails | Denied audit, no approval mutation or grant |
| Revoked or consumed | Any approval/consumption/replacement | Denied; terminal forever |
| Draft or approved past deadline | Derived `expired` view | Cannot approve/consume; may explicitly revoke |
| Any after uncertain transport/commit | Client `unknown` outcome | Abort; never treat it as approved or retry |

`expired`, `denied` and `unknown` are respectively a derived view, request outcome
and client knowledge state, not new mutable approval states. Clock rollback fails
closed. Neither queueing nor denial extends the validity window. Scope and consumed
tombstones have indefinite retention; deleting/recreating them is prohibited.

Invariants: at most one successful consumption per approval **and intended scope**;
one approved run ID and source SHA; attempt exactly `1`; immutable template;
no implicit renewal, replacement, consumed-to-approved transition, lease, refund
or cached success. Revocation and consumption share one serialization boundary.
No release before durable commit, and no execution following any authorization
failure. Cancellation, local admission failure or missing evidence after consume
leaves the approval consumed. This is **at-most-once admission**, conditional on
the trusted owner/executor boundary, never exactly-once completion.

## Transaction protocol and recovery

The production owner must use the following protocol, illustrated by
[`ubuntu_authority.py`](ubuntu_authority.py). Its SQLite database is a local-test
reference, not the chosen production infrastructure or a distributed consensus
system. [SQLite transactions](https://www.sqlite.org/lang_transaction.html) allow
one writer; `BEGIN IMMEDIATE` acquires that boundary before reading state.
The reference uses rollback journal mode `DELETE`, connection-local
[`synchronous=EXTRA`](https://www.sqlite.org/pragma.html#pragma_synchronous),
and zero lock-wait timeout. Filesystem sync behavior is an assumption, not tested
power-loss durability.

1. Authenticate and authorize the management/workload operation outside this core.
   Reject oversized/malformed requests without interpreting them as records.
   Observe identity/source through the independent adapter; no candidate work.
2. Begin the writer transaction, then sample trusted time and check its persistent
   high-water mark. Store the newer floor in the same transaction. A missing,
   malformed, unavailable or regressed clock aborts. A high-water mark detects
   rollback against committed transactional observations, not a malicious/incorrect
   clock or restored older database. An in-transaction clock regression raises an
   unavailable result and rolls back that transaction, including its newer floor.
   The reference has no durable clock-alarm latch: reopening after such a failure
   may accept a time above the last committed floor. Production must fence the
   owner on clock alarms until independently reconciled, not automatically resume.
3. Load the authoritative row by primary key and exact positive integer revision.
   Reconstruct the immutable template with current state/revision/consumed time;
   never load a client snapshot as authoritative state. Validate with the existing
   pure `consume_approval(record, claim, now, source_files)` contract.
4. Re-sample time after validation, still holding the lock. Require
   `not_before <= boundary < expires_at`. Perform the conditional update:

   ```sql
   UPDATE approvals
   SET state = 'consumed', revision = revision + 1, consumed_at = :boundary
   WHERE approval_id = :id AND state = 'approved' AND revision = :expected;
   ```

   All rows read remain under the same writer boundary, so the preceding deadline
   check and immutable record are part of the conditional transaction. Require
   exactly one changed row. Revocation uses the same lock and revision predicate.
   Whichever terminal transition commits first wins; the other gets no receipt.
5. Insert the success audit row and commit durably before returning anything.
   Validation denials commit a denial row and clock floor without changing the
   approval. Audit-write failure or commit failure produces no receipt. SQL
   triggers additionally prohibit deletion, audit mutation, template changes,
   terminal-state rewrites and non-incrementing revisions. Administrators with
   database-file/schema access can bypass them and are outside this reference's
   threat boundary.
6. Check delivery time again after commit. If commit was slow enough to cross
   expiry, clock fails or response delivery is uncertain, release nothing and
   retain consumption. The decision deadline is checked inside the transaction;
   physical fsync duration cannot be made zero. The production client also needs
   a bounded live response check immediately before acquisition; never cache it.

Only explicit `initialize(path)` creates fresh test storage; it refuses an existing
file. Ordinary operations use SQLite `mode=rw`, validate schema version/journal
mode, and never recreate missing/corrupt storage. Every operation uses a separate
connection; there is no process-local lock posing as shared persistence.

| Failure | Required outcome |
| --- | --- |
| Two claimants / consume-vs-revoke | At most one commits; conflict/busy is denial/unavailability, never retried automatically |
| Crash before commit | Roll back state and audit together; no response was released; prebound run still aborts, owner reconciles/revokes |
| Crash/restart after commit | Reopen sees consumed tombstone and success audit; no reissue |
| Commit returns error / timeout after commit / lost response | Client treats outcome as unknown and aborts; owner inspects durable state, never sends recovery grant |
| Authority/API/clock/storage unavailable | Abort before candidate acquisition; owner later revokes outstanding approval if not already consumed |
| Audit insert unavailable | Roll back transition; no receipt; ingress security log records inability if possible |
| Response lost or deadline passed after commit | Consumption stays committed; audit says committed, not delivered/executed |
| Backup restore / split brain / missing primary | Fence admissions until reconciled against an independently retained high-water mark and full tombstone history |

Production must have one authoritative writer/leader and durability guarantees
covering any failover before releasing a response. Backups alone are insufficient:
restoring an old `approved` image resurrects authority. Preserve all reservations,
terminal states and audits in an independently administered append-only witness
or equivalent non-rollback storage; fail closed when freshness/completeness cannot
be established. A restored owner must remain fenced, reconcile every issued scope,
and revoke unresolved approvals. Do not restore service on a guessed watermark.
Selecting storage, witness, clock and recovery custodians is a production blocker.
The SQLite reference does not implement this infrastructure or protect copied DBs.

The reference transaction log records sequence, owner clock, action, sanitized
approval label, outcome and bounded reason. Approval identity/run/source/review
reference remain in the immutable template linked by approval ID. No raw tokens
or client bodies are logged. A production ingress log must additionally bind
authenticated principal, reviewer, request correlation, job/check identity,
verification/observation digest and denial category. Invalid authentication,
lock contention, storage failure and untrusted-clock requests may never obtain a
database transaction: record these in the independently retained ingress log if
available, but never admit when logging/persistence fails. The reference does not
claim every unavailable request has an atomic database audit.

## Authenticated GitHub identity and future API adapter

There is **no HTTP server, JWT decoder, API client, management authentication or
runner integration** in this reference. All Python arguments are trusted synthetic
inputs, and its receipts have no execution authority.

Future workload endpoint: `POST /v1/approvals/{approval_id}/consume`, body exactly
`{"expected_revision": <positive integer>}`. The ID is a label, not a credential.
Reject duplicate/unknown JSON keys, floats/bools-as-integers, unbounded strings,
oversized bodies and redirects. Never accept trusted claims, timestamps, record
state or source-file hashes from this body. Management create/approve/revoke uses
a separate independently authenticated interface, unavailable to the runner.

The proposed verifier policy is exact issuer
`https://token.actions.githubusercontent.com`, one independently registered
authority-specific audience, approved asymmetric signature algorithms (initially
RS256 only), trusted issuer discovery/JWKS over verified TLS, and no token-provided
key URLs. Check signature, `iss`, `aud`, `sub`, `exp`, `nbf`, `iat`, bounded token
lifetime and owner clock; require `jti` for audit correlation. Proposed initial
maximum `exp-iat` is 600 seconds with no expiry grace; confirm provider
compatibility before deployment, otherwise remain blocked. Unknown key/algorithm,
missing claims, stale key trust or verification/API failure denies. Bounded JWKS
caching is key distribution, never cached approval. Token replay still hits the
single permanent scope and consumed state.

[GitHub's OIDC reference](https://docs.github.com/en/actions/reference/security/oidc)
documents repository, actor, event, ref, run/attempt and workflow claims;
`job_workflow_*` is specific to reusable workflows. Subject format can vary with
environment and repository settings. Pin the reviewed subject policy explicitly
and corroborate numeric IDs, rather than guessing `sub` from a repository name.
Future token acquisition needs `id-token: write`; this milestone changes no
permissions and obtains no tokens.

| Observation | Provenance and required handling |
| --- | --- |
| Repository/name, `repository_id`, owner ID | Signed workload claims corroborated by canonical provider repository; compare to independently registered IDs, never a client-selected repository |
| `run_id`, `run_attempt`, `event_name`, `ref` | Signed claims plus exact provider run/attempt observation; `workflow_dispatch`, `refs/heads/main`, attempt `1` only |
| `actor_id` / operator | Signed initial actor ID plus provider `actor.id`; equals approved operator |
| Triggering actor | Obtain provider `triggering_actor.id`; do not assume a `triggering_actor_id` OIDC claim exists; equals operator and original actor |
| `workflow_ref`, `workflow_sha` | Signed claims; exact registered repository/path/main ref, workflow revision equals activation commit; corroborate run workflow ID/path |
| Reusable workflow identity | Initially disallow reusable/matrix/parallel authorization jobs; any future `job_workflow_ref`/`job_workflow_sha` path needs explicit policy and its own byte review |
| Source commit | Authority retrieves provider run `head_sha` and requires approved A, consistent with signed `workflow_sha`; cross-check signed source `sha` if present, but never assume that claim exists or substitute local `GITHUB_SHA` for provider evidence |
| Current main | Fresh authority GitHub ref observation equals activation commit; an observation is not a cross-system atomic branch lock |
| Job / check identity | Prebind the single intended job, corroborate provider job/check data and signed `check_run_id` if supported; if that linkage cannot be established, block integration rather than admit another job in the run |
| Checkout / source files | Trusted executor observation, not a direct fact proved by an OIDC token or run API |

The [workflow-run API](https://docs.github.com/en/rest/actions/workflow-runs#get-a-workflow-run)
is a corroboration source, including original/triggering actors and run metadata.
The adapter must select the exact run/attempt and a nonterminal intended job,
reject conflicting responses and obtain every required field. Do not map
`head_branch=main` alone to an authenticated `refs/heads/main`; require the signed
ref too. Provider observations are trusted-control-plane assertions, not machine
attestation or atomic snapshots with the authority database. Bound their age
(proposed maximum 30 seconds), recheck before CAS if validation exceeded that
budget, and fail closed on disagreement. Branch protection/freeze is separately
required if policy insists main remain at the reviewed commit until execution.

An [App installation token](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/about-authentication-with-a-github-app)
authenticates an installation, not the particular run's operator/executed bytes.
Keep it server-side for corroboration; never use it alone as a workload assertion
or provide it to the candidate runner. Proposed minimal authority permissions:
repository metadata, Actions read for runs/jobs, Contents read for commit/blob/ref
observations. A custom environment protection callback would additionally need
its reviewed deployment permission/webhook design; it is optional and unconfigured.
Public unauthenticated APIs avoid App key custody but introduce availability/rate
limits; private resources need separately approved credentials. Choose App/hosting
and credential custody only after an independent owner is appointed.

Success is one live authenticated `201` response containing exactly `approval_id`,
`revision`, `state="consumed"`, `consumed_at`, `run_id`, `source_sha`, delivered to
the prebound job after durable commit. It is not a bearer grant for another call.
Use `400` for malformed requests, `401` for failed authentication, `403` for
unapproved/revoked/expired bindings, `409` for reuse/revision conflict, and `503`
or transport failure for unavailable/unknown outcome. No other status, response
shape, stale/cached response or timeout may release acquisition. Disable proxy
response caching and client retry. A later status lookup is diagnostic only.
The small core deliberately collapses denial reasons; the future adapter needs
its own typed response mapping tests before integration.

## Trusted source bytes and the admission barrier

An independent reviewer first reviews the **complete final activation commit A**
on main, including workflow registration, all prerequisites and pinned actions.
The external approval binds A after integration; a pre-merge PR head is insufficient.
The owner prebinds the pending run ID and intended job before independently
approving its template. The first claimant never chooses these bindings.

An owner-side observer retrieves immutable Git objects at A from the registered
repository, validates expected regular-file modes and paths (no symlinks,
submodules or LFS substitutions), and compares their bytes against the reviewed
manifest. Independently verify the workflow at A has the registered future
`.yml` path. The present `.disabled` file is deliberately unregistered; synthetic
fixtures label the future path without creating or activating it.

The existing `ubuntu_authorization.SOURCE_FILES` covers that workflow, runner,
verification/archive/packet readers, common/provenance helpers, both pins, policy
and package lock. It does **not** automatically close over new imports, stdlib,
actions or configuration. This offline authority is not in the executed runner
closure and does not change the existing model's manifest. Future integration
must review the complete activation import/configuration/action closure and
version the manifest if needed, including any newly executed adapter code.
The model's 128 KiB/file and 2 MiB aggregate bounds remain in force.

The authority can authenticate reviewed Git-object bytes and provider workflow/run
revision. It cannot directly see a runner's actual working tree or prevent mutation
there. A separately trusted bootstrap, running before importing candidate/repo
modules or doing inventory/tool invocation/acquisition, must measure the actual
pinned checkout and every required file, bind it to A and the specific job, and
constrain subsequent execution to those bytes. Git HEAD equality alone does not
establish executed-byte integrity; matching hashes supplied by the same mutable
process are assertions. `GITHUB_*` environment values are local assertions too.

Proposed sequence for a future reviewed executor:

1. Start only the approved immutable bootstrap on a fresh single-job runner.
2. Obtain workload identity, establish the pending run/job binding, and prepare
   the pinned checkout without candidate acquisition or repo-code imports.
3. Independently compare source observations; owner authenticates workload/API/Git
   observations and consumes the exact approval transactionally.
4. Accept only that live success on the bound channel; enforce local runtime
   admission and final byte observations before any inventory/acquisition/tools.
5. Enter the one reviewed verification invocation. Any error, interruption or
   missing evidence aborts; never retry, rerun or refund consumption.

Between observation and execution, an ordinary writable checkout can change.
Even read-only file modes or a second hash do not stop a privileged runner from
lying, remounting or replacing inputs. A defensible stronger boundary needs an
independently controlled immutable execution image/mount and launcher (or suitable
attestation) covering interpreter, imports, actions and mutation authority.
Otherwise reviewers must explicitly accept provider/runner integrity as a delegated
assumption. This milestone does not implement either boundary. The architecture
therefore proves only a conditional at-most-once admission decision, not actual
executed-byte authenticity, malicious-runner containment or completion.

## Reference coverage and production blockers

`Authority.initialize(path)` creates only fresh test storage.
`Authority(path, clock=...)` opens existing state; there is no default trusted
clock. Trusted-owner methods are `create_draft(record, claim, source_files)`,
`approve(id, expected_revision)`, `revoke(id, expected_revision)` and
`consume(id, expected_revision, claim, source_files)`. Creation validates the
exact existing record schema using `state=draft`, revision 1, then the pure
validator's approved-template check at `not_before`. That check supplies no
future-time approval. Creation/approve/revoke return no grant. Consume returns a
synthetic six-field receipt after commit/delivery-time checks. `Denied` and
`Unavailable` always mean abort. No CLI or networking path is provided.

Tests use fictional bytes, temporary databases, separate processes/connections,
and simulated process death/storage faults. They exercise terminal transitions,
permanent scope uniqueness, exact schema/revisions, claim/byte mismatches,
expiration before CAS and after commit, clock rollback, consume/revoke races,
audit/commit rollback, response loss and reopen. They do not validate real JWTs,
provider APIs, production crash/power-loss durability or an actual execution gate.

Before production, independently approve and verify: owner/reviewer/operator
policy; durable store and anti-rollback witness; clock/backup/failover procedures;
OIDC audience/claims/job binding and JWT implementation; GitHub API access and
freshness rules; trusted bootstrap/source-to-execution boundary; ingress audit;
single live response admission; pending-run termination/revocation reconciliation;
and a complete separate activation review. Selecting these external trust choices
is deliberately blocked, not guessed by this reference. Removing the three seals
alone remains insufficient.

Unresolved infrastructure choices have these decision criteria; none is selected
or provisioned by the reference:

| Decision | Alternatives | Approval criteria |
| --- | --- | --- |
| Production store | One independently owned host with SQLite; managed relational primary | Durable commit before response, fenced failover, recovery evidence, owner availability and ongoing maintenance budget; local tests qualify neither option |
| Anti-rollback witness | Separately administered append-only journal; independently immutable ledger/storage | Retain every scope/tombstone, detect stale restores, reconcile completeness before unfencing; no common reset authority |
| Clock | Monitored owner clock with independent time/rollback checks; separately operated trusted time source | Bound error and outage behavior, detect regressions, durable alarm fencing and explicit operator recovery; client time is excluded |
| API corroboration | Public provider reads; server-side App installation | Repository visibility, rate/availability limits, least privilege, independent key custody and rotation ownership |
| Execution integrity | Explicitly accepted hosted-runner trust; independent immutable launcher/image or attestation | Reviewer acceptance of residual mutation risk versus infrastructure cost and verifiable source-to-execution binding |

Run the synthetic reference tests from the repository root:

```fish
python3 -B -m unittest discover -s tests -p test_ubuntu_authority.py -v
```
