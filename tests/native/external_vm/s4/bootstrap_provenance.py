"""Bounded, data-only provenance consistency review. All crypto/execution gates are sealed."""
import json
import lzma
from email.utils import parsedate_to_datetime
from pathlib import Path, PurePosixPath
import re
import sys

from common import LOCK_SHA256, MIB, read_bounded, read_json, require, sha256

PINS_SHA256 = "f4e04473903387cd3df0684688c49509ef435aaacc32943b2f18cf1fcb54fa42"
MAX_MANIFEST = 512 * 1024
MAX_ARTIFACT = 32 * MIB
MAX_TOTAL = 96 * MIB
MAX_ROWS = 512
MAX_AGE = 86400
MAX_INDEX_EXPANSION = 128 * MIB
MAX_PACKAGE_RECORDS = 100000
GAPS = (
    "ubuntu_archive_anchor_independent_verifier_unavailable",
    "ubuntu_inrelease_signature_unverified",
    "ubuntu_package_provenance_unverified",
    "tool_package_membership_unverified",
    "elf_runtime_closure_unverified",
    "arch_release_signature_unverified",
    "arch_certifications_and_bindings_unverified",
    "arch_lifecycle_review_unverified",
    "execution_remains_sealed",
)


def fields(value, names, label):
    require(type(value) is dict and set(value) == set(names.split()), label + " fields")


def integer(value, minimum=0):
    return type(value) is int and minimum <= value < 2**63


def text(value, limit=2048):
    return type(value) is str and 0 < len(value) <= limit and "\x00" not in value


def relative(value):
    return text(value) and not value.startswith("/") and all(p not in ("", ".", "..") for p in value.split("/"))


def rows(value, label):
    require(type(value) is list and 0 < len(value) <= MAX_ROWS, label + " list budget")
    return value


def unique(values, label):
    require(len(set(values)) == len(values), "duplicate " + label)


def load_pins():
    """Source-controlled observations, not a verifier or executable trust policy."""
    raw = read_bounded(Path(__file__).with_name("bootstrap-provenance.pins.json"), MAX_MANIFEST)
    require(sha256(raw) == PINS_SHA256, "pinned reference hash changed")
    pins = read_json(raw)
    fields(pins, "schema_version lock_sha256 ubuntu_snapshot ubuntu_anchor ubuntu_anchor_source indexes tools arch", "reference")
    require(type(pins["schema_version"]) is int and pins["schema_version"] == 1 and
            pins["lock_sha256"] == LOCK_SHA256, "reference identity")
    require(set(pins["tools"]) == {"gpgv", "zstd", "vercmp"}, "reference tool identity")
    return pins


def release_hashes(raw, now):
    require(len(raw) <= 2 * MIB, "InRelease size budget")
    value = raw.decode("utf-8")
    start, end = "-----BEGIN PGP SIGNATURE-----", "-----END PGP SIGNATURE-----"
    require(value.startswith("-----BEGIN PGP SIGNED MESSAGE-----\n") and value.count(start) == 1 and
            value.count(end) == 1 and value.rstrip().endswith(end), "InRelease signature envelope missing")
    body, signature = value.split(start)
    require(signature.split(end)[0].strip(), "InRelease signature missing")
    for field, required in (("Date", True), ("Valid-Until", False)):
        values = [line[len(field) + 2:] for line in body.splitlines() if line.startswith(field + ": ")]
        require(len(values) == 1 if required else len(values) <= 1, "InRelease timestamp fields")
        if values:
            try:
                date = parsedate_to_datetime(values[0])
                require(date.utcoffset() is not None, "InRelease timestamp timezone")
                epoch = int(date.timestamp())
            except (ValueError, TypeError, OverflowError):
                raise ValueError("InRelease timestamp malformed") from None
            require((0 < epoch <= now) if field == "Date" else epoch > now, "InRelease timestamp conflict/stale")
    result, active = {}, False
    for line in body.splitlines():
        if line == "SHA256:":
            require(not active and not result, "ambiguous InRelease hash table")
            active = True
        elif active and line.startswith(" "):
            parts = line.split()
            require(len(parts) == 3, "InRelease hash row")
            digest, size, path = parts
            require(re.fullmatch(r"[0-9a-f]{64}", digest) and size.isdecimal() and len(size) <= 12 and
                    relative(path) and path not in result, "InRelease hash identity")
            result[path] = (digest, int(size))
        elif active:
            active = False
    require(result, "InRelease hash table missing")
    # The envelope and hash table are parsed data, never a signature-validity result.
    return result


def package_records(raw):
    require(type(raw) is bytes and len(raw) <= MAX_ARTIFACT, "package index input budget")
    data, remaining, streams = bytearray(), raw, 0
    while remaining:
        streams += 1
        require(streams <= 16 and remaining.startswith(b"\xfd7zXZ\x00"), "package index stream identity/budget")
        decoder = lzma.LZMADecompressor(memlimit=64 * MIB)
        chunk = decoder.decompress(remaining, max_length=MAX_INDEX_EXPANSION - len(data) + 1)
        data.extend(chunk)
        require(len(data) <= MAX_INDEX_EXPANSION, "aggregate index expansion budget")
        require(decoder.eof, "truncated package index stream")
        remaining = decoder.unused_data
        padding = len(remaining) - len(remaining.lstrip(b"\0"))
        require(padding % 4 == 0, "package index stream padding")
        remaining = remaining[padding:]
    require(streams, "empty package index stream")
    result = {}
    canonical = {key.lower(): key for key in ("Package", "Version", "Architecture", "Filename", "SHA256", "Size", "Depends")}
    for paragraph in data.decode("utf-8").split("\n\n"):
        if not paragraph.strip("\n"):
            continue
        require(not re.search(r"[\x00-\x08\x0b-\x1f\x7f-\x9f\u2028\u2029]", paragraph),
                "unsupported package index control or line separator")
        values, current = {}, None
        for line in paragraph.rstrip("\n").split("\n"):
            if line.startswith((" ", "\t")):
                require(current is not None and current not in canonical.values() and line.strip(" \t"),
                        "unsupported package index continuation")
                values[current].append(line)
                continue
            key, separator, value = line.partition(":")
            require(separator and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*", key), "malformed package index field")
            key = canonical.get(key.lower(), key.lower())
            require(key not in values, "duplicate package index field")
            values[key] = [value.lstrip(" \t")]
            current = key
        # Join once per field: optional contents retain line breaks and indentation
        # within the existing aggregate index expansion and record budgets.
        values = {key: "\n".join(parts) for key, parts in values.items()}
        needed = {"Package", "Version", "Architecture", "Filename", "SHA256", "Size"}
        require(needed <= set(values) and all(values[key] for key in needed), "package index identity missing")
        identity = (values["Package"], values["Version"], values["Architecture"])
        require(identity not in result, "duplicate package index identity")
        require(re.fullmatch(r"[0-9a-f]{64}", values["SHA256"]) and values["Size"].isdecimal() and
                len(values["Size"]) <= 12 and relative(values["Filename"]) and values["Filename"].startswith("pool/"),
                "package index hash/size/source identity")
        require(len(result) < MAX_PACKAGE_RECORDS, "package index record budget")
        result[identity] = values
    require(result, "empty package index")
    return result


def validate(manifest, blobs, pins, now):
    fields(manifest, "schema_version lock_sha256 observed_at artifacts ubuntu arch", "manifest")
    require(type(manifest["schema_version"]) is int and manifest["schema_version"] == 1 and
            manifest["lock_sha256"] == pins["lock_sha256"] == LOCK_SHA256, "lock identity")
    observed = manifest["observed_at"]
    require(integer(now, 1) and integer(observed, 1) and observed <= now, "review timestamp conflict")
    require(now - observed <= MAX_AGE, "stale evidence observation")
    require(type(blobs) is dict and len(blobs) <= MAX_ROWS, "artifact mapping budget")
    require(all(type(v) is bytes and len(v) <= MAX_ARTIFACT for v in blobs.values()), "artifact byte budget")
    require(sum(map(len, blobs.values())) <= MAX_TOTAL, "total artifact budget")
    descriptions = {}
    for row in rows(manifest["artifacts"], "artifact"):
        fields(row, "id source sha256 bytes", "artifact")
        name = row["id"]
        require(text(name, 64) and re.fullmatch(r"[a-z0-9][a-z0-9_.-]*", name), "artifact identity")
        require(name not in descriptions, "duplicate artifact identity")
        require(name in blobs and text(row["source"]) and integer(row["bytes"]) and
                row["bytes"] == len(blobs[name]) and row["sha256"] == sha256(blobs[name]), "artifact hash/size identity")
        descriptions[name] = row
    require(set(descriptions) == set(blobs), "extra or missing artifact bytes")
    used = set()

    def artifact(name, source=None, digest=None, size=None):
        require(type(name) is str and name in descriptions, "artifact missing")
        row = descriptions[name]
        require((source is None or row["source"] == source) and (digest is None or row["sha256"] == digest) and
                (size is None or row["bytes"] == size), "artifact pinned source/hash/size identity")
        used.add(name)
        return blobs[name]

    ubuntu = manifest["ubuntu"]
    fields(ubuntu, "anchor anchor_source indexes packages files tools", "ubuntu")
    require(ubuntu["anchor"] == pins["ubuntu_anchor"] and ubuntu["anchor_source"] == pins["ubuntu_anchor_source"],
            "Ubuntu anchor identity")
    indexes = {}
    for row in rows(ubuntu["indexes"], "index"):
        fields(row, "id release index", "index")
        identity = row["id"]
        require(identity in pins["indexes"] and identity not in indexes, "duplicate or unknown index identity")
        pin = pins["indexes"][identity]
        release = artifact(row["release"], pin["release_url"], pin["release_sha256"], pin["release_bytes"])
        index = artifact(row["index"], pin["index_url"], pin["index_sha256"], pin["index_bytes"])
        require(release_hashes(release, now).get(pin["index_path"]) == (sha256(index), len(index)), "InRelease index binding")
        indexes[identity] = package_records(index)
    require(set(indexes) == set(pins["indexes"]), "missing pinned index identity")
    packages = {}
    for row in rows(ubuntu["packages"], "package"):
        fields(row, "name version index artifact", "package")
        require(text(row["name"], 128) and text(row["version"], 128) and row["index"] in indexes, "package identity")
        require(row["name"] not in packages, "duplicate package identity")
        candidates = [v for (name, version, architecture), v in indexes[row["index"]].items()
                      if name == row["name"] and version == row["version"] and architecture in ("amd64", "all")]
        require(len(candidates) == 1, "ambiguous or missing package index identity")
        record = candidates[0]
        package = artifact(row["artifact"], pins["ubuntu_snapshot"] + "/" + record["Filename"])
        require(sha256(package) == record["SHA256"] and len(package) == int(record["Size"]), "package binding mismatch")
        packages[row["name"]] = (row, record)
    for name, pin in pins["tools"].items():
        require(pin["package"] in packages, "tool package identity missing")
        row, record = packages[pin["package"]]
        require(row["version"] == pin["version"] and row["index"] == pin["index"] and
                record["Filename"] == pin["filename"] and record["SHA256"] == pin["package_sha256"] and
                int(record["Size"]) == pin["package_bytes"], "pinned tool package identity")

    files = {}
    for row in rows(ubuntu["files"], "runtime"):
        fields(row, "id path package role artifact interpreter needed", "runtime")
        require(text(row["id"], 64) and row["id"] not in files, "duplicate runtime identity")
        path = row["path"]
        require(text(path) and path.startswith("/") and str(PurePosixPath(path)) == path and
                ".." not in PurePosixPath(path).parts and row["role"] in ("tool", "interpreter", "library") and
                row["package"] in packages, "runtime path/role/package provenance")
        require(type(row["needed"]) is list and len(row["needed"]) <= 64 and
                all(text(v, 64) for v in row["needed"]), "runtime dependency budget")
        unique(row["needed"], "runtime dependency")
        record = packages[row["package"]][1]
        raw = artifact(row["artifact"], pins["ubuntu_snapshot"] + "/" + record["Filename"] + "#" + path)
        require(raw, "runtime empty binary receipt")
        files[row["id"]] = row
    unique([r["path"] for r in files.values()], "runtime path")
    require(type(ubuntu["tools"]) is dict and set(ubuntu["tools"]) == set(pins["tools"]), "runtime tool identity")
    for tool, identity in ubuntu["tools"].items():
        require(identity in files and files[identity]["role"] == "tool" and
                files[identity]["path"] == pins["tools"][tool]["path"] and
                files[identity]["package"] == pins["tools"][tool]["package"], "runtime tool provenance")
    for row in files.values():
        require(all(v in files and files[v]["role"] in ("library", "interpreter") for v in row["needed"]),
                "runtime dependency provenance missing")
        loader = row["interpreter"]
        require((loader is None and row["role"] != "tool") or
                (type(loader) is str and loader in files and files[loader]["role"] == "interpreter"),
                "runtime ELF interpreter provenance missing")
    reachable, pending = set(), list(ubuntu["tools"].values())
    while pending:
        identity = pending.pop()
        if identity in reachable:
            continue
        reachable.add(identity)
        row = files[identity]
        pending.extend(row["needed"])
        if row["interpreter"] is not None:
            pending.append(row["interpreter"])
    require(reachable == set(files), "unreachable runtime provenance")
    # This checks a declared graph only. No ELF reader or package-membership verifier exists here.

    arch, pin = manifest["arch"], pins["arch"]
    fields(arch, "source_url master_source tag commit tag_artifact masters signers", "arch")
    require(all(arch[key] == pin[key] for key in ("source_url", "master_source", "tag", "commit")), "Arch source identity")
    source = pin["source_url"].removesuffix(".git")
    artifact(arch["tag_artifact"], source + "/-/tags/" + pin["tag"], pin["tag_sha256"], pin["tag_bytes"])
    prefix = source + "/-/raw/" + pin["commit"] + "/keyring/"
    masters = set()
    for row in rows(arch["masters"], "master"):
        fields(row, "fingerprint artifact", "master")
        fingerprint = row["fingerprint"]
        require(fingerprint in pin["masters"] and fingerprint not in masters, "duplicate or unknown master identity")
        expected = pin["masters"][fingerprint]
        artifact(row["artifact"], source + "/-/raw/" + pin["commit"] + "/" + expected["path"],
                 expected["sha256"], expected["bytes"])
        masters.add(fingerprint)
    require(masters == set(pin["masters"]), "missing master identity")

    def key_artifact(name, label):
        require(artifact(name), "empty key evidence")
        location = descriptions[name]["source"]
        require(location.startswith(prefix + "packager/") and relative(location[len(prefix):]) and
                not any(c in location[len(prefix):] for c in "?#%"), label + " source identity")

    identities = set()
    expected_signers = {(r["primary"], r["signing"]): r for r in pin["signers"]}
    for signer in rows(arch["signers"], "signer"):
        fields(signer, "primary signing primary_created signing_created primary_expires signing_expires first_signature last_signature revoked certifications binding lifecycle", "signer")
        identity = (signer["primary"], signer["signing"])
        require(identity not in identities, "duplicate signer identity")
        require(identity in expected_signers, "unknown signer identity")
        identities.add(identity)
        expected = expected_signers[identity]
        require(all(integer(signer[k], 1) for k in ("primary_created", "signing_created", "first_signature", "last_signature")) and
                signer["primary_created"] <= signer["signing_created"] <= signer["first_signature"] <= signer["last_signature"] <= observed and
                all(signer[k] == expected[k] for k in ("first_signature", "last_signature")) and signer["revoked"] is False,
                "signer time/revocation conflict")
        for name in ("primary_expires", "signing_expires"):
            expiry = signer[name]
            require(integer(expiry) and (expiry == 0 or expiry > now), "expired signer identity")
        lifecycle = signer["lifecycle"]
        fields(lifecycle, "status observed_at revocation_checked_at source", "lifecycle")
        require(lifecycle["status"] == "active" and lifecycle["source"] == pin["source_url"] and
                all(integer(lifecycle[k], 1) and signer["last_signature"] <= lifecycle[k] <= observed and
                    now - lifecycle[k] <= MAX_AGE for k in ("observed_at", "revocation_checked_at")) and
                lifecycle["revocation_checked_at"] <= lifecycle["observed_at"],
                "lifecycle incomplete/stale/conflicting")
        groups, seen = {}, set()
        for cert in rows(signer["certifications"], "certification"):
            fields(cert, "master subject uid artifact created expires revoked", "certification")
            cert_id = (cert["master"], cert["subject"], cert["uid"])
            require(cert_id not in seen, "duplicate certification identity")
            seen.add(cert_id)
            require(cert["master"] in masters and cert["subject"] == signer["primary"] and text(cert["uid"], 1024) and
                    integer(cert["created"], 1) and signer["primary_created"] <= cert["created"] <= signer["first_signature"] and
                    integer(cert["expires"]) and (cert["expires"] == 0 or cert["expires"] > now) and cert["revoked"] is False,
                    "certification identity/time/revocation conflict")
            key_artifact(cert["artifact"], "certification")
            groups.setdefault(cert["uid"], set()).add(cert["master"])
        require(any(len(group) >= 3 for group in groups.values()), "certification threshold incomplete")
        binding = signer["binding"]
        if signer["primary"] == signer["signing"]:
            require(binding is None, "unexpected primary-key binding")
        else:
            fields(binding, "primary signing artifact created expires revoked", "binding")
            require(binding["primary"] == signer["primary"] and binding["signing"] == signer["signing"] and
                    integer(binding["created"], 1) and signer["signing_created"] <= binding["created"] <= signer["first_signature"] and
                    integer(binding["expires"]) and (binding["expires"] == 0 or binding["expires"] > now) and binding["revoked"] is False,
                    "binding identity/time/revocation conflict")
            key_artifact(binding["artifact"], "binding")
    require(identities == set(expected_signers), "missing pinned signer identity")
    require(used == set(descriptions), "unused artifact evidence")
    return dict(artifacts=len(used), indexes=len(indexes), packages=len(packages), runtime_files=len(files), signers=len(identities))


def empty_result():
    return dict(schema_version=1, status="rejected", accepted=False, execution_authorized=False,
                  trust_policy_activation_allowed=False, real_certificate_set_validated=False,
                  cryptographic_verification="not_performed", consistency_checked=False,
                  errors=[], gaps=list(GAPS), counts={}, input_sha256=None, assessment_epoch=None)


def review(manifest_bytes, artifacts, *, now_epoch):
    """No verifier callback or proof flags exist. Consistency never activates S4 policy."""
    result = empty_result()
    try:
        require(type(manifest_bytes) is bytes and len(manifest_bytes) <= MAX_MANIFEST, "manifest byte budget")
        require(integer(now_epoch, 1), "review timestamp conflict")
        result["assessment_epoch"] = now_epoch
        result["input_sha256"] = sha256(manifest_bytes)
        manifest = read_json(manifest_bytes)
        result["counts"] = validate(manifest, artifacts, load_pins(), now_epoch)
        result.update(status="blocked", consistency_checked=True,
                      errors=["unauthenticated provenance; independently trusted verification is not implemented"])
    except json.JSONDecodeError:
        result["errors"] = ["invalid JSON input"]
    except ValueError as error:
        result["errors"] = [str(error)[:256]]
    except (KeyError, TypeError, UnicodeError, OSError, RecursionError, lzma.LZMAError):
        result["errors"] = ["malformed or unavailable bootstrap evidence"]
    return result


def encode_result(result):
    raw = (json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    require(len(raw) <= 65536, "review result budget")
    return raw


def main():
    result = empty_result()
    result["errors"] = ["bootstrap checker CLI remains sealed; use the non-authorizing in-memory review API"]
    sys.stdout.buffer.write(encode_result(result))
    return 78


if __name__ == "__main__":
    sys.exit(main())
