"""Offline SQLite reference owner, NOT an authenticated service or execution gate.

Every caller, clock and observation is trusted test input. No runner imports this
module. Local database access can defeat these guards; production needs the
independent administration and anti-rollback controls in the architecture guide.
"""
from contextlib import closing
import json
from pathlib import Path
import re
import sqlite3

from ubuntu_authorization import consume_approval

SCOPE = "ubuntu-s4-authentication-v1"
SCHEMA = """
BEGIN IMMEDIATE;
CREATE TABLE approvals (
    approval_id TEXT PRIMARY KEY NOT NULL,
    repository_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    scope TEXT NOT NULL CHECK(scope='ubuntu-s4-authentication-v1'),
    template TEXT NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('draft','approved','revoked','consumed')),
    revision INTEGER NOT NULL CHECK(revision > 0 AND revision < 9007199254740992),
    consumed_at INTEGER,
    UNIQUE(repository_id, scope),
    UNIQUE(repository_id, run_id),
    CHECK((state='consumed' AND consumed_at IS NOT NULL) OR
          (state!='consumed' AND consumed_at IS NULL))
);
CREATE TABLE audit (
    sequence INTEGER PRIMARY KEY,
    at INTEGER NOT NULL,
    action TEXT NOT NULL,
    approval_id TEXT,
    outcome TEXT NOT NULL CHECK(outcome IN ('ok','denied')),
    reason TEXT NOT NULL
);
CREATE TABLE clock_floor (singleton INTEGER PRIMARY KEY CHECK(singleton=1), epoch INTEGER NOT NULL);
INSERT INTO clock_floor VALUES (1, 0);
CREATE TRIGGER preserve_approval BEFORE DELETE ON approvals
BEGIN SELECT RAISE(ABORT, 'permanent scope tombstone'); END;
CREATE TRIGGER preserve_audit BEFORE DELETE ON audit
BEGIN SELECT RAISE(ABORT, 'append-only audit'); END;
CREATE TRIGGER immutable_audit BEFORE UPDATE ON audit
BEGIN SELECT RAISE(ABORT, 'append-only audit'); END;
CREATE TRIGGER approval_transition BEFORE UPDATE ON approvals
WHEN NEW.approval_id != OLD.approval_id OR NEW.repository_id != OLD.repository_id OR
     NEW.run_id != OLD.run_id OR NEW.scope != OLD.scope OR NEW.template != OLD.template OR
     NEW.revision != OLD.revision+1 OR NOT (
       (OLD.state='draft' AND NEW.state IN ('approved','revoked')) OR
       (OLD.state='approved' AND NEW.state IN ('consumed','revoked')))
BEGIN SELECT RAISE(ABORT, 'invalid approval transition'); END;
PRAGMA user_version=1;
COMMIT;
"""


class Denied(ValueError):
    """Known negative decision; never an execution grant."""


class Unavailable(RuntimeError):
    """Untrusted clock/storage or ambiguous outcome; abort without retry."""


def _identifier(value):
    return type(value) is str and re.fullmatch(r"[A-Za-z0-9_-]{16,64}", value) is not None


class Authority:
    """Trusted-owner-only test API. There is deliberately no default wall clock.

    Each operation opens an independent connection to the same existing database.
    Storage contention fails immediately; there are no automatic retries/refunds.
    """

    @staticmethod
    def initialize(path):
        """Explicit fresh test storage only; never reset an existing database."""
        path = Path(path)
        with path.open("xb"):
            pass
        # A failed initialization leaves an unusable file, never a fresh retry.
        with closing(sqlite3.connect(path, isolation_level=None)) as connection:
            connection.execute("PRAGMA journal_mode=DELETE")
            connection.execute("PRAGMA synchronous=EXTRA")
            connection.executescript(SCHEMA)

    def __init__(self, path, *, clock):
        self.path = Path(path).absolute()
        self.clock = clock

    def _connect(self):
        # mode=rw prevents a missing database from silently restoring authority.
        connection = sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True,
                                     timeout=0, isolation_level=None)
        try:
            if (connection.execute("PRAGMA user_version").fetchone()[0] != 1 or
                    connection.execute("PRAGMA journal_mode").fetchone()[0] != "delete"):
                raise Unavailable("unrecognized authority storage")
            connection.execute("PRAGMA synchronous=EXTRA")
            connection.row_factory = sqlite3.Row
            return connection
        except BaseException:
            connection.close()
            raise

    def _time(self, connection):
        try:
            now = self.clock()
        except Exception:
            raise Unavailable("authority clock unavailable") from None
        if type(now) is not int or not 0 < now < 2**53:
            raise Unavailable("authority clock invalid")
        floor = connection.execute("SELECT epoch FROM clock_floor WHERE singleton=1").fetchone()
        if floor is None or now < floor[0]:
            raise Unavailable("authority clock rollback")
        connection.execute("UPDATE clock_floor SET epoch=? WHERE singleton=1", (now,))
        return now

    def _run(self, action, approval_id, operation):
        try:
            with closing(self._connect()) as connection:
                try:
                    connection.execute("BEGIN IMMEDIATE")
                    now = self._time(connection)  # After lock acquisition, never queued client time.
                    denial = None
                    try:
                        result = operation(connection, now)
                    except (ValueError, TypeError, KeyError, sqlite3.IntegrityError):
                        # Operation validation occurs before changes, except guarded SQL CAS.
                        denial = Denied("authority request denied")
                    connection.execute("INSERT INTO audit(at, action, approval_id, outcome, reason) "
                        "VALUES (?, ?, ?, ?, ?)", (now, action,
                        approval_id if _identifier(approval_id) else None,
                        "denied" if denial else "ok", "validation-or-conflict" if denial else "transition"))
                    connection.execute("COMMIT")  # No result may escape before durable commit.
                except BaseException:
                    if connection.in_transaction:
                        connection.execute("ROLLBACK")
                    raise
            if denial:
                raise denial
            return result
        except sqlite3.Error:
            raise Unavailable("authority storage unavailable; outcome may be unknown") from None

    @staticmethod
    def _load(connection, approval_id, expected_revision):
        if (not _identifier(approval_id) or type(expected_revision) is not int or
                not 0 < expected_revision < 2**53-1):
            raise Denied("invalid identifier/revision")
        row = connection.execute("SELECT * FROM approvals WHERE approval_id=?", (approval_id,)).fetchone()
        if row is None or row["revision"] != expected_revision:
            raise Denied("missing approval/stale revision")
        return dict(json.loads(row["template"]), state=row["state"],
                    revision=row["revision"], consumed_at=row["consumed_at"])

    @staticmethod
    def _cas(connection, record, state, consumed_at=None):
        changed = connection.execute("UPDATE approvals SET state=?, revision=revision+1, consumed_at=? "
            "WHERE approval_id=? AND revision=? AND state=?", (state, consumed_at,
            record["approval_id"], record["revision"], record["state"])).rowcount
        if changed != 1:
            raise Denied("conditional transition conflict")

    def create_draft(self, record, claim, source_files):
        """Reserve the fixed scope forever; supplied observations are NOT authenticated.

        Reuse the exact model schema with draft/revision 1. Validation at not_before
        checks template shape, not permission to execute or a future-clock reading.
        """
        identifier = record.get("approval_id") if type(record) is dict else None
        def operation(connection, now):
            if type(record) is not dict or record.get("state") != "draft" or type(record.get("revision")) is not int or record["revision"] != 1:
                raise Denied("draft revision required")
            checked = dict(record, state="approved")
            consume_approval(checked, claim, record.get("not_before"), source_files)
            if now >= record["expires_at"]:
                raise Denied("expired draft")
            template = {key: value for key, value in record.items()
                        if key not in ("state", "revision", "consumed_at")}
            connection.execute("INSERT INTO approvals VALUES (?, ?, ?, ?, ?, 'draft', 1, NULL)",
                (identifier, record["repository_id"], record["run_id"], SCOPE,
                 json.dumps(template, sort_keys=True, separators=(",", ":"))))
        return self._run("create", identifier, operation)

    def approve(self, approval_id, expected_revision):
        def operation(connection, now):
            record = self._load(connection, approval_id, expected_revision)
            if record["state"] != "draft" or not record["not_before"] <= now < record["expires_at"]:
                raise Denied("draft not approvable")
            self._cas(connection, record, "approved")
        return self._run("approve", approval_id, operation)

    def revoke(self, approval_id, expected_revision):
        def operation(connection, now):
            record = self._load(connection, approval_id, expected_revision)
            if record["state"] not in ("draft", "approved"):
                raise Denied("terminal approval")
            self._cas(connection, record, "revoked")
        return self._run("revoke", approval_id, operation)

    def consume(self, approval_id, expected_revision, claim, source_files):
        """Commit one synthetic receipt; caller must never use it to run authentication."""
        def operation(connection, now):
            record = self._load(connection, approval_id, expected_revision)
            consume_approval(record, claim, now, source_files)
            boundary = self._time(connection)  # Expiry may pass during byte/claim validation.
            if not record["not_before"] <= boundary < record["expires_at"]:
                raise Denied("expired before conditional update")
            self._cas(connection, record, "consumed", boundary)
            receipt = dict(approval_id=approval_id, revision=expected_revision+1,
                state="consumed", consumed_at=boundary, run_id=record["run_id"], source_sha=record["source_sha"])
            return receipt, record["expires_at"]
        receipt, expires_at = self._run("consume", approval_id, operation)
        # A slow commit must burn, rather than release, an expired authorization.
        try:
            delivered_at = self.clock()
        except Exception:
            raise Unavailable("clock unavailable after commit; approval remains consumed") from None
        if type(delivered_at) is not int or not receipt["consumed_at"] <= delivered_at < expires_at:
            raise Unavailable("expired/untrusted delivery time; approval remains consumed")
        return receipt
