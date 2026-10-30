#!/usr/bin/env python3
"""Panda Audit Lab: opt-in, offline, qemu:///session VM lifecycle.

Never run as root. No service enablement, host sharing, or guest networking.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager, nullcontext
import fcntl
import json
import stat
import hashlib
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import xml.etree.ElementTree as ET

VM_NAME = "panda-ghostty-audit"
CONNECTION = "qemu:///session"
VERSION = "13.7.0"
ISO_NAME = f"debian-{VERSION}-amd64-DVD-1.iso"
BASE_URL = f"https://cdimage.debian.org/debian-cd/{VERSION}/amd64/iso-dvd/"
FINGERPRINTS = {
    "10460DAD76165AD81FBC0CE9988021A964E6EA7D",
    "DF9B9C49EAA9298432589D76DA87E80D6294BE9B",
}
VM_CPUS, VM_RAM_MIB, VM_DISK_GIB = 2, 4096, 40
DOWNLOAD_LIMITS = {
    ISO_NAME: 8 * 1024**3,
    "SHA512SUMS": 1024**2,
    "SHA512SUMS.sign": 64 * 1024,
}


class LabError(Exception):
    pass


def call(*argv: str, check: bool = True, capture: bool = True, **kwargs):
    try:
        return subprocess.run(argv, check=check, text=True, capture_output=capture, env={**os.environ, "LC_ALL": "C"}, **kwargs)
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise LabError(f"Command failed: {argv[0]} (exit {getattr(exc, 'returncode', 'unavailable')})") from exc


def paths() -> tuple[Path, Path, Path]:
    home = Path.home()
    base = home / "Workspace/VMs" / VM_NAME
    return base, base / "iso" / ISO_NAME, base / "disk.qcow2"


def check_user():
    if os.geteuid() == 0:
        raise LabError("Refusing to run as root; qemu:///session is user scoped")


def require_programs(*programs):
    missing = [program for program in programs if not shutil.which(program)]
    if missing:
        raise LabError("Missing programs: " + ", ".join(missing))


def ensure_safe_base(base: Path):
    """No symlink traversal within the managed VM path (or its parents)."""
    for path in (base, *base.parents):
        if path.is_symlink():
            raise LabError(f"Symlink in VM storage path: {path}")
    home = Path.home().resolve()
    if not base.is_relative_to(home):
        raise LabError("VM must reside under the user's home directory")


def regular_file(path: Path, *, nonempty=False, private=False):
    """Reject symlinks, special files and hard-linked managed files."""
    for candidate in (path, *path.parents):
        if candidate.is_symlink():
            raise LabError(f"Symlink in managed path: {candidate}")
    try:
        info = path.stat()
    except FileNotFoundError as exc:
        raise LabError(f"Missing managed file: {path}") from exc
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_nlink != 1:
        raise LabError(f"Unsafe managed file: {path}")
    if nonempty and info.st_size == 0:
        raise LabError(f"Empty managed file: {path}")
    if private and info.st_mode & 0o077:
        raise LabError(f"Private file permissions required: {path}")


def private_directory(path: Path):
    for candidate in (path, *path.parents):
        if candidate.is_symlink():
            raise LabError(f"Symlink in managed path: {candidate}")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise LabError(f"Owned mode 0700 directory required: {path}")


def reserve_file(path: Path):
    """Reserve a private output before a tool which otherwise overwrites it."""
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError as exc:
        raise LabError(f"Output already exists; inspect manually: {path}") from exc
    os.close(fd)


def write_private(path: Path, content: str):
    private_directory(path.parent)
    if path.exists() or path.is_symlink():
        regular_file(path, private=True)
    fd, temporary = tempfile.mkstemp(prefix=".write-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def operation_lock(base: Path):
    """Serialize this tool's mutators; never unlink a held lock."""
    private_directory(base)
    fd = os.open(base / ".operation.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        regular_file(base / ".operation.lock", private=True)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise LabError("Another Audit Lab operation is in progress") from exc
        yield
    finally:
        os.close(fd)


def assert_safe_image(path: Path):
    regular_file(path, private=True)
    try:
        info = json.loads(call("qemu-img", "info", "--output=json", "-f", "qcow2", str(path)).stdout)
    except (ValueError, TypeError) as exc:
        raise LabError("Invalid qemu-img metadata") from exc
    def external(value):
        if isinstance(value, dict):
            return any((key in {"backing-filename", "full-backing-filename", "data-file"} and item)
                       or external(item) for key, item in value.items())
        return isinstance(value, list) and any(external(item) for item in value)
    if (not isinstance(info, dict) or info.get("format") != "qcow2"
            or info.get("virtual-size") != VM_DISK_GIB * 1024**3 or external(info)):
        raise LabError("Expected standalone 40 GiB qcow2 without backing or external data")


def physical_storage_check(base: Path, required_gib=55):
    """Reject known-untrusted NVMe on panda-helios; otherwise report the target."""
    parent = base
    while not parent.exists():
        parent = parent.parent
    result = call("findmnt", "-n", "-T", str(parent), "-o", "SOURCE").stdout.strip()
    if not result:
        raise LabError("Could not resolve VM filesystem")
    print(f"Storage backing {parent}: {result}")
    if os.uname().nodename == "panda-helios":
        if result.split("[", 1)[0] != "/dev/sda2":
            raise LabError("panda-helios VM storage must remain on Samsung SATA /dev/sda2")
    usage = shutil.disk_usage(parent)
    print(f"Free: {usage.free // (1024**3)} GiB")
    if usage.free < required_gib * 1024**3:
        raise LabError(f"Need at least {required_gib} GiB available for this operation")


def domain_exists() -> bool:
    proc = call("virsh", "-c", CONNECTION, "list", "--all", "--name", check=False)
    if proc.returncode != 0:
        raise LabError("Cannot inventory session domains; refusing to assume absence")
    return VM_NAME in proc.stdout.splitlines()


def domain_xml(*, inactive=False) -> ET.Element:
    args = ("--inactive",) if inactive else ()
    try:
        return ET.fromstring(call("virsh", "-c", CONNECTION, "dumpxml", VM_NAME, *args).stdout)
    except ET.ParseError as exc:
        raise LabError("Invalid domain XML") from exc


def assert_isolated(root: ET.Element, expected_disk: Path):
    for tag in ("name", "vcpu", "memory", "devices"):
        if len(root.findall(tag)) != 1:
            raise LabError(f"Expected exactly one {tag} section")
    if len(root.findall("os")) > 1:
        raise LabError("Duplicate guest OS sections")
    firmware_roots = (Path("/usr/share/edk2"), Path("/usr/share/edk2-ovmf"), Path("/usr/share/OVMF"))
    for loader in root.findall("./os/loader"):
        if (loader.get("readonly") != "yes" or loader.get("type") != "pflash"
                or not loader.text or not any(
                    Path(loader.text).is_relative_to(directory)
                    and ".." not in Path(loader.text).parts
                    for directory in firmware_roots)):
            raise LabError("Unexpected writable or foreign firmware loader")
    for nvram in root.findall("./os/nvram"):
        source = nvram.find("source")
        filename = source.get("file") if source is not None else nvram.text
        if filename != str(expected_disk.parent / "nvram.fd"):
            raise LabError("Unexpected guest NVRAM path")
    for emulator in root.findall("./devices/emulator"):
        if emulator.text != "/usr/bin/qemu-system-x86_64":
            raise LabError("Unexpected host emulator")

    if any(node.tag.startswith("{") for node in root if node.tag != "metadata"):
        raise LabError("Unexpected namespaced domain extension")
    if (any(root.find(f"os/{item}") is not None
            for item in ("kernel", "initrd", "cmdline", "dtb", "bootloader"))
            or root.find("bootloader") is not None):
        raise LabError("Direct host boot paths are forbidden after installation")
    forbidden = ("interface", "filesystem", "hostdev", "redirdev", "channel", "smartcard", "tpm", "rng", "shmem", "vsock")
    devices = root.find("devices")
    if devices is None:
        raise LabError("Domain XML has no devices section")
    for item in forbidden:
        if devices.find(item) is not None:
            raise LabError(f"Isolation failed: forbidden {item} device exists")
    disks = [node for node in devices.findall("disk") if node.attrib.get("device") == "disk"]
    if len(disks) != 1:
        raise LabError("Expected exactly one virtual hard disk")
    source = disks[0].find("source")
    if (source is None or source.get("file") != str(expected_disk)
            or set(source.attrib) - {"file", "index"}
            or not source.get("index", "1").isdigit() or len(source)):
        raise LabError("Unexpected disk path")
    driver = disks[0].find("driver")
    target = disks[0].find("target")
    if (disks[0].get("type") != "file" or driver is None or driver.get("type") != "qcow2"
            or target is None or target.get("dev") != "vda" or target.get("bus") != "virtio"):
        raise LabError("Expected file qcow2 virtio vda disk")
    for node in devices.findall("disk"):
        backing = node.find("backingStore")
        if (backing is not None and (backing.attrib or len(backing))) or node.find("dataStore") is not None:
            raise LabError("External disk backing/data store forbidden")
    if root.findtext("name") != VM_NAME:
        raise LabError("Unexpected VM name")
    if root.findtext("vcpu") != str(VM_CPUS):
        raise LabError("Unexpected guest CPU allocation")
    memory = root.find("memory")
    if memory is None:
        raise LabError("Guest memory definition missing")
    mult = {"KiB": 1, "MiB": 1024}.get(memory.get("unit", "KiB"))
    if (mult is None or not memory.text or not memory.text.isdigit()
            or int(memory.text) * mult != VM_RAM_MIB * 1024):
        raise LabError("Unexpected guest memory allocation")
    for dev in devices.findall("disk"):
        if dev is disks[0]:
            continue
        if dev.get("device") != "cdrom":
            raise LabError("Unexpected additional guest disk device")
        cdsource = dev.find("source")
        if dev.get("type") != "file" or (cdsource is not None and (
                cdsource.get("file") != str(expected_disk.parent / "iso" / ISO_NAME)
                or set(cdsource.attrib) - {"file", "index"}
                or not cdsource.get("index", "1").isdigit() or len(cdsource))):
            raise LabError("Unexpected CD-ROM medium")
        if dev.find("readonly") is None:
            raise LabError("Guest CD-ROM must be read-only")
    for io in ("serial", "console"):
        for dev in devices.findall(io):
            if dev.get("type") != "pty":
                raise LabError(f"Unexpected {io} endpoint")
    if devices.find("parallel") is not None:
        raise LabError("Unexpected parallel endpoint")
    allowed = {"emulator", "disk", "controller", "serial", "console", "graphics", "video", "input", "memballoon", "audio"}
    for dev in devices:
        if dev.tag not in allowed:
            raise LabError(f"Unexpected device: {dev.tag}")
        if dev.tag == "audio" and dev.get("type") != "none":
            raise LabError("Host audio connection forbidden")
        if dev.tag == "video" and dev.find(".//acceleration") is not None:
            raise LabError("Host GPU acceleration forbidden")
        if dev.tag == "input" and (
                dev.get("type") not in {"mouse", "keyboard", "tablet"}
                or dev.find("source") is not None):
            raise LabError("Host input passthrough forbidden")
    for graphics in devices.findall("graphics"):
        if (graphics.find("gl") is not None or graphics.get("type") != "vnc"
                or graphics.get("socket") or graphics.get("listen") not in ("127.0.0.1", "::1")):
            raise LabError("VNC graphics must be loopback-only")
        for listener in graphics.findall("listen"):
            if listener.get("type") != "address" or listener.get("address") not in ("127.0.0.1", "::1"):
                raise LabError("Every VNC listener must be loopback-only")


def preflight(base: Path):
    check_user()
    require_programs("virsh", "qemu-img", "virt-install", "gpgv", "openssl", "findmnt", "xorriso", "cpio", "gzip", "find")
    ensure_safe_base(base)
    physical_storage_check(base)
    if not (os.access("/dev/kvm", os.R_OK) and os.access("/dev/kvm", os.W_OK)):
        raise LabError("KVM device is not readable/writable")
    caps = call("virsh", "-c", CONNECTION, "domcapabilities", "--virttype", "kvm").stdout
    if "<domain>kvm</domain>" not in caps or "<arch>x86_64</arch>" not in caps:
        raise LabError("x86_64 KVM domcapabilities unavailable")
    print("KVM and session libvirt: OK")
    if domain_exists():
        assert_isolated(domain_xml(), base / "disk.qcow2")
        print("Existing domain isolation: OK; will not recreate it")
    else:
        print("VM not defined yet")


def download(url: str, destination: Path):
    limit = DOWNLOAD_LIMITS.get(destination.name)
    if limit is None:
        raise LabError("Unknown media artifact; no acquisition byte limit")
    if destination.exists() or destination.is_symlink():
        regular_file(destination, nonempty=True)
        if destination.stat().st_size > limit:
            raise LabError(f"Cached artifact exceeds {limit} byte limit: {destination.name}")
        print(f"Reusing {destination}")
        return
    private_directory(destination.parent)
    fd, temporary = tempfile.mkstemp(prefix=".download-", dir=destination.parent)
    try:
        with os.fdopen(fd, "wb") as out, urllib.request.urlopen(url, timeout=45) as response:
            length = response.headers.get("Content-Length")
            if length is not None:
                if not length.isascii() or not length.isdecimal() or len(length) > 20:
                    raise LabError("Invalid media Content-Length")
                length = int(length)
                if length > limit:
                    raise LabError(f"Declared artifact exceeds {limit} byte limit: {destination.name}")
            received = 0
            while True:
                # Probe one byte beyond the remaining budget; never write that byte.
                chunk = response.read(min(1024**2, limit - received + 1))
                if not chunk:
                    break
                received += len(chunk)
                if received > limit:
                    raise LabError(f"Artifact exceeds {limit} byte limit: {destination.name}")
                out.write(chunk)
            if received == 0 or (length is not None and received != length):
                raise LabError("Empty or truncated media response")
        # Link publishes the completed file only if destination is still absent.
        # A concurrent external writer must never have its file replaced.
        try:
            os.link(temporary, destination)
        except FileExistsError as exc:
            raise LabError("Download destination appeared; existing file preserved") from exc
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def ensure_signing_keys(gnupg_home: Path):
    private_directory(gnupg_home)
    for fingerprint in sorted(FINGERPRINTS):
        proc = call("gpg", "--no-options", "--homedir", str(gnupg_home), "--list-keys", fingerprint, check=False)
        if proc.returncode != 0:
            call("gpg", "--no-options", "--batch", "--homedir", str(gnupg_home),
                 "--keyserver", "hkps://keyring.debian.org", "--recv-keys", fingerprint)
    fingerprints = call("gpg", "--no-options", "--homedir", str(gnupg_home),
                        "--with-colons", "--fingerprint", "--list-keys").stdout
    present = set(re.findall(r"^fpr:{9}([0-9A-F]+):", fingerprints, re.MULTILINE))
    if not FINGERPRINTS.issubset(present):
        raise LabError("Imported CD signing keys do not match Debian fingerprints")
    fd, temporary = tempfile.mkstemp(prefix=".trusted-", dir=gnupg_home)
    os.close(fd)
    try:
        call("gpg", "--no-options", "--batch", "--yes", "--homedir", str(gnupg_home),
             "--output", temporary, "--export", *sorted(FINGERPRINTS))
        regular_file(Path(temporary), nonempty=True)
        target = gnupg_home / "trustedkeys.gpg"
        if target.exists() or target.is_symlink():
            regular_file(target)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def verify_iso(base: Path, iso: Path):
    checksum = iso.parent / "SHA512SUMS"
    signature = iso.parent / "SHA512SUMS.sign"
    for candidate in (iso, checksum, signature):
        regular_file(candidate, nonempty=True)
    keyring = base / "gnupg"
    if keyring.is_symlink():
        raise LabError("Refusing symlinked keyring")
    regular_file(keyring / "trustedkeys.gpg", nonempty=True)
    verified = call("gpgv", "--homedir", str(keyring), "--keyring", str(keyring / "trustedkeys.gpg"),
                    "--status-fd", "1", str(signature), str(checksum))
    signed_lines = re.findall(r"^\[GNUPG:\] VALIDSIG ([^\n]+)", verified.stdout, re.MULTILINE)
    # VALIDSIG may give a signing subkey first, with the primary fingerprint last.
    valid = [line.split() for line in signed_lines]
    if not any(row and (row[0] in FINGERPRINTS or row[-1] in FINGERPRINTS)
               for row in valid):
        raise LabError("Signed checksums did not validate against pinned Debian CD signing key")
    line_re = re.compile(r"^([0-9a-fA-F]{128})\s+\*?" + re.escape(ISO_NAME) + r"$")
    matches = [m.group(1).lower() for line in checksum.read_text().splitlines()
               if (m := line_re.fullmatch(line))]
    if len(matches) != 1:
        raise LabError(f"Expected one checksum entry for {ISO_NAME}, got {len(matches)}")
    digest = hashlib.sha512()
    with iso.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != matches[0]:
        raise LabError("Debian ISO SHA512 mismatch")
    print(f"Verified Debian signing key + SHA512: {ISO_NAME}")


def acquire(base: Path, iso: Path):
    check_user()
    ensure_safe_base(base)
    require_programs("gpg", "gpgv", "findmnt")
    physical_storage_check(base)
    private_directory(base)
    ensure_signing_keys(base / "gnupg")
    for filename in (ISO_NAME, "SHA512SUMS", "SHA512SUMS.sign"):
        download(BASE_URL + filename, iso.parent / filename)
    verify_iso(base, iso)


def safe_password_file(base: Path) -> Path:
    secret_dir = base / "private"
    private_directory(secret_dir)
    secret_path = secret_dir / "audit-user-password"
    if not secret_path.exists() and not secret_path.is_symlink():
        reserve_file(secret_path)
        write_private(secret_path, secrets.token_urlsafe(24) + "\n")
    regular_file(secret_path, nonempty=True, private=True)
    return secret_path


def render_preseed(password_hash: str) -> str:
    """Local, offline installer answers. Destructiveness is confined to the new virtio disk."""
    return f"""d-i debian-installer/locale string en_US.UTF-8
 d-i keyboard-configuration/xkb-keymap select us
 d-i netcfg/choose_interface select none
 d-i netcfg/get_hostname string panda-audit
 d-i netcfg/get_domain string local
 d-i hw-detect/load_firmware boolean true
 d-i mirror/country string manual
 d-i apt-setup/use_mirror boolean false
 d-i apt-setup/services-select multiselect
 d-i passwd/root-login boolean false
 d-i passwd/make-user boolean true
 d-i passwd/user-fullname string Panda Auditor
 d-i passwd/username string auditor
 d-i passwd/user-password-crypted password {password_hash}
 d-i clock-setup/utc boolean true
 d-i time/zone string Etc/UTC
 d-i partman-auto/disk string /dev/vda
 d-i partman-auto/method string regular
 d-i partman-auto/choose_recipe select atomic
 d-i partman-partitioning/confirm_write_new_label boolean true
 d-i partman/choose_partition select finish
 d-i partman/confirm boolean true
 d-i partman/confirm_nooverwrite boolean true
 d-i apt-setup/cdrom/set-first boolean false
 d-i pkgsel/upgrade select none
 tasksel tasksel/first multiselect standard
 d-i grub-installer/only_debian boolean true
 d-i grub-installer/bootdev string /dev/vda
 d-i finish-install/reboot_in_progress note
""".replace("\n ", "\n")


def make_preseed(base: Path) -> Path:
    password = safe_password_file(base).read_text().strip()
    hashed = call("openssl", "passwd", "-6", "-stdin", input=password).stdout.strip()
    if not hashed.startswith("$6$"):
        raise LabError("Password hashing failed")
    seed_dir = base / "private"
    target = seed_dir / "preseed.cfg"
    write_private(target, render_preseed(hashed))
    return target


def assert_vm_absent(base: Path, disk: Path):
    if domain_exists():
        raise LabError("Domain already exists; refusing to re-install or modify")
    if disk.exists() or disk.is_symlink():
        raise LabError("Disk already exists; refusing to overwrite")
    for name in ("nvram.fd", ".install-completed"):
        if (base / name).exists() or (base / name).is_symlink():
            raise LabError("NVRAM or installer marker already exists; inspect previous installation")
    if (base / "baseline.qcow2").exists() or (base / "baseline.qcow2").is_symlink():
        raise LabError("Baseline already exists; refusing to overwrite")


def install(base: Path, iso: Path, disk: Path):
    """EXPLICIT install action: boots the guest; never used by master setup."""
    preflight(base)
    assert_vm_absent(base, disk)
    verify_iso(base, iso)
    preseed = make_preseed(base)
    private_directory(disk.parent)
    reserve_file(disk)
    # Explicit new disk creation, never --force, never overwrite.
    call("qemu-img", "create", "-f", "qcow2", str(disk), f"{VM_DISK_GIB}G")
    assert_safe_image(disk)
    args = ["virt-install", "--connect", CONNECTION, "--name", VM_NAME,
            "--memory", str(VM_RAM_MIB), "--vcpus", str(VM_CPUS),
            "--virt-type", "kvm", "--machine", "q35", "--boot", f"uefi,nvram={base / 'nvram.fd'}",
            "--disk", f"path={disk},format=qcow2,bus=virtio",
            "--location", f"{iso},kernel=install.amd/vmlinuz,initrd=install.amd/initrd.gz",
            "--initrd-inject", str(preseed),
            "--extra-args", "auto=true priority=critical preseed/file=/preseed.cfg interface=none",
            "--network", "none", "--graphics", "vnc,listen=127.0.0.1",
            "--channel", "none", "--redirdev", "none", "--rng", "none", "--tpm", "none",
            "--sound", "none", "--video", "vga", "--noautoconsole", "--noreboot",
            "--wait", "-1"]
    # Inspect post-install XML before virt-install is permitted to boot anything.
    # Installer-only direct kernel/initrd paths disappear from this second phase.
    try:
        generated = ET.fromstring(call(*args, "--dry-run", "--print-xml", "2").stdout)
    except ET.ParseError as exc:
        raise LabError("Invalid generated post-install domain XML") from exc
    assert_isolated(generated, disk)
    print("Guest install starting; host boot/GPU settings are unchanged.")
    try:
        call(*args, capture=False)
    except LabError:
        print("Installation failed. VM/disk preserved for inspection; no automatic cleanup.", file=sys.stderr)
        raise
    if not domain_exists():
        raise LabError("Installation command ended without a persistent domain")
    assert_isolated(domain_xml(), disk)
    off()
    write_private(base / ".install-completed", "virt-install completed; verify guest before baseline.\n")
    print("Installer completed. Verify the guest manually before creating a baseline.")


def state():
    if not domain_exists():
        return "absent"
    return call("virsh", "-c", CONNECTION, "domstate", VM_NAME).stdout.strip()


def off():
    if state() not in ("shut off", "absent"):
        raise LabError("Guest must be shut off for this operation")


def baseline(base: Path, disk: Path):
    off()
    if state() == "absent":
        raise LabError("Cannot baseline an undefined VM")
    assert_isolated(domain_xml(), disk)
    regular_file(base / ".install-completed", nonempty=True, private=True)
    if disk.is_symlink() or not disk.is_file():
        raise LabError("Guest disk missing")
    physical_storage_check(base, required_gib=41)
    assert_safe_image(disk)
    call("qemu-img", "check", "-f", "qcow2", str(disk))
    target = base / "baseline.qcow2"
    if target.exists() or target.is_symlink():
        raise LabError("Baseline already exists; refusing overwrite")
    temporary = base / ".baseline.pending.qcow2"
    if temporary.exists() or temporary.is_symlink():
        raise LabError("Stale baseline temporary file; inspect it manually")
    reserve_file(temporary)
    call("qemu-img", "convert", "-f", "qcow2", "-O", "qcow2", str(disk), str(temporary))
    assert_safe_image(temporary)
    off()
    os.chmod(temporary, 0o600)
    os.rename(temporary, target)
    print(f"Immutable by convention (not filesystem-enforced) baseline: {target}")


def reset(base: Path, disk: Path, confirm: bool):
    if not confirm:
        raise LabError("Reset is destructive. Pass --confirm-reset explicitly")
    off()
    if state() == "absent":
        raise LabError("VM not defined")
    assert_isolated(domain_xml(), disk)
    source = base / "baseline.qcow2"
    if source.is_symlink() or not source.is_file():
        raise LabError("No verified baseline exists")
    temporary = base / ".reset.pending.qcow2"
    if temporary.exists() or temporary.is_symlink():
        raise LabError("Stale reset temporary file exists; inspect manually")
    physical_storage_check(base, required_gib=41)
    regular_file(disk, private=True)
    assert_safe_image(source)
    call("qemu-img", "check", "-f", "qcow2", str(source))
    reserve_file(temporary)
    call("qemu-img", "convert", "-f", "qcow2", "-O", "qcow2", str(source), str(temporary))
    assert_safe_image(temporary)
    off()
    os.chmod(temporary, 0o600)
    os.replace(temporary, disk)
    print("Working disk replaced by baseline; prior guest changes are gone")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("plan", "preflight", "acquire", "verify", "install", "status", "start", "stop", "baseline", "reset"))
    parser.add_argument("--confirm-reset", action="store_true")
    args = parser.parse_args(argv)
    base, iso, disk = paths()
    if args.confirm_reset and args.command != "reset":
        parser.error("--confirm-reset is only valid with reset")
    if args.command == "plan":
        print(f"VM: {VM_NAME}; offline; 2 vCPU; 4096 MiB; 40 GiB; path: {base}")
        print(f"Pinned media: {BASE_URL}{ISO_NAME}")
        print("Preview only: no host probes, downloads, keys, directories, services or guests")
        return 0
    try:
        check_user()
        ensure_safe_base(base)
        if args.command == "reset" and not args.confirm_reset:
            raise LabError("Reset is destructive. Pass --confirm-reset explicitly")
        mutating = args.command in {"acquire", "install", "start", "stop", "baseline", "reset"}
        with operation_lock(base) if mutating else nullcontext():
            return dispatch(args, base, iso, disk)
    except (LabError, OSError, ValueError) as err:
        print(f"ERROR: {err}", file=sys.stderr)
        return 1


def dispatch(args, base, iso, disk):
    if args.command == "preflight":
        preflight(base)
        print(f"VM: {VM_NAME}; offline; 2 vCPU; 4096 MiB; 40 GiB; path: {base}")
        print("Read-only check complete; no VM has been created or started")
    elif args.command == "acquire":
        acquire(base, iso)
    elif args.command == "install":
        install(base, iso, disk)
    elif args.command == "status":
        require_programs("virsh")
        print(f"{VM_NAME}: {state()}")
    elif args.command == "verify":
        preflight(base)
        if domain_exists():
            assert_isolated(domain_xml(), disk)
            print(f"Guest domain: {state()}; isolation XML: OK")
        else:
            print("Not yet installed (expected before explicit install)")
        if iso.exists():
            verify_iso(base, iso)
        else:
            print("ISO not downloaded yet")
    elif args.command == "start":
        require_programs("virsh", "qemu-img", "gpgv", "findmnt")
        current = state()
        if current == "absent":
            raise LabError("VM not installed")
        root = domain_xml()
        assert_isolated(root, disk)
        if current == "running":
            print("Guest already running; isolation XML: OK")
            return 0
        if current != "shut off":
            raise LabError("Guest must be shut off before start")
        regular_file(base / ".install-completed", nonempty=True, private=True)
        for node in root.findall("./os/nvram"):
            regular_file(base / "nvram.fd", nonempty=True, private=True)
        physical_storage_check(base, required_gib=0)
        assert_safe_image(disk)
        if any(node.find("source") is not None for node in root.findall("./devices/disk")
               if node.get("device") == "cdrom"):
            verify_iso(base, iso)
        call("virsh", "-c", CONNECTION, "start", VM_NAME, capture=False)
    elif args.command == "stop":
        require_programs("virsh")
        if state() in ("absent", "shut off"):
            print("Already shut off")
        else:
            assert_isolated(domain_xml(), disk)
            call("virsh", "-c", CONNECTION, "shutdown", VM_NAME, capture=False)
            print("Graceful shutdown requested; check status before disk operations")
    elif args.command == "baseline":
        require_programs("virsh", "qemu-img")
        baseline(base, disk)
    elif args.command == "reset":
        require_programs("virsh", "qemu-img")
        reset(base, disk, args.confirm_reset)
    return 0


if __name__ == "__main__":
    sys.exit(main())
