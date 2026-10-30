# Panda Audit Lab

Opt-in Debian guest for routine development experiments using user-scoped
`qemu:///session`: 2 vCPU, 4096 MiB RAM and a standalone 40 GiB qcow2 disk.
The guest has no network, shared host directory, clipboard channel, USB/GPU
passthrough or host audio. Session QEMU still runs with the current user's host
privileges. This is not a demonstrated malware containment boundary.

This recovery has offline tests only. Package application, media availability,
real signature verification and unattended guest installation have **not** been
accepted on a live host. Keep deployment gated until the acceptance steps below
are explicitly authorized and completed.

## Package integration and safe preview

From the repository root:

```fish
fish bootstrap/setup-virtualization.fish --dry-run
# Equivalent existing Setup Manager selection:
fish bootstrap/panda-setup.fish --modules virtualization --dry-run
python virtualization/audit_lab.py plan
```

The shortcut delegates to the merged Panda Setup Manager. With no arguments it
previews packages. It accepts the manager's `--check`, `--verify`, and explicit
`--apply` / `--yes` modes; all existing package preflight, confirmation and host
safety gates remain in that manager. It never calls Audit Lab preflight or a VM
command, including after package application.

The single package list is `setup/manifests/virtualization-base.txt`, including
GnuPG, OpenSSL, Python, xorriso and initrd injection tools. Missing packages are
deduplicated with other selected modules. No media is downloaded by setup.
Legacy `setup-workstation.fish` remains unchanged: use the selectable manager
instead of adding an Audit Lab stage to the machine/boot setup workflow.

`audit_lab.py plan` is a pure preview: no subprocess, capability probe, download,
key acquisition or filesystem write. Runtime commands below are separate.
Libvirt client commands may activate an existing user session daemon/socket;
they are not pure previews, even when their requested operation is a query.

## Explicit lifecycle

The following commands describe the **separately authorized live workflow**.
They are not part of the recovery validation or automatic package setup:

```fish
python virtualization/audit_lab.py preflight
python virtualization/audit_lab.py acquire
python virtualization/audit_lab.py verify
python virtualization/audit_lab.py install
python virtualization/audit_lab.py status
python virtualization/audit_lab.py start
python virtualization/audit_lab.py stop
python virtualization/audit_lab.py baseline
python virtualization/audit_lab.py reset --confirm-reset
```

- `preflight` checks tools, trusted storage, free space, KVM permissions, session
  libvirt capabilities and existing domain XML. It does not create a guest.
- `acquire` is the host-network operation: it retrieves public Debian signing
  keys and pinned DVD-1 media plus signed SHA512 checksums. Downloads publish
  only after completion within explicit byte budgets. Existing files are reused, then verified; invalid
  cached media is preserved and fails verification rather than silently replaced.
- `verify` audits domain XML and existing media using `gpgv` with the previously
  acquired public keyring. It never fetches keys or missing media. Before first
  acquisition, missing media is reported as not yet downloaded.
- `install` creates the private disk and preseed, checks generated post-install
  XML with `virt-install --dry-run --print-xml 2`, then explicitly starts the
  unattended installer. The installer uses DVD-1 and no guest NIC or mirror.
  It waits for shutdown and writes a completion marker only after command
  success and domain isolation checks. This marker is not proof that Debian
  installed correctly; inspect the guest before taking a baseline.
- `start` checks the completion marker, disk metadata and domain isolation;
  a running isolated guest is left running. `stop` requests graceful shutdown
  without forced power-off. Check `status` before disk operations.
- `baseline` requires a stopped domain and a completion marker, validates qcow2,
  and makes a one-time standalone copy. It never overwrites an existing baseline.
- `reset` requires shutdown and `--confirm-reset`. It validates and converts the
  baseline to a private pending file before replacing the working disk.
  Failed conversion preserves both the working disk and pending evidence.

All mutating commands use a nonblocking per-lab lock. Do not concurrently operate
on the same domain/files using virt-manager, virsh or another tool: those tools
do not share this lock. The lock file persists; an unlocked file alone is not
evidence that an operation is active.

## Media and local state

The recovered pin is Debian `13.7.0` amd64 DVD-1, using a versioned URL rather
than the moving `current` directory. Its availability has not been checked by a
download. An absent or archived release fails explicitly. A pin/URL update must
be reviewed with fresh Debian release and signing evidence; there is no fallback
to a different image.

Checksums require a valid signature by one of the pinned stable Debian CD
signing keys and exactly one matching SHA512 entry. The fingerprints come from
[Debian's image verification instructions](https://www.debian.org/CD/verify).
Verification fails for unknown signers, changed bytes or duplicate entries.

Acquisition limits are **8 GiB (8,589,934,592 bytes)** for DVD-1,
**1 MiB (1,048,576 bytes)** for `SHA512SUMS`, and
**64 KiB (65,536 bytes)** for `SHA512SUMS.sign`. Declared oversize is refused
before reading the body. Actual streamed bytes are always counted, including
when Content-Length is missing or falsely small. Over-limit, empty and
truncated responses are not published; partial download files are removed.
An existing destination, including one appearing during transfer, is preserved.
These limits bound acquisition; signature and SHA512 verification are still
required before use.

Public keys are exported into the lab's dedicated keyring during `acquire`;
`verify` does not modify that keyring. Upstream
[virt-install documentation](https://github.com/virt-manager/virt-manager/blob/main/man/virt-install.rst)
describes the two-phase XML preview and installer options.

The fixed local root is:

`~/Workspace/VMs/panda-ghostty-audit/`

Managed directories require owner-only permissions. Media, keys, disk, NVRAM,
completion marker and baseline live under that root. Managed files reject
symlinks, hard links and special files. Private files use mode 0600.

An authorized install generates an `auditor` password at
`private/audit-user-password` and a SHA512-crypt hash in `private/preseed.cfg`.
Root login is disabled. Never commit or share either file, VM media, disk
contents or the private directory. Tests use inert fixtures and do not generate
real credentials.

## Storage, isolation and recovery

On `panda-helios`, storage must resolve to the trusted Samsung SATA
`/dev/sda2` (including a subvolume on that partition); other backing devices
are refused. Provisioning requires 55 GiB free, and baseline/reset conversions
require 41 GiB free. A changed device naming or storage layout needs manual
review, not a bypass.

First install refuses an existing domain, disk, baseline, NVRAM or completion
marker. XML rejects guest NICs, host sharing, passthrough, non-loopback VNC,
foreign disks/boot paths, writable firmware and unknown device types.
Disk operations reject backing chains and external data files. VNC is
loopback-only and has no password; local host processes can connect.

A baseline is immutable by convention, not filesystem-enforced. Reset replaces
the working disk only: it does not roll back UEFI NVRAM, domain XML or other
guest/host state. There is no claim of a complete VM snapshot rollback.

If provisioning fails, preserve its domain, disk, credentials and pending files.
Inspect them deliberately before retrying; the tool neither deletes them nor
automatically resumes an ambiguous installation. Do not switch to
`qemu:///system`, enable host networking/shares, or relax host safety policy as
a troubleshooting shortcut.

## Validation and remaining live acceptance

Offline checks (no package install, network download, real libvirt, KVM or VM):

```fish
python -B -m unittest discover -s virtualization/tests -v
python -B -m unittest discover -s tests -p 'test_panda_setup_manager.py' -v
fish -n bootstrap/setup-virtualization.fish bootstrap/panda-setup.fish
fish bootstrap/validate.fish
git diff --check
```

After separate authorization, live acceptance still needs to establish:

1. Official repository package availability and verified package application on
   the intended CachyOS host, without boot/GPU policy changes or service enablement.
2. Availability of the pinned DVD and real signature/SHA512 verification using
   Debian public keys; confirm a tampered copy fails in a disposable location.
3. Session KVM/OVMF capability, trusted storage, and actual generated installer
   and post-install XML for the installed virt-install/libvirt versions.
4. A first unattended offline installation, including DVD detection, preseed
   partitioning of only the new `/dev/vda`, user login and installer shutdown.
5. Real start/stop, absence of NIC/shares/host passthrough, and graceful shutdown.
6. Stopped-guest baseline/reset behavior, guest-disk changes being discarded,
   documented NVRAM persistence, and safe retention after an induced failure.

Do not use hostile code as an acceptance test. The guest is offline and does not
automatically receive security updates; rebuild with a newly reviewed verified
image as needed.
