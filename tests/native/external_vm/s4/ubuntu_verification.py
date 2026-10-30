"""Ubuntu signature/hash evidence protocol. Receipts never authorize S4 execution."""
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
import lzma
from pathlib import Path
import re

import bootstrap_provenance as consistency
from common import MIB, read_bounded, read_json, require, sha256
from ubuntu_artifacts import normalize, package_members, runtime_closure, runtime_graph

REFERENCES_SHA256 = "582c784e1fac0c6cbe013b64885b718a2443ef6d456ff020f5c0607a79629b4f"
IMAGE_VERSION = "20261026.354.1"
MAX_RECEIPT = 128 * 1024
MAX_RECEIPTS = MIB
SOURCE_NAMES = ("ubuntu_bootstrap_runner.py", "ubuntu_verification.py", "ubuntu_artifacts.py",
                "ubuntu-verification.pins.json", "bootstrap_provenance.py", "bootstrap-provenance.pins.json", "common.py")
RECEIPTS = ("runner-environment", "verification-toolchain", "archive-anchor", "inrelease-signatures",
            "index-hash-chain", "package-membership", "elf-closure", "consistency-review", "authorization-state")
ASSUMPTIONS = ["GitHub image/provisioning/control plane", "Canonical archive/key authority"]
UNRESOLVED = ["underlying runner integrity", "actual process mappings and dynamic loading",
              "current key lifecycle/revocation", "trusted clock and historical snapshot replay policy",
              "Arch trust/certification/lifecycle", "S4 execution remains sealed"]


def canonical(value, limit=MAX_RECEIPT):
    raw = (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()
    require(len(raw) <= limit, "receipt byte budget")
    return raw


def load_references():
    raw = read_bounded(Path(__file__).with_name("ubuntu-verification.pins.json"), MAX_RECEIPT)
    require(sha256(raw) == REFERENCES_SHA256, "Ubuntu reference hash changed")
    pins, bootstrap = read_json(raw), consistency.load_pins()
    consistency.fields(pins, "schema_version classification image_version anchor anchor_sources keyring_sha256 image_reference tools packages files links", "Ubuntu references")
    require(type(pins["schema_version"]) is int and pins["schema_version"] == 1 and
            pins["image_version"] == IMAGE_VERSION and pins["anchor"] == bootstrap["ubuntu_anchor"] and
            len(pins["files"]) == len(pins["packages"]) == 13 and
            pins["tools"] == {k: v["path"] for k, v in bootstrap["tools"].items()}, "Ubuntu reference identity")
    for tool, reference in bootstrap["tools"].items():
        package = pins["packages"][reference["package"]]
        require(package["index"] == reference["index"] and package["version"] == reference["version"] and
                package["filename"] == reference["filename"] and package["sha256"] == reference["package_sha256"] and
                int(package["size"]) == reference["package_bytes"], "Ubuntu tool reference binding")
    return pins, bootstrap


def runner_identity(env, os_release):
    required = dict(GITHUB_ACTIONS="true", RUNNER_ENVIRONMENT="github-hosted", RUNNER_OS="Linux",
                    RUNNER_ARCH="X64", ImageOS="ubuntu24", ImageVersion=IMAGE_VERSION,
                    GITHUB_REPOSITORY="adrianrusu16/panda-workstation", GITHUB_REF="refs/heads/main",
                    GITHUB_EVENT_NAME="workflow_dispatch")
    require(type(env) is dict and all(env.get(k) == v for k, v in required.items()), "reviewed hosted runner/image identity")
    require(not any(value for key, value in env.items() if key.startswith("LD_") or
                    key in ("GCONV_PATH", "PYTHONPATH", "PYTHONHOME", "GNUPGHOME")), "influencing host environment")
    require(re.fullmatch(r"[0-9a-f]{40}", env.get("GITHUB_SHA", "")) and
            env["GITHUB_SHA"] == env.get("REVIEWED_SOURCE_SHA"), "reviewed source identity")
    for key in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"):
        value = env.get(key, "")
        require(type(value) is str and re.fullmatch(r"[1-9][0-9]{0,19}", value), "runner run identity missing")
    for key in ("RUNNER_NAME", "GITHUB_JOB"):
        value = env.get(key, "")
        require(type(value) is str and 0 < len(value) <= 128 and not re.search(r"[\x00-\x1f\x7f]", value), "runner job identity missing")
    require(type(os_release) is bytes and len(os_release) <= 16384, "OS release budget")
    values = {}
    for line in os_release.decode("utf-8").splitlines():
        if not line or line.startswith("#"): continue
        key, separator, value = line.partition("=")
        require(separator and key not in values, "OS release fields")
        values[key] = value.strip('"')
    require(values.get("ID") == "ubuntu" and values.get("VERSION_ID") == "24.04", "Ubuntu OS identity")
    return dict(image_os=env["ImageOS"], image_version=env["ImageVersion"], runner_os=env["RUNNER_OS"],
                runner_arch=env["RUNNER_ARCH"], os_release_sha256=sha256(os_release), hardware_attested=False,
                job=dict(repository=env["GITHUB_REPOSITORY"], ref=env["GITHUB_REF"], head_sha=env["GITHUB_SHA"],
                         run_id=env["GITHUB_RUN_ID"], attempt=env["GITHUB_RUN_ATTEMPT"],
                         name=env["GITHUB_JOB"], runner_name=env["RUNNER_NAME"], runner_application_version=None))


def loader_configuration(files, hwcaps):
    required = {"/etc/ld.so.preload", "/etc/ld.so.cache", "/etc/ld.so.conf", "/etc/ssl/certs/ca-certificates.crt"}
    require(type(files) is dict and required <= set(files) and len(files) <= 64, "loader configuration incomplete")
    require(files["/etc/ld.so.preload"] in (None, b""), "system loader preload present")
    require(type(hwcaps) is list and not hwcaps, "unreviewed glibc hwcaps variants")
    rows = []
    for path, data in sorted(files.items()):
        require(path in required or path.startswith("/etc/ld.so.conf.d/") and path.endswith(".conf"), "loader configuration path")
        require(data is None and path == "/etc/ld.so.preload" or type(data) is bytes and 0 < len(data) <= 8*MIB or
                data == b"" and path == "/etc/ld.so.preload", "loader configuration missing/budget")
        rows.append(dict(path=path, present=data is not None, bytes=len(data) if data is not None else None,
                         sha256=sha256(data) if data is not None else None))
    return dict(files=rows, preload_absent_or_empty=True, hwcaps_variants=[], actual_mappings_verified=False,
                cache_interpretation="inventoried; actual loader selection remains a delegated-host assumption")


def status_rows(raw, allowed):
    require(type(raw) is bytes and 0 < len(raw) <= 16384 and raw.endswith(b"\n"), "GPG status byte budget/framing")
    text = raw.decode("utf-8")
    require(not re.search(r"[\x00-\x09\x0b-\x1f\x7f-\x9f\u2028\u2029]", text), "GPG status control")
    lines = text[:-1].split("\n")
    require(len(lines) <= 64, "GPG status record budget")
    result = {}
    for line in lines:
        require(line.startswith("[GNUPG:] "), "GPG status prefix")
        keyword, _, args = line[9:].partition(" ")
        require(keyword in allowed, "GPG failed/unknown status: " + keyword)
        result.setdefault(keyword, []).append(args)
    return result


def signature_status(returncode, raw, fingerprint, now):
    require(type(returncode) is int and returncode == 0 and type(now) is int and 0 < now < 2**63, "GPG verifier failure/assessment")
    rows = status_rows(raw, {"NEWSIG", "KEY_CONSIDERED", "SIG_ID", "GOODSIG", "VALIDSIG", "SIGINFO"})
    require(all(len(rows.get(name, [])) == 1 for name in ("NEWSIG", "SIG_ID", "GOODSIG", "VALIDSIG")) and
            len(rows.get("SIGINFO", [])) <= 1 and 0 < len(rows.get("KEY_CONSIDERED", [])) <= 8, "GPG incomplete/ambiguous status")
    require(all(value.split() == [fingerprint, "0"] for value in rows["KEY_CONSIDERED"]), "GPG considered identity")
    good = rows["GOODSIG"][0].split(" ", 1)
    require(len(good) == 2 and good[0] in (fingerprint, fingerprint[-16:]) and good[1], "GPG good-signature identity")
    valid = rows["VALIDSIG"][0].split()
    require(len(valid) == 10 and valid[0] == valid[9] == fingerprint and valid[4:9] == ["4", "0", "1", "10", "01"], "GPG full identity/algorithm")
    require(all(re.fullmatch(r"[0-9]{1,19}", value) for value in valid[2:4]), "GPG signature timestamps")
    created, expires = map(int, valid[2:4])
    require(0 < created <= now and (expires == 0 or expires > now and expires > created), "GPG signature expired/future")
    date = datetime.fromtimestamp(created, timezone.utc).strftime("%Y-%m-%d")
    require(valid[1] == date, "GPG signature date conflict")
    sig_id = rows["SIG_ID"][0].split()
    require(len(sig_id) == 3 and re.fullmatch(r"[A-Za-z0-9+/=_-]{1,128}", sig_id[0]) and
            sig_id[1:] == [date, str(created)], "GPG signature ID conflict")
    require(not rows.get("SIGINFO") or rows["SIGINFO"] == [str(created)], "GPG signature info conflict")
    return dict(fingerprint=fingerprint, primary_fingerprint=fingerprint, signature_epoch=created,
                expires_epoch=expires, public_key_algorithm="RSA", hash_algorithm="SHA512", signature_class="01",
                status_sha256=sha256(raw), status_text=raw.decode("utf-8"), status_records=rows, key_lifecycle_verified=False)


def negative_status(returncode, raw, case, fingerprint):
    require(type(returncode) is int and returncode in (1, 2), "negative probe did not fail cryptographically")
    rows = status_rows(raw, {"NEWSIG", "KEY_CONSIDERED", "BADSIG", "ERRSIG", "NO_PUBKEY", "FAILURE"})
    require(len(rows.get("NEWSIG", [])) == 1, "negative signature context missing")
    if case == "altered-content":
        require(len(rows.get("BADSIG", [])) == 1 and rows["BADSIG"][0].split()[0] == fingerprint[-16:] and
                not rows.get("ERRSIG") and not rows.get("NO_PUBKEY"), "altered-content signature failure missing")
    else:
        require(case == "empty-keyring" and rows.get("NO_PUBKEY") == [fingerprint[-16:]] and
                len(rows.get("ERRSIG", [])) == 1 and not rows.get("BADSIG"), "empty-keyring signature failure missing")
        error = rows["ERRSIG"][0].split()
        require(len(error) == 7 and error[0] == fingerprint[-16:] and error[1:4] == ["1", "10", "01"] and
                error[5:] == ["9", fingerprint], "empty-keyring signature identity")
    return dict(case=case, returncode=returncode, failure_observed=True, status_sha256=sha256(raw),
                status_text=raw.decode("utf-8"), status_records=rows)


def release_content(raw, suite, now):
    require(type(raw) is bytes and 0 < len(raw) <= 2*MIB and type(now) is int, "authenticated Release budget")
    text = raw.decode("utf-8")
    require(not re.search(r"[\x00-\x09\x0b-\x1f\x7f-\x9f\u2028\u2029]", text), "Release control characters")
    fields, current = {}, None
    for line in text.rstrip("\n").split("\n"):
        if line.startswith(" "):
            require(current in ("sha256", "sha512", "sha1", "md5sum"), "Release unsupported continuation")
            fields[current].append(line)
            continue
        key, separator, value = line.partition(":")
        require(separator and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*", key), "Release field")
        current = key.lower()
        require(current not in fields, "duplicate Release field")
        fields[current] = [value.lstrip(" ")]
    single = lambda name: fields.get(name, [None])[0]
    require(single("origin") == "Ubuntu" and single("suite") == suite and single("codename") == "noble" and
            "amd64" in (single("architectures") or "").split() and fields.get("sha256", [None])[0] == "", "Release identity/hash table")
    dates = {}
    for name in ("date", "valid-until"):
        value = single(name)
        require(value is not None or name == "valid-until", "Release Date missing")
        if value is None: dates[name] = None; continue
        parsed = parsedate_to_datetime(value)
        require(parsed.utcoffset() is not None, "Release date timezone")
        epoch = int(parsed.timestamp())
        require(0 < epoch <= now if name == "date" else epoch > now, "Release expired/future")
        dates[name] = epoch
    hashes = {}
    for line in fields["sha256"][1:]:
        row = line.split()
        require(len(row) == 3, "Release hash row")
        digest, size, path = row
        require(re.fullmatch(r"[0-9a-f]{64}", digest) and re.fullmatch(r"[0-9]{1,12}", size) and
                consistency.relative(path) and path not in hashes, "Release hash identity")
        hashes[path] = (digest, int(size))
    require(hashes, "Release empty hash table")
    return hashes, dict(suite=suite, date=dates["date"], valid_until=dates["valid-until"],
                        components=(single("components") or "").split(),
                        freshness_policy_established=False, authenticated_content_sha256=sha256(raw))


def keyring_anchor(raw, fingerprint, expected_hash, now):
    require(type(raw) is bytes and 0 < len(raw) <= 128*1024 and sha256(raw) == expected_hash, "preinstalled keyring hash/budget")
    pos, keys, active = 0, {}, None
    for _ in range(128):
        if pos == len(raw): break
        header = raw[pos]; pos += 1
        require(header & 128 and pos < len(raw), "OpenPGP packet header")
        if header & 64:
            tag = header & 63; size = raw[pos]; pos += 1
            if 192 <= size <= 223:
                require(pos < len(raw), "OpenPGP length")
                size = (size-192)*256+raw[pos]+192; pos += 1
            elif size == 255:
                require(pos+4 <= len(raw), "OpenPGP long length")
                size = int.from_bytes(raw[pos:pos+4], "big"); pos += 4
            else: require(size < 192, "OpenPGP partial length unsupported")
        else:
            tag, length = (header >> 2)&15, header&3
            require(length != 3, "OpenPGP indeterminate length")
            width = (1, 2, 4)[length]
            require(pos+width <= len(raw), "OpenPGP old length")
            size = int.from_bytes(raw[pos:pos+width], "big"); pos += width
        require(0 < size <= len(raw)-pos, "OpenPGP packet bounds")
        body = raw[pos:pos+size]; pos += size
        if tag == 6:
            require(len(body) >= 6 and body[0] == 4 and len(body) < 65536, "OpenPGP primary key version")
            active = hashlib.sha1(b"\x99"+len(body).to_bytes(2, "big")+body).hexdigest().upper()
            require(active not in keys, "ambiguous OpenPGP primary key")
            keys[active] = body
        if tag == 2 and active == fingerprint:
            require(len(body) >= 2 and body[1] != 0x20, "observed anchor revocation packet")
    require(pos == len(raw) and fingerprint in keys, "OpenPGP anchor missing/packet budget")
    body = keys[fingerprint]
    require(body[5] == 1 and len(body) >= 8, "OpenPGP anchor algorithm")
    bits = int.from_bytes(body[6:8], "big"); end = 8+(bits+7)//8
    require(bits == 4096 and end+2 <= len(body) and int.from_bytes(body[8:end], "big").bit_length() == bits, "OpenPGP RSA key size")
    e_bits = int.from_bytes(body[end:end+2], "big")
    require(end+2+(e_bits+7)//8 == len(body) and int.from_bytes(body[end+2:], "big") == 65537, "OpenPGP RSA exponent")
    created = int.from_bytes(body[1:5], "big")
    require(0 < created <= now, "OpenPGP anchor creation time")
    return dict(fingerprint=fingerprint, primary_fingerprints=sorted(keys), keyring_sha256=sha256(raw),
                primary_packet_sha256=sha256(body), key_created_epoch=created, rsa_bits=bits,
                key_lifecycle_verified=False, root_basis="preinstalled keyring plus reviewed Canonical fingerprint")


def verify_toolchain(value, pins):
    consistency.fields(value, "tools extensions files packages loader source_hashes keyring", "verification toolchain")
    require(set(value["tools"]) == {"gpgv", "zstd", "python"} and type(value["files"]) is dict and
            3 <= len(value["files"]) <= 128 and type(value["extensions"]) is list and len(value["extensions"]) <= 32 and
            type(value["source_hashes"]) is dict and set(value["source_hashes"]) == set(SOURCE_NAMES) and
            all(type(digest) is str and re.fullmatch(r"[0-9a-f]{64}", digest) for digest in value["source_hashes"].values()),
            "verification toolchain incomplete/budget")
    for name in ("gpgv", "zstd"):
        path = value["tools"][name]
        require(path == pins["tools"][name] and path in value["files"] and
                value["files"][path]["sha256"] == pins["files"][path]["sha256"] and
                value["files"][path]["bytes"] == pins["files"][path]["bytes"], "preinstalled verifier/decompressor identity")
        require(value["packages"].get(name) == dict(version=pins["packages"][name]["version"], architecture="amd64"), "preinstalled package metadata identity")
    require(value["packages"].get("ubuntu-keyring") == dict(version="2023.11.28.1", architecture="all"), "preinstalled keyring package identity")
    keyring = value["keyring"]
    consistency.fields(keyring, "path mode uid bytes sha256 package", "preinstalled keyring file")
    require(keyring["path"] == "/usr/share/keyrings/ubuntu-archive-keyring.gpg" and
            keyring["package"] == "ubuntu-keyring" and keyring["sha256"] == pins["keyring_sha256"] and
            type(keyring["bytes"]) is int and 0 < keyring["bytes"] <= 128*1024 and
            type(keyring["uid"]) is int and keyring["uid"] == 0 and
            type(keyring["mode"]) is int and not keyring["mode"] & 0o7022, "preinstalled keyring ownership/identity")
    require(type(value["packages"]) is dict and len(value["packages"]) <= 128, "installed package inventory budget")
    for name, row in value["packages"].items():
        consistency.fields(row, "version architecture", "installed package")
        require(re.fullmatch(r"[a-z0-9][a-z0-9+.-]{0,127}", name) and row["architecture"] in ("amd64", "all") and
                type(row["version"]) is str and re.fullmatch(r"[A-Za-z0-9.+:~_-]{1,128}", row["version"]), "installed package identity")
    require(value["tools"]["python"].startswith("/usr/bin/python3") and value["tools"]["python"] in value["files"], "preinstalled Python identity")
    pending, seen = list(value["tools"].values())+value["extensions"], set()
    total = 0
    while pending:
        path = pending.pop()
        if path in seen: continue
        require(path in value["files"] and normalize(path) == path and path.startswith(("/usr/bin/", "/usr/lib/", "/lib/", "/lib64/")), "verifier dependency missing/path")
        seen.add(path); row = value["files"][path]
        consistency.fields(row, "sha256 bytes mode uid elf interpreter needed package", "verifier file")
        consistency.fields(row["elf"], "machine bits interpreter needed soname build_ids required_versions provided_versions", "verifier ELF")
        require(re.fullmatch(r"[0-9a-f]{64}", row["sha256"]) and type(row["bytes"]) is int and 0 < row["bytes"] <= 32*MIB and
                type(row["mode"]) is int and not row["mode"] & 0o7022 and type(row["uid"]) is int and row["uid"] == 0 and
                row["package"] in value["packages"] and
                row["elf"].get("machine") == 62 and row["elf"].get("bits") == 64, "verifier file identity/ownership")
        total += row["bytes"]
        reference = pins["files"].get(path)
        if reference is not None and row["sha256"] == reference["sha256"]:
            require(row["bytes"] == reference["bytes"] and
                    all(row["elf"][key] == reference[key] for key in ("needed", "interpreter")),
                    "identical verifier bytes have contradictory ELF metadata")
        require(total <= 64*MIB and set(row["needed"]) == set(row["elf"]["needed"]), "verifier closure byte/dependency budget")
        if row["elf"]["interpreter"] is not None:
            require(type(row["interpreter"]) is str, "verifier interpreter missing")
            pending.append(row["interpreter"])
        else: require(row["interpreter"] is None, "unexpected verifier interpreter")
        require(set(row["elf"]["required_versions"]) <= set(row["needed"]), "verifier version provider missing")
        for name, target in row["needed"].items():
            require(target in value["files"] and value["files"][target]["elf"]["soname"] == name,
                    "verifier dependency SONAME conflict")
            require(set(row["elf"]["required_versions"].get(name, [])) <=
                    set(value["files"][target]["elf"]["provided_versions"]), "verifier symbol version missing")
        pending.extend(row["needed"].values())
    require(seen == set(value["files"]), "unreachable verifier inventory")
    loader = value["loader"]
    consistency.fields(loader, "files preload_absent_or_empty hwcaps_variants actual_mappings_verified cache_interpretation", "loader inventory")
    require(loader.get("preload_absent_or_empty") is True and loader.get("hwcaps_variants") == [] and
            loader.get("actual_mappings_verified") is False and type(loader.get("files")) is list and
            4 <= len(loader["files"]) <= 64 and type(loader["cache_interpretation"]) is str and
            0 < len(loader["cache_interpretation"]) <= 256, "loader evidence assumptions")
    required = {"/etc/ld.so.preload", "/etc/ld.so.cache", "/etc/ld.so.conf", "/etc/ssl/certs/ca-certificates.crt"}
    paths = set()
    for row in loader["files"]:
        consistency.fields(row, "path present bytes sha256", "loader file")
        path = row["path"]
        require(normalize(path) == path and path not in paths and
                (path in required or path.startswith("/etc/ld.so.conf.d/") and path.endswith(".conf")) and
                type(row["present"]) is bool, "loader file identity")
        paths.add(path)
        if not row["present"]:
            require(path == "/etc/ld.so.preload" and row["bytes"] is None and row["sha256"] is None, "missing loader file")
        else:
            require(type(row["bytes"]) is int and 0 <= row["bytes"] <= 8*MIB and
                    type(row["sha256"]) is str and re.fullmatch(r"[0-9a-f]{64}", row["sha256"]), "loader file hash/budget")
            require(row["bytes"] == 0 and row["sha256"] == sha256(b"") if path == "/etc/ld.so.preload" else row["bytes"] > 0,
                    "loader preload/empty file conflict")
    require(required <= paths, "incomplete loader configuration evidence")
    canonical(value)  # Includes bounded source/parser hashes; no raw system files.
    return value


def index_content(raw):
    data, remaining, count = bytearray(), raw, 0
    while remaining:
        count += 1
        require(count <= 16 and remaining.startswith(b"\xfd7zXZ\x00"), "index stream identity/budget")
        decoder = lzma.LZMADecompressor(memlimit=64*MIB)
        data.extend(decoder.decompress(remaining, max_length=consistency.MAX_INDEX_EXPANSION-len(data)+1))
        require(len(data) <= consistency.MAX_INDEX_EXPANSION and decoder.eof, "index expansion/truncation budget")
        remaining = decoder.unused_data
        padding = len(remaining)-len(remaining.lstrip(b"\0"))
        require(padding % 4 == 0, "index stream padding")
        remaining = remaining[padding:]
    require(count, "empty index")
    return bytes(data)


def verify_ubuntu(env, os_release, now, keyring, toolchain, acquire, verifier, inflate):
    """In-memory protocol; production callbacks are supplied only by the sealed runner."""
    identity = runner_identity(env, os_release)
    pins, bootstrap = load_references()
    verify_toolchain(toolchain, pins)
    anchor = keyring_anchor(keyring, pins["anchor"], pins["keyring_sha256"], now)
    anchor["reviewed_fingerprint_sources"] = pins["anchor_sources"]
    blobs, descriptions = {}, []
    def artifact(name, source, expected_hash, expected_size):
        if name in blobs: return blobs[name]
        require(type(expected_size) is int and 0 < expected_size <= consistency.MAX_ARTIFACT, "artifact expected budget")
        try: raw = acquire(name, source, expected_size)
        except (KeyError, OSError): raise ValueError("artifact unavailable: "+name) from None
        require(type(raw) is bytes and len(raw) == expected_size and sha256(raw) == expected_hash, "artifact hash/size mismatch: "+name)
        require(sum(map(len, blobs.values()))+len(raw) <= consistency.MAX_TOTAL, "aggregate artifact budget")
        blobs[name] = raw
        descriptions.append(dict(id=name, source=source, sha256=sha256(raw), bytes=len(raw)))
        return raw
    signatures, hash_tables = {}, {}
    for suite in sorted({row["suite"] for row in bootstrap["indexes"].values()}):
        reference = next(row for row in bootstrap["indexes"].values() if row["suite"] == suite)
        raw = artifact("release-"+suite, reference["release_url"], reference["release_sha256"], reference["release_bytes"])
        code, status, plain = verifier(raw, keyring)
        result = signature_status(code, status, pins["anchor"], now)
        require(result["signature_epoch"] >= anchor["key_created_epoch"], "signature predates anchor")
        hashes, metadata = release_content(plain, suite, now)
        negative = []
        start = raw.find(b"\n\n")+2
        require(start >= 2 and start < len(raw), "InRelease cleartext boundary")
        mutated = raw[:start]+bytes([raw[start] ^ 1])+raw[start+1:]
        for case, value, ring in (("altered-content", mutated, keyring), ("empty-keyring", raw, b"")):
            code, status, _ = verifier(value, ring)
            negative.append(negative_status(code, status, case, pins["anchor"]))
        signatures[suite] = dict(inrelease_sha256=sha256(raw), authenticated_content=metadata, signature=result, negative_cases=negative)
        hash_tables[suite] = hashes
    indexes, index_receipts, index_rows = {}, [], []
    for name, row in sorted(bootstrap["indexes"].items()):
        identifier = "index-"+name.replace(":", "-")
        raw = artifact(identifier, row["index_url"], row["index_sha256"], row["index_bytes"])
        hashes = hash_tables[row["suite"]]
        require(row["component"] in signatures[row["suite"]]["authenticated_content"]["components"] and
                hashes.get(row["index_path"]) == (sha256(raw), len(raw)), "authenticated index hash binding")
        plain = index_content(raw)
        require(hashes.get(row["index_path"].removesuffix(".xz")) == (sha256(plain), len(plain)), "authenticated plain index hash binding")
        indexes[name] = consistency.package_records(raw)
        index_receipts.append(dict(id=name, compressed_sha256=sha256(raw), plain_sha256=sha256(plain), records=len(indexes[name])))
        index_rows.append(dict(id=name, release="release-"+row["suite"], index=identifier))
    packages, package_rows, nodes, contents, expansion = {}, [], {}, {}, [0]
    for name, reference in sorted(pins["packages"].items()):
        record = indexes[reference["index"]].get((name, reference["version"], reference["architecture"]))
        require(record is not None and all(record[key] == reference[key.lower()] for key in
                ("Package", "Version", "Architecture", "Filename", "SHA256", "Size")), "authenticated exact package membership")
        identifier = "package-"+name
        raw = artifact(identifier, bootstrap["ubuntu_snapshot"]+"/"+record["Filename"], record["SHA256"], int(record["Size"]))
        wanted = {path for path, row in pins["files"].items() if row["package"] == name}
        control, members, selected = package_members(raw, name, wanted, inflate, budget=expansion)
        require(control["version"] == record["Version"] and control["architecture"] == record["Architecture"], "Debian control/index identity conflict")
        for path, member in members.items():
            require(path not in nodes or member["kind"] == nodes[path]["kind"] == "directory", "cross-package member collision")
            nodes[path] = member
        require(not set(contents) & set(selected), "runtime member collision")
        contents.update(selected)
        packages[name] = dict(version=record["Version"], architecture=record["Architecture"], index=reference["index"],
                              filename=record["Filename"], sha256=sha256(raw), bytes=len(raw), selected_members=sorted(selected))
        package_rows.append(dict(name=name, version=record["Version"], index=reference["index"], artifact=identifier))
    closure = runtime_closure(nodes, contents, pins["files"], pins["links"], pins["tools"])
    ids = {path: "elf-"+str(i) for i, path in enumerate(sorted(contents))}
    runtime_rows = []
    for path, row in sorted(closure["files"].items()):
        identifier = ids[path]; raw = contents[path]
        require(sum(map(len, blobs.values()))+len(raw) <= consistency.MAX_TOTAL, "reconciliation artifact budget")
        blobs[identifier] = raw
        descriptions.append(dict(id=identifier, source=bootstrap["ubuntu_snapshot"]+"/"+packages[row["package"]]["filename"]+"#"+path,
                                 sha256=sha256(raw), bytes=len(raw)))
        edges = [edge for edge in closure["edges"] if edge["source"] == path]
        interp = [ids[edge["target"]] for edge in edges if edge["kind"] == "PT_INTERP"]
        role = "tool" if path in pins["tools"].values() else "interpreter" if path in [edge["target"] for edge in closure["edges"] if edge["kind"] == "PT_INTERP"] else "library"
        runtime_rows.append(dict(id=identifier, path=path, package=row["package"], role=role, artifact=identifier,
                                 interpreter=interp[0] if interp else None,
                                 needed=[ids[edge["target"]] for edge in edges if edge["kind"] == "DT_NEEDED"]))
    manifest = dict(schema_version=1, lock_sha256=bootstrap["lock_sha256"], observed_at=now, artifacts=descriptions,
        ubuntu=dict(anchor=pins["anchor"], anchor_source=bootstrap["ubuntu_anchor_source"], indexes=index_rows,
                    packages=package_rows, files=runtime_rows, tools={name: ids[path] for name, path in pins["tools"].items()}), arch={})
    review = consistency.review(canonical(manifest, consistency.MAX_MANIFEST), blobs, now_epoch=now)
    require(review["status"] == "rejected" and review["errors"] == ["arch fields"] and
            all(review[key] is False for key in ("accepted", "execution_authorized", "trust_policy_activation_allowed")), "checker reconciliation failed or acquired authority")
    authority = dict(accepted=False, execution_authorized=False, trust_policy_activation_allowed=False,
                     hardware_attested=False, delegated_assumptions=ASSUMPTIONS, unresolved=UNRESOLVED)
    identity.pop("job")  # Job/time/path context is captured separately by the runner.
    payloads = (("runner-environment", "local_observation", identity), ("verification-toolchain", "local_observation", toolchain),
                ("archive-anchor", "hash_membership_result", anchor), ("inrelease-signatures", "cryptographic_result", signatures),
                ("index-hash-chain", "hash_membership_result", index_receipts), ("package-membership", "hash_membership_result", packages),
                ("elf-closure", "hash_membership_result", closure), ("consistency-review", "local_observation", review),
                ("authorization-state", "policy_assumption", authority))
    receipts = {name: dict(schema_version=1, claim_class=kind, data=data) for name, kind, data in payloads}
    # The legacy checker embeds the assessment time and manifest hash. Retain it as
    # contextual evidence, while stable content receipts identify its scope/limits.
    receipts["consistency-review"]["data"] = {k: v for k, v in review.items() if k not in ("assessment_epoch", "input_sha256")}
    bundle = dict(receipts=receipts, manifest={name: sha256(canonical(row)) for name, row in receipts.items()})
    validate_receipts(canonical(bundle, MAX_RECEIPTS))
    return bundle


def _validate_receipts(raw):
    require(type(raw) is bytes and len(raw) <= MAX_RECEIPTS, "receipt set budget")
    value = read_json(raw)
    consistency.fields(value, "receipts manifest", "receipt set")
    require(set(value["receipts"]) == set(RECEIPTS) and set(value["manifest"]) == set(RECEIPTS), "incomplete receipt set")
    for name in RECEIPTS:
        row = value["receipts"][name]
        consistency.fields(row, "schema_version claim_class data", "receipt")
        classes = {"runner-environment": "local_observation", "verification-toolchain": "local_observation",
                   "archive-anchor": "hash_membership_result", "inrelease-signatures": "cryptographic_result",
                   "index-hash-chain": "hash_membership_result", "package-membership": "hash_membership_result",
                   "elf-closure": "hash_membership_result", "consistency-review": "local_observation",
                   "authorization-state": "policy_assumption"}
        require(type(row["schema_version"]) is int and row["schema_version"] == 1 and row["claim_class"] == classes[name] and
                sha256(canonical(row)) == value["manifest"][name], "receipt class/hash conflict")
    data = {name: row["data"] for name, row in value["receipts"].items()}
    pins, bootstrap = load_references()
    runner = data["runner-environment"]
    consistency.fields(runner, "image_os image_version runner_os runner_arch os_release_sha256 hardware_attested", "runner receipt")
    require(runner["image_version"] == IMAGE_VERSION and runner["image_os"] == "ubuntu24" and
            runner["runner_os"] == "Linux" and runner["runner_arch"] == "X64" and
            re.fullmatch(r"[0-9a-f]{64}", runner["os_release_sha256"]) and runner["hardware_attested"] is False,
            "receipt runner assumptions")
    anchor = data["archive-anchor"]
    consistency.fields(anchor, "fingerprint primary_fingerprints keyring_sha256 primary_packet_sha256 key_created_epoch rsa_bits key_lifecycle_verified root_basis reviewed_fingerprint_sources", "anchor receipt")
    require(anchor["fingerprint"] == pins["anchor"] and anchor["keyring_sha256"] == pins["keyring_sha256"] and
            anchor["reviewed_fingerprint_sources"] == pins["anchor_sources"] and
            type(anchor["key_created_epoch"]) is int and anchor["key_created_epoch"] > 0 and anchor["rsa_bits"] == 4096 and
            type(anchor["primary_fingerprints"]) is list and 1 <= len(anchor["primary_fingerprints"]) <= 16 and
            anchor["primary_fingerprints"] == sorted(set(anchor["primary_fingerprints"])) and
            anchor["fingerprint"] in anchor["primary_fingerprints"] and
            all(re.fullmatch(r"[0-9A-F]{40}", item) for item in anchor["primary_fingerprints"]) and
            re.fullmatch(r"[0-9a-f]{64}", anchor["primary_packet_sha256"]) and
            anchor["root_basis"] == "preinstalled keyring plus reviewed Canonical fingerprint" and
            anchor["key_lifecycle_verified"] is False, "receipt anchor identity/lifecycle")
    signatures = data["inrelease-signatures"]
    require(set(signatures) == {"noble", "noble-security", "noble-updates"}, "incomplete signature evidence")
    for suite, row in signatures.items():
        consistency.fields(row, "inrelease_sha256 authenticated_content signature negative_cases", "InRelease receipt")
        metadata = row["authenticated_content"]
        consistency.fields(metadata, "suite date valid_until components freshness_policy_established authenticated_content_sha256", "authenticated content receipt")
        reference = next(item for item in bootstrap["indexes"].values() if item["suite"] == suite)
        require(row["inrelease_sha256"] == reference["release_sha256"] and
                row["authenticated_content"]["suite"] == suite and
                row["authenticated_content"]["freshness_policy_established"] is False,
                "receipt InRelease reference conflict")
        require(type(metadata["date"]) is int and metadata["date"] > 0 and
                (metadata["valid_until"] is None or type(metadata["valid_until"]) is int and metadata["valid_until"] > metadata["date"]) and
                type(metadata["components"]) is list and all(item["component"] in metadata["components"]
                    for item in bootstrap["indexes"].values() if item["suite"] == suite) and
                re.fullmatch(r"[0-9a-f]{64}", metadata["authenticated_content_sha256"]), "incomplete authenticated content receipt")
        signature = row["signature"]
        require(signature["signature_epoch"] >= anchor["key_created_epoch"], "receipt signature predates anchor")
        require(signature_status(0, signature["status_text"].encode(), anchor["fingerprint"], signature["signature_epoch"]) == signature,
                "signature receipt status conflict")
        require(len(row["negative_cases"]) == 2 and {negative["case"] for negative in row["negative_cases"]} ==
                {"altered-content", "empty-keyring"}, "incomplete negative signature evidence")
        for negative in row["negative_cases"]:
            require(negative_status(negative["returncode"], negative["status_text"].encode(), negative["case"], anchor["fingerprint"]) == negative,
                    "negative signature receipt conflict")
    indexes = data["index-hash-chain"]
    require(type(indexes) is list and len(indexes) == 4 and {row["id"] for row in indexes} ==
            {"noble:main", "noble:universe", "noble-security:main", "noble-updates:main"}, "incomplete index evidence")
    for row in indexes:
        consistency.fields(row, "id compressed_sha256 plain_sha256 records", "index receipt")
        require(row["compressed_sha256"] == bootstrap["indexes"][row["id"]]["index_sha256"] and
                re.fullmatch(r"[0-9a-f]{64}", row["plain_sha256"]) and
                type(row["records"]) is int and 0 < row["records"] <= consistency.MAX_PACKAGE_RECORDS, "index receipt identity/budget")
    packages, closure = data["package-membership"], data["elf-closure"]
    consistency.fields(closure, "files links edges closure_complete actual_candidate_mappings_verified", "runtime receipt")
    require(type(packages) is dict and len(packages) == 13 and type(closure["files"]) is dict and len(closure["files"]) == 13 and
            closure["closure_complete"] is True and closure["actual_candidate_mappings_verified"] is False,
            "incomplete runtime/package evidence")
    for path, row in closure["files"].items():
        require(normalize(path) == path and row["package"] in packages and re.fullmatch(r"[0-9a-f]{64}", row["sha256"]) and
                type(row["bytes"]) is int and 0 < row["bytes"] <= 32*MIB, "runtime receipt membership")
    require(set(packages) == set(pins["packages"]) and set(closure["files"]) == set(pins["files"]) and
            set(closure["links"]) == set(pins["links"]), "receipt reference membership")
    for name, row in packages.items():
        consistency.fields(row, "version architecture index filename sha256 bytes selected_members", "package receipt")
        reference = pins["packages"][name]
        require(all(row[key] == reference[key] for key in ("version", "architecture", "index", "filename", "sha256")) and
                type(row["bytes"]) is int and row["bytes"] == int(reference["size"]) and
                row["selected_members"] == sorted(path for path, item in closure["files"].items() if item["package"] == name),
                "receipt package/file reference conflict")
    for path, row in closure["files"].items():
        consistency.fields(row, "package sha256 bytes elf", "ELF receipt")
        consistency.fields(row["elf"], "machine bits interpreter needed soname build_ids required_versions provided_versions", "ELF metadata receipt")
        reference = pins["files"][path]
        require(all(row[key] == reference[key] for key in ("package", "sha256", "bytes")) and
                all(row["elf"][key] == reference[key] for key in ("needed", "interpreter")) and
                row["elf"]["machine"] == 62 and row["elf"]["bits"] == 64, "receipt ELF reference conflict")
    for path, row in closure["links"].items():
        require(all(row[key] == pins["links"][path][key] for key in ("kind", "target", "package")) and
                row["package"] in packages, "receipt link reference conflict")
    require(runtime_graph(closure["files"], closure["links"], pins["tools"]) == closure,
            "receipt dependency graph conflict")
    verify_toolchain(data["verification-toolchain"], pins)
    by_hash = {row["sha256"]: row for row in closure["files"].values()}
    for row in data["verification-toolchain"]["files"].values():
        if row["sha256"] in by_hash:
            candidate = by_hash[row["sha256"]]
            require(row["bytes"] == candidate["bytes"] and row["elf"] == candidate["elf"],
                    "same-content verifier/candidate ELF metadata conflict")
    review = data["consistency-review"]
    consistency.fields(review, "schema_version status accepted execution_authorized trust_policy_activation_allowed real_certificate_set_validated cryptographic_verification consistency_checked errors gaps counts", "checker receipt")
    require(review["status"] == "rejected" and review["errors"] == ["arch fields"] and
            review["cryptographic_verification"] == "not_performed" and
            type(review["schema_version"]) is int and review["schema_version"] == 1 and
            review["gaps"] == list(consistency.GAPS) and review["counts"] == {} and
            all(review[key] is False for key in ("accepted", "execution_authorized", "trust_policy_activation_allowed", "consistency_checked", "real_certificate_set_validated")),
            "checker receipt acquired authority")
    authority = value["receipts"]["authorization-state"]["data"]
    consistency.fields(authority, "accepted execution_authorized trust_policy_activation_allowed hardware_attested delegated_assumptions unresolved", "authorization receipt")
    require(all(authority.get(key) is False for key in ("accepted", "execution_authorized", "trust_policy_activation_allowed")) and
            authority.get("hardware_attested") is False and authority.get("delegated_assumptions") == ASSUMPTIONS and
            authority.get("unresolved") == UNRESOLVED, "receipt authority/assumption conflict")
    return dict(consistency_checked=True, cryptographic_verification="not_performed_by_receipt_validator",
                accepted=False, execution_authorized=False, trust_policy_activation_allowed=False)


def validate_receipts(raw):
    """Consistency only: a self-consistent receipt cannot authenticate its producer."""
    try:
        return _validate_receipts(raw)
    except (KeyError, TypeError, UnicodeError, RecursionError) as error:
        raise ValueError("malformed or incomplete receipt evidence") from error
