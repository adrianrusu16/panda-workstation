"""Proposed offline authentication. CLI sealed; no default trust or network path."""
import base64
import importlib.util
from pathlib import Path
import re
import tarfile

from common import FdPath, LOCK_SHA256, MIB, private_copy, read_bounded, read_json, require, run_tool, sha256


def check_policy(policy):
    require(policy.get("status") == "reviewed", "explicitly reviewed trust root required")
    require(set(policy) == {"schema_version", "status", "lock_sha256", "review_reference",
                           "reviewed_at_epoch", "keyring_sha256", "signers", "tools"}, "trust fields drift")
    require(type(policy["schema_version"]) is int and policy["schema_version"] == 1 and
            policy["lock_sha256"] == LOCK_SHA256, "trust/lock mismatch")
    require(isinstance(policy["review_reference"], str) and 1 <= len(policy["review_reference"]) <= 1024,
            "review record required")
    require(type(policy["reviewed_at_epoch"]) is int and policy["reviewed_at_epoch"] > 0, "review time required")
    require(isinstance(policy["keyring_sha256"], str) and
            re.fullmatch(r"[0-9a-f]{64}", policy["keyring_sha256"]), "reviewed public keyring hash required")
    require(set(policy["tools"]) == {"gpgv", "zstd", "vercmp"}, "reviewed tool receipts required")
    for tool in policy["tools"].values():
        require(set(tool) == {"sha256"} and re.fullmatch(r"[0-9a-f]{64}", tool["sha256"]), "tool hash required")
    require(isinstance(policy["signers"], list) and 0 < len(policy["signers"]) <= 128, "reviewed signer list required")
    identities = set()
    for signer in policy["signers"]:
        require(set(signer) == {"primary_fingerprint", "signing_fingerprint", "valid_from", "valid_until",
                               "lifecycle_review"}, "explicit signer lifecycle fields required")
        for key in ("primary_fingerprint", "signing_fingerprint"):
            require(re.fullmatch(r"[0-9A-F]{40}|[0-9A-F]{64}", signer[key]), "full signer fingerprint required")
        identity = (signer["primary_fingerprint"], signer["signing_fingerprint"])
        require(identity not in identities, "duplicate signer")
        identities.add(identity)
        require(type(signer["valid_from"]) is int and type(signer["valid_until"]) is int and
                0 < signer["valid_from"] < signer["valid_until"] <= policy["reviewed_at_epoch"],
                "reviewed historical key acceptance window required")
        require(signer["lifecycle_review"] == "accepted-no-known-revocation", "key lifecycle review required")
    return policy


def signature_status(text, signers, reviewed_at_epoch):
    require(len(text) <= 65536, "signature status budget")
    records = []
    rejected = {"BADSIG", "ERRSIG", "EXPKEYSIG", "EXPSIG", "REVKEYSIG", "NO_PUBKEY",
                "FAILURE", "ERROR", "NODATA", "BADARMOR", "KEYEXPIRED", "SIGEXPIRED", "KEYREVOKED"}
    for line in text.splitlines():
        require(line.startswith("[GNUPG:] "), "unexpected gpgv output")
        fields = line[len("[GNUPG:] "):].split()
        require(fields and fields[0] not in rejected, "signature rejected")
        if fields[0] == "VALIDSIG":
            require(len(fields) == 11, "complete VALIDSIG identity required")
            # GnuPG DETAILS: fingerprint, date, timestamp, expiry, version,
            # reserved, public-key algorithm, hash algorithm, class, primary fpr.
            _, signing, _, timestamp, expiry, version, _, algorithm, digest, kind, primary = fields
            require(version in ("4", "5", "6") and algorithm in ("1", "19", "22", "27") and
                    digest in ("8", "9", "10") and kind == "00", "signature algorithm/class rejected")
            require(timestamp.isdecimal() and expiry.isdecimal(), "signature time unavailable")
            epoch, expires = int(timestamp), int(expiry)
            accepted = [s for s in signers if s["primary_fingerprint"] == primary and
                        s["signing_fingerprint"] == signing and s["valid_from"] <= epoch <= s["valid_until"]]
            require(len(accepted) == 1 and epoch <= reviewed_at_epoch and
                    (expires == 0 or expires > reviewed_at_epoch), "unreviewed signer or signature time")
            records.append(dict(primary_fingerprint=primary, signing_fingerprint=signing,
                                signature_epoch=epoch, digest_algorithm=int(digest)))
    require(len(records) == 1, "one valid detached signature required")
    return records[0]


def check_pkginfo(data, row):
    require(len(data) <= MIB, "PKGINFO budget exceeded")
    fields = {}
    for line in data.decode("utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition(" = ")
        require(separator and key and value and "\x00" not in line, "malformed PKGINFO")
        fields.setdefault(key, []).append(value)
    for name, expected in (("pkgname",row["name"]), ("pkgver",row["version"]),
                           ("arch",row["architecture"]), ("builddate",str(row["build_epoch"])),
                           ("pkgbase",row["source_base"])):
        require(fields.get(name) == [expected], "signed PKGINFO identity mismatch: " + name)
    for field, locked in (("depend","depends"),("provides","provides")):
        values = fields.get(field, [])
        require(len(set(values)) == len(values) and sorted(values) == sorted(row[locked]),
                "signed PKGINFO dependency mismatch: " + field)
    return dict(row, depends=fields.get("depend",[]), provides=fields.get("provides",[]))


def check_closure(lock, metadata, compare):
    path = Path(__file__).resolve().parent.parent / "lock_snapshot.py"
    spec = importlib.util.spec_from_file_location("s4_snapshot_resolver", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    require(module.PROVIDERS == lock["provider_choices"], "provider choice drift")
    require(set(metadata) == {p["name"] for p in lock["packages"]}, "missing signed package metadata")
    rows = {name:{"VERSION":[p["version"]], "DEPENDS":p["depends"], "PROVIDES":p["provides"]}
            for name,p in metadata.items()}
    names, edges = module.resolve(rows,lock["runtime_roots"]+lock["build_roots"],compare)
    require(names == set(rows) and edges == lock["dependency_edges"], "signed dependency closure differs from lock")
    runtime,_ = module.resolve(rows,lock["runtime_roots"],compare)
    require(runtime == {p["name"] for p in metadata.values() if p["role"] == "runtime"}, "runtime closure drift")


def authenticate_set(lock_path, policy_path, keyring_path, cache, tool_paths, private):
    """Future VM only. Caller supplies a newly created mode-0700 private spool.

    No receipt is accepted as authorization. All inputs are copied and verified
    within this invocation. No keyring or executable is inferred from PATH.
    """
    policy_bytes = read_bounded(policy_path, MIB)
    policy = check_policy(read_json(policy_bytes))  # refusal precedes all tool/payload access
    raw = read_bounded(lock_path,4*MIB)
    require(sha256(raw) == LOCK_SHA256, "locked package set changed")
    lock = read_json(raw)
    require(isinstance(private,FdPath) and private.is_dir() and not private.is_symlink() and not any(private.iterdir()) and
            private.stat().st_mode & 0o777 == 0o700, "empty private authentication spool required")
    require(sum(p["compressed_bytes"] for p in lock["packages"]) <= 512*MIB, "archive budget")
    keyring = private_copy(keyring_path,private/"trusted-public-keys.gpg",policy["keyring_sha256"],8*MIB)
    require(set(tool_paths) == set(policy["tools"]), "explicit tool paths required")
    tools = {name:private_copy(Path(tool_paths[name]),private/name,receipt["sha256"],64*MIB,executable=True)
             for name,receipt in policy["tools"].items()}
    home = private/"gnupg-home"
    home.mkdir(mode=0o700)
    metadata, bundles, tar_total = {}, {}, 0
    from archives import inspect_tar
    for index,row in enumerate(lock["packages"]):
        payload = private_copy(cache/row["filename"],private/(str(index)+".pkg.tar.zst"),row["sha256"],
                               row["compressed_bytes"],expected_bytes=row["compressed_bytes"])
        signature_bytes = base64.b64decode(row["signature_base64"],validate=True)
        require(100 <= len(signature_bytes) <= 8192, "signature size")
        signature = private/(str(index)+".sig")
        signature.write_bytes(signature_bytes)
        status = run_tool([tools["gpgv"],"--homedir",home,"--keyring",keyring,"--status-fd","1",
                           "--",signature,payload],home,private/(str(index)+".status"),65536)
        signer = signature_status(read_bounded(status,65536).decode("utf-8"),policy["signers"],policy["reviewed_at_epoch"])
        require(signer["signature_epoch"] >= row["build_epoch"], "signature predates package build")
        unpacked = run_tool([tools["zstd"],"--decompress","--stdout","--memory=256MB","--no-progress","--",payload],
                            private,private/(str(index)+".tar"),min(2*1024*MIB,row["installed_bytes"]+64*MIB),seconds=60)
        tar_total += unpacked.stat().st_size
        require(tar_total <= 2*1024*MIB+256*MIB, "total tar expansion budget")
        members = inspect_tar(unpacked)
        infos = [m for m in members if m.name.removeprefix("./") == ".PKGINFO"]
        require(len(infos) == 1 and infos[0].isfile() and infos[0].size <= MIB, "one regular PKGINFO required")
        with tarfile.open(unpacked,mode="r:") as archive:
            with archive.extractfile(infos[0]) as source:
                metadata[row["name"]] = check_pkginfo(source.read(MIB+1),row)
        bundles[row["name"]] = dict(path=unpacked,members=members,signature=signer,
            payload_sha256=row["sha256"],signature_sha256=sha256(signature_bytes))

    counter = 0
    def compare(actual,wanted):
        nonlocal counter
        counter += 1
        output = run_tool([tools["vercmp"],actual,wanted],private,private/("version-"+str(counter)),64,seconds=5)
        text = read_bounded(output,64).decode().strip()
        require(text in ("-1","0","1"), "unexpected Arch vercmp result")
        return int(text)
    check_closure(lock,metadata,compare)
    spool_bytes=sum((private/name).stat().st_size for name in private.iterdir()
                    if not (private/name).is_dir())
    return bundles,dict(schema_version=1,status="authenticated-packages",lock_sha256=LOCK_SHA256,
        policy_sha256=sha256(policy_bytes),keyring_sha256=policy["keyring_sha256"],
        review_reference=policy["review_reference"],reviewed_at_epoch=policy["reviewed_at_epoch"],
        tools=policy["tools"],spool_bytes=spool_bytes,package_count=len(bundles),signatures_verified=True,
        dependency_closure_verified=True,assembly_executed=False,native_worker_executed=False,
        packages={name:{k:v for k,v in bundle.items() if k not in ("path","members")}
                  for name,bundle in bundles.items()})


if __name__ == "__main__":
    raise SystemExit("S4 authentication CLI is sealed pending trust/source review and VM authorization")
