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
