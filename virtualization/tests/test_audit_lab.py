import importlib.util
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "audit_lab.py"
spec = importlib.util.spec_from_file_location("audit_lab", SOURCE)
lab = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = lab
spec.loader.exec_module(lab)


def xml(devices):
    return ET.fromstring(f"<domain><name>{lab.VM_NAME}</name><vcpu>2</vcpu><memory unit='MiB'>4096</memory><devices>{devices}</devices></domain>")


class TestAuditLab(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.disk = Path(self.tmp.name) / "disk.qcow2"
        self.clean_devices = f"<disk type='file' device='disk'><driver name='qemu' type='qcow2'/><source file='{self.disk}'/><target dev='vda' bus='virtio'/></disk>"

    def test_isolation_rejects_network(self):
        with self.assertRaisesRegex(lab.LabError, "interface"):
            lab.assert_isolated(xml(self.clean_devices + "<interface type='user'/>"), self.disk)

    def test_isolation_rejects_shared_directory(self):
        with self.assertRaisesRegex(lab.LabError, "filesystem"):
            lab.assert_isolated(xml(self.clean_devices + "<filesystem/>"), self.disk)

    def test_isolation_rejects_foreign_disk(self):
        with self.assertRaisesRegex(lab.LabError, "Unexpected disk"):
            lab.assert_isolated(xml("<disk device='disk'><source file='/tmp/other'/></disk>"), self.disk)

    def test_isolation_rejects_public_vnc(self):
        with self.assertRaisesRegex(lab.LabError, "loopback"):
            lab.assert_isolated(xml(self.clean_devices + "<graphics type='vnc' listen='0.0.0.0'/>"), self.disk)

    def test_isolation_accepts_offline_domain(self):
        lab.assert_isolated(xml(self.clean_devices + "<graphics type='vnc' listen='127.0.0.1'/>"), self.disk)

    def test_install_never_replaces_existing_disk(self):
        self.disk.write_text("user data")
        with patch.object(lab, "domain_exists", return_value=False):
            with self.assertRaisesRegex(lab.LabError, "already exists"):
                lab.assert_vm_absent(self.disk.parent, self.disk)
        self.assertEqual(self.disk.read_text(), "user data")

    def test_reset_requires_confirmation(self):
        with self.assertRaisesRegex(lab.LabError, "confirm-reset"):
            lab.reset(self.disk.parent, self.disk, False)

    def test_preseed_no_network_mirror(self):
        seed = lab.render_preseed("$6$dummy")
        self.assertIn("netcfg/choose_interface select none", seed)
        self.assertIn("apt-setup/use_mirror boolean false", seed)
        self.assertIn("partman-auto/disk string /dev/vda", seed)
        self.assertNotIn("/dev/sda", seed)

    def test_baseline_needs_guest_shutdown(self):
        with patch.object(lab, "state", return_value="running"):
            with self.assertRaisesRegex(lab.LabError, "shut off"):
                lab.baseline(self.disk.parent, self.disk)

    def test_plan_never_contacts_host_or_creates_files(self):
        with patch.object(lab, "paths", return_value=(self.disk.parent, self.disk.parent / lab.ISO_NAME, self.disk)), \
             patch.object(lab, "check_user"), patch.object(Path, "home", return_value=self.disk.parent), \
             patch.object(lab, "call", side_effect=AssertionError("host contact")), \
             patch.object(lab, "physical_storage_check", side_effect=AssertionError("host probe")):
            self.assertEqual(lab.main(["plan"]), 0)
        self.assertEqual(list(self.disk.parent.iterdir()), [])

    def test_domain_inventory_failure_is_not_absence(self):
        failed = subprocess.CompletedProcess([], 1, "", "session unavailable")
        with patch.object(lab, "call", return_value=failed):
            with self.assertRaises(lab.LabError):
                lab.domain_exists()

    def test_domain_inventory_lists_exact_name(self):
        for inventory, expected in (("", False), ("panda-ghostty-audit-old\n", False),
                                    ("other\npanda-ghostty-audit\n", True)):
            with self.subTest(inventory=inventory), patch.object(lab, "call", return_value=subprocess.CompletedProcess([], 0, inventory, "")):
                self.assertEqual(lab.domain_exists(), expected)

    def test_isolation_rejects_alternate_host_paths(self):
        extras = [
            "<disk type='block' device='cdrom'><source dev='/dev/sda'/><readonly/></disk>",
            "<graphics type='vnc' listen='127.0.0.1'><listen type='address' address='0.0.0.0'/></graphics>",
            "<graphics type='vnc' listen='127.0.0.1' socket='/tmp/display'/>",
            "<audio type='pipewire' id='1'/>",
            "<input type='passthrough'><source evdev='/dev/input/event0'/></input>",
        ]
        for extra in extras:
            with self.subTest(extra=extra), self.assertRaises(lab.LabError):
                lab.assert_isolated(xml(self.clean_devices + extra), self.disk)

    def test_isolation_rejects_disk_backing_and_wrong_format(self):
        for replacement in (
            self.clean_devices.replace("</disk>", "<backingStore type='file'><source file='/tmp/host'/></backingStore></disk>"),
            self.clean_devices.replace("type='qcow2'", "type='raw'"),
            self.clean_devices.replace("bus='virtio'", "bus='sata'"),
        ):
            with self.subTest(replacement=replacement), self.assertRaises(lab.LabError):
                lab.assert_isolated(xml(replacement), self.disk)

    def test_isolation_rejects_boot_path_prefix_and_qemu_override(self):
        root = xml(self.clean_devices)
        ET.SubElement(ET.SubElement(root, "os"), "kernel").text = str(self.disk.parent) + "-other/vmlinuz"
        with self.assertRaises(lab.LabError):
            lab.assert_isolated(root, self.disk)
        root = xml(self.clean_devices)
        ET.SubElement(root, "{http://libvirt.org/schemas/domain/qemu/1.0}commandline")
        with self.assertRaises(lab.LabError):
            lab.assert_isolated(root, self.disk)

    def test_verify_media_never_fetches_keys(self):
        iso_dir = self.disk.parent / "iso"
        iso_dir.mkdir()
        iso = iso_dir / lab.ISO_NAME
        iso.write_bytes(b"fixture ISO")
        digest = hashlib.sha512(b"fixture ISO").hexdigest()
        (iso_dir / "SHA512SUMS").write_text(digest + "  " + lab.ISO_NAME + "\n")
        (iso_dir / "SHA512SUMS.sign").write_text("fixture signature")
        keyring = self.disk.parent / "gnupg"
        keyring.mkdir()
        (keyring / "trustedkeys.gpg").write_bytes(b"fixture public keyring")
        fingerprint = "10460DAD76165AD81FBC0CE9988021A964E6EA7D"
        def verify_command(*args, **kwargs):
            self.assertEqual(args[0], "gpgv")
            return subprocess.CompletedProcess(args, 0, "[GNUPG:] VALIDSIG " + fingerprint + " 2026-01-01 0 0 4 0 1 10 00 " + fingerprint + "\n", "")
        with patch.object(lab, "ensure_signing_keys", side_effect=AssertionError("network/keyring write")), \
             patch.object(lab, "call", side_effect=verify_command):
            lab.verify_iso(self.disk.parent, iso)

    def test_preseed_symlink_never_overwrites_host_file(self):
        private = self.disk.parent / "private"
        private.mkdir(mode=0o700)
        fixture = private / "fixture"
        fixture.write_text("inert fixture")
        victim = self.disk.parent / "host-file"
        victim.write_text("preserve")
        (private / "preseed.cfg").symlink_to(victim)
        with patch.object(lab, "safe_password_file", return_value=fixture), \
             patch.object(lab, "call", return_value=subprocess.CompletedProcess([], 0, "$6$fixture", "")):
            with self.assertRaises(lab.LabError):
                lab.make_preseed(self.disk.parent)
        self.assertEqual(victim.read_text(), "preserve")

    def test_verify_rejects_symlinked_iso_before_subprocess(self):
        media = self.disk.parent / "iso"
        media.mkdir()
        victim = self.disk.parent / "foreign"
        victim.write_bytes(b"fixture")
        iso = media / lab.ISO_NAME
        iso.symlink_to(victim)
        with patch.object(lab, "call", side_effect=AssertionError("must reject before external calls")):
            with self.assertRaises(lab.LabError):
                lab.verify_iso(self.disk.parent, iso)

    def test_image_metadata_rejects_backing_and_external_data(self):
        self.disk.touch(mode=0o600)
        good = {"format": "qcow2", "virtual-size": 42949672960}
        for unsafe in (
            dict(good, **{"backing-filename": "/tmp/host"}),
            dict(good, **{"data-file": "/tmp/host"}),
            dict(good, **{"format-specific": {"type": "qcow2", "data": {"data-file": "/tmp/host"}}}),
            {"format": "raw", "virtual-size": 42949672960},
        ):
            with self.subTest(unsafe=unsafe), patch.object(lab, "call", return_value=subprocess.CompletedProcess([], 0, json.dumps(unsafe), "")):
                with self.assertRaises(lab.LabError):
                    lab.assert_safe_image(self.disk)
        with patch.object(lab, "call", return_value=subprocess.CompletedProcess([], 0, json.dumps(good), "")):
            lab.assert_safe_image(self.disk)

    def test_managed_lock_refuses_parallel_mutation(self):
        with lab.operation_lock(self.disk.parent):
            with self.assertRaises(lab.LabError):
                with lab.operation_lock(self.disk.parent):
                    self.fail("parallel mutation permitted")

    def test_malformed_domain_xml_reports_lab_error(self):
        with patch.object(lab, "call", return_value=subprocess.CompletedProcess([], 0, "<bad", "")):
            with self.assertRaises(lab.LabError):
                lab.domain_xml()

    def media_fixture(self):
        media = self.disk.parent / "iso"
        media.mkdir(mode=0o700)
        iso = media / lab.ISO_NAME
        iso.write_bytes(b"fixture ISO")
        (media / "SHA512SUMS").write_text(hashlib.sha512(b"fixture ISO").hexdigest() + "  " + lab.ISO_NAME + "\n")
        (media / "SHA512SUMS.sign").write_text("fixture signature")
        keyring = self.disk.parent / "gnupg"
        keyring.mkdir(mode=0o700)
        (keyring / "trustedkeys.gpg").write_bytes(b"fixture public keyring")
        return iso

    def test_media_rejects_unknown_signer_hash_mismatch_and_duplicate(self):
        iso = self.media_fixture()
        pinned = "10460DAD76165AD81FBC0CE9988021A964E6EA7D"
        for signer in ("0" * 40, ""):
            with self.subTest(signer=signer), patch.object(lab, "call", return_value=subprocess.CompletedProcess([], 0, "[GNUPG:] VALIDSIG " + signer + "\n", "")):
                with self.assertRaisesRegex(lab.LabError, "pinned"):
                    lab.verify_iso(self.disk.parent, iso)
        signed = subprocess.CompletedProcess([], 0, "[GNUPG:] VALIDSIG " + pinned + "\n", "")
        iso.write_bytes(b"corrupted")
        with patch.object(lab, "call", return_value=signed):
            with self.assertRaisesRegex(lab.LabError, "mismatch"):
                lab.verify_iso(self.disk.parent, iso)
        iso.write_bytes(b"fixture ISO")
        checksums = iso.parent / "SHA512SUMS"
        checksums.write_text(checksums.read_text() * 2)
        with patch.object(lab, "call", return_value=signed):
            with self.assertRaisesRegex(lab.LabError, "got 2"):
                lab.verify_iso(self.disk.parent, iso)

    def test_download_failure_leaves_no_partial_destination(self):
        import io
        target = self.disk.parent / "iso" / lab.ISO_NAME
        class FailedRead(io.BytesIO):
            headers = {}
            def read(self, *args):
                raise OSError("fixture read failure")
        with patch.object(lab.urllib.request, "urlopen", return_value=FailedRead(b"")):
            with self.assertRaises(OSError):
                lab.download("https://example.invalid/fixture", target)
        self.assertFalse(target.exists())
        self.assertEqual(list(target.parent.iterdir()), [])

    def test_existing_download_is_reused_without_network(self):
        target = self.disk.parent / lab.ISO_NAME
        target.write_bytes(b"existing")
        with patch.object(lab.urllib.request, "urlopen", side_effect=AssertionError("network")):
            lab.download("https://example.invalid/fixture", target)
        self.assertEqual(target.read_bytes(), b"existing")

    def test_private_writer_rejects_hardlink(self):
        target = self.disk.parent / "private-file"
        target.write_text("preserve")
        target.chmod(0o600)
        alias = self.disk.parent / "alias"
        os.link(target, alias)
        with self.assertRaises(lab.LabError):
            lab.write_private(target, "replacement")
        self.assertEqual(alias.read_text(), "preserve")

    def test_isolation_rejects_foreign_firmware_emulator_and_duplicate_sections(self):
        for extra in ("<os><nvram>/tmp/host</nvram></os>",
                      "<os><loader readonly='no' type='pflash'>/tmp/host</loader></os>",
                      "<devices/>"):
            root = xml(self.clean_devices)
            root.append(ET.fromstring(extra))
            with self.subTest(extra=extra), self.assertRaises(lab.LabError):
                lab.assert_isolated(root, self.disk)
        with self.assertRaises(lab.LabError):
            lab.assert_isolated(xml(self.clean_devices + "<emulator>/tmp/foreign-program</emulator>"), self.disk)

    def test_install_checks_generated_xml_before_guest_boot(self):
        base = self.disk.parent
        iso = base / "iso" / lab.ISO_NAME
        seed = base / "private" / "preseed.cfg"
        commands = []
        def external(*args, **kwargs):
            commands.append(args)
            if args[0] == "qemu-img" and args[1] == "create":
                self.disk.write_bytes(b"fixture disk")
            elif args[0] == "qemu-img" and args[1] == "info":
                return subprocess.CompletedProcess(args, 0, '{"format":"qcow2","virtual-size":42949672960}', "")
            elif args[0] == "virt-install":
                if "--print-xml" in args:
                    return subprocess.CompletedProcess(args, 0, ET.tostring(xml(self.clean_devices + "<interface type='user'/>"), encoding="unicode"), "")
                self.fail("guest started before XML isolation validation")
            return subprocess.CompletedProcess(args, 0, "", "")
        with patch.object(lab, "preflight"), patch.object(lab, "verify_iso"), \
             patch.object(lab, "make_preseed", return_value=seed), patch.object(lab, "domain_exists", return_value=False), \
             patch.object(lab, "call", side_effect=external):
            with self.assertRaisesRegex(lab.LabError, "interface"):
                lab.install(base, iso, self.disk)
        self.assertTrue(self.disk.exists())
        self.assertFalse((base / ".install-completed").exists())

    def test_start_is_idempotent_but_checks_existing_isolation(self):
        import argparse
        with patch.object(lab, "require_programs"), patch.object(lab, "state", return_value="running"), \
             patch.object(lab, "domain_xml", return_value=xml(self.clean_devices)), \
             patch.object(lab, "call", side_effect=AssertionError("must not start a running guest")):
            self.assertEqual(lab.dispatch(argparse.Namespace(command="start"), self.disk.parent, self.disk.parent / lab.ISO_NAME, self.disk), 0)

    def test_reset_cli_without_confirmation_creates_nothing(self):
        with patch.object(lab, "paths", return_value=(self.disk.parent, self.disk.parent / lab.ISO_NAME, self.disk)), \
             patch.object(lab, "check_user"), patch.object(Path, "home", return_value=self.disk.parent), \
             patch.object(lab, "call", side_effect=AssertionError("host contact")):
            self.assertEqual(lab.main(["reset"]), 1)
        self.assertEqual(list(self.disk.parent.iterdir()), [])

    def test_install_refuses_stale_firmware_before_provisioning(self):
        stale = self.disk.parent / "nvram.fd"
        stale.write_bytes(b"previous guest data")
        with patch.object(lab, "domain_exists", return_value=False):
            with self.assertRaisesRegex(lab.LabError, "NVRAM"):
                lab.assert_vm_absent(self.disk.parent, self.disk)
        self.assertFalse(self.disk.exists())

    def test_active_disk_source_index_is_permitted(self):
        root = xml(self.clean_devices)
        root.find("./devices/disk/source").set("index", "1")
        lab.assert_isolated(root, self.disk)

    def test_storage_rejects_similarly_named_untrusted_device(self):
        from types import SimpleNamespace
        for source, accepted in (("/dev/sda2", True), ("/dev/sda2[/@home]", True),
                                 ("/dev/sda20", False), ("/dev/nvme0n1p2", False)):
            with self.subTest(source=source), patch.object(lab.os, "uname", return_value=SimpleNamespace(nodename="panda-helios")), \
                 patch.object(lab.shutil, "disk_usage", return_value=SimpleNamespace(free=60 * 1024**3)), \
                 patch.object(lab, "call", return_value=subprocess.CompletedProcess([], 0, source, "")):
                if accepted:
                    lab.physical_storage_check(self.disk.parent)
                else:
                    with self.assertRaises(lab.LabError):
                        lab.physical_storage_check(self.disk.parent)

    def lifecycle_fixture(self, *, fail_conversion=False):
        self.disk.write_bytes(b"working guest")
        self.disk.chmod(0o600)
        marker = self.disk.parent / ".install-completed"
        marker.write_text("fixture completion marker")
        marker.chmod(0o600)
        def command(*args, **kwargs):
            if args[:2] == ("qemu-img", "info"):
                return subprocess.CompletedProcess(args, 0, '{"format":"qcow2","virtual-size":42949672960}', "")
            if args[:2] == ("qemu-img", "convert"):
                Path(args[-1]).write_bytes(Path(args[-2]).read_bytes())
                if fail_conversion:
                    raise lab.LabError("fixture conversion failed")
            elif args[:2] != ("qemu-img", "check"):
                self.fail("unexpected external command: " + repr(args))
            return subprocess.CompletedProcess(args, 0, "", "")
        return command

    def test_baseline_and_reset_publish_checked_copies(self):
        command = self.lifecycle_fixture()
        with patch.object(lab, "state", return_value="shut off"), \
             patch.object(lab, "domain_xml", return_value=xml(self.clean_devices)), \
             patch.object(lab, "physical_storage_check"), patch.object(lab, "call", side_effect=command):
            lab.baseline(self.disk.parent, self.disk)
            baseline = self.disk.parent / "baseline.qcow2"
            self.assertEqual(baseline.read_bytes(), b"working guest")
            self.disk.write_bytes(b"later guest changes")
            lab.reset(self.disk.parent, self.disk, True)
            self.assertEqual(self.disk.read_bytes(), b"working guest")
            self.assertEqual(baseline.read_bytes(), b"working guest")
            self.assertEqual(self.disk.stat().st_mode & 0o777, 0o600)
            with self.assertRaisesRegex(lab.LabError, "already exists"):
                lab.baseline(self.disk.parent, self.disk)

    def test_failed_reset_retains_working_disk_and_pending_evidence(self):
        command = self.lifecycle_fixture(fail_conversion=True)
        baseline = self.disk.parent / "baseline.qcow2"
        baseline.write_bytes(b"baseline guest")
        baseline.chmod(0o600)
        with patch.object(lab, "state", return_value="shut off"), \
             patch.object(lab, "domain_xml", return_value=xml(self.clean_devices)), \
             patch.object(lab, "physical_storage_check"), patch.object(lab, "call", side_effect=command):
            with self.assertRaisesRegex(lab.LabError, "conversion failed"):
                lab.reset(self.disk.parent, self.disk, True)
        self.assertEqual(self.disk.read_bytes(), b"working guest")
        self.assertEqual((self.disk.parent / ".reset.pending.qcow2").read_bytes(), b"baseline guest")

    def test_install_success_and_failure_preserve_retry_evidence(self):
        for fail_launch in (False, True):
            with self.subTest(fail_launch=fail_launch), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                disk = base / "disk.qcow2"
                devices = f"<disk type='file' device='disk'><driver name='qemu' type='qcow2'/><source file='{disk}'/><target dev='vda' bus='virtio'/></disk>"
                completed_xml = xml(devices)
                defined = False
                launch_count = 0
                def command(*args, **kwargs):
                    nonlocal defined, launch_count
                    if args[:2] == ("qemu-img", "create"):
                        disk.write_bytes(b"fixture guest disk")
                    elif args[:2] == ("qemu-img", "info"):
                        return subprocess.CompletedProcess(args, 0, '{"format":"qcow2","virtual-size":42949672960}', "")
                    elif args[0] == "virt-install":
                        self.assertEqual(args[args.index("--connect") + 1], "qemu:///session")
                        self.assertEqual(args[args.index("--network") + 1], "none")
                        for option in ("--channel", "--redirdev", "--rng", "--tpm", "--sound"):
                            self.assertEqual(args[args.index(option) + 1], "none")
                        self.assertIn("--noreboot", args)
                        if "--print-xml" in args:
                            self.assertIn("--dry-run", args)
                            return subprocess.CompletedProcess(args, 0, ET.tostring(completed_xml, encoding="unicode"), "")
                        launch_count += 1
                        defined = True
                        if fail_launch:
                            raise lab.LabError("fixture installer failure")
                    elif args[:4] == ("virsh", "-c", "qemu:///session", "domstate"):
                        return subprocess.CompletedProcess(args, 0, "shut off\n", "")
                    else:
                        self.fail("unexpected command: " + repr(args))
                    return subprocess.CompletedProcess(args, 0, "", "")
                with patch.object(lab, "preflight"), patch.object(lab, "verify_iso"), \
                     patch.object(lab, "make_preseed", return_value=base / "fixture-preseed"), \
                     patch.object(lab, "domain_exists", side_effect=lambda: defined), \
                     patch.object(lab, "domain_xml", return_value=completed_xml), patch.object(lab, "call", side_effect=command):
                    if fail_launch:
                        with self.assertRaisesRegex(lab.LabError, "installer failure"):
                            lab.install(base, base / lab.ISO_NAME, disk)
                        self.assertFalse((base / ".install-completed").exists())
                    else:
                        lab.install(base, base / lab.ISO_NAME, disk)
                        self.assertEqual((base / ".install-completed").stat().st_mode & 0o777, 0o600)
                    self.assertEqual(launch_count, 1)
                    self.assertEqual(disk.read_bytes(), b"fixture guest disk")
                    with self.assertRaisesRegex(lab.LabError, "already exists"):
                        lab.install(base, base / lab.ISO_NAME, disk)

    def test_start_and_stop_emit_only_session_lifecycle_commands(self):
        import argparse
        command = self.lifecycle_fixture()
        operations = []
        def external(*args, **kwargs):
            if args[0] == "qemu-img":
                return command(*args, **kwargs)
            operations.append(args)
            return subprocess.CompletedProcess(args, 0, "", "")
        with patch.object(lab, "require_programs"), patch.object(lab, "state", return_value="shut off"), \
             patch.object(lab, "domain_xml", return_value=xml(self.clean_devices)), \
             patch.object(lab, "physical_storage_check"), patch.object(lab, "call", side_effect=external):
            self.assertEqual(lab.dispatch(argparse.Namespace(command="start"), self.disk.parent, self.disk.parent / lab.ISO_NAME, self.disk), 0)
        with patch.object(lab, "require_programs"), patch.object(lab, "state", return_value="running"), \
             patch.object(lab, "domain_xml", return_value=xml(self.clean_devices)), patch.object(lab, "call", side_effect=external):
            self.assertEqual(lab.dispatch(argparse.Namespace(command="stop"), self.disk.parent, self.disk.parent / lab.ISO_NAME, self.disk), 0)
        self.assertEqual(operations, [
            ("virsh", "-c", "qemu:///session", "start", "panda-ghostty-audit"),
            ("virsh", "-c", "qemu:///session", "shutdown", "panda-ghostty-audit")])

    def test_download_stream_caps_apply_without_or_with_forged_length(self):
        import io
        limits = {lab.ISO_NAME: 8, "SHA512SUMS": 10, "SHA512SUMS.sign": 6}
        class Response(io.BytesIO):
            pass
        for filename, limit in limits.items():
            for headers in ({}, {"Content-Length": "1"}):
                with self.subTest(filename=filename, headers=headers):
                    target = self.disk.parent / "iso" / filename
                    response = Response(b"x" * (limit + 1))
                    response.headers = headers
                    with patch.dict(lab.DOWNLOAD_LIMITS, limits), \
                         patch.object(lab.urllib.request, "urlopen", return_value=response):
                        with self.assertRaisesRegex(lab.LabError, "byte limit"):
                            lab.download("https://example.invalid/fixture", target)
                    self.assertFalse(target.exists())
                    self.assertEqual(list(target.parent.iterdir()), [])

    def test_download_declared_over_limit_rejects_before_body_read(self):
        import io
        class Response(io.BytesIO):
            headers = {"Content-Length": "9"}
        response = Response(b"")
        target = self.disk.parent / "iso" / lab.ISO_NAME
        with patch.dict(lab.DOWNLOAD_LIMITS, {lab.ISO_NAME: 8}), \
             patch.object(response, "read", side_effect=AssertionError("body read")), \
             patch.object(lab.urllib.request, "urlopen", return_value=response):
            with self.assertRaisesRegex(lab.LabError, "byte limit"):
                lab.download("https://example.invalid/fixture", target)
        self.assertFalse(target.exists())
        self.assertEqual(list(target.parent.iterdir()), [])

    def test_download_exact_bound_publishes_then_reuses_without_network(self):
        import io
        target = self.disk.parent / lab.ISO_NAME
        response = io.BytesIO(b"12345678")
        response.headers = {"Content-Length": "8"}
        with patch.dict(lab.DOWNLOAD_LIMITS, {lab.ISO_NAME: 8}), \
             patch.object(lab.urllib.request, "urlopen", return_value=response):
            lab.download("https://example.invalid/fixture", target)
        self.assertEqual(target.read_bytes(), b"12345678")
        with patch.object(lab.urllib.request, "urlopen", side_effect=AssertionError("network")):
            lab.download("https://example.invalid/fixture", target)
        self.assertEqual(target.read_bytes(), b"12345678")

    def test_download_preserves_destination_created_during_transfer(self):
        import io
        target = self.disk.parent / lab.ISO_NAME
        class Response(io.BytesIO):
            headers = {}
            def read(self, size):
                chunk = super().read(size)
                if not chunk:
                    target.write_bytes(b"preexisting destination")
                return chunk
        with patch.object(lab.urllib.request, "urlopen", return_value=Response(b"download")):
            with self.assertRaises(lab.LabError):
                lab.download("https://example.invalid/fixture", target)
        self.assertEqual(target.read_bytes(), b"preexisting destination")
        self.assertEqual(list(target.parent.iterdir()), [target])


if __name__ == "__main__":
    unittest.main()
