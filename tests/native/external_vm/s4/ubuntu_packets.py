"""Bounded atomic evidence packets. Completeness never confers execution authority."""
import ctypes
import os
from pathlib import Path
import re
import shutil
import stat

import ubuntu_verification as protocol
from common import MIB, read_json, require, sha256

DESTINATION = "panda-ubuntu-bootstrap-verification"
SUCCESS = frozenset(name+".json" for name in protocol.RECEIPTS)
FAILURE = frozenset(("failure.json", "authorization-state.json"))
COMMON = frozenset(("SHA256SUMS", "run-context.json", "context-binding.json", "completion.json"))
MAX_PACKET = 2*MIB
NOFOLLOW = os.O_NOFOLLOW | os.O_NONBLOCK


def _canonical(value, limit=protocol.MAX_RECEIPT):
    return protocol.canonical(value, limit)


def _json(raw, limit):
    require(type(raw) is bytes and len(raw) <= limit, "packet JSON byte budget")
    value = read_json(raw)
    require(_canonical(value, limit) == raw, "packet JSON is not canonical")
    return value


def _documents(documents, packet_type):
    require(packet_type in ("success", "failure"), "packet type")
    allowed = SUCCESS if packet_type == "success" else FAILURE
    require(type(documents) is dict and set(documents) == allowed, "packet document allowlist")
    require(all(type(raw) is bytes and len(raw) <= protocol.MAX_RECEIPT for raw in documents.values()) and
            sum(map(len, documents.values())) <= protocol.MAX_RECEIPTS, "packet content budget")
    values = {name: _json(raw, protocol.MAX_RECEIPT) for name, raw in documents.items()}
    if packet_type == "success":
        receipts = {name.removesuffix(".json"): value for name, value in values.items()}
        protocol.validate_receipts(_canonical(dict(receipts=receipts,
            manifest={name: sha256(documents[name+".json"]) for name in receipts}), protocol.MAX_RECEIPTS))
    else:
        failure, authority = values["failure.json"], values["authorization-state.json"]
        protocol.consistency.fields(failure, "schema_version status phase error_class evidence_complete", "failure packet")
        require(type(failure["schema_version"]) is int and failure["schema_version"] == 1 and
                failure["status"] == "failed-closed" and failure["evidence_complete"] is False and
                failure["phase"] in ("runner-admission", "authentication-and-membership", "packet-publication") and
                type(failure["error_class"]) is str and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", failure["error_class"]),
                "failure packet classification")
        require(authority == dict(accepted=False, execution_authorized=False,
            trust_policy_activation_allowed=False, hardware_attested=False) and
            all(type(value) is bool for value in authority.values()), "failure packet acquired authority")
    return allowed


def _identity(info):
    return dict(device=info.st_dev, inode=info.st_ino, mtime_ns=info.st_mtime_ns, ctime_ns=info.st_ctime_ns)


def _metadata(row, *, directory=False):
    names = "device inode" if directory else "sha256 bytes device inode mtime_ns ctime_ns"
    protocol.consistency.fields(row, names, "packet file metadata")
    for name in names.split():
        if name == "sha256": require(type(row[name]) is str and re.fullmatch(r"[0-9a-f]{64}", row[name]), "packet digest type")
        else: require(type(row[name]) is int and 0 <= row[name] < 2**63, "packet metadata integer type")


def _read_file(directory_fd, name, limit):
    fd = os.open(name, os.O_RDONLY | NOFOLLOW, dir_fd=directory_fd)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_uid == os.getuid() and
                stat.S_IMODE(before.st_mode) == 0o600 and before.st_nlink == 1 and 0 < before.st_size <= limit,
                "packet file type/ownership/mode/link/size")
        data = bytearray()
        while len(data) <= limit:
            chunk = os.read(fd, min(65536, limit+1-len(data)))
            if not chunk: break
            data.extend(chunk)
        after = os.fstat(fd)
        require(_identity(before) == _identity(after) and before.st_size == after.st_size == len(data), "packet file changed/size")
        require(_identity(os.stat(name, dir_fd=directory_fd, follow_symlinks=False)) == _identity(after), "packet file replaced")
        return bytes(data), dict(sha256=sha256(data), bytes=len(data), **_identity(after))
    finally: os.close(fd)


def _names(fd):
    names = set()
    with os.scandir(fd) as entries:
        for entry in entries:
            require(len(names) < len(SUCCESS | COMMON), "packet directory entry budget")
            require(entry.name not in names, "duplicate packet directory entry")
            names.add(entry.name)
    return names


def _validate_fd(fd):
    before = os.fstat(fd)
    require(stat.S_ISDIR(before.st_mode) and before.st_uid == os.getuid() and
            stat.S_IMODE(before.st_mode) == 0o700, "packet directory ownership/mode")
    completion, completion_row = _read_file(fd, "completion.json", 16384)
    manifest = _json(completion, 16384)
    protocol.consistency.fields(manifest, "schema_version packet_type directory files", "completion manifest")
    packet_type = manifest["packet_type"]
    require(type(manifest["schema_version"]) is int and manifest["schema_version"] == 1 and
            packet_type in ("success", "failure"), "completion version/type")
    documents = SUCCESS if packet_type == "success" else FAILURE
    names = set(documents | COMMON)
    require(type(manifest["files"]) is dict and set(manifest["files"]) == names-{"completion.json"} and
            _names(fd) == names, "packet filename set")
    _metadata(manifest["directory"], directory=True)
    require(manifest["directory"] == dict(device=before.st_dev, inode=before.st_ino), "packet directory replaced")
    data, total = {}, len(completion)
    for name in sorted(names-{"completion.json"}):
        limit = 32768 if name == "run-context.json" else 16384 if name in COMMON else protocol.MAX_RECEIPT
        raw, row = _read_file(fd, name, limit)
        _metadata(manifest["files"][name])
        require(row == manifest["files"][name], "packet file hash/identity conflict")
        data[name] = raw; total += len(raw)
        require(total <= MAX_PACKET, "packet aggregate byte budget")
    _documents({name: data[name] for name in documents}, packet_type)
    context = _json(data["run-context.json"], 32768)
    require(type(context) is dict and context.get("hardware_attested") is False, "packet context assumptions")
    checksums = "".join(sha256(data[name])+"  "+name+"\n" for name in sorted(documents)).encode()
    require(data["SHA256SUMS"] == checksums, "packet content checksums")
    binding = _json(data["context-binding.json"], 16384)
    require(type(binding) is dict and type(binding.get("schema_version")) is int and
            binding.get("machine_integrity_attested") is False and binding == dict(schema_version=1, packet_type=packet_type, content_manifest_sha256=sha256(checksums),
            run_context_sha256=sha256(data["run-context.json"]), machine_integrity_attested=False), "packet context binding")
    require(_identity(os.stat("completion.json", dir_fd=fd, follow_symlinks=False)) ==
            {key: completion_row[key] for key in ("device", "inode", "mtime_ns", "ctime_ns")}, "completion manifest replaced")
    require(_identity(os.fstat(fd)) == _identity(before) and _names(fd) == names, "packet directory changed")
    for name in names:
        expected = completion_row if name == "completion.json" else manifest["files"][name]
        current = os.stat(name, dir_fd=fd, follow_symlinks=False)
        require(stat.S_ISREG(current.st_mode) and current.st_uid == os.getuid() and
                stat.S_IMODE(current.st_mode) == 0o600 and current.st_nlink == 1 and
                current.st_size == expected["bytes"] and _identity(current) ==
                {key: expected[key] for key in ("device", "inode", "mtime_ns", "ctime_ns")}, "packet member changed during validation")
    # This handoff binds this invocation's completion file and its local identity.
    # It authenticates neither the host nor the producer and is not an S4 seal.
    token = sha256(_canonical(completion_row))
    return dict(packet_type=packet_type, packet_token=token, files=sorted(names))


def _path(directory):
    path = Path(directory)
    require(path.is_absolute() and len(str(path)) <= 4096 and not re.search(r"[\x00-\x1f\x7f]", str(path)) and
            path.parent.resolve(strict=True) == path.parent, "packet directory path")
    return path


def validate_packet(directory, *, expected_token=None):
    """Read-only independent admission; no writes, repairs or execution authority."""
    path = _path(directory)
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | NOFOLLOW)
    try:
        result = _validate_fd(fd)
        current = os.stat(path, follow_symlinks=False)
        require(current.st_ino == os.fstat(fd).st_ino and current.st_dev == os.fstat(fd).st_dev, "packet path replaced")
        if expected_token is not None:
            require(type(expected_token) is str and re.fullmatch(r"[0-9a-f]{64}", expected_token) and
                    result["packet_token"] == expected_token, "packet publication token conflict")
        return result
    except (KeyError, TypeError, UnicodeError, RecursionError) as error:
        raise ValueError("malformed packet evidence") from error
    finally: os.close(fd)


def _write_all(fd, raw):
    position = 0
    while position < len(raw):
        count = os.write(fd, memoryview(raw)[position:])
        if type(count) is not int or not 0 < count <= len(raw)-position: raise OSError("packet short write")
        position += count


def _rename_absent(parent_fd, source, destination):
    # Linux filesystem primitive, not an external executable. No replacing fallback.
    libc = ctypes.CDLL(None, use_errno=True)
    rename = libc.renameat2
    rename.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
    rename.restype = ctypes.c_int
    if rename(parent_fd, os.fsencode(source), parent_fd, os.fsencode(destination), 1) != 0:
        number = ctypes.get_errno()
        raise OSError(number, os.strerror(number))


def publish_packet(directory, documents, context, *, packet_type):
    allowed = _documents(documents, packet_type)
    path = _path(directory)
    parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | NOFOLLOW)
    staging = ".panda-packet-"+os.urandom(16).hex()
    stage_fd, created = None, False
    try:
        info = os.fstat(parent)
        require(info.st_uid == os.getuid() and not info.st_mode & 0o022, "packet parent ownership/mode")
        os.mkdir(staging, 0o700, dir_fd=parent); created = True
        stage_fd = os.open(staging, os.O_RDONLY | os.O_DIRECTORY | NOFOLLOW, dir_fd=parent)
        context_bytes = _canonical(context, 32768)
        sums = "".join(sha256(documents[name])+"  "+name+"\n" for name in sorted(allowed)).encode()
        binding = _canonical(dict(schema_version=1, packet_type=packet_type, content_manifest_sha256=sha256(sums),
            run_context_sha256=sha256(context_bytes), machine_integrity_attested=False))
        outputs = {**documents, "SHA256SUMS": sums, "run-context.json": context_bytes, "context-binding.json": binding}
        rows = {}
        def write(name, raw):
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | NOFOLLOW, 0o600, dir_fd=stage_fd)
            try: _write_all(fd, raw); os.fsync(fd)
            finally: os.close(fd)
        for name, raw in sorted(outputs.items()):
            write(name, raw)
            _, rows[name] = _read_file(stage_fd, name, protocol.MAX_RECEIPT)
        info = os.fstat(stage_fd)
        completion = _canonical(dict(schema_version=1, packet_type=packet_type,
            directory=dict(device=info.st_dev, inode=info.st_ino), files=rows), 16384)
        write("completion.json", completion)
        os.fsync(stage_fd); os.fsync(parent)
        validated = _validate_fd(stage_fd)
        require(_identity(os.stat(staging, dir_fd=parent, follow_symlinks=False)) == _identity(os.fstat(stage_fd)), "packet staging replaced")
        _rename_absent(parent, staging, path.name)
        created = False  # Rename is the final publication operation; no fallible post-commit writes.
        return validated
    finally:
        if stage_fd is not None: os.close(stage_fd)
        try:
            if created: shutil.rmtree(staging, dir_fd=parent)
        finally: os.close(parent)


def failure_documents(phase, error):
    name = type(error).__name__
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", name): name = "Exception"
    return {"failure.json": _canonical(dict(schema_version=1, status="failed-closed", phase=phase,
                error_class=name, evidence_complete=False)),
            "authorization-state.json": _canonical(dict(accepted=False, execution_authorized=False,
                trust_policy_activation_allowed=False, hardware_attested=False))}


def publish_with_fallback(directory, documents, context, *, failure=None, phase="authentication-and-membership"):
    try:
        packet_type = "failure" if failure is not None else "success"
        inputs = failure_documents(phase, failure) if failure is not None else documents
        packet = publish_packet(directory, inputs, context, packet_type=packet_type)
        return dict(exit_code=78 if failure is not None else 0, packet_token=packet["packet_token"])
    except Exception as error:
        try:
            packet = publish_packet(directory, failure_documents("packet-publication", error), context, packet_type="failure")
            return dict(exit_code=78, packet_token=packet["packet_token"])
        except Exception:
            return dict(exit_code=78, packet_token=None)


def upload_gate(directory, token):
    require(type(token) is str and re.fullmatch(r"[0-9a-f]{64}", token), "current publication token required")
    packet = validate_packet(directory, expected_token=token)
    path = _path(directory)
    return dict(packet_type=packet["packet_type"], paths=[str(path/name) for name in packet["files"]])


def _workflow_output(raw):
    require(len(raw) <= 65536, "workflow output budget")
    fd = os.open(os.environ["GITHUB_OUTPUT"], os.O_WRONLY | os.O_APPEND | NOFOLLOW)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and not info.st_mode & 0o022, "workflow output file")
        _write_all(fd, raw)
    finally: os.close(fd)


def github_publication_handoff(token):
    require(type(token) is str and re.fullmatch(r"[0-9a-f]{64}", token), "publication handoff token")
    _workflow_output(("packet_token="+token+"\n").encode())


def github_upload_gate():
    """Workflow contract: emit upload paths only after complete read-only admission."""
    packet = upload_gate(Path(os.environ["RUNNER_TEMP"])/DESTINATION, os.environ.get("PACKET_TOKEN", ""))
    _workflow_output(("paths<<PACKET_PATHS\n"+"\n".join(packet["paths"])+"\nPACKET_PATHS\ncomplete=true\n").encode())
