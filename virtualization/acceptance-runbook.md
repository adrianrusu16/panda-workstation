# Audit Lab operator acceptance runbook

This is a staged **future operator procedure**, not permission to run it now.
PR #29 stays draft until its six live gates have observed acceptance results.
Run one stage at a time, after the owner authorizes that stage's affected
resources. A successful earlier stage does not authorize the next stage.

Use an ordinary user on the intended CachyOS host and the reviewed source
revision. All host command blocks use Fish, from the repository root.
Commands labelled **guest console only** are typed inside this VM's console,
never in the workstation terminal. Do not batch the live blocks into a script.
Record the revision, authorization, exit status and observed result privately;
exclude passwords, preseed contents, raw guest disks and personal host evidence
from Git, PRs and chat.

## What is established, and what is not

Official web observations on **2026-11-01**:

- [Debian's release page](https://www.debian.org/releases/trixie/) identifies
  stable 13.7, released 2026-09-12.
- [Debian's image page](https://www.debian.org/CD/http-ftp/) identifies current
  stable installation images as 13.7.0 and describes DVD-1 as sufficient for a
  standard offline installation.
- [Debian's verification page](https://www.debian.org/CD/verify) lists the two
  stable CD signing fingerprints pinned by this tool:
  `10460DAD76165AD81FBC0CE9988021A964E6EA7D` and
  `DF9B9C49EAA9298432589D76DA87E80D6294BE9B`.

The code pin remains `debian-13.7.0-amd64-DVD-1.iso`, under
`https://cdimage.debian.org/debian-cd/13.7.0/amd64/iso-dvd/`.
The browsing tool could not read the image-server directory because robots.txt
denied access. Exact artifact presence, length, SHA512SUMS bytes/digest and the
detached signature's actual signer/validity were **not** established. No image,
signature or signing key was downloaded or cryptographically executed during
preparation. A web release announcement is not signed-media acceptance.

| Live gate | Offline preparation | Remaining operator evidence |
| --- | --- | --- |
| 1: packages | One manifest, existing manager guards and mock tests inspected | Actual cached-repository availability, approved transaction and installed tools |
| 2: media | Release identity, published fingerprints, bounded/signature/hash refusal tests | Actual versioned artifacts, pinned-key signature/hash and tampered-copy refusal |
| 3: KVM/OVMF/XML | Fixed resource/device/file contracts and XML refusal tests | Session KVM, trusted storage, firmware and actual installer/final XML |
| 4: installation | Offline DVD/preseed arguments and separate readiness gate inspected | Installed-disk boot, login, disk target and shutdown |
| 5: lifecycle/isolation | Session-only start/stop and device constraints tested with doubles | Observed runtime devices, start and graceful shutdown |
| 6: baseline/reset/failure | Standalone-image, stale-receipt and failed-conversion tests | Disk restoration, NVRAM/config persistence and approved live failure cases |

## Resources and universal stop rules

The fixed domain is `panda-ghostty-audit`, using **only** `qemu:///session`.
Its root is `~/Workspace/VMs/panda-ghostty-audit/`; the hard disk is
`disk.qcow2`, with two vCPUs and 4096 MiB guest RAM. Reserve host RAM/CPU
headroom; package checks do not establish memory pressure or VM performance.

The code requires 55 GiB free before provisioning and 41 GiB before each
baseline/reset conversion. These are per-operation minima, not the whole
acceptance budget. A conservative full-run budget is **150 GiB free** on the
trusted filesystem: up to three 40 GiB disk images, an 8 GiB ISO, an 8 GiB
negative-test copy and overhead. Sparse allocation may use less; do not rely on
that to pass capacity checks. On `panda-helios`, the backing source must be
Samsung SATA `/dev/sda2`, optionally with a subvolume suffix.

Stop advancing on any nonzero status, unexpected path/device, unsafe permissions,
changed receipt, unavailable tool, pending-upgrade/package-policy refusal or
missing evidence. An explicitly labelled negative test is successful only for
its specified refusal; any other error is a stop, not a pass.

Never switch to `qemu:///system`, add a NIC, host directory/socket sharing,
clipboard, passthrough or host GPU acceleration. Do not enable services, change
user/group membership, firmware, kernels, boot/GPU/sleep policy or storage layout
to make a check pass. Escalate those prerequisites as separate owner decisions.
Do not delete/undefine guests, overwrite disks/receipts, clear pending files or
adopt existing state automatically. Do not run hostile code as acceptance data.

No concurrent libvirt/virt-manager mutations or disk operations: external tools
do not share the lab lock. In virt-manager use this domain's console only;
do not edit its hardware or configuration.

## Stage 0 — Select source and preview

**Authority/resources:** source inspection and pure preview only; unittest
allocates new temporary synthetic fixtures. No package, guest or media action.

```fish
git status --short
git rev-parse HEAD
python -B virtualization/audit_lab.py plan
fish --no-config bootstrap/setup-virtualization.fish --dry-run
python -B -m unittest discover -s virtualization/tests -v
```

**Expected/success:** the owner has reviewed this exact clean revision, the plan
names the fixed VM/resources/13.7.0 pin, the package preview ends
`DRY RUN COMPLETE`, and the Lab suite passes (52 tests at preparation revision).
Record unrelated work rather than discarding it. A clean checkout is not a live
readiness result.

**Failure/stop:** preserve the source and outputs; resolve a source or test
failure through normal review. Do not execute the legacy all-workstation master
or rerun old recovery patches. Establish separately whether current main needs
integration before accepting this revision; do not rebase or force-push it.

## Stage 1 — Package eligibility and separately approved application (gate 1)

**Authority/resources:** first command reads host policy and cached pacman
metadata. The second installs missing packages using sudo/pacman and may run
system package hooks; it needs explicit transaction authorization. No VM/media
action is part of this stage.

Run each command separately, inspecting its status before continuing:

```fish
fish --no-config bootstrap/setup-virtualization.fish --check
```

Expected `READINESS CHECK PASSED`. Cached repository state must be usable and
package policy must accept the complete transaction. If it requests unrelated
kernel/GPU/boot changes, pending upgrades or recovery-critical dependencies,
stop for the owner. Do not refresh only sync databases or bypass the guard.

After separate package-application approval, inspect the transaction and type
the literal `APPLY` only if it matches that approval:

```fish
fish --no-config bootstrap/setup-virtualization.fish --apply
fish --no-config bootstrap/setup-virtualization.fish --verify
```

Expected application success and `VERIFICATION COMPLETE`, with every selected
manifest package present and Helios post-hook safety checks passing. Hooks may
have effects even if pacman fails. A failure leaves prior changes in place;
preserve diagnostics, stop later stages and investigate before reboot/retry.
Do not enable libvirt services as a fallback.

The reviewed manifest and binary prerequisites are:

| Package layer | Commands/resources checked later |
| --- | --- |
| qemu-base and its resolved dependencies | qemu-img, qemu-system-x86_64, x86_64 KVM support |
| libvirt | virsh and an available user session connection |
| virt-install / virt-manager | local installer and console UI |
| edk2-ovmf | readable packaged UEFI loader/template |
| gnupg / openssl / python | gpg, gpgv, password hashing, Python 3 |
| xorriso / cpio / gzip / findutils | local DVD extraction/initrd injection |
| Existing Arch base utilities | findmnt and the normal user filesystem tools |

This table is a source dependency map, not proof that a particular host's
repository resolved it. Verify actual commands without starting them:

```fish
set -l panda_missing_programs
for program in python virsh qemu-img qemu-system-x86_64 virt-install virt-manager gpg gpgv openssl findmnt xorriso cpio gzip find
    if not command -s $program
        set -a panda_missing_programs $program
    end
end
if test (count $panda_missing_programs) -gt 0
    printf "STOP: missing prerequisites: %s\n" (string join ", " -- $panda_missing_programs)
    false
end
```

Every name must resolve. Missing commands or firmware stop the stage; do not
install replacements or change the manifest without review.

## Stage 2 — Session/KVM/storage eligibility (host part of gate 3)

**Authority/resources:** authorize actual host capability/storage queries.
Connecting a libvirt client can activate an existing user daemon/socket even
though no guest is created. This is not the pure preview.

```fish
free -h
nproc
python -B virtualization/audit_lab.py preflight
python -B virtualization/audit_lab.py status
```

**Expected/success:** trusted backing source, at least the required free space,
`KVM and session libvirt: OK`, and `VM not defined yet` / status `absent` for
a fresh acceptance. The code checks readable/writable `/dev/kvm` and x86_64 KVM
domain capabilities. Record resource headroom separately; these checks do not
measure host available RAM. Record `free -h` / `nproc` results and ensure the
owner has reserved the two vCPUs and 4096 MiB plus host/QEMU headroom; low memory
or CPU pressure is a stop, not permission to change power/GPU policy.

**Failure/stop:** existing domains/files mean this is not a fresh install: stop
and reconcile their provenance. Permission, connection, free-space or firmware
problems need owner review; no system connection, service enablement, module,
storage or permission-policy workaround is authorized here. No XML or actual
guest behavior is accepted by this stage alone.

## Stage 3 — Acquire and authenticate exact media (gate 2)

**Authority/resources:** authorize host Internet access to the pinned Debian
image URL and HKPS Debian keyserver, up to 8 GiB ISO + 1 MiB checksums + 64 KiB
signature, private lab/keyring directories and possible user GPG helper daemons.
The guest has no network. A versioned URL returning 404 is a stop, not permission
to choose `current`, another image or another signer.

```fish
python -B virtualization/audit_lab.py acquire
python -B virtualization/audit_lab.py verify
```

**Expected/success:** exit zero and
`Verified Debian signing key + SHA512: debian-13.7.0-amd64-DVD-1.iso`.
The checks require a successful gpgv signature status pinned to a listed stable
CD key and exactly one matching SHA512 entry. Independently record the actual
observed signer/digest privately if required by the owner; do not invent them
from the release page. Verification may repeat KVM/session preflight.

After authorizing a second local ISO-sized copy, run the following negative
test. It changes one byte of a **new copy**, keeps the real signed checksums and
leaves the real ISO/keyring unchanged. It retains its new private directory:

```fish
python -B -c '
from pathlib import Path
import shutil, sys, tempfile
sys.path.insert(0, "virtualization")
import audit_lab as lab
base, iso, _ = lab.paths()
trial = Path(tempfile.mkdtemp(prefix=".media-negative-", dir=base))
for name in (lab.ISO_NAME, "SHA512SUMS", "SHA512SUMS.sign"):
    shutil.copy2(iso.parent / name, trial / name)
target = trial / lab.ISO_NAME
with target.open("r+b") as stream:
    first = stream.read(1)
    if not first:
        raise SystemExit("STOP: empty copied ISO")
    stream.seek(0)
    stream.write(bytes([first[0] ^ 1]))
try:
    lab.verify_iso(base, target)
except lab.LabError as error:
    if "SHA512 mismatch" not in str(error):
        raise
    print("EXPECTED REJECTION: tampered copied ISO")
else:
    raise SystemExit("STOP: changed ISO was accepted")
print("Retained public-media negative copy:", trial)
'
```

**Failure/stop:** anything except the named hash-mismatch refusal is a failed
negative test. Preserve invalid cached media and evidence; do not auto-redownload,
replace keys, disable signatures or delete pending/old files. The retained copy
consumes capacity; any cleanup is a deliberate later owner action.

## Stage 4 — Unattended installation and actual XML (gates 3 and 4)

**Authority/resources:** explicitly authorize a first new disk, private generated
auditor credential/preseed, NVRAM, installer cache/log files, session domain
definition, CPU/RAM use and first guest boot. The installer writes **guest**
`/dev/vda`; no host device is attached for partitioning. Source preseed intent
is not proof that this installation consumed it correctly. See
[Debian's preseed reference](https://www.debian.org/releases/trixie/amd64/apbs04.en.html)
for the underlying installer fields.

```fish
python -B virtualization/audit_lab.py install
```

The command waits for shutdown. Its generated post-install XML must pass the
tool's checks before actual launch. In a second authorized host terminal, while
the installer is active, inspect both views without editing:

```fish
virsh -c qemu:///session dumpxml panda-ghostty-audit
virsh -c qemu:///session dumpxml panda-ghostty-audit --inactive
virt-manager --connect qemu:///session
```

Use only this guest's console in the GUI. Record XML privately. Check:

- Exactly one file qcow2 hard disk, the fixed lab `disk.qcow2`, virtio `vda`;
  no external backing/data file or host block device.
- Two vCPUs, 4096 MiB, KVM/x86_64, packaged read-only pflash loader and private
  `nvram.fd`. No host GPU acceleration.
- No interface, filesystem share, hostdev, channel, redirection, TPM, RNG,
  shmem or vsock. Only loopback VNC; no host audio/input passthrough.
- Installer-only kernel/initrd paths and preseed boot arguments must correspond
  to the verified DVD's `install.amd/vmlinuz` / `install.amd/initrd.gz`
  extraction. The only installer optical medium is the verified ISO, read-only.
  After install, kernel/initrd/cmdline boot overrides must be gone; the CD-ROM
  may be empty. Do not relax the final-domain validator for installer paths.

**Expected/success:** console shows unattended offline installation targeting
only the new 40 GiB virtio disk. No network mirror, additional media or firmware
download is needed. The installer shuts down; the host command exits zero and
prints installer completion. Then:

```fish
python -B virtualization/audit_lab.py status
python -B virtualization/audit_lab.py verify
```

Expect `shut off` and final isolation/media checks passing. The
`.install-completed` file proves only successful host command completion and
checks. It is not guest readiness. Do not display or collect the generated
password or preseed in logs, PRs or chat; use the credential privately.

**Failure/stop:** manual installer questions, wrong disk, unexpected devices,
signature/media errors, missing shutdown or a nonzero command status are not
success. For the first trial, stop advancing after 30 minutes without completion
and inspect the console; do not mistake cancellation for guest shutdown.
Preserve domain/disk/NVRAM/private files and pending evidence. Do not reinstall,
force-power-off, undefine or accept readiness. If graceful recovery cannot be
established using the guest's own controls, obtain a separate recovery decision.

## Stage 5 — Installed boot, observed isolation and readiness (gates 4 and 5)

**Authority/resources:** authorize guest startup and manual console inspection,
then graceful shutdown. The same loopback console connection may be used.

```fish
python -B virtualization/audit_lab.py start
python -B virtualization/audit_lab.py status
python -B virtualization/audit_lab.py verify
virsh -c qemu:///session domiflist panda-ghostty-audit
virsh -c qemu:///session domblklist panda-ghostty-audit --details
virsh -c qemu:///session dumpxml panda-ghostty-audit
```

**Expected:** status `running`, XML/media checks pass, no interface rows, only
the fixed working disk and optional empty/verified read-only optical device.
Inspect the actual runtime XML as well as the command's pass message.

Log into the installed guest as `auditor`. **Guest console only:**

```fish
id -un
cat /etc/debian_version
lsblk -o NAME,TYPE,SIZE,MOUNTPOINTS
findmnt -no SOURCE /
ip -brief link
ip route
sudo passwd --status root
printf "baseline-approved\n" > ~/panda-baseline-acceptance.txt
```

Expect `auditor`, Debian 13-family release information, root on a partition of
the new `vda`, loopback only and no default route. The guest-only sudo command
may ask for the auditor password privately; expect root status `L` (locked),
not `P` or `NP`. Do not run it on the host. The text witness is
harmless test data, not a password or acceptance proof. Missing guest diagnostic
tools or ambiguous results stop acceptance; do not add a NIC to install them.

On the **host**, request shutdown and repeat status until shut off:

```fish
python -B virtualization/audit_lab.py stop
python -B virtualization/audit_lab.py status
```

Expect `Graceful shutdown requested`, then `shut off` within 60 seconds. A request
alone is not shutdown proof. If not shut off, stop and investigate; no force
destroy is authorized.

Before acceptance, this labelled negative test must refuse with a missing
readiness message and leave the baseline/pending disk absent:

```fish
python -B virtualization/audit_lab.py baseline
```

Only after all the preceding observations are accepted by the operator:

```fish
python -B virtualization/audit_lab.py accept-readiness --confirm-readiness
```

**Success:** explicit operator readiness accepted, with a private receipt bound
to UUID, inactive XML and installation marker. Repeating this exact command for
unchanged state is idempotent. **This is an operator assertion, not automated
guest proof, publisher authentication or proof of all six gates.**

**Failure/stop:** absent/unsafe/stale receipts or changed guest identity/config
must be investigated and retained; do not copy/refresh a receipt to bypass a
failure. If a receipt already exists at the start of this fresh trial, reconcile
that state before proceeding rather than expecting the negative test to pass.

## Stage 6 — Baseline/reset and failure acceptance (gate 6)

**Authority/resources:** explicitly approve one-time baseline creation, another
working-disk replacement and disposal of subsequent guest changes. Reserve
41 GiB free before each conversion; the snapshot does not include NVRAM or XML.

With the guest confirmed shut off:

```fish
python -B virtualization/audit_lab.py baseline
python -B virtualization/audit_lab.py start
```

Expect a newly published baseline and a normal installed-disk boot. In the
**guest console only**:

```fish
cat ~/panda-baseline-acceptance.txt
printf "discard-this-change\n" > ~/panda-after-baseline.txt
```

The first file must contain `baseline-approved`. Shut down from the **host**:

```fish
python -B virtualization/audit_lab.py stop
python -B virtualization/audit_lab.py status
```

Proceed only after the observed state is `shut off`. A successful `status`
command alone does not establish shutdown. Then measure:

```fish
set -l lab_root "$HOME/Workspace/VMs/panda-ghostty-audit"
and sha256sum "$lab_root/nvram.fd"
and begin
    virsh -c qemu:///session dumpxml panda-ghostty-audit --inactive | sha256sum
    set -l lab_xml_status $pipestatus
    if test "$lab_xml_status[1]" -ne 0; or test "$lab_xml_status[2]" -ne 0
        printf "STOP: XML acquisition/hash failed; discard this measurement\n" >&2
        false
    else
        true
    end
end
```

Record the two hashes privately only after this block succeeds. This negative
confirmation test must refuse and preserve the current working disk:

```fish
python -B virtualization/audit_lab.py reset
```

Expect the explicit `--confirm-reset` refusal. Now, after destructive reset
authorization:

```fish
python -B virtualization/audit_lab.py reset --confirm-reset
and sha256sum "$lab_root/nvram.fd"
and begin
    virsh -c qemu:///session dumpxml panda-ghostty-audit --inactive | sha256sum
    set -l lab_xml_status $pipestatus
    if test "$lab_xml_status[1]" -ne 0; or test "$lab_xml_status[2]" -ne 0
        printf "STOP: XML acquisition/hash failed; discard this measurement\n" >&2
        false
    else
        true
    end
end
```

Accept each pair of hashes only when both checksum commands and the XML producer
succeeded. A printed digest with a STOP or nonzero result is invalid evidence.
Compare the before/after pairs privately and stop if either differs. Only after
confirming working-disk replacement and unchanged NVRAM/inactive-XML hashes,
start the guest:

```fish
python -B virtualization/audit_lab.py start
```

Expect successful boot. In the **guest console only**:

```fish
cat ~/panda-baseline-acceptance.txt
test ! -e ~/panda-after-baseline.txt && printf "RESET WITNESS ABSENT\n"
```

Expect retained baseline witness and `RESET WITNESS ABSENT`. Finish with host
`stop` / `status` as in Stage 5; retain the domain, disk, baseline, NVRAM, receipts
and evidence.

**Failure/stop:** conversion/check/readiness failures must leave the previous
working disk and any pending image available for investigation. Do not rerun over
a pending file or use the baseline as permission to delete guest data. The offline
`test_failed_reset_retains_working_disk_and_pending_evidence` exercises the
mid-conversion error branch with tool doubles. It is not a real conversion fault.

The live gate's induced partial-conversion-failure case still needs a separately
reviewed disposable fault-injection procedure and authorization. This runbook
does not authorize power cuts, filling the trusted SSD, corrupting managed
images or interrupting a live converter to manufacture failure. Record this case
as **not accepted**, even if the happy path and confirmation refusal passed.

## Acceptance record and next decision

For each gate record `not run`, `failed`, `partially observed` or `accepted`,
the exact source revision and actual command/result. Do not promote a gate using
fixture results, a release announcement, an installed-file marker or a readiness
receipt. Gate 3 is incomplete until both actual installer and final XML have been
reviewed; gate 6 is incomplete while its approved failure case is outstanding.

Keep PR #29 draft until the owner has accepted all required live evidence.
A source fix discovered during acceptance returns to isolated RED/GREEN tests,
independent review and an ordinary update of the existing branch. No automatic
merge, destructive cleanup or protected host workaround is part of this guide.
