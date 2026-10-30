"""Offline persistence tests; synthetic receipts grant no execution authority."""
import copy
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import hashlib
import importlib
import multiprocessing
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest

S4 = Path(__file__).resolve().parent / "native/external_vm/s4"


def crash_before_commit(path):
    connection = sqlite3.connect(path, isolation_level=None)
    connection.execute("BEGIN IMMEDIATE")
    connection.execute("UPDATE approvals SET state='consumed', revision=revision+1, consumed_at=150")
    os._exit(0)  # Simulated process death; no COMMIT, never a candidate process.


def process_claim(path, claim, files, ready, start, output):
    from ubuntu_authority import Authority, Denied, Unavailable
    ready.put(True)
    start.wait(10)
    try:
        Authority(path, clock=lambda: 150).consume("synthetic-approval-01", 2, claim, files)
        output.put("consumed")
    except (Denied, Unavailable):
        output.put("blocked")


class DurableAuthority(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(S4)); self.addCleanup(sys.path.remove, str(S4))
        self.api = importlib.import_module("ubuntu_authority")
        model = importlib.import_module("ubuntu_authorization")
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "authority.sqlite"
        self.files = {name: ("synthetic reviewed bytes: " + name).encode() for name in model.SOURCE_FILES}
        self.record = dict(schema_version=1, approval_id="synthetic-approval-01", revision=1,
            state="draft", source_sha="a"*40, repository_id="123", operator_id="456", run_id="789",
            not_before=100, expires_at=200, review_reference="synthetic review; no approval",
            source_hashes={name: hashlib.sha256(raw).hexdigest() for name, raw in self.files.items()},
            consumed_at=None)
        self.claim = dict(repository="adrianrusu16/panda-workstation", repository_id="123",
            source_sha="a"*40, reviewed_source_sha="a"*40, checkout_sha="a"*40, workflow_sha="a"*40,
            main_sha="a"*40, ref="refs/heads/main", event_name="workflow_dispatch",
            workflow_path=".github/workflows/panda-ubuntu-bootstrap-verification.yml",
            run_id="789", run_attempt="1", actor_id="456", triggering_actor_id="456")
        self.now = 150
        self.api.Authority.initialize(self.path)
        self.owner = self.api.Authority(self.path, clock=lambda: self.now)

    def draft(self):
        self.owner.create_draft(self.record, self.claim, self.files)

    def approved(self):
        self.draft()
        self.owner.approve(self.record["approval_id"], 1)

    def consume(self, revision=2, claim=None, files=None):
        return self.owner.consume(self.record["approval_id"], revision,
            self.claim if claim is None else claim, self.files if files is None else files)

    def rows(self, table):
        with closing(sqlite3.connect(self.path)) as connection:
            connection.row_factory = sqlite3.Row
            return [dict(row) for row in connection.execute("SELECT * FROM " + table)]

    def test_lifecycle_commits_receipt_and_audit_then_denies_replay_after_reopen(self):
        self.approved()
        receipt = self.consume()
        self.assertEqual(receipt, dict(approval_id="synthetic-approval-01", revision=3,
            state="consumed", consumed_at=150, run_id="789", source_sha="a"*40))
        self.owner = self.api.Authority(self.path, clock=lambda: 151)
        with self.assertRaises(self.api.Denied): self.consume()
        self.assertEqual(self.rows("approvals")[0]["state"], "consumed")
        self.assertEqual([(r["action"], r["outcome"]) for r in self.rows("audit")],
            [("create", "ok"), ("approve", "ok"), ("consume", "ok"), ("consume", "denied")])

    def test_draft_is_not_authority_and_stale_or_malformed_revisions_are_denied(self):
        self.draft()
        with self.assertRaises(self.api.Denied): self.consume(1)
        for revision in (None, True, "1", 0, -1, 2**53, 2):
            with self.subTest(revision=revision), self.assertRaises(self.api.Denied):
                self.owner.approve(self.record["approval_id"], revision)
        self.assertEqual(self.rows("approvals")[0]["state"], "draft")
        self.owner.approve(self.record["approval_id"], 1)
        with self.assertRaises(self.api.Denied): self.consume(1)

    def test_revocation_from_draft_or_approved_is_terminal_and_durable(self):
        self.draft()
        self.owner.revoke(self.record["approval_id"], 1)
        with self.assertRaises(self.api.Denied): self.owner.approve(self.record["approval_id"], 2)
        with self.assertRaises(self.api.Denied): self.consume()
        self.assertEqual(self.rows("approvals")[0]["state"], "revoked")

    def test_approved_revocation_wins_before_consumption(self):
        self.approved()
        self.owner.revoke(self.record["approval_id"], 2)
        with self.assertRaises(self.api.Denied): self.consume(3)
        self.assertEqual(self.rows("approvals")[0]["state"], "revoked")

    def test_scope_cannot_be_reissued_under_new_id_run_or_source(self):
        self.approved(); self.consume()
        replacement = copy.deepcopy(self.record)
        replacement.update(approval_id="synthetic-replacement-01", run_id="790", source_sha="b"*40)
        claim = dict(self.claim, run_id="790", **{k: "b"*40 for k in
            ("source_sha", "reviewed_source_sha", "checkout_sha", "workflow_sha", "main_sha")})
        with self.assertRaises(self.api.Denied): self.owner.create_draft(replacement, claim, self.files)
        with self.assertRaises(self.api.Denied): self.draft()
        self.assertEqual(len(self.rows("approvals")), 1)

    def test_unknown_ids_and_invalid_requests_are_audited_without_raw_payloads(self):
        for identifier in ("synthetic-unknown-01", "bad\nsecret", None, []):
            with self.subTest(identifier=identifier), self.assertRaises(self.api.Denied):
                self.owner.consume(identifier, 1, {}, {})
        audit = self.rows("audit")
        self.assertEqual(len(audit), 4)
        self.assertTrue(all(r["outcome"] == "denied" for r in audit))
        self.assertNotIn("secret", repr(audit))

    def test_creation_rejects_schema_or_identity_changes_without_reserving_scope(self):
        mutations = (("extra", True), ("schema_version", True), ("revision", 2),
            ("state", "approved"), ("operator_id", "0"), ("expires_at", 99),
            ("source_hashes", {}), ("consumed_at", 123))
        for key, value in mutations:
            record = copy.deepcopy(self.record); record[key] = value
            with self.subTest(key=key), self.assertRaises(self.api.Denied):
                self.owner.create_draft(record, self.claim, self.files)
        self.assertEqual(self.rows("approvals"), [])
        self.draft()

    def test_claim_source_and_byte_mutations_do_not_consume(self):
        self.approved()
        mutations = [(key, "b"*40) for key in
            ("source_sha", "reviewed_source_sha", "checkout_sha", "workflow_sha", "main_sha")]
        mutations += [("repository_id", "124"), ("actor_id", "457"), ("triggering_actor_id", "457"),
            ("run_id", "790"), ("run_attempt", "2"), ("event_name", "pull_request"),
            ("ref", "refs/tags/main"), ("workflow_path", "other.yml"), ("extra", "x")]
        for key, value in mutations:
            with self.subTest(key=key), self.assertRaises(self.api.Denied):
                self.consume(claim=dict(self.claim, **{key: value}))
        for name in self.files:
            with self.subTest(name=name), self.assertRaises(self.api.Denied):
                self.consume(files=dict(self.files, **{name: b"changed"}))
        self.assertEqual(self.rows("approvals")[0]["state"], "approved")
        self.consume()

    def test_expiry_is_derived_and_never_refunds_or_renews(self):
        self.approved()
        for now in (99, 200, 201):
            self.owner = self.api.Authority(self.path, clock=lambda: now)
            with self.subTest(now=now), self.assertRaises((self.api.Denied, self.api.Unavailable)):
                self.consume()
        self.assertEqual(self.rows("approvals")[0]["state"], "approved")
        self.owner = self.api.Authority(self.path, clock=lambda: 199)
        with self.assertRaises(self.api.Unavailable): self.consume()  # Durable clock high-water mark.

    def test_expiry_during_validation_is_checked_again_at_cas(self):
        self.approved()
        times = iter((150, 200))
        self.owner = self.api.Authority(self.path, clock=lambda: next(times))
        with self.assertRaises(self.api.Denied): self.consume()
        self.assertEqual(self.rows("approvals")[0]["state"], "approved")

    def test_expiry_after_commit_burns_approval_without_returning_receipt(self):
        self.approved()
        times = iter((150, 150, 200))
        self.owner = self.api.Authority(self.path, clock=lambda: next(times))
        with self.assertRaises(self.api.Unavailable): self.consume()
        self.assertEqual(self.rows("approvals")[0]["state"], "consumed")

    def test_bad_clock_and_clock_rollback_fail_closed(self):
        self.approved()
        for value in (True, None, "150", -1, 2**53, 149):
            self.owner = self.api.Authority(self.path, clock=lambda: value)
            with self.subTest(value=value), self.assertRaises(self.api.Unavailable): self.consume()
        self.assertEqual(self.rows("approvals")[0]["state"], "approved")

    def test_clock_floor_is_not_a_persistent_clock_health_fence(self):
        self.approved()
        times = iter((199, 198))
        self.owner = self.api.Authority(self.path, clock=lambda: next(times))
        with self.assertRaises(self.api.Unavailable): self.consume()
        self.assertEqual(self.rows("clock_floor")[0]["epoch"], 150)
        # Deliberately demonstrates the reference limit, not a permitted client retry.
        # A production clock alarm must fence the owner outside this transaction.
        self.owner = self.api.Authority(self.path, clock=lambda: 198)
        self.assertEqual(self.consume()["consumed_at"], 198)

    def test_two_processes_share_one_persistent_serialization_boundary(self):
        self.approved()
        context = multiprocessing.get_context("spawn")
        ready, output, start = context.Queue(), context.Queue(), context.Event()
        processes = [context.Process(target=process_claim,
            args=(str(self.path), self.claim, self.files, ready, start, output)) for _ in range(2)]
        for process in processes: process.start()
        try:
            for _ in processes: self.assertTrue(ready.get(timeout=10))
            start.set()
            results = [output.get(timeout=10) for _ in processes]
            self.assertCountEqual(results, ["consumed", "blocked"])
            for process in processes:
                process.join(10); self.assertEqual(process.exitcode, 0)
        finally:
            for process in processes:
                if process.is_alive(): process.terminate(); process.join(10)
            ready.close(); output.close()
        self.assertEqual(self.rows("approvals")[0]["state"], "consumed")
        self.assertEqual(sum(r["action"] == "consume" and r["outcome"] == "ok"
            for r in self.rows("audit")), 1)

    def test_revocation_and_consumption_race_has_one_terminal_winner(self):
        self.approved()
        barrier = threading.Barrier(2)
        def transition(action):
            owner = self.api.Authority(self.path, clock=lambda: 150)
            barrier.wait(timeout=10)
            try:
                if action == "consume": owner.consume(self.record["approval_id"], 2, self.claim, self.files)
                else: owner.revoke(self.record["approval_id"], 2)
                return action
            except (self.api.Denied, self.api.Unavailable): return "blocked"
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(transition, ("consume", "revoke")))
        self.assertEqual(results.count("blocked"), 1)
        self.assertIn(self.rows("approvals")[0]["state"], ("revoked", "consumed"))

    def test_audit_failure_rolls_back_consumption(self):
        self.approved()
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("CREATE TRIGGER synthetic_audit_failure BEFORE INSERT ON audit "
                "BEGIN SELECT RAISE(ABORT, 'synthetic audit failure'); END")
        with self.assertRaises(self.api.Unavailable): self.consume()
        self.assertEqual(self.rows("approvals")[0]["state"], "approved")

    def test_commit_failure_never_returns_a_receipt(self):
        self.approved()
        with closing(sqlite3.connect(self.path, isolation_level=None)) as reader:
            reader.execute("BEGIN")
            reader.execute("SELECT * FROM approvals").fetchall()
            with self.assertRaises(self.api.Unavailable): self.consume()
            reader.execute("ROLLBACK")
        self.assertEqual(self.rows("approvals")[0]["state"], "approved")

    def test_process_death_before_commit_rolls_back_on_reopen(self):
        self.approved()
        process = multiprocessing.get_context("spawn").Process(target=crash_before_commit, args=(str(self.path),))
        process.start(); process.join(10)
        if process.is_alive(): process.terminate(); process.join(10)
        self.assertEqual(process.exitcode, 0)
        self.assertEqual(self.rows("approvals")[0]["state"], "approved")
        self.consume()

    def test_discarded_response_and_client_reset_do_not_restore_authority(self):
        self.approved(); self.consume()  # Deliberately discard committed response.
        self.owner = self.api.Authority(self.path, clock=lambda: 151)
        for revision in (2, 3):
            with self.assertRaises(self.api.Denied): self.consume(revision)
        with self.assertRaises(self.api.Denied): self.owner.revoke(self.record["approval_id"], 3)
        self.assertEqual(self.rows("approvals")[0]["state"], "consumed")

    def test_database_guards_block_deletion_and_terminal_or_immutable_rewrites(self):
        self.approved(); self.consume()
        statements = ("DELETE FROM approvals", "DELETE FROM audit", "UPDATE audit SET outcome='ok'",
            "UPDATE approvals SET state='approved', revision=revision+1, consumed_at=NULL",
            "UPDATE approvals SET template='{}'", "UPDATE approvals SET run_id='790'")
        for sql in statements:
            with self.subTest(sql=sql), closing(sqlite3.connect(self.path)) as connection:
                with self.assertRaises(sqlite3.IntegrityError): connection.execute(sql)

    def test_missing_corrupt_or_existing_database_is_never_implicitly_reinitialized(self):
        with self.assertRaises(FileExistsError): self.api.Authority.initialize(self.path)
        self.path.unlink()
        with self.assertRaises(self.api.Unavailable): self.consume()
        self.assertFalse(self.path.exists())
        self.path.write_bytes(b"synthetic corruption")
        with self.assertRaises(self.api.Unavailable): self.consume()
        self.assertEqual(self.path.read_bytes(), b"synthetic corruption")


if __name__ == "__main__":
    unittest.main()
