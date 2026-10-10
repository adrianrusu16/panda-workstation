"""Versioned Ghostty simulation enrollment; no real-HOME enrollment API."""

from dataclasses import dataclass
import hashlib
import json
import os
from types import MappingProxyType

PATHS = {
    "source": "source/home/dot_config/ghostty/config.ghostty",
    "hook": "config/ghostty/config.ghostty",
    "target": "config/panda/generated/ghostty.conf",
}
PURPOSE = "panda-theme-b1-ghostty-simulation"
VERSION = "1.3.1"  # Installed documentation reviewed for Stage A / B1.
IDENTITY_KEYS = {"device", "inode", "uid", "gid", "mode"}
FINGERPRINT_KEYS = IDENTITY_KEYS | {"nlink", "size", "mtime_ns", "sha256"}


def digest(content):
    return hashlib.sha256(content).hexdigest()


def encode_record(value):
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate record key")
        result[key] = value
    return result


def decode_record(content):
    if not isinstance(content, bytes) or len(content) > 65536:
        raise ValueError("record exceeds bounded metadata limit")
    try:
        return json.loads(content, object_pairs_hook=_unique)
    except (ValueError, RecursionError) as error:
        raise ValueError("invalid simulation metadata") from error


def _identity(values, *, root=False):
    if (not isinstance(values, dict) or set(values) != IDENTITY_KEYS or
            any(type(v) is not int or v < 0 or v > 2**63-1 for v in values.values()) or
            values["uid"] != os.getuid() or values["mode"] > 0o777 or
            (root and values["mode"] != 0o700)):
        raise ValueError("unsupported enrollment identity")


def _fingerprint(values):
    if not isinstance(values, dict) or set(values) != FINGERPRINT_KEYS:
        raise ValueError("incomplete enrollment fingerprint")
    _identity({key: values[key] for key in IDENTITY_KEYS})
    if (any(type(values[k]) is not int or not 0 <= values[k] <= 2**63-1
            for k in ("nlink", "size", "mtime_ns")) or values["nlink"] != 1 or
            values["size"] > 65536 or values["mode"] & 0o600 != 0o600 or
            values["mode"] & 0o022 or not isinstance(values["sha256"], str) or
            len(values["sha256"]) != 64 or
            any(c not in "0123456789abcdef" for c in values["sha256"])):
        raise ValueError("unsupported enrollment fingerprint")


@dataclass(frozen=True)
class Enrollment:
    component: str
    application_version: str
    critical: bool
    root_identity: object
    paths: object
    fingerprints: object

    @classmethod
    def from_dict(cls, data):
        expected = {"schema_version", "purpose", "component", "application_version", "critical",
                    "root_identity", "paths", "fingerprints"}
        if (not isinstance(data, dict) or set(data) != expected or
                type(data["schema_version"]) is not int or data["schema_version"] != 1 or
                data["purpose"] != PURPOSE or data["component"] != "ghostty" or
                data["application_version"] != VERSION or data["critical"] is not True or
                data["paths"] != PATHS or not isinstance(data["fingerprints"], dict) or
                set(data["fingerprints"]) != {"source", "hook"}):
            raise ValueError("unsupported or ambiguous Ghostty simulation enrollment")
        _identity(data["root_identity"], root=True)
        for values in data["fingerprints"].values():
            _fingerprint(values)
        if data["fingerprints"]["source"]["sha256"] != data["fingerprints"]["hook"]["sha256"]:
            raise ValueError("chezmoi source and deployed baseline differ")
        return cls("ghostty", VERSION, True, MappingProxyType(dict(data["root_identity"])),
                   MappingProxyType(dict(PATHS)), MappingProxyType({
                       key: MappingProxyType(dict(value)) for key, value in data["fingerprints"].items()}))

    def to_dict(self):
        return {"schema_version": 1, "purpose": PURPOSE, "component": self.component,
                "application_version": self.application_version, "critical": self.critical,
                "root_identity": dict(self.root_identity), "paths": dict(self.paths),
                "fingerprints": {k: dict(v) for k, v in self.fingerprints.items()}}


def enroll_fixture(root, *, version):
    """Enroll only an existing private B1 fixture after every input validates."""
    from adapters.live_ghostty import model_hook
    from live_fs import _TreeIO, MARKER
    if version != VERSION:
        raise ValueError("Ghostty simulation supports only the reviewed 1.3.1 contract")
    with _TreeIO(root) as fs:
        fingerprints = {key: fs.fingerprint(PATHS[key]) for key in ("source", "hook")}
        model_hook(fs.read(PATHS["hook"]).content)
        record = Enrollment.from_dict({
            "schema_version": 1, "purpose": PURPOSE, "component": "ghostty",
            "application_version": version, "critical": True, "root_identity": fs.root_identity(),
            "paths": PATHS, "fingerprints": fingerprints,
        })
        existing = fs.read(MARKER)
        if existing is not None:
            if existing.mode != 0o600 or Enrollment.from_dict(decode_record(existing.content)) != record:
                raise ValueError("existing enrollment differs; refusing replacement")
            return record
        fs.write_enrollment(record)
        return record
