# Offline package and rootfs preparation

Source-only proposal for the external VM's locked Arch package set and one Cyber
KSvg frame (`widgets/background.svg`, 288×88, DPR 1). The existing package lock,
candidate contract and native source seal remain authoritative.

## Usage

From the repository root, inspect the stage contract or run the synthetic tests:

```fish
python3 -B tests/native/external_vm/s4/harness.py --plan
python3 -B -m unittest discover -s tests -p test_external_vm_s4.py -v
```

`--plan` checks preserved input hashes and prints JSON to stdout; no checked-in
snapshot is needed. Tests use synthetic metadata and ordinary temporary files.
They do not invoke package tools, rootfs assembly or native code.

## Sealed bootstrap-provenance review

`bootstrap_provenance.review(manifest_bytes, artifact_bytes, now_epoch=...)`
checks bounded in-memory data only. `artifact_bytes` maps manifest identifiers to
already held byte buffers; URLs and file paths are labels, never fetch or read
instructions. The API reuses S4's strict JSON parsing and frozen lock identity.
The CLI refuses unconditionally with a bounded JSON result and exit code 78,
including for help or activation requests.

`bootstrap-provenance.pins.json` records the observed Ubuntu snapshot metadata,
tool-package hashes and Arch source/key identities from the trust investigation.
These are source-controlled consistency references, not independently verified
trust anchors, executable hashes or an activated policy. InRelease hash tables
and package records are parsed; package payloads are only hashed, never decoded.
Package records support LF-delimited Deb822 fields with nonempty space/tab-prefixed
continuations on optional fields. Optional contents retain line breaks and
continuation indentation under lowercase field names within the existing index
budgets. Package, Version, Architecture, Filename, SHA256, Size and Depends remain
single-line fields. Field names are case-insensitive; duplicate fields, orphan or
whitespace-only continuations, malformed declarations and unsupported control or
line-separator characters are rejected.
The runtime graph and certificate/lifecycle fields are declarations whose
consistency can be checked, not proof of ELF dependencies or valid signatures.

Every result has `accepted=false`, `execution_authorized=false` and
`trust_policy_activation_allowed=false`. Even a fully consistent bundle is
blocked on an independently trusted cryptographic verifier, authenticated
package-to-file membership, actual ELF dependency closure and Arch lifecycle
review. `now_epoch` is an explicit assessment context, not a trusted-clock proof.
Unknown proof flags such as `verified=true` are rejected. The synthetic tests
substitute fictional references at the loader boundary; no synthetic success
validates the real certificate set. No result can update `trust-policy.json`.

## Sealed hosted Ubuntu authentication

The [external single-use architecture](ubuntu-single-use-authorization.md) compares
independent authority mechanisms and specifies identity, source observation,
transactions and recovery. Its disconnected SQLite reference tests durable
single-use state locally; it supplies no production gate or execution authority.

The [authorization-readiness review](ubuntu-auth-authorization-readiness.md) records
the reviewed baseline, proposed future activation changes, one-shot scope, admission
criteria, abort conditions and unresolved decisions. It authorizes no execution.
The pure `ubuntu_authorization.consume_approval` model validates proposals for
an external owner's transaction, including scoped reviewed bytes; it is not
connected to the runner and cannot enforce durable single use by itself.
The guide defines the required CAS/identity/time/source-observer interface and
marks production integration blocked. The sealed adapter now explicitly requires
observed final Python 3.12 at resolved `/usr/bin/python3.12` and attempt `1`,
before inventory/acquisition. These local checks do not supply missing approval.

`ubuntu_bootstrap_runner.py` implements the hosted adapter but refuses all CLI
calls with exit 78 while `AUTHENTICATION_ENABLED=False`. The workflow source is
`.github/workflows/panda-ubuntu-bootstrap-verification.yml.disabled`: GitHub does
not load this suffix, and its job additionally has an unconditional false guard.
No source-only test removes these seals or runs the real verification sequence.

The implementation requires a standard x86-64 GitHub-hosted `ubuntu-24.04` runner
reporting image version **20261026.354.1**. Another or missing image fails before
inventory, download or verifier invocation. The rolling runner label cannot
guarantee this version remains available. The exact reviewed source SHA must
match both GitHub's context and the detached checkout. Run/job/runner identity,
actual image, kernel and observed runner-application version are contextual data;
an unobservable/conflicting application version also fails closed.

GitHub image/provisioning/control-plane integrity and Canonical's archive/key
authority are explicit delegated assumptions. No hardware or machine attestation
is established. The preinstalled archive keyring is measured and cross-checked
against the reviewed full fingerprint
`F6ECB3762474EDA9D21B7022871920D1991BC93C`; a downloaded keyring never replaces it.
The adjacent `ubuntu-verification.pins.json` records reviewed package, file and
link observations, **not** an activated trust policy or verified runner inventory.

The future adapter uses only preinstalled `/usr/bin/gpgv`, `/usr/bin/zstd` and
system Python. It inventories their static ELF dependencies, loaded native stdlib
module files, source hashes, dpkg file owners and installed versions, TLS CA bundle
and loader configuration. Keyring evidence includes its resolved path, size,
ownership, mode and digest; every inventoried ELF must have one installed owner.
It refuses influencing environment variables, nonempty system preload files,
unreviewed hardware-capability variants, unsafe ownership and missing dependencies.
Actual loader mappings and the underlying machine's integrity remain unresolved.

The protocol verifies three InRelease signatures and six negative probes (altered
content and an empty isolated keyring for each signature), checks full signing and
primary fingerprints and permitted algorithms, then verifies compressed/plain
index hashes and 13 exact package payloads. Candidate archives are decoded only
as bounded data: no scriptlet, executable, interpreter or library is run. Thirteen
ELFs and all required path aliases are checked against authenticated package
membership, PT_INTERP/DT_NEEDED, SONAME and recorded symbol-version requirements.
No rootfs-shaped output tree is created. Package installation dependencies are a
separate graph outside this static executable closure.

`gpgv` [does not check key expiry or revocation](https://gnupg.org/documentation/manuals/gnupg/gpgv.html).
The implementation rejects failed/expired/revoked statuses when observed, checks
signature expiration itself and rejects an observed anchor-revocation packet.
Complete current key lifecycle, a trusted clock and historical snapshot replay
acceptance remain unresolved; absent Valid-Until values are recorded explicitly.
Successful signature equations never imply those properties.

Nine bounded canonical JSON receipts distinguish cryptographic results, hash
membership, local observations and policy assumptions. Sorted content checksums,
job context and a context binding are separate from the receipts. Changing job
identity does not change content receipts. These
unsigned receipts identify content; they do not authenticate their producer.
`validate_receipts(raw)` binds declared identities to reviewed references and
recomputes the declared static graph. It performs data-only consistency checking
and always returns
`accepted=false`, `execution_authorized=false` and
`trust_policy_activation_allowed=false`. The integrated checker is invoked with
real Ubuntu data and an empty Arch section; its rejection at `arch fields` records
the Ubuntu-only boundary without fabricating Arch evidence or altering its flags.

`ubuntu_packets.py` writes either the exact nine success receipts or an exact
two-document failure set into a fresh private sibling staging directory. Files
are mode 0600, the directory is mode 0700, and every file and the staging directory
are synchronized before publication. A versioned `completion.json` binds the
packet type, hashes, sizes and local filesystem identities. Linux
`renameat2(RENAME_NOREPLACE)` publishes the verified directory atomically without
replacing an existing destination. There is no replacing fallback. This filesystem
primitive uses preinstalled libc through ctypes; the loaded `_ctypes` extension
and its library dependencies enter the verifier inventory. No candidate is loaded.

Incomplete staging is discarded. A publication failure attempts a complete failure
packet from separate fresh staging; if that also fails, no publication token is
handed off. A complete failure packet records `evidence_complete=false` for the
authentication evidence and keeps every authority flag false. Its failure packet
can still be exported as complete diagnostic evidence.

The producer hands off a token binding the completion file and its local identity.
The read-only pre-upload validator checks exact names, packet type, canonical JSON,
ownership, modes, file types, single-link membership, byte limits, hashes, context
binding and final member identities. Only its exact validated path list reaches
upload, and upload additionally requires that validation step to succeed. `always()`
cannot bypass either check. Success packets contain 13 files; failure packets
contain six. The completion manifest and handoff token are contextual filesystem
observations, not deterministic content receipts or machine attestation. Atomic
visibility does not promise recovery after VM or filesystem loss. Mutation after
the final validation remains part of the delegated runner-integrity assumption.

The GnuPG status parsers accept bounded `PLAINTEXT` and optional `PLAINTEXT_LENGTH`
records following GnuPG 2.4.4 DETAILS. Filenames remain opaque escaped metadata and
are never paths. Binary lengths are checked against extracted bytes; text lengths
may differ after line-ending conversion. These informational records cannot replace
the existing positive or negative cryptographic requirements.

Before separately authorized execution, review the exact source revision and the
three explicit source changes needed to enable this template: its suffix, false
job guard and new adapter seal. The minimal proposed run admits one reviewed
image, inventories preinstalled inputs, retrieves only the pinned snapshot's
three releases, four indexes and 13 packages, performs authentication/static
inspection and exports only bounded JSON receipts plus their checksums. No APT,
keyserver retrieval, candidate code, assembly, rendering, S4 activation, external
VM preparation or Arch authentication is part of that scope. Existing S4 seals
and `trust-policy.json` remain untouched. Failure packets identify incomplete
evidence and contain no success or execution authority.

The proposed Python interfaces are:

- `authenticate.authenticate_set(lock_path, policy_path, keyring_path, cache,
  tool_paths, private)`: verify local locked payloads/signatures, reconcile signed
  PKGINFO and dependency closure, and return authentication data in held private
  storage. `private` must be a `common.FdPath` anchor.
- `archives.plan_members(packages)`: admit the complete archive graph as metadata,
  rejecting unsafe paths, collisions, link graphs, special files and budget excess.
- `archives.assemble(destination, lock_path, policy_path, keyring_path, cache,
  tool_paths)`: proposed future VM API that authenticates and replans before writing
  a new private rootfs. It runs no package hooks or scriptlets. Do not invoke it yet.

## Execution restrictions

Authentication and assembly CLIs refuse execution. The delivered trust policy is
`pending-review` and fails before payload/tool work. The underlying Python APIs
are unvalidated source proposals, not approved execution entry points.

Build has a command design only. Capture remains unconditionally sealed.
`check_export_manifest()` validates names, regular-file declarations, hashes and
size budgets only. Both `export_evidence()` and its stage gate refuse every call
before filesystem access, including preparation, build and failure packets.
A claimed `producer_reaped` receipt cannot enable export: the process-tree
kill/reap and prevention of further producer writes are not implemented.

Do not dispatch workflows, install or decode packages, assemble a rootfs, build
or execute the native candidate, render frames or change the Helios desktop
under this source-only proposal. Each execution stage needs separate review and
authorization. Source checks do not establish runtime compatibility or containment.

## Prerequisites for execution

1. Review the public-key trust root, primary/signing identities, revocation and
   validity decisions; record the keyring, lock and existing gpgv/zstd/vercmp tool
   hashes and durable review reference. Do not guess pending policy values.
2. Authenticate all 158 frozen payloads and exact signatures offline. Reconcile
   signed PKGINFO/closure and admit actual archive paths, collisions and links;
   resolve discrepancies through explicit reviewed changes.
3. Validate assembly in a disposable hosted VM with quotas, namespaces and failure
   cases. Require 6 GiB free staging space; enforce the planner's 2 GiB rootfs and
   combined 4 GiB spool/rootfs budgets. A failed destination is incomplete: never
   resume or reuse it as a rootfs or accept a saved receipt as authority.
4. Implement and review the VM build launcher, read-only rootfs admission and
   nonexecuting ELF manifest reader. Measure loader/toolchain provenance and sealed
   build success without running the candidate.
5. Implement and review pre-main confinement, runtime/plugin/font hashes, loaded
   mappings, process-tree limits and complete teardown. Export needs a supervisor
   boundary proving producers are reaped and cannot continue writing, with tests
   for descendants, timeouts and output races before the seal can be removed.
   Native capture additionally needs a separate source-unsealing review.
