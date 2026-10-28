"""Fixed inert-profile source candidate. No sandbox/native dispatch in Gate 1.

The CLI only emits blockers. Pure planning and fixture lifecycle code are usable
for review; launch_inert is sealed, without a CLI/environment/permit override.
Do not turn fixture-generated evidence into an isolation attestation.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
import ctypes
import resource
import signal
import time

HERE = Path(__file__).absolute().parent
PROFILE_SHA256 = "143038e00e529bf3b329a3004cdc2f620086c6c076215baa99c07d5dca521cc0"
MAX_FILE = 16 * 1024 * 1024
ERRNO = 0x00050001
ALLOW = 0x7fff0000
KILL = 0x80000000
DIRS = ("runtime", "inputs", "etc", "work", "out", "cache", "home", "config",
        "data", "state", "tmp", "run", "shm", "logs", "unexposed")


class Refused(ValueError):
    """Stop and preserve evidence; never retry with weaker policy."""


def encoded(value):
    try:
        return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()
    except (ValueError, TypeError, RecursionError, UnicodeError) as exc:
        raise Refused("noncanonical JSON value") from exc


def digest(data):
    return hashlib.sha256(data).hexdigest()


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise Refused("duplicate JSON key")
        result[key] = value
    return result


def parse_profile(raw):
    if not isinstance(raw, bytes) or len(raw) > 65536 or digest(raw) != PROFILE_SHA256:
        raise Refused("profile identity differs from reviewed source candidate")
    try:
        return json.loads(raw, object_pairs_hook=_pairs)
    except (ValueError, UnicodeError) as exc:
        raise Refused("malformed profile") from exc


def load_profile():
    raw, _ = _read_file(HERE / "inert-profile.json")
    profile = parse_profile(raw)
    if file_receipt(HERE / "inert_probe.c")["sha256"] != profile["probe_source_sha256"]:
        raise Refused("probe source differs from the measured candidate")
    return profile


def _identity(info):
    return {name: getattr(info, "st_" + name) for name in
            ("dev", "ino", "mode", "uid", "gid", "nlink", "size", "mtime_ns", "ctime_ns")}


def _binding(info):
    return info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid


def _path(path):
    try:
        text = os.fspath(path)
        if not isinstance(text, str) or any(p in (".", "..") for p in text.split("/")):
            raise Refused("plain non-traversing path required")
        path = Path(text)
    except (TypeError, ValueError) as exc:
        raise Refused("invalid path") from exc
    if (not path.is_absolute() or
            any(not re.fullmatch(r"[A-Za-z0-9_.-]+", part) for part in path.parts[1:])):
        raise Refused("absolute non-traversing plain path required")
    return path


class DirectoryChain:
    """No symlink traversal; retained descriptors bind every parent to its name."""
    def __init__(self, path):
        self.fds, self.bindings = [], []
        try:
            path = _path(path)
            current = os.open("/", os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW)
            self.fds.append(current)
            for part in path.parts[1:]:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                dir_fd=current)
                self.fds.append(child)
                info = os.fstat(child)
                sticky = info.st_uid == 0 and info.st_mode & stat.S_ISVTX
                if info.st_uid not in (0, os.getuid()) or (info.st_mode & 0o022 and not sticky):
                    raise Refused("unsafe directory owner or mode")
                self.bindings.append((current, part, child, _binding(info)))
                current = child
            self.fd = current
            self.verify()
        except (OSError, Refused) as exc:
            self.close()
            raise Refused("directory chain refused") from exc

    def verify(self):
        try:
            for parent, name, child, expected in self.bindings:
                if (_binding(os.fstat(child)) != expected or
                        _binding(os.stat(name, dir_fd=parent, follow_symlinks=False)) != expected):
                    raise Refused("parent binding changed")
        except OSError as exc:
            raise Refused("parent binding unavailable") from exc

    def close(self):
        for fd in reversed(self.fds):
            os.close(fd)
        self.fds = []


def _read_file(path, max_bytes=MAX_FILE):
    path = _path(path)
    if type(max_bytes) is not int or not 0 < max_bytes <= MAX_FILE:
        raise Refused("invalid file bound")
    chain = DirectoryChain(path.parent)
    fd = None
    try:
        before = os.stat(path.name, dir_fd=chain.fd, follow_symlinks=False)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid not in (0, os.getuid()) or
                before.st_nlink != 1 or before.st_mode & 0o7022 or before.st_size > max_bytes):
            raise Refused("bounded singly-linked regular nonprivileged file required")
        fd = os.open(path.name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_NOATIME,
                     dir_fd=chain.fd)
        if _identity(os.fstat(fd)) != _identity(before):
            raise Refused("file changed during open")
        attrs = {name: digest(os.getxattr(fd, name)) for name in sorted(os.listxattr(fd))}
        if "security.capability" in attrs:
            raise Refused("file capabilities are forbidden")
        chunks, length = [], 0
        while True:
            data = os.read(fd, min(65536, max_bytes + 1 - length))
            if not data:
                break
            chunks.append(data)
            length += len(data)
            if length > max_bytes:
                raise Refused("file grew past bound")
        chain.verify()
        if (_identity(os.fstat(fd)) != _identity(before) or
                _identity(os.stat(path.name, dir_fd=chain.fd, follow_symlinks=False)) != _identity(before)):
            raise Refused("file identity drift")
        if attrs != {name: digest(os.getxattr(fd, name)) for name in sorted(os.listxattr(fd))}:
            raise Refused("extended attributes changed during read")
        raw = b"".join(chunks)
        return raw, {**_identity(before), "sha256": digest(raw), "xattrs": attrs}
    except OSError as exc:
        raise Refused("non-mutating file read refused") from exc
    finally:
        if fd is not None:
            os.close(fd)
        chain.close()


def file_receipt(path, max_bytes=MAX_FILE):
    return _read_file(path, max_bytes)[1]


def verify_receipt(path, expected):
    actual = file_receipt(path)
    if actual != expected:
        raise Refused("stale bytes, identity or metadata")
    return actual


def elf_from_bytes(raw):
    """Bounded ELF64 metadata decoding; never ldd, dlopen or a binary invocation."""
    try:
        if len(raw) < 64 or raw[:7] != b"\x7fELF\x02\x01\x01":
            raise Refused("Linux little-endian ELF64 required")
        header = struct.unpack_from("<HHIQQQIHHHHHH", raw, 16)
        kind, machine, version, _, offset, _, _, ehsize, stride, count, _, _, _ = header
        if (kind not in (2, 3) or machine != 62 or version != 1 or ehsize != 64 or
                stride != 56 or not 0 < count <= 128 or offset + count * stride > len(raw)):
            raise Refused("unsupported ELF header")
        headers = [struct.unpack_from("<IIQQQQQQ", raw, offset + i * stride) for i in range(count)]
        build_ids, interpreter, needed, string_address, string_size = [], None, [], None, None
        for ptype, _, start, _, _, size, _, _ in headers:
            if start + size > len(raw):
                raise Refused("ELF segment exceeds file")
            if ptype == 3:
                if interpreter is not None or not raw[start:start+size].endswith(b"\0"):
                    raise Refused("invalid ELF interpreter")
                interpreter = raw[start:start+size-1].decode("ascii")
            elif ptype == 4:
                end, at = start + size, start
                while at + 12 <= end:
                    nlen, dlen, ntype = struct.unpack_from("<III", raw, at)
                    at += 12
                    desc = at + ((nlen + 3) & ~3)
                    next_note = desc + ((dlen + 3) & ~3)
                    if next_note > end:
                        raise Refused("ELF note exceeds segment")
                    if ntype == 3 and raw[at:at+nlen] == b"GNU\0":
                        build_ids.append(raw[desc:desc+dlen].hex())
                    at = next_note
            elif ptype == 2:
                if size % 16:
                    raise Refused("invalid ELF dynamic segment")
                for tag, value in struct.iter_unpack("<qQ", raw[start:start+size]):
                    if tag == 0:
                        break
                    if tag == 1:
                        needed.append(value)
                    elif tag == 5:
                        string_address = value
                    elif tag == 10:
                        string_size = value
        if len(build_ids) != 1 or not build_ids[0]:
            raise Refused("one GNU build ID required")
        libraries = []
        if needed:
            if string_address is None or string_size is None or string_size > MAX_FILE:
                raise Refused("missing dynamic string table")
            tables = [start + string_address - address for ptype, _, start, address, _, size, _, _ in headers
                      if ptype == 1 and address <= string_address and string_address + string_size <= address + size]
            if len(tables) != 1:
                raise Refused("unmapped dynamic strings")
            strings = raw[tables[0]:tables[0]+string_size]
            for index in needed:
                if index >= len(strings) or b"\0" not in strings[index:]:
                    raise Refused("invalid needed library")
                libraries.append(strings[index:].split(b"\0", 1)[0].decode("ascii"))
        return {"build_id": build_ids[0], "interpreter": interpreter, "needed": libraries}
    except (struct.error, UnicodeError, OverflowError) as exc:
        raise Refused("malformed ELF metadata") from exc


def verify_pin(path, pin):
    if not isinstance(pin, dict) or set(pin) != {"identity", "build_id", "distribution"}:
        raise Refused("complete exact provenance receipt required")
    raw, identity = _read_file(path)
    build_id = elf_from_bytes(raw)["build_id"]
    distro = pin["distribution"]
    if (not isinstance(distro, dict) or set(distro) != {"package", "version", "source_receipt"} or
            not all(isinstance(v, str) and v for v in distro.values()) or
            not re.fullmatch("[0-9a-f]{64}", distro["source_receipt"]) or
            not isinstance(build_id, str) or not re.fullmatch("[0-9a-f]+", build_id) or
            pin["build_id"] != build_id):
        raise Refused("unverified build or distribution provenance")
    if identity != pin["identity"]:
        raise Refused("stale bytes, identity or metadata")
    # Matching caller-supplied receipts is consistency, not authenticated origin.


def compile_filter():
    """Complete classic-BPF program, x86-64 only; bytes are never installed here.

    A default-deny allowlist excludes sockets, all clone/fork/thread creation,
    ptrace, mount/namespaces, BPF, io_uring and execveat. execve is required for
    bwrap's initial payload exec. BPF cannot inspect the pointed-to pathname.
    The intended probe/loader/libc closure alone does NOT prove helper refusal:
    writable mounts and loader-mediated execution still require a reviewed
    executable-identity boundary. This unresolved handoff blocks dispatch.
    """
    policy = load_profile()["syscalls"]
    insns = [(0x20, 0, 0, 4), (0x15, 1, 0, policy["arch"]), (0x06, 0, 0, KILL),
             (0x20, 0, 0, 0), (0x45, 0, 1, policy["x32_mask"]), (0x06, 0, 0, KILL)]
    for nr in sorted(policy["allow"].values()):
        insns.extend(((0x15, 0, 1, nr), (0x06, 0, 0, ALLOW)))
    # prctl(157) is restricted to dumpability, NNP and further filtering.
    options = policy["prctl_options"]
    insns.extend(((0x15, 0, len(options) * 2 + 1, 157), (0x20, 0, 0, 16)))
    for option in options:
        insns.extend(((0x15, 0, 1, option), (0x06, 0, 0, ALLOW)))
    insns.append((0x06, 0, 0, ERRNO))
    return b"".join(struct.pack("<HBBI", *i) for i in insns)


def evaluate_filter(raw, nr, *, arch=0xc000003e, arg0=0):
    """Bounded fixture interpreter for exactly this cBPF subset; no syscalls."""
    if not isinstance(raw, bytes) or len(raw) % 8:
        raise Refused("malformed BPF")
    insns = list(struct.iter_unpack("<HBBI", raw))
    pc, acc = 0, 0
    for _ in range(len(insns)):
        if not 0 <= pc < len(insns):
            raise Refused("BPF jumps out of range")
        code, yes, no, value = insns[pc]
        if code == 0x20 and value in (0, 4, 16):
            acc = {0: nr, 4: arch, 16: arg0}[value] & 0xffffffff
        elif code == 0x15:
            pc += yes if acc == value else no
        elif code == 0x45:
            pc += yes if acc & value else no
        elif code == 0x06:
            return value
        else:
            raise Refused("unsupported BPF instruction")
        pc += 1
    raise Refused("BPF did not return")


def make_plan(worktree, nonce):
    if not isinstance(nonce, str) or not re.fullmatch("[0-9a-f]{16}", nonce):
        raise Refused("fresh 16-hex nonce required")
    worktree = _path(worktree)
    chain = DirectoryChain(worktree)
    chain.close()
    profile = load_profile()
    root = worktree / ".local-ai/d4c3-s2-isolation" / ("run-" + nonce)
    mounts = [{"kind": "tmpfs", "target": "/", "readonly": True},
              {"kind": "proc", "target": "/proc", "readonly": True},
              {"kind": "dev", "target": "/dev", "readonly": False}]
    targets = {"runtime": "/runtime", "inputs": "/inputs", "etc": "/etc", "work": "/work",
               "out": "/out", "cache": "/cache", "home": "/home/probe", "config": "/config",
               "data": "/data", "state": "/state", "tmp": "/tmp", "run": "/run/private", "shm": "/dev/shm"}
    for source, target in targets.items():
        ro = source in ("runtime", "inputs", "etc")
        mounts.append({"kind": "ro-bind" if ro else "bind", "source": str(root / source),
                       "target": target, "readonly": ro})
    argv = [profile["tools"]["tracer"], "-f", "--kill-on-exit", "-q", "-ttt", "-T",
            "-s", str(profile["limits"]["file_bytes"]), "-v", "-yy", "-e", "trace=all", "-o", str(root / "logs/trace"),
            "--", profile["tools"]["bubblewrap"], "--unshare-user", "--unshare-pid",
            "--unshare-ipc", "--unshare-net", "--unshare-uts", "--unshare-cgroup",
            "--die-with-parent", "--new-session", "--uid", "1000", "--gid", "1000",
            "--hostname", "panda-inert", "--cap-drop", "ALL", "--clearenv"]
    for key, value in sorted(profile["environment"].items()):
        argv.extend(("--setenv", key, value))
    # Mount namespace is mandatory/default in the pinned bwrap implementation.
    argv.extend(("--tmpfs", "/"))
    for mount in mounts[1:]:
        argv.append("--" + mount["kind"])
        if "source" in mount:
            argv.append(mount["source"])
        argv.append(mount["target"])
        if mount["kind"] == "proc":
            argv.extend(("--remount-ro", "/proc"))
    argv.extend(("--remount-ro", "/", "--chdir", "/work", "--seccomp", "3",
                 "--json-status-fd", "4", "--", profile["executable"]))
    plan = {"id": profile["id"], "execution_enabled": False, "root": str(root), "argv": argv,
            "host_environment": {"LANG": "C", "LC_ALL": "C", "TZ": "UTC"},
            "environment": profile["environment"], "mounts": mounts, "limits": profile["limits"],
            "descriptors": {"payload": [0, 1, 2], "launcher_only": [3, 4]},
            "profile_sha256": PROFILE_SHA256, "filter_sha256": digest(compile_filter()),
            "source_sha256": {name: file_receipt(HERE / name)["sha256"] for name in
                              ("sandbox_supervisor.py", "inert_probe.c")},
            "blockers": profile["blockers"]}
    plan["plan_sha256"] = digest(encoded(plan))
    return plan


def _validate_plan(plan):
    try:
        root = _path(plan["root"])
        if root.parent.name != "d4c3-s2-isolation" or root.parent.parent.name != ".local-ai":
            raise Refused("wrong run boundary")
        expected = make_plan(root.parents[2], root.name.removeprefix("run-"))
        if encoded(expected) != encoded(plan):
            raise Refused("plan modified or source/profile changed")
    except (KeyError, TypeError, OSError) as exc:
        raise Refused("invalid fixed inert plan") from exc


class Journal:
    def __init__(self, root, chain, files, dirs):
        self.root, self.chain, self.files, self.dirs = root, chain, files, dirs

    def close(self):
        self.chain.close()


def create_journal(worktree, nonce):
    plan = make_plan(worktree, nonce)
    root = Path(plan["root"])
    chain = DirectoryChain(_path(worktree))
    files, dirs = {}, {}
    try:
        # Keep the original worktree/ancestor descriptors for the WHOLE lifetime.
        # Never reopen a name and silently accept a new parent binding.
        for name in (".local-ai", "d4c3-s2-isolation", root.name):
            chain.verify()
            try:
                os.mkdir(name, 0o700, dir_fd=chain.fd)
            except FileExistsError:
                if name == root.name:
                    raise Refused("fresh run required; preserve existing root")
            chain.verify()
            parent = chain.fd
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            chain.fds.append(child)
            info = os.fstat(child)
            if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
                raise Refused("private owned ancestors required")
            chain.bindings.append((parent, name, child, _binding(info)))
            chain.fd = child
            chain.verify()
        # Persist the root/parent creation bindings BEFORE preparing any child
        # resources, so an initialization failure leaves an attributable root.
        initial = encoded({"status": "initializing-unexecuted", "plan_sha256": plan["plan_sha256"],
                           "root_identity": list(_binding(os.fstat(chain.fd))),
                           "parent_bindings": [list(item[3]) for item in chain.bindings]})
        fd = os.open("initialization.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=chain.fd)
        with os.fdopen(fd, "wb") as stream:
            stream.write(initial)
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(chain.fd)
        files["initialization.json"] = file_receipt(root / "initialization.json")
        chain.verify()
        for name in DIRS:
            chain.verify()
            os.mkdir(name, 0o700, dir_fd=chain.fd)
            dirs[name] = _binding(os.stat(name, dir_fd=chain.fd, follow_symlinks=False))
        prepared = {
            "etc/passwd": b"probe:x:1000:1000:inert:/home/probe:/nonexistent\n",
            "etc/group": b"probe:x:1000:\n",
            "etc/nsswitch.conf": b"passwd: files\ngroup: files\nhosts: files\n",
            "inputs/readonly-sentinel": b"panda-inert-sentinel",
            "inputs/outer-filter.bpf": compile_filter(),
            "unexposed/sentinel": b"panda-inert-unexposed",
            "logs/stdin": b"", "logs/stdout": b"", "logs/stderr": b"",
            "logs/trace": b"", "logs/status": b"", "logs/parent-namespaces": b""}
        for relative, data in prepared.items():
            directory, name = relative.split("/")
            chain.verify()
            parent = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=chain.fd)
            try:
                if _binding(os.fstat(parent)) != dirs[directory]:
                    raise Refused("prepared directory changed")
                fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=parent)
                with os.fdopen(fd, "wb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.fsync(parent)
            finally:
                os.close(parent)
            files[relative] = file_receipt(root / relative)
            chain.verify()
        body = encoded({"status": "prepared-unexecuted", "plan_sha256": plan["plan_sha256"],
                        "root_identity": list(_binding(os.fstat(chain.fd))),
                        "directories": {k: list(v) for k, v in dirs.items()}, "files": files})
        fd = os.open("journal.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=chain.fd)
        with os.fdopen(fd, "wb") as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        files["journal.json"] = file_receipt(root / "journal.json")
        os.fsync(chain.fd)
        chain.verify()
        return Journal(root, chain, files, dirs)
    except BaseException as exc:
        # Even partially initialized roots survive failure for investigation.
        chain.close()
        if isinstance(exc, OSError):
            raise Refused("initialization failed; retain partial preparation") from exc
        raise


def stream_inventory(journal):
    """Bind measured raw fd0/1/2 to prepared private regular files, not a socket/TTY."""
    journal.chain.verify()
    records = []
    for number, name in enumerate(("stdin", "stdout", "stderr")):
        relative = "logs/" + name
        actual = file_receipt(journal.root / relative)
        expected = journal.files[relative]
        for field in ("dev", "ino", "mode", "uid", "gid"):
            if actual[field] != expected[field]:
                raise Refused("private standard stream replaced")
        if not stat.S_ISREG(actual["mode"]) or stat.S_IMODE(actual["mode"]) != 0o600:
            raise Refused("private regular standard stream required")
        records.append({"fd": number, "mode": actual["mode"], "dev": actual["dev"],
                        "ino": actual["ino"], "cloexec": 0})
    return records


def cleanup(journal, *, evidence_reviewed=False):
    """Only this exact empty preparation. Never recursively remove runtime evidence.

    Gate 2 output must first get its own identified, reviewed disposable-object
    inventory. No glob/rmtree/path-based recursive cleanup is offered.
    """
    if evidence_reviewed is not True:
        raise Refused("retain evidence until review")
    chain = journal.chain
    chain.verify()
    top_files = {name for name in journal.files if "/" not in name}
    if set(os.listdir(chain.fd)) != top_files | set(journal.dirs):
        raise Refused("unknown objects: retain all evidence")
    for name, expected in journal.files.items():
        verify_receipt(journal.root / name, expected)
    children = {}
    try:
        for name, expected in journal.dirs.items():
            fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=chain.fd)
            children[name] = fd
            expected_names = {p.split("/")[1] for p in journal.files if p.startswith(name + "/")}
            if (_binding(os.fstat(fd)) != expected or set(os.listdir(fd)) != expected_names or
                    _binding(os.stat(name, dir_fd=chain.fd, follow_symlinks=False)) != expected):
                raise Refused("changed/unknown disposable directory contents")
        # All preflight refusals above perform zero deletion. Recheck before each
        # unlink with anchored descriptors; abort rather than widening scope.
        for relative, expected in journal.files.items():
            chain.verify()
            verify_receipt(journal.root / relative, expected)
            if "/" in relative:
                directory, name = relative.split("/")
                parent = children[directory]
                if _binding(os.stat(directory, dir_fd=chain.fd, follow_symlinks=False)) != journal.dirs[directory]:
                    raise Refused("late parent directory replacement")
            else:
                name, parent = relative, chain.fd
            os.unlink(name, dir_fd=parent)
        for name, expected in reversed(tuple(journal.dirs.items())):
            chain.verify()
            if _binding(os.stat(name, dir_fd=chain.fd, follow_symlinks=False)) != expected:
                raise Refused("late directory replacement")
            os.rmdir(name, dir_fd=chain.fd)
        chain.verify()
        parent, name, _, _ = chain.bindings[-1]
        os.rmdir(name, dir_fd=parent)
        os.fsync(parent)
    except OSError as exc:
        raise Refused("cleanup interrupted; retain remaining objects") from exc
    finally:
        for fd in children.values():
            os.close(fd)


class PrivateCapture:
    """Four retained, singly linked 0600 files; each has a hard kernel cap.

    RLIMIT_FSIZE caps every output file before tracer ELF loading. The aggregate
    sampled cap may overshoot between polls, but cannot exceed four file caps.
    Reaching any cap is a refusal even when SIGXFSZ was handled by the writer.
    """
    def __init__(self, journal, limits):
        self.journal, self.limit, self.fds = journal, limits["file_bytes"], {}
        self.directory = None
        try:
            journal.chain.verify()
            self.directory = os.open("logs", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                     dir_fd=journal.chain.fd)
            if _binding(os.fstat(self.directory)) != journal.dirs["logs"]:
                raise Refused("capture directory changed")
            for name in ("stdout", "stderr", "trace", "status"):
                fd = os.open(name, os.O_RDWR | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_NOATIME,
                             dir_fd=self.directory)
                self.fds[name] = fd
                expected = journal.files["logs/" + name]
                actual = os.fstat(fd)
                if (any(getattr(actual, "st_" + k) != expected[k] for k in ("dev", "ino", "mode", "uid", "gid")) or
                        not stat.S_ISREG(actual.st_mode) or stat.S_IMODE(actual.st_mode) != 0o600 or actual.st_nlink != 1):
                    raise Refused("capture identity differs from preparation")
            self.snapshot()
        except BaseException:
            self.close()
            raise

    def snapshot(self):
        self.journal.chain.verify()
        if (_binding(os.fstat(self.directory)) != self.journal.dirs["logs"] or
                _binding(os.stat("logs", dir_fd=self.journal.chain.fd, follow_symlinks=False)) != self.journal.dirs["logs"]):
            raise Refused("capture parent replaced")
        sizes = {}
        for name, fd in self.fds.items():
            actual = os.fstat(fd)
            named = os.stat(name, dir_fd=self.directory, follow_symlinks=False)
            expected = self.journal.files["logs/" + name]
            if (_identity(actual) != _identity(named) or actual.st_nlink != 1 or
                    any(getattr(actual, "st_" + k) != expected[k] for k in ("dev", "ino", "mode", "uid", "gid")) or
                    os.listxattr(fd)):
                raise Refused("capture file replaced or metadata changed")
            sizes[name] = actual.st_size
        return sizes

    def read(self, name):
        self.snapshot()
        return os.pread(self.fds[name], self.limit, 0)

    def close(self):
        for fd in self.fds.values():
            os.close(fd)
        self.fds = {}
        if self.directory is not None:
            os.close(self.directory)
            self.directory = None


class OwnedTree:
    """Dedicated cgroup-v2 domain + dedicated subreaper; no process-group claim.

    No constructor is called in Gate 1. Delegation is an unresolved prerequisite.
    cgroup.kill covers changing sessions, double forks and leader exit. A domain
    stays private for inspection; no automatic cgroup/evidence cleanup occurs.
    """
    def __init__(self, plan):
        delegated = load_profile()["delegated_cgroup"]
        if delegated is None:
            raise Refused("no reviewed private cgroup-v2 delegation")
        self.chain = DirectoryChain(_path(delegated))
        self.pid, self.pidfd, self.exit_code, self.wait_usage = None, None, None, []
        self.reaped = False
        self.handles = {}
        try:
            name = Path(plan["root"]).name
            os.mkdir(name, 0o700, dir_fd=self.chain.fd)
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=self.chain.fd)
            info = os.fstat(child)
            self.chain.fds.append(child)
            self.chain.bindings.append((self.chain.fd, name, child, _binding(info)))
            self.chain.fd = child
            for filename in ("cgroup.procs", "cgroup.kill", "cgroup.events", "cpu.stat", "memory.peak"):
                self.handles[filename] = os.open(
                    filename, (os.O_WRONLY if filename in ("cgroup.procs", "cgroup.kill") else os.O_RDONLY) | os.O_NOFOLLOW,
                    dir_fd=child)
            for filename, value in (("memory.max", plan["limits"]["address_space_bytes"]),
                                    ("memory.swap.max", 0), ("pids.max", 16)):
                fd = os.open(filename, os.O_WRONLY | os.O_NOFOLLOW, dir_fd=child)
                try:
                    if os.write(fd, str(value).encode()) != len(str(value)):
                        raise Refused("short cgroup limit write")
                finally:
                    os.close(fd)
            self.chain.verify()
        except BaseException:
            self.close()
            raise

    def terminate(self):
        failed = False
        # The stopped child may not yet be in the cgroup. Retain direct-child
        # authority until wait4 reaps it, then rely on the whole-tree domain.
        try:
            if self.pid is not None and self.exit_code is None:
                if self.pidfd is not None:
                    signal.pidfd_send_signal(self.pidfd, signal.SIGKILL)
                else:
                    # Only the failed-pidfd-open path: SIGCHLD is default and
                    # this dedicated supervisor has no other reaper. The own
                    # unreaped child's PID cannot be reused in this interval.
                    os.kill(self.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except OSError:
            failed = True
        try:
            self.chain.verify()
            if os.write(self.handles["cgroup.kill"], b"1") != 1:
                failed = True
        except (OSError, Refused):
            failed = True
        if failed:
            raise Refused("incomplete direct-child/whole-tree kill")

    def sample(self):
        # This supervisor must be a dedicated, single-threaded subreaper with
        # no preexisting children. wait4(-1) must never reap unrelated children.
        while True:
            try:
                pid, status, usage = os.wait4(-1, os.WNOHANG)
            except ChildProcessError:
                self.reaped = True
                break
            if pid == 0:
                self.reaped = False
                break
            self.wait_usage.append({"pid": pid, "status": status,
                                   "cpu_seconds": usage.ru_utime + usage.ru_stime,
                                   "max_rss_bytes": usage.ru_maxrss * 1024})
            if pid == self.pid:
                self.exit_code = os.waitstatus_to_exitcode(status)
        self.chain.verify()
        def values(name):
            raw = os.pread(self.handles[name], 4097, 0)
            if len(raw) > 4096:
                raise Refused("oversized cgroup accounting")
            return raw.decode("ascii")
        try:
            events = dict(line.split() for line in values("cgroup.events").splitlines())
            cpu = dict(line.split() for line in values("cpu.stat").splitlines())
            peak = int(values("memory.peak").strip())
            if events.get("populated") not in ("0", "1") or peak < 0:
                raise Refused("incomplete cgroup accounting")
            seconds = int(cpu["usage_usec"]) / 1000000
            if seconds < 0:
                raise Refused("negative cgroup accounting")
        except (ValueError, UnicodeError, KeyError) as exc:
            raise Refused("malformed cgroup accounting") from exc
        return {"exit_code": self.exit_code, "populated": events["populated"] == "1",
                "reaped": self.reaped, "cpu_seconds": seconds, "max_rss_bytes": peak}

    def close(self):
        if self.pidfd is not None:
            os.close(self.pidfd)
            self.pidfd = None
        for fd in self.handles.values():
            os.close(fd)
        self.handles = {}
        self.chain.close()


def verify_bundle(plan, journal):
    """Exact snapshot closure, not caller-declared supply-chain attestation."""
    _validate_plan(plan)
    if not isinstance(journal, Journal) or str(journal.root) != plan["root"]:
        raise Refused("matching retained journal required")
    journal.chain.verify()
    profile = load_profile()
    paths = {"probe": journal.root / "runtime/inert-probe",
             "loader": journal.root / "runtime/ld-linux-x86-64.so.2",
             "libc": journal.root / "runtime/libc.so.6",
             "tracer": Path(profile["tools"]["tracer"]),
             "bubblewrap": Path(profile["tools"]["bubblewrap"])}
    if set(os.listdir(journal.root / "runtime")) != set(profile["runtime_files"]):
        raise Refused("runtime closure differs from exact allowlist")
    for name, path in paths.items():
        pin = profile["candidate_pins"][name]
        raw, identity = _read_file(path)
        if identity != pin["identity"] or elf_from_bytes(raw) != pin["elf"]:
            raise Refused("binary identity, loader or dependency closure changed")
        if identity["mode"] & 0o222:
            raise Refused("runtime/tool binary is writable; immutable snapshot required")
    filter_raw, _ = _read_file(journal.root / "inputs/outer-filter.bpf")
    if filter_raw != compile_filter() or digest(filter_raw) != plan["filter_sha256"]:
        raise Refused("filter identity changed")
    for name in ("etc/passwd", "etc/group", "etc/nsswitch.conf", "inputs/readonly-sentinel", "unexposed/sentinel"):
        verify_receipt(journal.root / name, journal.files[name])
    # Candidate hashes are measurements. There is deliberately no field a
    # caller can set to assert authenticated distribution or pre-main safety.
    raise Refused("distribution provenance and immutable host dependency closure remain unverified")


def dispatch_fixed(plan, journal):
    """Concrete fixed fork/exec recipe, dormant behind an unconditional gate.

    No caller-supplied command, authorization bool, environment override, permit
    file or CLI flag can open this gate. Changing it requires source review.
    """
    _validate_plan(plan)
    raise Refused("pre-main executable/helper confinement is infeasible with the current execve/loader/writable-mount policy; Gate 2 remains unauthorized")


def close_child_descriptors(libc):
    """Linux x86-64 close_range(5, UINT_MAX, 0); no soft-limit blind spot.

    Called only in the dormant child before ELF loading. Unsupported kernels
    refuse rather than falling back to a potentially unbounded close loop.
    """
    if libc.syscall(436, ctypes.c_uint(5), ctypes.c_uint(0xffffffff), ctypes.c_uint(0)) != 0:
        raise Refused("complete kernel descriptor closure unavailable")


def registered_fork(tree):
    """Record the own child and pidfd before delivering asynchronous handlers.

    The child keeps signals blocked until its parent admits the stopped child.
    Only the fixed, sealed adapter calls this primitive; it takes no command.
    """
    if signal.getsignal(signal.SIGCHLD) != signal.SIG_DFL:
        raise Refused("dedicated supervisor requires default SIGCHLD disposition")
    previous = signal.pthread_sigmask(signal.SIG_BLOCK,
                                     signal.valid_signals() - {signal.SIGKILL, signal.SIGSTOP})
    pid = None
    try:
        pid = os.fork()
        if pid != 0:
            tree.pid = pid
            tree.pidfd = os.pidfd_open(pid, 0)
        return pid, previous
    finally:
        if pid != 0:
            signal.pthread_sigmask(signal.SIG_SETMASK, previous)


def admit_stopped_child(tree, seconds):
    """Parent-side admission: observe stop, enroll, then continue via pidfd."""
    deadline = time.monotonic() + seconds
    while True:
        pid, status, usage = os.wait4(tree.pid, os.WNOHANG | os.WUNTRACED)
        if pid:
            if pid != tree.pid:
                raise Refused("unexpected stop handshake child")
            if os.WIFSTOPPED(status) and os.WSTOPSIG(status) == signal.SIGSTOP:
                break
            if os.WIFEXITED(status) or os.WIFSIGNALED(status):
                tree.exit_code = os.waitstatus_to_exitcode(status)
                tree.wait_usage.append({"pid": pid, "status": status,
                                        "cpu_seconds": usage.ru_utime + usage.ru_stime,
                                        "max_rss_bytes": usage.ru_maxrss * 1024})
            raise Refused("child failed before cgroup admission")
        if time.monotonic() >= deadline:
            raise Refused("child stop handshake timed out")
        time.sleep(0.01)
    data = str(tree.pid).encode()
    if os.write(tree.handles["cgroup.procs"], data) != len(data):
        raise Refused("incomplete stopped-child cgroup admission")
    signal.pidfd_send_signal(tree.pidfd, signal.SIGCONT)


def _fork_fixed(plan, journal):
    """Dormant OS adapter. The same unopenable source gate protects direct calls.

    Source is reviewable without making Gate 1 an implicit execution permit.
    FD mapping and resource limits precede tracer/bwrap/probe executable loading.
    """
    dispatch_fixed(plan, journal)
    verify_bundle(plan, journal)
    import threading
    if threading.active_count() != 1:
        raise Refused("dedicated single-threaded supervisor required")
    children = Path("/proc/self/task") / str(os.getpid()) / "children"
    if children.read_bytes().strip():
        raise Refused("dedicated supervisor has preexisting children")
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
        raise Refused("subreaper unavailable")
    tree, capture = OwnedTree(plan), None
    try:
        capture = PrivateCapture(journal, plan["limits"])
        if any(capture.snapshot().values()):
            raise Refused("new empty capture required")
        # Keep duplicate sources above fd4 so remapping cannot clobber one.
        import fcntl
        extra, opened = [], []
        try:
            stdin = os.open(journal.root / "logs/stdin", os.O_RDONLY | os.O_NOFOLLOW)
            opened.append(stdin)
            bpf = os.open(journal.root / "inputs/outer-filter.bpf", os.O_RDONLY | os.O_NOFOLLOW)
            opened.append(bpf)
            for fd in (stdin, capture.fds["stdout"], capture.fds["stderr"], bpf, capture.fds["status"]):
                extra.append(fcntl.fcntl(fd, fcntl.F_DUPFD_CLOEXEC, 10))
            parent_ns = {name: os.readlink("/proc/self/ns/" + name) for name in load_profile()["namespaces"]}
            parent_fd = os.open(journal.root / "logs/parent-namespaces", os.O_WRONLY | os.O_NOFOLLOW)
            try:
                data = encoded(parent_ns)
                if os.write(parent_fd, data) != len(data):
                    raise Refused("incomplete parent namespace capture")
                os.fsync(parent_fd)
            finally:
                os.close(parent_fd)
            parent_pid = os.getpid()
            pid, previous_mask = registered_fork(tree)
            if pid == 0:
                try:
                    # Close the parent-death-before-prctl race by checking the
                    # original parent identity immediately after arming it.
                    if libc.prctl(1, signal.SIGKILL, 0, 0, 0) != 0 or os.getppid() != parent_pid:
                        os._exit(126)
                    os.kill(os.getpid(), signal.SIGSTOP)
                    signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
                    os.setsid()
                    for number, fd in enumerate(extra):
                        os.dup2(fd, number, inheritable=True)
                    close_child_descriptors(libc)
                    bounds = plan["limits"]
                    for which, value in ((resource.RLIMIT_CPU, bounds["cpu_seconds"]),
                                         (resource.RLIMIT_AS, bounds["address_space_bytes"]),
                                         (resource.RLIMIT_FSIZE, bounds["file_bytes"]),
                                         (resource.RLIMIT_NOFILE, bounds["open_files"]),
                                         (resource.RLIMIT_NPROC, bounds["processes"]),
                                         (resource.RLIMIT_CORE, 0)):
                        resource.setrlimit(which, (value, value))
                    if libc.prctl(38, 1, 0, 0, 0) != 0 or libc.prctl(4, 0, 0, 0, 0) != 0:
                        os._exit(126)
                    os.chdir(journal.root)
                    os.execve(plan["argv"][0], plan["argv"], plan["host_environment"])
                except BaseException:
                    os._exit(126)
            admit_stopped_child(tree, plan["limits"]["wall_seconds"])
        finally:
            for fd in extra + opened:
                os.close(fd)
        return tree
    except BaseException:
        if tree.pid is not None:
            _, complete = terminate_and_account(tree, plan["limits"]["teardown_seconds"])
            if not complete:
                # Preserve cgroup path and all evidence; never claim successful
                # teardown merely because the direct forked child disappeared.
                raise Refused("dispatch failure with incomplete process-tree teardown")
        tree.close()
        raise
    finally:
        if capture is not None:
            capture.close()


def launch_inert(plan, journal=None):
    _validate_plan(plan)
    raise Refused("Gate 2 is not authorized; inert dispatch adapter remains sealed")


def checked_sample(process):
    value = process.sample()
    keys = {"exit_code", "populated", "reaped", "cpu_seconds", "max_rss_bytes"}
    if not isinstance(value, dict) or set(value) != keys:
        raise Refused("incomplete process-tree sample")
    encoded(value)  # also rejects nonfinite measurements
    if (type(value["populated"]) is not bool or type(value["reaped"]) is not bool or
            (value["exit_code"] is not None and type(value["exit_code"]) is not int) or
            any(type(value[k]) not in (int, float) or value[k] < 0 for k in ("cpu_seconds", "max_rss_bytes")) or
            (value["reaped"] and value["exit_code"] is None)):
        raise Refused("contradictory process-tree sample")
    return value


def terminate_and_account(process, seconds):
    """Kill the owned domain even after leader exit; bounded wait/reap/account."""
    sample = None
    kill_ok = True
    try:
        process.terminate()
    except (OSError, Refused, KeyboardInterrupt):
        kill_ok = False
    try:
        deadline = time.monotonic() + seconds
        while True:
            sample = checked_sample(process)
            if not sample["populated"] and sample["reaped"]:
                return sample, kill_ok
            if time.monotonic() >= deadline:
                break
            time.sleep(0.01)
    except (OSError, Refused, KeyboardInterrupt):
        pass
    return sample, False


def collect_inert(plan, *, journal=None):
    """Bounded private-file collection. No PIPE or communicate allocation.

    The launch boundary remains sealed. A source-review double may return the
    same owned-tree interface. Success always requires separate raw review.
    """
    _validate_plan(plan)
    capture, process, status, sample = None, None, "launch-refused", None
    try:
        if journal is not None:
            if not isinstance(journal, Journal) or str(journal.root) != plan["root"]:
                raise Refused("matching owned journal required")
            capture = PrivateCapture(journal, plan["limits"])
        process = launch_inert(plan, journal)
        if capture is None:
            raise Refused("owned private capture required")
        deadline = time.monotonic() + plan["limits"]["wall_seconds"]
        while True:
            sample = checked_sample(process)
            sizes = capture.snapshot()
            if (any(n >= plan["limits"]["file_bytes"] for n in sizes.values()) or
                    sum(sizes.values()) >= plan["limits"]["output_bytes"]):
                status = "output-limit"
                break
            if sample["cpu_seconds"] > plan["limits"]["cpu_seconds"] or sample["max_rss_bytes"] > plan["limits"]["address_space_bytes"]:
                status = "resource-limit"
                break
            if sample["exit_code"] is not None:
                status = "child-process-escape" if sample["populated"] else (
                    "exited" if sample["exit_code"] == 0 else "early-failure")
                break
            if time.monotonic() >= deadline:
                status = "timeout"
                break
            time.sleep(0.01)
    except (OSError, Refused, KeyboardInterrupt):
        status = "launch-refused" if process is None else "interrupted"
    finally:
        # ALWAYS kill the owned cgroup, even after leader exit. setsid/double
        # fork does not escape membership. Never signal a discovered host PID.
        teardown_ok = process is None
        if process is not None:
            final_sample, teardown_ok = terminate_and_account(process, plan["limits"]["teardown_seconds"])
            if final_sample is not None:
                sample = final_sample
        if not teardown_ok:
            status = "teardown-incomplete"
    result = {"status": status, "accepted": False, "tree_empty": teardown_ok,
              "reaped": sample is not None and sample["reaped"],
              "exit_code": None if sample is None else sample["exit_code"]}
    if sample is not None:
        result["rusage"] = {k: sample[k] for k in ("cpu_seconds", "max_rss_bytes")}
    if capture is not None:
        try:
            sizes = capture.snapshot()
            if (teardown_ok and (any(v >= plan["limits"]["file_bytes"] for v in sizes.values()) or
                                 sum(sizes.values()) >= plan["limits"]["output_bytes"])):
                result["status"] = "output-limit"
            result.update({name: capture.read(name) for name in ("stdout", "stderr")})
            result["capture_sizes"] = sizes
        except (OSError, Refused):
            result["status"] = "capture-invalid"
        finally:
            capture.close()
    if process is not None and teardown_ok and hasattr(process, "close"):
        process.close()
    return result


def _json_record(raw, bound):
    if not isinstance(raw, bytes) or not raw or len(raw) > bound:
        raise Refused("missing/oversized raw JSON")
    try:
        return json.loads(raw, object_pairs_hook=_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(Refused("nonfinite JSON")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise Refused("partial/malformed raw JSON") from exc


def parse_mountinfo(raw):
    """Preserve every mount, its backing identity, flags and propagation data.

    No normalization into the intended plan: unknown submounts remain visible.
    Escaped/stacked targets are conservatively refused, never hidden by a dict.
    """
    if not isinstance(raw, str) or len(raw) > 65536 or not raw.endswith("\n"):
        raise Refused("partial/oversized mountinfo")
    records, ids, targets = [], set(), set()
    for line in raw.splitlines():
        fields = line.split()
        try:
            split = fields.index("-")
            if split < 6 or len(fields) != split + 4:
                raise ValueError
            mid, parent = int(fields[0]), int(fields[1])
            target = fields[4]
            _path(target)
            if (mid <= 0 or parent < 0 or mid in ids or target in targets or
                    "\\" in line or not re.fullmatch(r"[0-9]+:[0-9]+", fields[2])):
                raise ValueError
            options = fields[5].split(",")
            if len(set(options) & {"ro", "rw"}) != 1:
                raise ValueError
            records.append({"id": mid, "parent": parent, "device": fields[2],
                            "root": fields[3], "target": target, "options": options,
                            "optional": fields[6:split], "fstype": fields[split+1],
                            "source": fields[split+2], "super_options": fields[split+3].split(","),
                            "readonly": "ro" in options, "noexec": "noexec" in options})
            ids.add(mid)
            targets.add(target)
        except (ValueError, IndexError) as exc:
            raise Refused("ambiguous/malformed mount graph") from exc
    if not records or "/" not in targets:
        raise Refused("missing root mount")
    return records


def parse_trace(raw):
    """Strict strace -f -ttt records, including resumed calls and terminal events.

    This is a raw-observation adapter, not a syscall-policy or write attestation.
    Retain all calls, including failures, for independent boundary review.
    """
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_FILE or not raw.endswith(b"\n"):
        raise Refused("partial/oversized trace")
    try:
        lines = raw.decode("ascii").splitlines()
    except UnicodeError as exc:
        raise Refused("non-ASCII trace") from exc
    seen, ended, born, execs, calls, pending = set(), {}, set(), [], [], {}
    for line in lines:
        match = re.fullmatch(r"([1-9][0-9]*)\s+([0-9]+\.[0-9]+)\s+(.+)", line)
        if match is None:
            raise Refused("unparsed trace line, tracer error or lost process")
        pid, timestamp, body = int(match[1]), match[2], match[3]
        if pid in ended:
            raise Refused("records after process exit")
        seen.add(pid)
        terminal = re.fullmatch(r"\+\+\+ (exited with ([0-9]+)|killed by ([A-Z0-9]+)(?: \(core dumped\))?) \+\+\+", body)
        if terminal:
            ended[pid] = body
            continue
        if body.startswith("--- ") and body.endswith(" ---"):
            calls.append({"pid": pid, "timestamp": timestamp, "signal": body})
            continue
        if body.endswith(" <unfinished ...>"):
            if pid in pending:
                raise Refused("duplicate unfinished trace call")
            pending[pid] = body.removesuffix(" <unfinished ...>")
            continue
        resumed = re.fullmatch(r"<\.\.\. ([a-zA-Z0-9_]+) resumed>(.*)", body)
        if resumed:
            prefix = pending.pop(pid, None)
            if prefix is None or not prefix.startswith(resumed[1] + "("):
                raise Refused("unmatched resumed call")
            body = prefix + resumed[2]
        call = re.fullmatch(r"([a-zA-Z0-9_]+)\((.*)\)\s+=\s+(.+?)(?: <[0-9.]+>)?", body)
        if call is None or "..." in call[2] or "???" in body:
            raise Refused("unparsed or truncated syscall")
        name, args, result = call.groups()
        calls.append({"pid": pid, "timestamp": timestamp, "syscall": name,
                      "arguments": args, "result": result})
        if name in ("clone", "clone3", "fork", "vfork") and re.fullmatch(r"[1-9][0-9]*", result):
            born.add(int(result))
        if name in ("execve", "execveat") and result == "0":
            path = re.match(r'"([^"\\]+)"', args) if name == "execve" else None
            if path is None:
                raise Refused("unsupported successful exec identity")
            execs.append(path[1])
    if pending or seen != set(ended) or not born <= seen or len(seen - born) != 1:
        raise Refused("incomplete process lifetime or birth accounting")
    return {"pids": sorted(seen), "execs": execs, "calls": calls,
            "terminal_records": ended, "trace_sha256": digest(raw)}


def adapt_raw_evidence(plan, journal, outcome):
    """Decode bounded raw files into observations. Never fill gaps from a plan.

    All observations and the original files need independent review. Host-side
    namespace, mount-source and pre-main provenance evidence remains separate.
    This function has no accepted/authorized/attested outcome.
    """
    _validate_plan(plan)
    if not isinstance(journal, Journal) or str(journal.root) != plan["root"]:
        raise Refused("matching private journal required")
    capture = PrivateCapture(journal, plan["limits"])
    try:
        sizes = capture.snapshot()
        if any(v >= plan["limits"]["file_bytes"] for v in sizes.values()) or sum(sizes.values()) >= plan["limits"]["output_bytes"]:
            raise Refused("truncated/overflowed raw evidence")
        raw = {name: capture.read(name) for name in capture.fds}
    finally:
        capture.close()
    probe = _json_record(raw["stdout"], plan["limits"]["file_bytes"])
    expected = {"schema_version", "pid", "ppid", "namespaces", "proc_pid_namespace", "mountinfo", "status",
                "fds", "environment", "dumpable", "no_new_privs", "seccomp_mode", "denials", "sentinels", "limits"}
    if not isinstance(probe, dict) or set(probe) != expected or type(probe["schema_version"]) is not int or probe["schema_version"] != 1:
        raise Refused("incomplete/unknown probe record")
    for name in ("pid", "ppid", "dumpable", "no_new_privs", "seccomp_mode"):
        if type(probe[name]) is not int or probe[name] < 0:
            raise Refused("invalid raw integer")
    namespaces = probe["namespaces"]
    if not isinstance(namespaces, dict) or set(namespaces) != set(load_profile()["namespaces"]):
        raise Refused("partial namespace inventory")
    for name, value in namespaces.items():
        prefix = "mnt" if name == "mnt" else name
        if not isinstance(value, str) or not re.fullmatch(prefix + r":\[[1-9][0-9]*\]", value):
            raise Refused("invalid namespace identity")
    parent_raw, _ = _read_file(journal.root / "logs/parent-namespaces", 4096)
    parent_ns = _json_record(parent_raw, 4096)
    if not isinstance(parent_ns, dict) or set(parent_ns) != set(namespaces):
        raise Refused("missing parent namespace observations")
    for name, value in parent_ns.items():
        if (not isinstance(value, str) or not re.fullmatch(name + r":\[[1-9][0-9]*\]", value) or
                value == namespaces[name]):
            raise Refused("shared/malformed parent namespace")
    if probe["proc_pid_namespace"] != namespaces["pid"]:
        raise Refused("procfs belongs to a different PID namespace")
    mounts = parse_mountinfo(probe["mountinfo"])
    status = {}
    if not isinstance(probe["status"], str) or len(probe["status"]) > 65536:
        raise Refused("missing status inventory")
    for line in probe["status"].splitlines():
        key, separator, value = line.partition(":")
        if not separator or key in status:
            raise Refused("ambiguous status record")
        status[key] = value.strip()
    for name in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb"):
        if not re.fullmatch(r"0{16}", status.get(name, "")):
            raise Refused("nonzero/missing capability inventory")
    if status.get("NoNewPrivs") != "1" or status.get("Seccomp") != "2" or probe["dumpable"] != 0 or probe["no_new_privs"] != 1 or probe["seccomp_mode"] != 2:
        raise Refused("missing process security state")
    fds = probe["fds"]
    if (not isinstance(fds, list) or len(fds) != 3 or
            any(not isinstance(v, dict) or set(v) != {"fd", "mode", "dev", "ino", "cloexec"} or
                any(type(n) is not int or n < 0 for n in v.values()) for v in fds)):
        raise Refused("malformed descriptor inventory")
    if encoded(sorted(fds, key=lambda v: v["fd"])) != encoded(stream_inventory(journal)):
        raise Refused("unexpected inherited descriptor")
    env = {}
    if not isinstance(probe["environment"], list):
        raise Refused("missing raw environment")
    for entry in probe["environment"]:
        if not isinstance(entry, str) or "=" not in entry:
            raise Refused("malformed raw environment")
        key, value = entry.split("=", 1)
        if key in env:
            raise Refused("duplicate environment name")
        env[key] = value
    if encoded(env) != encoded(plan["environment"]):
        raise Refused("unexpected environment")
    expected_denials = {n: 1 for n in ("socket", "clone", "unshare", "ptrace", "mount", "execve", "io_uring_setup")}
    if encoded(probe["denials"]) != encoded(expected_denials):
        raise Refused("missing/contradictory syscall observations")
    if encoded(probe["sentinels"]) != encoded({"readonly_errno": 30, "hidden_errno": 2, "output_bytes": 17}):
        raise Refused("missing/contradictory filesystem observations")
    bounds = plan["limits"]
    expected_limits = {"cpu": [bounds["cpu_seconds"]] * 2, "address_space": [bounds["address_space_bytes"]] * 2,
                       "file_size": [bounds["file_bytes"]] * 2, "open_files": [bounds["open_files"]] * 2,
                       "processes": [bounds["processes"]] * 2, "core": [0, 0]}
    if encoded(probe["limits"]) != encoded(expected_limits):
        raise Refused("missing/changed raw resource limits")
    trace = parse_trace(raw["trace"])
    if trace["execs"] != [plan["argv"][plan["argv"].index("--")+1], load_profile()["executable"]]:
        raise Refused("unexpected executable history")
    # bwrap JSON is a stream of records, not a trusted success Boolean.
    statuses = [_json_record(line, 4096) for line in raw["status"].splitlines() if line]
    if not statuses or any(not isinstance(item, dict) for item in statuses):
        raise Refused("partial launcher status stream")
    starts = [item["child-pid"] for item in statuses if "child-pid" in item]
    exits = [item["exit-code"] for item in statuses if "exit-code" in item]
    if (len(starts) != 1 or type(starts[0]) is not int or starts[0] <= 0 or
            len(exits) != 1 or type(exits[0]) is not int or exits[0] != 0 or
            starts[0] not in trace["pids"] or trace["terminal_records"][starts[0]] != "+++ exited with 0 +++"):
        raise Refused("launcher PID/exit contradicts complete trace")
    if not isinstance(outcome, dict):
        raise Refused("missing lifetime accounting")
    if (not isinstance(outcome, dict) or outcome.get("status") != "exited" or outcome.get("tree_empty") is not True or
            outcome.get("reaped") is not True or
            type(outcome.get("exit_code")) is not int or outcome["exit_code"] != 0):
        raise Refused("incomplete lifetime accounting")
    usage = outcome.get("rusage")
    if not isinstance(usage, dict) or set(usage) != {"cpu_seconds", "max_rss_bytes"}:
        raise Refused("missing aggregate lifetime resource accounting")
    encoded(usage)
    for key, bound in (("cpu_seconds", bounds["cpu_seconds"]), ("max_rss_bytes", bounds["address_space_bytes"])):
        if type(usage[key]) not in (int, float) or not 0 <= usage[key] <= bound:
            raise Refused("aggregate resource accounting exceeds limit")
    # Only purpose-created files are inspected. Never inspect host HOME/Plasma.
    preserved = {}
    for name in ("inputs/readonly-sentinel", "unexposed/sentinel", "inputs/outer-filter.bpf",
                 "etc/passwd", "etc/group", "etc/nsswitch.conf"):
        preserved[name] = verify_receipt(journal.root / name, journal.files[name])
    output, output_identity = _read_file(journal.root / "out/sentinel", 64)
    if output != b"panda-inert-output" or stat.S_IMODE(output_identity["mode"]) != 0o600:
        raise Refused("unexpected output sentinel")
    inventory = post_exit_inventory(journal)
    return {"status": "raw-observations-only", "probe": probe, "parent_namespaces": parent_ns,
            "mounts": mounts, "status_fields": status, "post_exit_inventory": inventory,
            "trace": trace, "launcher_records": statuses, "lifetime": outcome,
            "preserved": preserved, "output_identity": output_identity,
            "raw_sha256": {name: digest(value) for name, value in raw.items()},
            "unresolved": load_profile()["blockers"]}


def post_exit_inventory(journal):
    """Bounded, flat inventory of only this run; no recursive symlink traversal."""
    journal.chain.verify()
    result = {}
    count = 0
    top_files = {name for name in journal.files if "/" not in name}
    top_names = set()
    with os.scandir(journal.chain.fd) as entries:
        for entry in entries:
            count += 1
            if count > 128:
                raise Refused("post-exit root inventory exceeds contract")
            top_names.add(entry.name)
    if top_names != top_files | set(journal.dirs):
        raise Refused("unknown/missing post-exit root object")
    for name in top_files:
        result[name] = verify_receipt(journal.root / name, journal.files[name])
    for directory, binding in journal.dirs.items():
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=journal.chain.fd)
        try:
            if _binding(os.fstat(fd)) != binding:
                raise Refused("post-exit directory replaced")
            with os.scandir(fd) as entries:
                for entry in entries:
                    count += 1
                    if count > 128 or not re.fullmatch(r"[A-Za-z0-9_.-]+", entry.name):
                        raise Refused("post-exit inventory exceeds contract")
                    relative = directory + "/" + entry.name
                    result[relative] = file_receipt(journal.root / relative, max_bytes=MAX_FILE)
            if _binding(os.stat(directory, dir_fd=journal.chain.fd, follow_symlinks=False)) != binding:
                raise Refused("post-exit directory binding changed")
        finally:
            os.close(fd)
    journal.chain.verify()
    return result


def validate_evidence(plan, evidence, *, journal=None):
    """Consistency check of normalized private evidence, never authentication.

    Raw trace/probe/status/journal must be independently examined. No parser or
    caller-supplied booleans are sufficient proof; the sealed dispatcher cannot
    currently generate this envelope. Fixtures exercise its refusal contract.
    """
    _validate_plan(plan)
    keys = {"profile_sha256", "plan_sha256", "exit_code", "timed_out", "reaped", "trace_complete",
            "trace_sha256", "namespaces", "proc_pid_namespace", "mounts", "environment", "fds",
            "cap_eff", "no_new_privs", "dumpable", "denials", "readonly_errno", "hidden_errno",
            "sentinels_preserved", "provenance_verified", "journal_verified", "limits",
            "unexpected_writes", "unexpected_execs", "rusage", "streams"}
    if not isinstance(evidence, dict) or set(evidence) != keys:
        raise Refused("missing/unknown evidence fields")
    if len(encoded(evidence)) > 262144:
        raise Refused("evidence exceeds bound")
    if not isinstance(journal, Journal) or str(journal.root) != plan["root"]:
        raise Refused("owned private journal required for stream identities")
    if encoded(evidence["streams"]) != encoded(stream_inventory(journal)):
        raise Refused("standard descriptors are not the expected private regular files")
    for key, expected in (("profile_sha256", plan["profile_sha256"]), ("plan_sha256", plan["plan_sha256"]),
                          ("mounts", plan["mounts"]), ("environment", plan["environment"]),
                          ("fds", [0, 1, 2]), ("limits", plan["limits"]),
                          ("unexpected_writes", []), ("unexpected_execs", [])):
        if encoded(evidence[key]) != encoded(expected):
            raise Refused("evidence mismatch: " + key)
    for key, expected in (("exit_code", 0), ("cap_eff", 0), ("no_new_privs", 1),
                          ("dumpable", 0), ("hidden_errno", 2)):
        if type(evidence[key]) is not int or evidence[key] != expected:
            raise Refused("invalid measured integer: " + key)
    for key in ("reaped", "trace_complete", "sentinels_preserved", "provenance_verified", "journal_verified"):
        if evidence[key] is not True:
            raise Refused("incomplete evidence: " + key)
    if (evidence["timed_out"] is not False or type(evidence["readonly_errno"]) is not int or
            evidence["readonly_errno"] not in (13, 30)):
        raise Refused("timeout or writable readonly sentinel")
    if not isinstance(evidence["trace_sha256"], str) or not re.fullmatch("[0-9a-f]{64}", evidence["trace_sha256"]):
        raise Refused("missing complete trace identity")
    ns = evidence["namespaces"]
    names = set(load_profile()["namespaces"])
    if not isinstance(ns, dict) or set(ns) != names:
        raise Refused("missing namespace")
    for pair in ns.values():
        if (not isinstance(pair, dict) or set(pair) != {"parent", "child"} or
                any(not isinstance(v, str) or not v for v in pair.values()) or pair["parent"] == pair["child"]):
            raise Refused("shared or missing namespace")
    if evidence["proc_pid_namespace"] != ns["pid"]["child"]:
        raise Refused("procfs not bound to child pid namespace")
    denials = {name: 1 for name in ("socket", "clone", "unshare", "ptrace", "mount", "execve", "io_uring_setup")}
    if encoded(evidence["denials"]) != encoded(denials):
        raise Refused("missing/wrong syscall denials")
    usage = evidence["rusage"]
    bounds = {"cpu_seconds": plan["limits"]["cpu_seconds"],
              "max_rss_bytes": plan["limits"]["address_space_bytes"],
              "output_bytes": plan["limits"]["output_bytes"]}
    if not isinstance(usage, dict) or set(usage) != set(bounds):
        raise Refused("missing resource accounting")
    for key, bound in bounds.items():
        if type(usage[key]) not in (int, float) or not 0 <= usage[key] <= bound:
            raise Refused("resource bound exceeded")
    return {"status": "review-candidate", "gate2_authorized": False,
            "native_runtime_verified": False, "independent_raw_review_required": True}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Gate 1 inert source review only; no execution mode")
    parser.add_argument("--plan", action="store_true", help="emit fixed policy and blockers only")
    parser.parse_args(argv)
    profile = load_profile()
    print(json.dumps({"status": "execution-refused", "profile_sha256": PROFILE_SHA256,
                      "executable": profile["executable"], "blockers": profile["blockers"],
                      "filter_sha256": digest(compile_filter()),
                      "source_receipts": {name: file_receipt(HERE / name) for name in
                                          ("sandbox_supervisor.py", "inert_probe.c")},
                      "candidate_pins": profile["candidate_pins"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
