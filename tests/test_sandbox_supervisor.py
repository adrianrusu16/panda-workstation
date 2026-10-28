"""Gate 1: disposable files and process-dispatch doubles only; no native launch."""
import copy
import importlib.util
import json
import io
import contextlib
import os
from pathlib import Path
import subprocess
import struct
import tempfile
import signal
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class SupervisorTests(unittest.TestCase):
    def setUp(self):
        source = ROOT / "tests/native/sandbox_supervisor.py"
        if not source.exists():
            self.fail("Gate 1 supervisor is not implemented")
        spec = importlib.util.spec_from_file_location("sandbox_supervisor", source)
        self.api = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.api)
        self.temp = tempfile.TemporaryDirectory(prefix="panda-inert-fixture-")
        self.addCleanup(self.temp.cleanup)
        self.worktree = Path(self.temp.name)
        self.profile = self.api.load_profile()

    def plan(self):
        return self.api.make_plan(self.worktree, "0123456789abcdef")

    def journal(self):
        value = self.api.create_journal(self.worktree, "0123456789abcdef")
        self.addCleanup(value.close)
        return value

    def test_default_entry_point_refuses_execution_without_creating_a_root(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.api.main([]), 0)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.api.main(["--execute"])
        with self.assertRaises(self.api.Refused):
            self.api.launch_inert(self.plan())
        self.assertEqual(list(self.worktree.iterdir()), [])

    def test_profile_cannot_be_extended_into_a_generic_command_runner(self):
        raw = (ROOT / "tests/native/inert-profile.json").read_bytes()
        self.assertEqual(self.api.parse_profile(raw)["id"], "panda-inert-v1")
        for key, value in (("executable", "/bin/sh"), ("namespaces", []),
                           ("execution_enabled", True), ("worker", "panda-frame-worker")):
            altered = json.loads(raw)
            altered[key] = value
            with self.subTest(key=key), self.assertRaises(self.api.Refused):
                self.api.parse_profile(json.dumps(altered).encode())
        with self.assertRaises(self.api.Refused):
            self.api.parse_profile(b'{"id":"one","id":"two"}')

    def test_command_uses_mandatory_namespaces_fixed_payload_and_outer_filter(self):
        plan = self.plan()
        argv = plan["argv"]
        self.assertEqual(argv[0], "/usr/bin/strace")
        self.assertEqual(argv[-1], "/runtime/inert-probe")
        for flag in ("--unshare-user", "--unshare-pid", "--unshare-ipc",
                     "--unshare-net", "--unshare-uts", "--unshare-cgroup",
                     "--die-with-parent", "--new-session", "--clearenv"):
            self.assertIn(flag, argv)
        self.assertEqual(argv[argv.index("--seccomp") + 1], "3")
        self.assertEqual(argv[argv.index("--cap-drop") + 1], "ALL")
        self.assertEqual(argv[argv.index("--json-status-fd") + 1], "4")
        self.assertFalse(any("-try" in x for x in argv))
        self.assertNotIn("-p", argv)
        self.assertNotIn("/bin/sh", argv)
        self.assertFalse(plan["execution_enabled"])

    def test_environment_is_exact_and_does_not_inherit_session_or_credentials(self):
        with patch.dict(os.environ, {"DISPLAY": ":0", "WAYLAND_DISPLAY": "wayland-0",
                                    "SSH_AUTH_SOCK": "/secret", "LD_PRELOAD": "/secret"}):
            plan = self.plan()
        self.assertEqual(plan["host_environment"], {"LANG": "C", "LC_ALL": "C", "TZ": "UTC"})
        self.assertEqual(plan["environment"]["HOME"], "/home/probe")
        self.assertEqual(plan["environment"]["XDG_RUNTIME_DIR"], "/run/private")
        for key in ("DISPLAY", "WAYLAND_DISPLAY", "SSH_AUTH_SOCK", "LD_PRELOAD",
                    "DBUS_SESSION_BUS_ADDRESS", "DBUS_SYSTEM_BUS_ADDRESS", "PATH"):
            self.assertNotIn(key, plan["environment"])
        argv = plan["argv"]
        for key, value in plan["environment"].items():
            self.assertIn(["--setenv", key, value], [argv[i:i+3] for i in range(len(argv))])

    def test_mounts_expose_only_fresh_paths_and_minimal_readonly_runtime(self):
        plan = self.plan()
        mounts = {x["target"]: x for x in plan["mounts"]}
        self.assertTrue(mounts["/"]["readonly"])
        self.assertTrue(mounts["/runtime"]["readonly"])
        self.assertTrue(mounts["/inputs"]["readonly"])
        self.assertTrue(mounts["/etc"]["readonly"])
        self.assertTrue(mounts["/proc"]["readonly"])
        for target in ("/sys", "/run/user", "/home/adrian", "/dev/dri"):
            self.assertNotIn(target, mounts)
        for item in plan["mounts"]:
            if item["kind"] in ("bind", "ro-bind"):
                self.assertTrue(item["source"].startswith(plan["root"] + "/"))
        self.assertEqual(plan["descriptors"], {"payload": [0, 1, 2], "launcher_only": [3, 4]})

    def test_paths_nonces_symlinks_and_unsafe_parents_are_zero_write_refusals(self):
        for nonce in ("../escape", "--help", "", "0" * 15, "0" * 17, "g" * 16):
            with self.subTest(nonce=nonce), self.assertRaises(self.api.Refused):
                self.api.make_plan(self.worktree, nonce)
        target = self.worktree / "target"
        target.mkdir()
        alias = self.worktree / "alias"
        alias.symlink_to(target, target_is_directory=True)
        for root in (alias, self.worktree / "../escape", Path("relative")):
            with self.subTest(root=root), self.assertRaises(self.api.Refused):
                self.api.make_plan(root, "0" * 16)
        target.chmod(0o777)
        with self.assertRaises(self.api.Refused):
            self.api.make_plan(target, "0" * 16)
        self.assertFalse((self.worktree / ".local-ai").exists())

    def test_receipts_detect_bytes_identity_metadata_and_hardlink_drift(self):
        p = self.worktree / "receipt"
        p.write_bytes(b"reviewed")
        p.chmod(0o600)
        receipt = self.api.file_receipt(p)
        self.api.verify_receipt(p, receipt)
        p.write_bytes(b"changed!")
        with self.assertRaises(self.api.Refused):
            self.api.verify_receipt(p, receipt)
        p.unlink()
        p.write_bytes(b"reviewed")
        p.chmod(0o600)
        with self.assertRaises(self.api.Refused):
            self.api.verify_receipt(p, receipt)
        (self.worktree / "link").hardlink_to(p)
        with self.assertRaises(self.api.Refused):
            self.api.file_receipt(p)

    def test_receipts_refuse_symlink_fifo_wrong_hash_and_oversize(self):
        p = self.worktree / "file"
        p.write_bytes(b"data")
        alias = self.worktree / "alias"
        alias.symlink_to(p)
        fifo = self.worktree / "fifo"
        os.mkfifo(fifo, 0o600)
        for path in (alias, fifo):
            with self.subTest(path=path), self.assertRaises(self.api.Refused):
                self.api.file_receipt(path)
        receipt = self.api.file_receipt(p)
        receipt["sha256"] = "0" * 64
        with self.assertRaises(self.api.Refused):
            self.api.verify_receipt(p, receipt)
        with self.assertRaises(self.api.Refused):
            self.api.file_receipt(p, max_bytes=3)

    def test_pin_verification_requires_exact_complete_provenance(self):
        p = self.worktree / "candidate"
        # Minimal inert ELF metadata fixture: no loadable code or executable mode.
        header = b"\x7fELF\x02\x01\x01" + bytes(9) + struct.pack("<HHIQQQIHHHHHH", 3, 62, 1, 0, 64, 0, 0, 64, 56, 1, 0, 0, 0)
        segment = struct.pack("<IIQQQQQQ", 4, 4, 120, 0, 0, 20, 20, 4)
        note = struct.pack("<III", 4, 2, 3) + b"GNU\0\x12\x34\0\0"
        p.write_bytes(header + segment + note)
        pin = {"identity": self.api.file_receipt(p), "build_id": "1234",
               "distribution": {"package": "fixture", "version": "1", "source_receipt": "a" * 64}}
        self.api.verify_pin(p, pin)
        for field in ("build_id", "distribution", "identity"):
            bad = copy.deepcopy(pin)
            del bad[field]
            with self.subTest(field=field), self.assertRaises(self.api.Refused):
                self.api.verify_pin(p, bad)
        pin["build_id"] = "ffff"
        with self.assertRaises(self.api.Refused):
            self.api.verify_pin(p, pin)
        for raw in (b"not ELF", bytes(64), header + segment, header + segment + note[:10]):
            with self.subTest(raw=len(raw)), self.assertRaises(self.api.Refused):
                self.api.elf_from_bytes(raw)

    def test_filter_behavior_rejects_arch_x32_helpers_threads_network_and_new_syscalls(self):
        raw = self.api.compile_filter()
        self.assertEqual(len(raw) % 8, 0)
        # Literal kernel ABI outcomes; this interpreter never installs the filter.
        self.assertEqual(self.api.evaluate_filter(raw, 0, arch=0xc000003e), 0x7fff0000)
        self.assertEqual(self.api.evaluate_filter(raw, 59), 0x7fff0000)
        self.assertEqual(self.api.evaluate_filter(raw, 0, arch=0x40000003), 0x80000000)
        self.assertEqual(self.api.evaluate_filter(raw, 0x40000000), 0x80000000)
        for nr in (41, 42, 56, 57, 58, 101, 165, 166, 250, 272, 298,
                   308, 310, 311, 313, 317, 321, 322, 323, 425, 426, 427, 435, 9999):
            with self.subTest(nr=nr):
                self.assertEqual(self.api.evaluate_filter(raw, nr), 0x00050001)
        self.assertEqual(self.api.evaluate_filter(raw, 157, arg0=22), 0x7fff0000)
        self.assertEqual(self.api.evaluate_filter(raw, 157, arg0=0), 0x00050001)

    def test_fresh_journal_preserves_existing_ancestors_and_refuses_reuse(self):
        journal = self.journal()
        self.assertEqual(journal.root.stat().st_mode & 0o777, 0o700)
        self.assertEqual((journal.root / "journal.json").stat().st_mode & 0o777, 0o600)
        before = journal.root.stat()
        with self.assertRaises(self.api.Refused):
            self.api.create_journal(self.worktree, "0123456789abcdef")
        self.assertEqual(journal.root.stat(), before)
        self.assertEqual(json.loads((journal.root / "journal.json").read_text())["status"], "prepared-unexecuted")
        early = json.loads((journal.root / "initialization.json").read_text())
        self.assertEqual(early["status"], "initializing-unexecuted")
        self.assertEqual(early["root_identity"][1], journal.root.stat().st_ino)
        self.assertEqual((journal.root / "inputs/readonly-sentinel").read_bytes(), b"panda-inert-sentinel")
        self.assertEqual((journal.root / "etc/nsswitch.conf").read_bytes(), b"passwd: files\ngroup: files\nhosts: files\n")

    def test_journal_parent_replacement_cannot_redirect_cleanup(self):
        journal = self.journal()
        parent = journal.root.parent
        moved = parent.with_name("moved")
        parent.rename(moved)
        parent.symlink_to(moved, target_is_directory=True)
        with self.assertRaises(self.api.Refused):
            self.api.cleanup(journal, evidence_reviewed=True)
        self.assertTrue((moved / journal.root.name / "journal.json").exists())

    def test_parent_replacement_during_creation_stops_before_new_root_writes(self):
        local = self.worktree / "parent"
        local.mkdir(mode=0o700)
        chain = self.api.DirectoryChain(local)
        self.addCleanup(chain.close)
        local.rename(self.worktree / "moved")
        local.mkdir(mode=0o700)
        with self.assertRaises(self.api.Refused):
            chain.verify()
        self.assertEqual(list(local.iterdir()), [])

    def test_mutated_plan_types_cannot_bypass_exact_command_contract(self):
        for change in (lambda p: p.update(execution_enabled=0),
                       lambda p: p["limits"].update(wall_seconds=5.0),
                       lambda p: p["descriptors"].update(payload=[False, 1, 2])):
            plan = self.plan()
            change(plan)
            with self.subTest(plan=plan), self.assertRaises(self.api.Refused):
                self.api.launch_inert(plan)
            # Exercise the plan validator before sealed dispatch: a changed
            # plan must be refused even when process dispatch is replaced.
            with patch.object(self.api, "launch_inert", side_effect=AssertionError("dispatch reached")):
                with self.assertRaises(self.api.Refused):
                    self.api.collect_inert(plan)

    def test_cleanup_refuses_replaced_empty_directory_and_missing_leaf(self):
        journal = self.journal()
        (journal.root / "out").rename(journal.root / "out-moved")
        (journal.root / "out").mkdir(mode=0o700)
        with self.assertRaises(self.api.Refused):
            self.api.cleanup(journal, evidence_reviewed=True)
        (journal.root / "out-moved").rmdir()
        (journal.root / "journal.json").unlink()
        with self.assertRaises(self.api.Refused):
            self.api.cleanup(journal, evidence_reviewed=True)

    def test_cleanup_requires_review_and_rejects_unknown_objects(self):
        journal = self.journal()
        with self.assertRaises(self.api.Refused):
            self.api.cleanup(journal)
        extra = journal.root / "out/unreviewed"
        extra.write_bytes(b"preserve evidence")
        with self.assertRaises(self.api.Refused):
            self.api.cleanup(journal, evidence_reviewed=True)
        self.assertEqual(extra.read_bytes(), b"preserve evidence")

    def test_cleanup_refuses_changed_journal_or_object_identity(self):
        journal = self.journal()
        (journal.root / "journal.json").write_text("tampered")
        with self.assertRaises(self.api.Refused):
            self.api.cleanup(journal, evidence_reviewed=True)
        self.assertTrue(journal.root.exists())

    def test_cleanup_only_removes_its_exact_reviewed_empty_preparation(self):
        journal = self.journal()
        outside = self.worktree / "keep"
        outside.write_bytes(b"keep")
        self.api.cleanup(journal, evidence_reviewed=True)
        self.assertFalse(journal.root.exists())
        self.assertEqual(outside.read_bytes(), b"keep")

    def complete(self):
        if not hasattr(self, "evidence_journal"):
            self.evidence_journal = self.journal()
        plan = self.plan()
        ns = {name: {"parent": "parent-" + name, "child": "child-" + name}
              for name in ("user", "mnt", "pid", "ipc", "net", "uts", "cgroup")}
        return {"profile_sha256": plan["profile_sha256"], "plan_sha256": plan["plan_sha256"],
                "exit_code": 0, "timed_out": False, "reaped": True, "trace_complete": True,
                "trace_sha256": "a" * 64, "namespaces": ns, "proc_pid_namespace": "child-pid",
                "mounts": plan["mounts"], "environment": plan["environment"],
                "fds": [0, 1, 2], "streams": self.api.stream_inventory(self.evidence_journal),
                "cap_eff": 0, "no_new_privs": 1, "dumpable": 0,
                "denials": {name: 1 for name in ("socket", "clone", "unshare", "ptrace", "mount", "execve", "io_uring_setup")},
                "readonly_errno": 30, "hidden_errno": 2, "sentinels_preserved": True,
                "provenance_verified": True, "journal_verified": True,
                "limits": plan["limits"], "unexpected_writes": [], "unexpected_execs": [],
                "rusage": {"cpu_seconds": 0.01, "max_rss_bytes": 1000000, "output_bytes": 2000}}

    def test_complete_fixture_is_only_a_review_candidate_never_execution_approval(self):
        verdict = self.api.validate_evidence(self.plan(), self.complete(), journal=self.evidence_journal)
        self.assertEqual(verdict["status"], "review-candidate")
        self.assertFalse(verdict["gate2_authorized"])
        self.assertFalse(verdict["native_runtime_verified"])

    def test_partial_timeout_forged_or_contradictory_evidence_never_passes(self):
        cases = [("exit_code", 1), ("exit_code", False), ("timed_out", True), ("reaped", False),
                 ("trace_complete", False), ("fds", [0, 1, 2, 3]), ("cap_eff", 1),
                 ("provenance_verified", False), ("unexpected_writes", ["elsewhere"]),
                 ("environment", {}), ("mounts", []), ("plan_sha256", "0" * 64),
                 ("readonly_errno", 30.0), ("streams", []), ("streams", [{"fd": 0, "mode": 49152}])]
        for key, value in cases:
            data = self.complete()
            data[key] = value
            with self.subTest(key=key), self.assertRaises(self.api.Refused):
                self.api.validate_evidence(self.plan(), data, journal=self.evidence_journal)
        data = self.complete()
        del data["trace_sha256"]
        with self.assertRaises(self.api.Refused):
            self.api.validate_evidence(self.plan(), data, journal=self.evidence_journal)
        data = self.complete()
        data["namespaces"]["net"]["child"] = "parent-net"
        with self.assertRaises(self.api.Refused):
            self.api.validate_evidence(self.plan(), data, journal=self.evidence_journal)

    def test_malformed_and_unbounded_evidence_is_a_typed_refusal(self):
        for value in (float("nan"), object(), {"unhashable": set()}, "x" * 300000):
            data = self.complete()
            data["mounts"] = value
            with self.subTest(value=type(value).__name__), self.assertRaises(self.api.Refused):
                self.api.validate_evidence(self.plan(), data, journal=self.evidence_journal)

    def test_dangerous_file_capabilities_and_xattr_drift_are_refused(self):
        p = self.worktree / "file"
        p.write_bytes(b"receipt")
        try:
            os.setxattr(p, "user.panda-fixture", b"one")
        except OSError as exc:
            self.skipTest("fixture filesystem has no user xattrs: " + str(exc))
        receipt = self.api.file_receipt(p)
        os.setxattr(p, "user.panda-fixture", b"two")
        with self.assertRaises(self.api.Refused):
            self.api.verify_receipt(p, receipt)



class BoundedDispatchTests(unittest.TestCase):
    """Real private files; replace only the launch boundary, never launch a child."""
    setUp = SupervisorTests.setUp
    plan = SupervisorTests.plan
    journal = SupervisorTests.journal
    def process(self, journal, *, exit_code=0, populated=False, stuck=False, failure=None):
        class Process:
            killed = False
            def sample(inner):
                if failure is not None and not inner.killed:
                    raise failure
                return {"exit_code": (-9 if inner.killed and exit_code is None else exit_code) if not stuck else None,
                        "populated": populated if not inner.killed else stuck,
                        "reaped": not stuck and (exit_code is not None or inner.killed),
                        "cpu_seconds": 0.01, "max_rss_bytes": 4096}
            def terminate(inner):
                inner.killed = True
        return Process()

    def collect(self, journal, process):
        with patch.object(self.api, "launch_inert", return_value=process):
            return self.api.collect_inert(self.plan(), journal=journal)

    def test_capture_is_private_bounded_and_detects_identity_replacement(self):
        journal = self.journal()
        capture = self.api.PrivateCapture(journal, self.plan()["limits"])
        self.addCleanup(capture.close)
        self.assertEqual(set(capture.fds), {"stdout", "stderr", "trace", "status"})
        path = journal.root / "logs/stdout"
        path.write_bytes(b"partial")
        self.assertEqual(capture.read("stdout"), b"partial")
        path.rename(journal.root / "logs/moved")
        path.write_bytes(b"forged")
        path.chmod(0o600)
        with self.assertRaises(self.api.Refused):
            capture.snapshot()

    def test_output_overflow_terminates_tree_and_keeps_bounded_prefix(self):
        journal = self.journal()
        # A writer double may exceed the kernel cap; collection still reads at
        # most the explicit file bound and never calls communicate().
        (journal.root / "logs/stdout").write_bytes(b"x" * (self.plan()["limits"]["file_bytes"] + 1))
        process = self.process(journal)
        result = self.collect(journal, process)
        self.assertEqual(result["status"], "output-limit")
        self.assertTrue(process.killed)
        self.assertEqual(len(result["stdout"]), self.plan()["limits"]["file_bytes"])
        self.assertFalse(result["accepted"])

    def test_leader_exit_does_not_hide_session_escaped_child(self):
        journal = self.journal()
        process = self.process(journal, populated=True)
        result = self.collect(journal, process)
        self.assertTrue(process.killed)
        self.assertEqual(result["status"], "child-process-escape")
        self.assertTrue(result["tree_empty"])

    def test_early_failure_retains_output_and_full_tree_accounting(self):
        journal = self.journal()
        (journal.root / "logs/stderr").write_bytes(b"before main")
        result = self.collect(journal, self.process(journal, exit_code=126))
        self.assertEqual(result["status"], "early-failure")
        self.assertEqual(result["stderr"], b"before main")
        self.assertEqual(result["rusage"]["max_rss_bytes"], 4096)

    def test_timeout_and_incomplete_teardown_never_pass(self):
        journal = self.journal()
        for stuck in (False, True):
            process = self.process(journal, exit_code=None, populated=True, stuck=stuck)
            with self.subTest(stuck=stuck), patch.object(self.api.time, "monotonic", side_effect=range(1000)):
                result = self.collect(journal, process)
            self.assertTrue(process.killed)
            self.assertEqual(result["status"], "teardown-incomplete" if stuck else "timeout")
            self.assertFalse(result["accepted"])

    def test_post_launch_error_still_terminates_and_accounts(self):
        journal = self.journal()
        for error in (OSError("fixture read"), KeyboardInterrupt()):
            process = self.process(journal, failure=error)
            result = self.collect(journal, process)
            self.assertTrue(process.killed)
            self.assertEqual(result["status"], "interrupted")
            self.assertTrue(result["tree_empty"])

    def test_no_dispatch_adapter_can_bypass_unproven_pre_main_boundary(self):
        journal = self.journal()
        with patch.object(self.api.os, "fork", side_effect=AssertionError("fork reached")):
            with self.assertRaisesRegex(self.api.Refused, "pre-main"):
                self.api.dispatch_fixed(self.plan(), journal)

    def test_partial_raw_records_and_trace_are_refused(self):
        journal = self.journal()
        for raw in (b"", b"{", b"{}", b'{"schema_version":1,"schema_version":1}'):
            (journal.root / "logs/stdout").write_bytes(raw)
            with self.subTest(raw=raw), self.assertRaises(self.api.Refused):
                self.api.adapt_raw_evidence(self.plan(), journal, {})

    def raw_fixture(self):
        journal = self.journal()
        plan = self.plan()
        names = self.profile["namespaces"]
        child = {name: name + ":[200]" for name in names}
        bounds = plan["limits"]
        probe = {"schema_version": 1, "pid": 2, "ppid": 1, "namespaces": child,
                 "proc_pid_namespace": child["pid"],
                 "mountinfo": "1 0 0:1 / / ro,nosuid - tmpfs tmpfs ro\n",
                 "status": "".join(name + ":\t0000000000000000\n" for name in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb")) + "NoNewPrivs:\t1\nSeccomp:\t2\n",
                 "fds": self.api.stream_inventory(journal),
                 "environment": [k + "=" + v for k, v in plan["environment"].items()],
                 "dumpable": 0, "no_new_privs": 1, "seccomp_mode": 2,
                 "denials": {n: 1 for n in ("socket", "clone", "unshare", "ptrace", "mount", "execve", "io_uring_setup")},
                 "sentinels": {"readonly_errno": 30, "hidden_errno": 2, "output_bytes": 17},
                 "limits": {"cpu": [bounds["cpu_seconds"]] * 2, "address_space": [bounds["address_space_bytes"]] * 2,
                            "file_size": [bounds["file_bytes"]] * 2, "open_files": [bounds["open_files"]] * 2,
                            "processes": [bounds["processes"]] * 2, "core": [0, 0]}}
        parent = {name: name + ":[100]" for name in names}
        (journal.root / "logs/parent-namespaces").write_bytes(self.api.encoded(parent))
        (journal.root / "logs/stdout").write_bytes(self.api.encoded(probe))
        (journal.root / "logs/trace").write_bytes(b'100 1.000 execve("/usr/bin/bwrap", [], []) = 0 <0.001>\n100 1.001 execve("/runtime/inert-probe", [], []) = 0 <0.001>\n100 1.002 exit_group(0) = ?\n100 1.003 +++ exited with 0 +++\n')
        (journal.root / "logs/status").write_bytes(b'{"child-pid":100}\n{"exit-code":0}\n')
        (journal.root / "out/sentinel").write_bytes(b"panda-inert-output")
        (journal.root / "out/sentinel").chmod(0o600)
        return journal, probe, {"status": "exited", "tree_empty": True, "exit_code": 0,
                                "reaped": True,
                                "rusage": {"cpu_seconds": 0.01, "max_rss_bytes": 4096}}

    def test_raw_adapter_preserves_observations_without_inventing_attestation(self):
        journal, probe, outcome = self.raw_fixture()
        result = self.api.adapt_raw_evidence(self.plan(), journal, outcome)
        self.assertEqual(result["status"], "raw-observations-only")
        self.assertEqual(result["probe"], probe)
        self.assertTrue(result["unresolved"])
        self.assertNotIn("accepted", result)
        self.assertNotIn("provenance_verified", result)

    def test_raw_adapter_rejects_descriptor_limits_namespace_and_security_drift(self):
        journal, probe, outcome = self.raw_fixture()
        for key, bad in (("fds", [None]), ("fds", {}), ("limits", {}), ("environment", ["HOME=/", "HOME=/"]),
                         ("namespaces", {}), ("status", "CapEff:\t1\n"), ("dumpable", True),
                         ("denials", {}), ("sentinels", {})):
            data = copy.deepcopy(probe)
            data[key] = bad
            (journal.root / "logs/stdout").write_bytes(self.api.encoded(data))
            with self.subTest(key=key), self.assertRaises(self.api.Refused):
                self.api.adapt_raw_evidence(self.plan(), journal, outcome)

    def test_raw_adapter_checks_preservation_and_unrelated_objects(self):
        journal, probe, outcome = self.raw_fixture()
        (journal.root / "inputs/readonly-sentinel").write_bytes(b"tampered")
        with self.assertRaises(self.api.Refused):
            self.api.adapt_raw_evidence(self.plan(), journal, outcome)
        (journal.root / "out/host-link").symlink_to("/etc/passwd")
        with self.assertRaises(self.api.Refused):
            self.api.post_exit_inventory(journal)

    def test_filter_profile_and_runtime_identity_changes_are_refused(self):
        journal = self.journal()
        (journal.root / "runtime/unexpected").write_bytes(b"not executable")
        with self.assertRaisesRegex(self.api.Refused, "runtime closure"):
            self.api.verify_bundle(self.plan(), journal)
        plan = self.plan()
        plan["filter_sha256"] = "0" * 64
        with self.assertRaises(self.api.Refused):
            self.api.verify_bundle(plan, journal)

    def test_mount_parser_preserves_full_graph_and_refuses_ambiguity(self):
        raw = "1 0 0:1 / / ro,nosuid - tmpfs tmpfs ro\n2 1 0:2 / /proc ro,nosuid,nodev,noexec - proc proc ro\n"
        records = self.api.parse_mountinfo(raw)
        self.assertEqual([r["target"] for r in records], ["/", "/proc"])
        self.assertTrue(records[1]["noexec"])
        for bad in (raw + raw, raw[:-1], raw.replace("/proc", "/bad\\040path"), "garbage\n"):
            with self.subTest(bad=bad), self.assertRaises(self.api.Refused):
                self.api.parse_mountinfo(bad)

    def test_trace_parser_requires_all_lifetimes_and_rejects_truncation(self):
        raw = b'100 1.000 execve("/runtime/inert-probe", [], []) = 0 <0.001>\n100 1.100 exit_group(0) = ?\n100 1.101 +++ exited with 0 +++\n'
        result = self.api.parse_trace(raw)
        self.assertEqual(result["pids"], [100])
        self.assertEqual(result["execs"], ["/runtime/inert-probe"])
        for bad in (raw[:-1], raw.split(b"100 1.101")[0], raw + b"strace: detached\n"):
            with self.subTest(bad=bad), self.assertRaises(self.api.Refused):
                self.api.parse_trace(bad)

    def test_trace_plan_does_not_abbreviate_a_bounded_probe_record(self):
        plan = self.plan()
        argv = plan["argv"]
        self.assertEqual(argv[argv.index("-s") + 1], str(plan["limits"]["file_bytes"]))
        self.assertNotIn("-qq", argv)

    def test_late_output_overflow_after_leader_exit_is_refused(self):
        journal = self.journal()
        process = self.process(journal)
        terminate = process.terminate
        def late_write():
            terminate()
            (journal.root / "logs/stderr").write_bytes(b"x" * self.plan()["limits"]["file_bytes"])
        process.terminate = late_write
        result = self.collect(journal, process)
        self.assertEqual(result["status"], "output-limit")

    def test_failed_whole_tree_kill_is_incomplete_teardown(self):
        journal = self.journal()
        process = self.process(journal)
        def denied():
            raise OSError("fixture cgroup kill failure")
        process.terminate = denied
        result = self.collect(journal, process)
        self.assertEqual(result["status"], "teardown-incomplete")
        self.assertFalse(result["tree_empty"])

    def test_raw_launcher_exit_must_agree_with_trace_and_collector(self):
        journal, probe, outcome = self.raw_fixture()
        for raw in (b'{}\n', b'{"child-pid":100}\n', b'{"child-pid":100}\n{"exit-code":90}\n',
                    b'{"child-pid":true}\n{"exit-code":0}\n'):
            (journal.root / "logs/status").write_bytes(raw)
            with self.subTest(raw=raw), self.assertRaises(self.api.Refused):
                self.api.adapt_raw_evidence(self.plan(), journal, outcome)

    def test_post_exit_inventory_refuses_root_additions_and_journal_drift(self):
        journal = self.journal()
        extra = journal.root / "unexpected"
        extra.write_bytes(b"retain")
        with self.assertRaises(self.api.Refused):
            self.api.post_exit_inventory(journal)
        extra.unlink()
        (journal.root / "journal.json").write_bytes(b"changed")
        with self.assertRaises(self.api.Refused):
            self.api.post_exit_inventory(journal)

    def test_raw_lifetime_requires_explicit_complete_reaping(self):
        journal, probe, outcome = self.raw_fixture()
        for missing in (False, True):
            bad = copy.deepcopy(outcome)
            if missing:
                del bad["reaped"]
            else:
                bad["reaped"] = False
            with self.subTest(missing=missing), self.assertRaises(self.api.Refused):
                self.api.adapt_raw_evidence(self.plan(), journal, bad)

    def test_kernel_descriptor_close_covers_fds_above_lowered_soft_limit(self):
        # Model a descriptor table whose inherited fd survives a lowered soft
        # limit. Only the process-dispatch syscall boundary is replaced.
        inherited = {3, 4, 5, 31, 1000, 100000}
        class Kernel:
            def syscall(inner, number, first, last, flags):
                self.assertEqual(number, 436)  # reviewed Linux x86-64 close_range
                inherited.difference_update(fd for fd in list(inherited) if first.value <= fd <= last.value)
                return 0
        self.api.close_child_descriptors(Kernel())
        self.assertEqual(inherited, {3, 4})
        class Unsupported:
            def syscall(inner, *args):
                return -1
        with self.assertRaises(self.api.Refused):
            self.api.close_child_descriptors(Unsupported())

    def test_fork_registration_precedes_interrupt_delivery(self):
        from types import SimpleNamespace
        tree = SimpleNamespace(pid=None, pidfd=None)
        masks = []
        def mask(how, values):
            masks.append(how)
            if how == signal.SIG_SETMASK:
                self.assertEqual(tree.pid, 987654)
                self.assertEqual(tree.pidfd, 123)
                raise KeyboardInterrupt()
            return set()
        with patch.object(self.api.signal, "pthread_sigmask", side_effect=mask), \
                patch.object(self.api.signal, "getsignal", return_value=signal.SIG_DFL), \
                patch.object(self.api.os, "fork", return_value=987654), \
                patch.object(self.api.os, "pidfd_open", return_value=123):
            with self.assertRaises(KeyboardInterrupt):
                self.api.registered_fork(tree)
        self.assertEqual(masks, [signal.SIG_BLOCK, signal.SIG_SETMASK])

    def test_teardown_kills_owned_child_even_before_cgroup_enrollment(self):
        # The direct child has not reached its stop/admission handshake yet.
        from types import SimpleNamespace
        journal = self.journal()
        kill_file = journal.root / "logs/cgroup-kill-fixture"
        fd = os.open(kill_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        self.addCleanup(os.close, fd)
        tree = object.__new__(self.api.OwnedTree)
        tree.chain = SimpleNamespace(verify=lambda: None)
        tree.handles = {"cgroup.kill": fd}
        tree.pid, tree.pidfd, tree.exit_code = 987654, 123, None
        with patch.object(self.api.signal, "pidfd_send_signal") as send:
            tree.terminate()
        send.assert_called_once_with(123, signal.SIGKILL)
        self.assertEqual(kill_file.read_bytes(), b"1")

    def test_stopped_child_is_admitted_before_it_can_continue(self):
        from types import SimpleNamespace
        journal = self.journal()
        path = journal.root / "logs/cgroup-procs-fixture"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        self.addCleanup(os.close, fd)
        tree = SimpleNamespace(pid=987654, pidfd=123, exit_code=None,
                               wait_usage=[], handles={"cgroup.procs": fd})
        stopped = (signal.SIGSTOP << 8) | 0x7f
        def continued(handle, sig):
            self.assertEqual((handle, sig), (123, signal.SIGCONT))
            self.assertEqual(path.read_bytes(), b"987654")
        with patch.object(self.api.os, "wait4", return_value=(987654, stopped, None)), \
                patch.object(self.api.signal, "pidfd_send_signal", side_effect=continued):
            self.api.admit_stopped_child(tree, 1)

    def test_raw_procfs_and_errno_variants_refuse_coercion(self):
        journal, probe, outcome = self.raw_fixture()
        changes = [("proc_pid_namespace", "pid:[999]")]
        for name, bad in changes:
            data = copy.deepcopy(probe)
            data[name] = bad
            (journal.root / "logs/stdout").write_bytes(self.api.encoded(data))
            with self.assertRaises(self.api.Refused):
                self.api.adapt_raw_evidence(self.plan(), journal, outcome)

        for container, name, bad in (("denials", "socket", True), ("denials", "execve", 1.0),
                                      ("sentinels", "readonly_errno", 30.0), ("sentinels", "hidden_errno", False)):
            data = copy.deepcopy(probe)
            data[container][name] = bad
            (journal.root / "logs/stdout").write_bytes(self.api.encoded(data))
            with self.subTest(container=container, name=name), self.assertRaises(self.api.Refused):
                self.api.adapt_raw_evidence(self.plan(), journal, outcome)


    def test_cgroup_binding_drift_does_not_skip_owned_child_kill(self):
        from types import SimpleNamespace
        def changed():
            raise self.api.Refused("fixture cgroup binding drift")
        tree = object.__new__(self.api.OwnedTree)
        tree.chain = SimpleNamespace(verify=changed)
        tree.pid, tree.pidfd, tree.exit_code = 987654, 123, None
        tree.handles = {}
        with patch.object(self.api.signal, "pidfd_send_signal") as send:
            with self.assertRaises(self.api.Refused):
                tree.terminate()
        send.assert_called_once_with(123, signal.SIGKILL)


if __name__ == "__main__":
    unittest.main()
