"""Pure proposal for a trusted owner's atomic transaction; disconnected from the runner.

This function neither authenticates callers nor persists/consumes real approvals.
A returned record has no execution authority. See the readiness guide for the
external CAS, identity, trusted-time and source-observation requirements.
"""
import re

from common import MIB, require, sha256

WORKFLOW = ".github/workflows/panda-ubuntu-bootstrap-verification.yml"
SOURCE_FILES = frozenset({WORKFLOW, "tests/native/external_vm/packages.lock.json"} |
    {"tests/native/external_vm/s4/"+name for name in (
        "ubuntu_authorization.py", "ubuntu_bootstrap_runner.py", "ubuntu_verification.py",
        "ubuntu_artifacts.py", "ubuntu_packets.py", "common.py", "bootstrap_provenance.py",
        "ubuntu-verification.pins.json", "bootstrap-provenance.pins.json", "trust-policy.json")})
RECORD_FIELDS = frozenset(("schema_version approval_id revision state source_sha repository_id operator_id "
                          "run_id not_before expires_at review_reference source_hashes consumed_at").split())
CLAIM_FIELDS = frozenset(("repository repository_id source_sha reviewed_source_sha checkout_sha workflow_sha "
                         "main_sha ref event_name workflow_path run_id run_attempt actor_id triggering_actor_id").split())


def consume_approval(record, claim, now, source_files):
    """Validate a proposal; the owner must CAS the original revision/state before use.

    All arguments must come from independently verified owner-side observations,
    never a dispatch input, local ledger or unverified client assertion.
    """
    require(type(record) is dict and set(record) == RECORD_FIELDS, "approval record fields")
    require(type(claim) is dict and set(claim) == CLAIM_FIELDS and
            all(type(value) is str and 0 < len(value) <= 256 for value in claim.values()), "verified claim fields")
    require(type(record["schema_version"]) is int and record["schema_version"] == 1 and
            type(record["revision"]) is int and 0 < record["revision"] < 2**53-1 and
            record["state"] == "approved" and record["consumed_at"] is None, "approval state/version")
    require(type(record["approval_id"]) is str and re.fullmatch(r"[A-Za-z0-9_-]{16,64}", record["approval_id"]),
            "approval identifier")
    for key in ("repository_id", "operator_id", "run_id"):
        require(type(record[key]) is str and re.fullmatch(r"[1-9][0-9]{0,19}", record[key]), "approval identity")
    require(type(record["source_sha"]) is str and re.fullmatch(r"[0-9a-f]{40}", record["source_sha"]), "approval source SHA")
    require(type(record["review_reference"]) is str and 0 < len(record["review_reference"]) <= 256 and
            not re.search(r"[\x00-\x1f\x7f]", record["review_reference"]), "approval review reference")
    require(all(type(value) is int and 0 < value < 2**53 for value in
                (record["not_before"], record["expires_at"], now)) and
            record["not_before"] <= now < record["expires_at"], "approval validity window")
    require(claim["repository"] == "adrianrusu16/panda-workstation" and
            claim["repository_id"] == record["repository_id"] and claim["run_id"] == record["run_id"] and
            claim["actor_id"] == claim["triggering_actor_id"] == record["operator_id"] and
            claim["run_attempt"] == "1" and claim["ref"] == "refs/heads/main" and
            claim["event_name"] == "workflow_dispatch" and claim["workflow_path"] == WORKFLOW,
            "approval execution identity")
    require(all(claim[key] == record["source_sha"] for key in
                ("source_sha", "reviewed_source_sha", "checkout_sha", "workflow_sha", "main_sha")),
            "approval immutable source identity")
    hashes = record["source_hashes"]
    require(type(hashes) is dict and set(hashes) == SOURCE_FILES and
            all(type(digest) is str and re.fullmatch(r"[0-9a-f]{64}", digest) for digest in hashes.values()),
            "approved source manifest")
    require(type(source_files) is dict and set(source_files) == SOURCE_FILES and
            all(type(raw) is bytes and 0 < len(raw) <= 128*1024 for raw in source_files.values()) and
            sum(map(len, source_files.values())) <= 2*MIB, "observed source file set/budget")
    require(all(sha256(source_files[name]) == hashes[name] for name in SOURCE_FILES), "reviewed source bytes changed")
    return dict(record, source_hashes=dict(hashes), state="consumed",
                revision=record["revision"]+1, consumed_at=now)
