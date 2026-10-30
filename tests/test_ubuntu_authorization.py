"""Synthetic authorization model tests. The test owner grants no real authority."""
import copy
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib
from pathlib import Path
import sys
import threading
import unittest

S4 = Path(__file__).resolve().parent / "native/external_vm/s4"


class AuthorizationAdmission(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(S4)); self.addCleanup(sys.path.remove, str(S4))
        self.api = importlib.import_module("ubuntu_authorization")
        self.files = {name: ("synthetic reviewed bytes: "+name).encode() for name in self.api.SOURCE_FILES}
        self.record = dict(schema_version=1, approval_id="synthetic-approval-01", revision=1,
            state="approved", source_sha="a"*40, repository_id="123", operator_id="456", run_id="789",
            not_before=100, expires_at=200, review_reference="synthetic review; no approval",
            source_hashes={name: hashlib.sha256(raw).hexdigest() for name, raw in self.files.items()},
            consumed_at=None)
        self.claim = dict(repository="adrianrusu16/panda-workstation", repository_id="123",
            source_sha="a"*40, reviewed_source_sha="a"*40, checkout_sha="a"*40, workflow_sha="a"*40,
            main_sha="a"*40, ref="refs/heads/main", event_name="workflow_dispatch",
            workflow_path=".github/workflows/panda-ubuntu-bootstrap-verification.yml",
            run_id="789", run_attempt="1", actor_id="456", triggering_actor_id="456")

    def transition(self, record=None, claim=None, now=150, files=None):
        return self.api.consume_approval(self.record if record is None else record,
            self.claim if claim is None else claim, now,
            self.files if files is None else files)

    def test_consumption_returns_new_terminal_record_without_mutating_approval(self):
        before = copy.deepcopy(self.record)
        result = self.transition()
        self.assertEqual(result["state"], "consumed")
        self.assertEqual(result["revision"], 2)
        self.assertEqual(result["consumed_at"], 150)
        self.assertEqual(self.record, before)
        result["source_hashes"].clear()
        self.assertEqual(self.record, before)

    def test_missing_malformed_unknown_or_unapproved_record_rejects(self):
        for value in (None, [], {}, {"approved": True}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.api.consume_approval(value, self.claim, 150, self.files)
        for key, value in (("schema_version", True), ("revision", True), ("revision", 0),
                           ("state", "revoked"), ("state", "consumed"), ("state", "pending"),
                           ("approval_id", "../approval"), ("operator_id", True),
                           ("repository_id", ""), ("run_id", "0"), ("source_sha", "A"*40),
                           ("not_before", True), ("expires_at", "200"), ("expires_at", 99),
                           ("review_reference", ""), ("review_reference", "bad\nreview"),
                           ("consumed_at", 120), ("source_hashes", {}), ("extra", "approved")):
            record = copy.deepcopy(self.record); record[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                self.transition(record=record)

    def test_expiry_boundaries_and_untrusted_time_shape_reject(self):
        self.assertEqual(self.transition(now=100)["state"], "consumed")
        self.assertEqual(self.transition(now=199)["state"], "consumed")
        for now in (99, 200, 201, None, True, "150", -1, 2**63):
            with self.subTest(now=now), self.assertRaises(ValueError):
                self.transition(now=now)

    def test_claim_identity_operator_event_branch_and_rerun_constraints(self):
        mutations = [(key, "b"*40) for key in
                     ("source_sha", "reviewed_source_sha", "checkout_sha", "workflow_sha", "main_sha")]
        mutations += [("repository", "other/repo"), ("repository_id", "124"), ("run_id", "790"),
                      ("actor_id", "457"), ("triggering_actor_id", "457"), ("run_attempt", "2"),
                      ("ref", "refs/heads/feature"), ("ref", "refs/tags/main"),
                      ("event_name", "pull_request"), ("workflow_path", "other.yml"),
                      ("extra", "approved")]
        for key, value in mutations:
            claim = dict(self.claim); claim[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                self.transition(claim=claim)
        for claim in (None, [], {}, {**self.claim, "source_sha": None}):
            with self.subTest(claim=claim), self.assertRaises(ValueError):
                self.api.consume_approval(self.record, claim, 150, self.files)

    def test_modified_missing_extra_or_malformed_working_bytes_reject(self):
        for name in self.files:
            files = dict(self.files); files[name] += b"modified checkout"
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "source bytes"):
                self.transition(files=files)
        missing = dict(self.files); missing.pop(next(iter(missing)))
        for files in (missing, {**self.files, "extra.py": b"x"},
                      {**self.files, next(iter(self.files)): "not bytes"}):
            with self.subTest(files=tuple(files)), self.assertRaises(ValueError):
                self.transition(files=files)

    def test_reuse_and_local_state_reset_cannot_restore_external_record(self):
        external = self.transition()
        for _ in range(2):  # A new local client still sees consumed external state.
            with self.assertRaises(ValueError):
                self.api.consume_approval(copy.deepcopy(external), dict(self.claim), 151, dict(self.files))

    def test_two_concurrent_claims_have_exactly_one_winner_under_external_cas(self):
        lock, barrier = threading.Lock(), threading.Barrier(2)
        external = [copy.deepcopy(self.record)]
        def claimant():
            snapshot = copy.deepcopy(external[0])
            proposal = self.transition(record=snapshot)
            barrier.wait()
            with lock:
                if external[0] != snapshot:
                    return "conflict"
                external[0] = proposal
                return "consumed"
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: claimant(), range(2)))
        self.assertCountEqual(results, ["consumed", "conflict"])
        self.assertEqual(external[0]["state"], "consumed")

    def test_pure_model_itself_has_no_durable_single_use_enforcement(self):
        # Replaying an old snapshot works: only the trusted owner's CAS may commit it.
        self.assertEqual(self.transition(), self.transition())

    def test_control_plane_failure_and_lost_response_burn_committed_approval(self):
        lock = threading.Lock()
        external = [copy.deepcopy(self.record)]
        def consume(*, available=True, lose_response=False):
            if not available:
                raise ConnectionError("synthetic authority unavailable")
            with lock:
                proposal = self.transition(record=external[0])
                external[0] = proposal
            if lose_response:
                raise TimeoutError("synthetic response lost after durable commit")
            return proposal
        with self.assertRaises(ConnectionError):
            consume(available=False)
        self.assertEqual(external[0]["state"], "approved")
        with self.assertRaises(TimeoutError):
            consume(lose_response=True)
        self.assertEqual(external[0]["state"], "consumed")
        with self.assertRaises(ValueError):
            consume()  # No retry, cancellation refund or missing-evidence refund.
