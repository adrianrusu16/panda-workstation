"""B3B1 fixture-only, file-only prototype and frozen stdlib recovery artifact.

Directories belong to the separate operator, never to this engine/provider.
Checksums and advisory locks assume a cooperative sole user, not hostile UID peers.
No entrypoint is connected to panda-theme or accepts a live destination.
"""

import base64
from contextlib import contextmanager
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

SOURCE = "source/home/dot_config/ghostty/config.ghostty"
DEPLOYED = "config/ghostty/config.ghostty"
TARGET = "config/panda/generated/ghostty.conf"
SUPPORT = "state/panda-ghostty-b3b-canary"
PROGRAM = SUPPORT + "/canary.py"
SOURCE_BEFORE = SUPPORT + "/source.before"
DEPLOYED_BEFORE = SUPPORT + "/deployed.before"
LOCK = SUPPORT + "/lock"
PROVISION = SUPPORT + "/provisioning.json"
BASELINE = SUPPORT + "/baseline.json"
JOURNAL = SUPPORT + "/journal.json"
CLEANUP = SUPPORT + "/cleanup.json"
OUTPUT_DIRS = ("config/panda", "config/panda/generated")
FIXED_DIRS = ("home", "config", "data", "state", "cache", "runtime", "source",
              "source/home", "source/home/dot_config", "source/home/dot_config/ghostty",
              "config/ghostty", SUPPORT)
MANAGED = (TARGET, SOURCE, DEPLOYED)
STAGES = {p: p.rsplit("/", 1)[0] + "/." + p.rsplit("/", 1)[1] + ".panda-b3b-stage"
          for p in (*MANAGED, JOURNAL, PROVISION, CLEANUP)}
# Preserve the complete numbered host role manifest in an exact fixture mapping.
ROLES = (SOURCE, DEPLOYED, *OUTPUT_DIRS, TARGET, SUPPORT, PROGRAM, SOURCE_BEFORE,
         DEPLOYED_BEFORE, LOCK, PROVISION, BASELINE, JOURNAL, CLEANUP,
         STAGES[SOURCE], STAGES[DEPLOYED], STAGES[TARGET], STAGES[JOURNAL],
         STAGES[PROVISION], STAGES[CLEANUP], SOURCE.rsplit("/", 1)[0],
         DEPLOYED.rsplit("/", 1)[0], "config", "state")
FILES = frozenset((*MANAGED, PROGRAM, SOURCE_BEFORE, DEPLOYED_BEFORE, LOCK,
                   PROVISION, BASELINE, JOURNAL, CLEANUP, *STAGES.values()))
SCOPE = "b3b1-file-only-fixture"
LIMIT = 1024 * 1024
BASE_HASH = "87d967432b7086b7c746929ce712a2dc5b2fc40899c2faf4456d16e6d234c359"
HOOK_HASH = "408e26c4b9e6a89728276051670a37ca2bd8ba11c8ea675ff7631bbfec2977b6"
MINIMAL_HASH = "5241a5b1d58bb15fa5d72e48bd8b9a1b89f12b4cddabb9474fcbc59e376ab03d"
HOOK = b"config-file = ?../panda/generated/ghostty.conf\n"
MINIMAL = b"""# Panda Theme fixture fragment: Ghostty
background = #0B0D0F
foreground = #F1F3F4
cursor-color = #DDE3E6
selection-background = #335B49
selection-foreground = #F1F3F4
background-opacity = 1
palette = 0=#0B0D0F
palette = 1=#E99089
palette = 2=#6FCF97
palette = 3=#D6B96A
palette = 4=#DDE3E6
palette = 5=#DDE3E6
palette = 6=#DDE3E6
palette = 7=#F1F3F4
palette = 8=#8B949E
palette = 9=#E99089
palette = 10=#6FCF97
palette = 11=#D6B96A
palette = 12=#DDE3E6
palette = 13=#DDE3E6
palette = 14=#DDE3E6
palette = 15=#F1F3F4
"""
FORWARD = tuple((kind, path) for path in MANAGED for kind in ("stage", "publish"))
REVERSE = (("stage", DEPLOYED), ("publish", DEPLOYED), ("stage", SOURCE),
           ("publish", SOURCE), ("unlink", TARGET))
PIN_KEYS = {"dev", "ino", "uid", "gid", "mode", "mount"}
IMAGE_KEYS = {"data", "sha256", "mode", "uid", "gid", "atime", "mtime"}
RESTORED = "files-restored / manual-directory-cleanup-pending"
CLOSED = "fully-restored after verified cleanup"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n"


def pack(value):
    raw = canonical({"payload": value, "sha256": digest(canonical(value))})
    require(len(raw) <= LIMIT, "record too large")
    return raw


def _unique(pairs):
    result = {}
    for k, v in pairs:
        require(k not in result, "duplicate key")
        result[k] = v
    return result


def unpack(raw):
    require(isinstance(raw, bytes) and len(raw) <= LIMIT, "record bound")
    try:
        value = json.loads(raw, object_pairs_hook=_unique)
        require(isinstance(value, dict) and set(value) == {"payload", "sha256"}, "envelope fields")
        require(pack(value["payload"]) == raw, "noncanonical/corrupt record")
    except RecursionError as error:
        raise ValueError("record nesting exceeds parser bound") from error
    return value["payload"]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def keys(value, expected):
    require(isinstance(value, dict) and set(value) == set(expected), "unexpected fields")


def integer(value):
    require(type(value) is int and 0 <= value < 2**63, "invalid integer")


def validate_pin(pin, mode):
    keys(pin, PIN_KEYS)
    for v in pin.values():
        integer(v)
    require(pin["uid"] == os.getuid() and pin["gid"] == os.getgid() and pin["mode"] == mode,
            "unsafe pin ownership/mode")


def validate_id(value):
    require(isinstance(value, str) and len(value) == 32 and
            all(c in "0123456789abcdef" for c in value), "invalid enrollment ID")


def validate_object(obj, mode, *, authority=False):
    keys(obj, {"image", "pin", "ctime_ns"} if authority else {"image", "pin"})
    decode(obj["image"])
    validate_pin(obj["pin"], mode)
    require(obj["image"]["mode"] == mode, "image/pin mode differs")
    if authority:
        integer(obj["ctime_ns"])


def image(raw, mode=0o600, atime=0, mtime=0):
    return dict(data=base64.b64encode(raw).decode(), sha256=digest(raw), mode=mode,
                uid=os.getuid(), gid=os.getgid(), atime=atime, mtime=mtime)


def decode(value):
    keys(value, IMAGE_KEYS)
    for k in ("mode", "uid", "gid", "atime", "mtime"):
        integer(value[k])
    require(value["mode"] in (0o600, 0o644) and value["uid"] == os.getuid() and
            value["gid"] == os.getgid(), "unsupported file metadata")
    require(isinstance(value["data"], str) and len(value["data"]) <= 4 * LIMIT // 3 + 4,
            "image size bound")
    raw = base64.b64decode(value["data"], validate=True)
    require(len(raw) <= LIMIT and digest(raw) == value["sha256"] and
            base64.b64encode(raw).decode() == value["data"], "corrupt image")
    return raw


def namespace():
    return {n: os.readlink("/proc/self/ns/" + n) for n in ("mnt", "user")}


def tmp_identity(fd):
    s = os.fstat(fd)
    with open("/proc/self/uid_map", encoding="ascii") as f:
        root_mapped = any(int(line.split()[0]) == 0 for line in f)
    # A rootless test namespace can show the parent as the overflow UID.
    # Never learn an arbitrary owner or relax private child ownership.
    require(s.st_uid == (0 if root_mapped else 65534) and
            stat.S_IMODE(s.st_mode) == 0o1777 and not os.listxattr(fd), "unsafe tmp parent")
    return [s.st_dev, s.st_ino, s.st_uid, s.st_gid, stat.S_IMODE(s.st_mode), mount(fd)]


def mount(fd):
    with open("/proc/self/fdinfo/" + str(fd), encoding="ascii") as f:
        for line in f:
            if line.startswith("mnt_id:"):
                return int(line.split()[1])
    raise ValueError("mount identity unavailable")


def _checkpoint(name):
    """Private observation point for controlled fixture faults, never a CLI option."""


class FS:
    """Fixed-role descriptor traversal. Opening never grants enrollment authority."""

    def __init__(self, root, pins=None):
        raw = os.fspath(root)
        require(isinstance(raw, str) and raw.startswith("/tmp/panda-theme-b3b1-") and
                raw.count("/") == 2 and len(raw) > len("/tmp/panda-theme-b3b1-") and
                "/.." not in raw and "\x00" not in raw, "invalid fixture root")
        self.root = raw
        self.pins = dict(pins or {})
        self.fds = {}
        self.ns = namespace()
        self.tmp = None
        self.fd = None
        try:
            # Opening a directory FD without reading its entries does not change
            # atime. O_NOATIME requires ownership and is inappropriate for /tmp.
            self.tmp = os.open("/tmp", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            self.tmp_pin = tmp_identity(self.tmp)
            self.fd = os.open(raw.split("/")[-1], os.O_RDONLY | os.O_DIRECTORY |
                              os.O_NOFOLLOW | os.O_NOATIME, dir_fd=self.tmp)
            self.fds[""] = self.fd
            root_pin = self.pin(self.fd)
            if "" in self.pins:
                require(root_pin == self.pins[""], "root replacement")
        except BaseException:
            self.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        for fd in set(self.fds.values()):
            os.close(fd)
        self.fds.clear()
        if self.tmp is not None:
            os.close(self.tmp)
            self.tmp = None

    def pin(self, fd, file=False):
        s = os.fstat(fd)
        mode = stat.S_IMODE(s.st_mode)
        require((stat.S_ISREG(s.st_mode) if file else stat.S_ISDIR(s.st_mode)) and
                s.st_uid == os.getuid() and s.st_gid == os.getgid() and
                mode in ((0o600, 0o644) if file else (0o700,)) and not os.listxattr(fd),
                "unsafe type/owner/mode/ACL/xattrs")
        if file:
            require(s.st_nlink == 1 and s.st_size <= LIMIT, "unsafe links/size")
        else:
            # Refuse potential separately mounted/subvolume roots; no storage probing.
            require(s.st_ino != 256, "unapproved subvolume characteristic")
        m = mount(fd)
        if self.fd is not None:
            require(m == mount(self.fd), "redirected mount")
        return dict(dev=s.st_dev, ino=s.st_ino, uid=s.st_uid, gid=s.st_gid, mode=mode, mount=m)

    def directory(self, path):
        require(path in ("", *FIXED_DIRS, *OUTPUT_DIRS), "directory role not allowlisted")
        if path not in self.fds:
            parent, _, name = path.rpartition("/")
            parent_fd = self.directory(parent)
            fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NOATIME,
                         dir_fd=parent_fd)
            try:
                actual = self.pin(fd)
                if path in self.pins:
                    require(actual == self.pins[path], "directory replacement")
                self.fds[path] = fd
            except BaseException:
                os.close(fd)
                raise
        self.bind(path, self.fds[path])
        return self.fds[path]

    def bind(self, path, fd):
        require(namespace() == self.ns, "namespace drift")
        tmp = os.open("/tmp", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        current = None
        try:
            require(tmp_identity(tmp) == self.tmp_pin, "tmp binding drift")
            current = os.open(self.root.split("/")[-1], os.O_RDONLY | os.O_DIRECTORY |
                              os.O_NOFOLLOW | os.O_NOATIME, dir_fd=tmp)
            require(self.pin(current) == self.pin(self.fd), "stale root descriptor")
            if path:
                prefix = ""
                for part in path.split("/"):
                    nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW |
                                  os.O_NOATIME, dir_fd=current)
                    os.close(current)
                    current = nxt
                    prefix = prefix + "/" + part if prefix else part
                    actual = self.pin(current)
                    if prefix in self.pins:
                        require(actual == self.pins[prefix], "ancestor binding drift")
            require(self.pin(current) == self.pin(fd), "stale directory descriptor")
        finally:
            if current is not None:
                os.close(current)
            os.close(tmp)

    def directory_witnesses(self, paths):
        return {p: self.pin(self.directory(p)) for p in ("", *paths)}

    def parent(self, path):
        require(path in FILES, "file role not allowlisted")
        parent, name = path.rsplit("/", 1)
        return parent, self.directory(parent), name

    def read(self, path, *, authority=False):
        parent, fd, name = self.parent(path)
        self.bind(parent, fd)
        try:
            s = os.stat(name, dir_fd=fd, follow_symlinks=False)
        except FileNotFoundError:
            self.bind(parent, fd)
            return None
        require(stat.S_ISREG(s.st_mode) and s.st_nlink == 1, "unsafe file type/links")
        handle = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NOATIME | os.O_NONBLOCK,
                         dir_fd=fd)
        try:
            pin = self.pin(handle, file=True)
            before = os.fstat(handle)
            chunks = []
            count = 0
            while True:
                raw = os.read(handle, min(65536, LIMIT + 1 - count))
                if not raw:
                    break
                chunks.append(raw)
                count += len(raw)
                require(count <= LIMIT, "read bound")
            after = os.fstat(handle)
            bound = os.stat(name, dir_fd=fd, follow_symlinks=False)
            require(before == after and bound == after and
                    (before.st_atime_ns, before.st_mtime_ns, before.st_ctime_ns) ==
                    (after.st_atime_ns, after.st_mtime_ns, after.st_ctime_ns) ==
                    (bound.st_atime_ns, bound.st_mtime_ns, bound.st_ctime_ns),
                    "file changed during read")
            self.bind(parent, fd)
            raw = b"".join(chunks)
            value = {"image": image(raw, pin["mode"], after.st_atime_ns, after.st_mtime_ns),
                     "pin": pin}
            if authority:
                value["ctime_ns"] = after.st_ctime_ns
            return value
        finally:
            os.close(handle)

    def expect(self, path, expected):
        actual = self.read(path, authority=expected is not None and "ctime_ns" in expected)
        if path == PROGRAM and actual is not None and expected is not None:
            # The interpreter reads its frozen script before our entrypoint runs.
            # Code read-atime is not a restoration promise; all other artifact
            # metadata, content/digest and pinned identity remain mandatory.
            actual["image"]["atime"] = expected["image"]["atime"]
        require(actual == expected, "unexpected object: " + path)

    def capture(self, path, expected):
        actual = self.read(path, authority=True)
        require(actual is not None and
                {k: actual[k] for k in ("image", "pin")} == expected,
                "created object changed before authority capture: " + path)
        return actual

    def entries(self, path, expected):
        fd = self.directory(path)
        require(set(os.listdir(fd)) == set(expected), "unexpected directory contents: " + path)
        self.bind(path, fd)

    def create(self, path, img):
        raw = decode(img)
        parent, fd, name = self.parent(path)
        self.expect(path, None)
        _checkpoint("before-create:" + path)
        self.bind(parent, fd)
        handle = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         img["mode"], dir_fd=fd)
        try:
            # Never repair ownership; stage must already have the requested identity.
            p = self.pin(handle, file=True)
            require(p["uid"] == img["uid"] and p["gid"] == img["gid"], "stage ownership")
            position = 0
            while position < len(raw):
                written = os.write(handle, raw[position:])
                require(written > 0, "short stage write")
                position += written
            os.utime(handle, ns=(img["atime"], img["mtime"]))
            os.fsync(handle)
            require(self.pin(handle, file=True) == p and
                    self.read(path) == {"image": img, "pin": p}, "unverified stage")
            self.bind(parent, fd)
            os.fsync(fd)
            _checkpoint("created:" + path)
            return {"image": img, "pin": p}
        finally:
            os.close(handle)

    def publish(self, path, staged, expected):
        stage = STAGES[path]
        parent, fd, name = self.parent(path)
        self.expect(path, expected)
        self.expect(stage, staged)
        handle = os.open(stage.rsplit("/", 1)[1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NOATIME,
                         dir_fd=fd)
        try:
            require(self.pin(handle, file=True) == staged["pin"], "stage descriptor mismatch")
            _checkpoint("before-publish:" + path)
            self.bind(parent, fd)
            self.expect(path, expected)
            self.expect(stage, staged)
            require(self.pin(handle, file=True) == staged["pin"], "stale staged descriptor")
            os.replace(stage.rsplit("/", 1)[1], name, src_dir_fd=fd, dst_dir_fd=fd)
            os.fsync(handle)
            os.fsync(fd)
            self.expect(path, staged)
            self.expect(stage, None)
            _checkpoint("published:" + path)
        finally:
            os.close(handle)

    def record(self, path, value, expected):
        staged = self.create(STAGES[path], image(pack(value)))
        self.publish(path, staged, expected)
        self.expect(path, staged)
        return staged

    def sync(self, removed=()):
        for path in sorted(FILES):
            if path in (TARGET, STAGES[TARGET]) and OUTPUT_DIRS[1] in removed:
                continue
            current = self.read(path)
            if current is not None:
                parent, fd, name = self.parent(path)
                handle = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NOATIME, dir_fd=fd)
                try:
                    require(self.pin(handle, file=True) == current["pin"], "sync binding drift")
                    os.fsync(handle)
                    self.bind(parent, fd)
                    self.expect(path, current)
                finally:
                    os.close(handle)
        # File data first, then all surviving parents/ancestors. Revalidation
        # by the caller follows this replay before any transactional write.
        for p in ("", *FIXED_DIRS, *OUTPUT_DIRS):
            if p not in removed:
                os.fsync(self.directory(p))


@contextmanager
def approved_program():
    """Freeze the complete stable source, retaining its descriptor through bootstrap.

    This checks consistency of the cooperative operator's source, not authenticity
    against a hostile same-UID writer. No source path is accepted from the caller.
    """
    handle = os.open(__file__, os.O_RDONLY | os.O_NOFOLLOW | os.O_NOATIME | os.O_NONBLOCK)
    try:
        before = os.fstat(handle)
        require(stat.S_ISREG(before.st_mode) and before.st_uid == os.getuid() and
                before.st_gid == os.getgid() and stat.S_IMODE(before.st_mode) in (0o600, 0o644) and
                before.st_nlink == 1 and 0 < before.st_size <= LIMIT and not os.listxattr(handle),
                "unsafe recovery source type/owner/mode/links/size/xattrs")

        def bound():
            def fingerprint(s):
                # stat_result sequence equality omits the precise timestamp fields.
                return tuple(getattr(s, k) for k in (
                    "st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink", "st_size",
                    "st_atime_ns", "st_mtime_ns", "st_ctime_ns"))
            require(fingerprint(os.fstat(handle)) == fingerprint(before) and
                    fingerprint(os.stat(__file__, follow_symlinks=False)) == fingerprint(before) and
                    not os.listxattr(handle),
                    "recovery source identity/metadata changed")

        bound()
        chunks, count = [], 0
        while True:
            try:
                raw = os.read(handle, min(65536, LIMIT + 1 - count))
            except InterruptedError:
                continue
            if not raw:
                break
            chunks.append(raw)
            count += len(raw)
            require(count <= LIMIT, "recovery source read bound")
        bound()
        require(count == before.st_size, "incomplete recovery source")
        program = b"".join(chunks)
        # Syntax checking never executes source; a complete but unusable bootstrap
        # must not authorize enrollment either.
        compile(program, __file__, "exec")
        yield program, bound
        bound()
    finally:
        os.close(handle)


class Provider:
    """Record explicitly operator-witnessed identities; never provision directories.

    Instances cannot resume interrupted provisioning. Retain evidence for inspection.
    Witnesses are trusted operator attestations, not defense against forged same-UID input.
    """

    def __init__(self, root, witnesses):
        require(set(witnesses) == {"", *FIXED_DIRS}, "incomplete operator witnesses")
        for pin in witnesses.values():
            validate_pin(pin, 0o700)
        self.fs = FS(root, witnesses)
        try:
            require(self.fs.directory_witnesses(FIXED_DIRS) == witnesses, "unattested root")
            self.p = None
            self.record = None
            self.enrolled = False
            self.seal_attempted = False
        except BaseException:
            self.fs.close()
            raise

    def close(self):
        self.fs.close()

    def checkpoint_matches(self):
        require(self.record is not None and unpack(decode(self.record["image"])) == self.p,
                "in-memory provisioning differs from durable checkpoint")
        self.fs.expect(PROVISION, self.record)

    def published_checkpoint(self, expected):
        return self.fs.capture(PROVISION, expected)

    def start(self):
        require(self.p is None, "provisioning is single use")
        fs = self.fs
        fs.entries(SUPPORT, ())
        for path in (PROGRAM, SOURCE_BEFORE, DEPLOYED_BEFORE, LOCK, PROVISION, BASELINE,
                     JOURNAL, CLEANUP, *STAGES.values()):
            if path == STAGES[TARGET]:
                continue
            fs.expect(path, None)
        require(not os.path.lexists(fs.root + "/" + OUTPUT_DIRS[0]), "output already exists")
        before = {p: fs.read(p) for p in (SOURCE, DEPLOYED)}
        for value in before.values():
            require(value is not None and value["image"]["mode"] == 0o644 and
                    value["image"]["sha256"] == BASE_HASH, "baseline bytes/mode differ")
        with approved_program() as (program, bound):
            bound()
            frozen = fs.create(PROGRAM, image(program))
            fs.expect(PROGRAM, frozen)  # exact complete bytes/digest and support metadata
            bound()
            support = {PROGRAM: frozen,
                       SOURCE_BEFORE: fs.create(SOURCE_BEFORE, image(decode(before[SOURCE]["image"]))),
                       DEPLOYED_BEFORE: fs.create(DEPLOYED_BEFORE, image(decode(before[DEPLOYED]["image"]))),
                       LOCK: fs.create(LOCK, image(b""))}
            bound()
            for path, expected in support.items():
                fs.expect(path, expected)
            support = {p: fs.capture(p, expected) for p, expected in support.items()}
            pending = dict(schema=2, scope=SCOPE, enrollment_id=os.urandom(16).hex(),
                           root=fs.root, ns=fs.ns, tmp=fs.tmp_pin, dirs=dict(fs.pins),
                           before=before, support=support, done=[], pending=None,
                           state="provisioning", preseal=None)
            record = fs.create(PROVISION, image(pack(pending)))
        # A visible bootstrap checkpoint cannot authorize continued provisioning
        # until the retained source's final binding check has also succeeded.
        self.p, self.record = pending, self.published_checkpoint(record)
        _checkpoint("provision:started")

    def directory_intent(self, path):
        require(self.p is not None and self.p["state"] == "provisioning" and
                not self.enrolled and self.p["pending"] is None and
                len(self.p["done"]) < 2 and path == OUTPUT_DIRS[len(self.p["done"])],
                "invalid provisioning transition")
        self.checkpoint_matches()
        require(not os.path.lexists(self.fs.root + "/" + path), "foreign output")
        self.p["pending"] = path
        self.record = self.published_checkpoint(self.fs.record(PROVISION, self.p, self.record))
        _checkpoint("provision:intent:" + path)

    def attest_directory(self, path, witness):
        require(self.p is not None and self.p["pending"] == path, "no directory intent")
        self.checkpoint_matches()
        validate_pin(witness, 0o700)
        actual = self.fs.pin(self.fs.directory(path))
        require(actual == witness, "operator witness mismatch")
        self.fs.pins[path] = witness
        fd = self.fs.directory(path)
        require(not os.listdir(fd), "foreign provisioned contents")
        os.fsync(fd)
        os.fsync(self.fs.directory(path.rpartition("/")[0]))
        self.p["dirs"][path] = witness
        self.p["done"].append(path)
        self.p["pending"] = None
        self.record = self.published_checkpoint(self.fs.record(PROVISION, self.p, self.record))
        _checkpoint("provision:attested:" + path)

    def seal(self):
        require(self.p is not None and self.p["state"] == "provisioning" and
                not self.seal_attempted and not self.enrolled and self.p["pending"] is None and
                self.p["done"] == list(OUTPUT_DIRS), "incomplete provisioning")
        self.seal_attempted = True
        self.checkpoint_matches()
        fs = self.fs
        for path, expected in {**self.p["before"], **self.p["support"]}.items():
            fs.expect(path, expected)
        for path in (TARGET, JOURNAL, CLEANUP, *STAGES.values()):
            fs.expect(path, None)
        require(fs.directory_witnesses((*FIXED_DIRS, *OUTPUT_DIRS)) == self.p["dirs"],
                "directory provenance changed")
        fs.entries(OUTPUT_DIRS[0], (OUTPUT_DIRS[1].rsplit("/", 1)[1],))
        fs.entries(OUTPUT_DIRS[1], ())
        fs.entries(SUPPORT, (p.rsplit("/", 1)[1] for p in (*self.p["support"], PROVISION)))
        fs.expect(PROVISION, self.record)
        fs.expect(BASELINE, None)
        preseal = self.record  # exact retained last durable checkpoint
        completed = {**self.p, "state": "completed", "preseal": preseal}
        # No self-pin or forward baseline reference: persist the receipt first.
        self.record = self.published_checkpoint(fs.record(PROVISION, completed, self.record))
        # Only a successfully returned publication supplies the completed state.
        self.p = unpack(decode(self.record["image"]))
        self.checkpoint_matches()
        receipt = self.record  # original post-publication pin/ctime, never a learned replacement
        fs.expect(PROVISION, receipt)
        value = dict(schema=2, scope=SCOPE, enrollment_id=self.p["enrollment_id"],
                     root=fs.root, ns=fs.ns, tmp=fs.tmp_pin, roles=list(ROLES),
                     dirs=self.p["dirs"], before=self.p["before"], support=self.p["support"],
                     preseal=preseal, completed_provisioning=receipt)
        baseline = fs.create(BASELINE, image(pack(value)))
        fs.sync()
        _checkpoint("provision:sealed")
        # Publication/durability can expose late changes to any prerequisite.
        # Reobserve the entire capability read-only against retained images and
        # identities, never learning a new baseline or repairing a failed seal.
        self.checkpoint_matches()
        fs.expect(BASELINE, baseline)
        enrollment, observed_baseline = load(fs)
        require(observed_baseline == baseline and
                enrollment == value,
                "sealed enrollment differs from retained capability")
        verify(fs, enrollment, baseline)
        # The last observation-to-return interval remains cooperative/non-atomic.
        self.enrolled = True


def load(fs):
    baseline = fs.read(BASELINE)
    require(baseline is not None, "fixture not explicitly enrolled")
    validate_pin(baseline["pin"], 0o600)
    e = unpack(decode(baseline["image"]))
    keys(e, {"schema", "scope", "enrollment_id", "root", "ns", "tmp", "roles", "dirs",
             "before", "support", "preseal", "completed_provisioning"})
    validate_id(e["enrollment_id"])
    require(type(e["schema"]) is int and e["schema"] == 2 and e["scope"] == SCOPE and
            e["root"] == fs.root and e["ns"] == fs.ns and e["roles"] == list(ROLES),
            "enrollment scope/namespace/roles differ")
    require(baseline["image"]["atime"] == baseline["image"]["mtime"] == 0,
            "unexpected baseline timestamps")
    require(e["tmp"] == fs.tmp_pin, "enrolled tmp binding differs")
    keys(e["dirs"], {"", *FIXED_DIRS, *OUTPUT_DIRS})
    for pin in e["dirs"].values():
        validate_pin(pin, 0o700)
    fs.pins = dict(e["dirs"])
    fs.directory("")
    keys(e["before"], {SOURCE, DEPLOYED})
    keys(e["support"], {PROGRAM, SOURCE_BEFORE, DEPLOYED_BEFORE, LOCK})
    for obj in e["before"].values():
        validate_object(obj, 0o644)
    for obj in (*e["support"].values(), e["preseal"], e["completed_provisioning"]):
        validate_object(obj, 0o600, authority=True)
    for path in (SOURCE, DEPLOYED):
        require(e["before"][path]["image"]["sha256"] == BASE_HASH, "before-image baseline differs")
    for backup, original in ((SOURCE_BEFORE, SOURCE), (DEPLOYED_BEFORE, DEPLOYED)):
        require(decode(e["support"][backup]["image"]) == decode(e["before"][original]["image"]),
                "independent before-image differs")
    require(decode(e["support"][LOCK]["image"]) == b"", "lock not empty")
    provision = unpack(decode(e["preseal"]["image"]))
    require(provision == dict(schema=2, scope=SCOPE, enrollment_id=e["enrollment_id"],
                              root=fs.root, ns=fs.ns, tmp=fs.tmp_pin,
                              dirs=e["dirs"], before=e["before"], support=e["support"],
                              done=list(OUTPUT_DIRS), pending=None, state="provisioning",
                              preseal=None), "preseal not complete")
    require(e["completed_provisioning"]["image"] == image(pack(
            {**provision, "state": "completed", "preseal": e["preseal"]})),
            "completed receipt differs from historical preseal")
    # Expected receipt authority comes solely from validated baseline content.
    # Never synthesize its expected identity from the object being validated.
    for p, obj in {**e["support"], PROVISION: e["completed_provisioning"]}.items():
        fs.expect(p, obj)
    fs.expect(BASELINE, baseline)
    return e, baseline


def proposals(e):
    result = {TARGET: image(MINIMAL)}
    require(len(MINIMAL) == 516 and digest(MINIMAL) == MINIMAL_HASH, "frozen Minimal differs")
    for path in (SOURCE, DEPLOYED):
        before = e["before"][path]["image"]
        raw = decode(before)
        require(len(raw) == 1376 and digest(raw) == BASE_HASH and raw.endswith(b"\n") and
                HOOK not in raw, "hook baseline invalid")
        result[path] = {**before, "data": base64.b64encode(raw + HOOK).decode(),
                        "sha256": digest(raw + HOOK)}
        require(len(raw + HOOK) == 1423 and result[path]["sha256"] == HOOK_HASH, "hook differs")
    return result


def new_journal(enrollment, proposed):
    e = unpack(decode(enrollment["image"]))
    return dict(schema=2, scope=SCOPE, enrollment_id=e["enrollment_id"],
                enrollment=digest(decode(enrollment["image"])),
                proposed=proposed, phase="applying", forward=[], reverse=[], intent=None,
                cleanup=None)


def model(j, e, baseline):
    keys(j, {"schema", "scope", "enrollment_id", "enrollment", "proposed", "phase", "forward", "reverse",
             "intent", "cleanup"})
    validate_id(j["enrollment_id"])
    require(type(j["schema"]) is int and j["schema"] == 2 and j["scope"] == SCOPE and
            j["enrollment_id"] == e["enrollment_id"] and
            j["enrollment"] == digest(decode(baseline["image"])) and
            j["proposed"] == proposals(e), "journal schema/images/binding")
    require(j["phase"] in ("applying", "installed", "recovering", "restored", "closed"),
            "invalid phase")
    require(isinstance(j["forward"], list) and len(j["forward"]) <= 6 and
            isinstance(j["reverse"], list) and len(j["reverse"]) <= 5, "operation bound")
    current = {TARGET: None, **e["before"]}
    stages = {p: None for p in MANAGED}
    identities = {(p["dev"], p["ino"]) for p in e["dirs"].values()}
    identities.update((v["pin"]["dev"], v["pin"]["ino"])
                      for v in (*e["before"].values(), *e["support"].values()))
    if j["phase"] in ("recovering", "restored", "closed"):
        require(len(j["forward"]) % 2 == 0, "recovery with an unpublished forward stage")
    for history, operations, restoring in ((j["forward"], FORWARD, False),
                                           (j["reverse"], REVERSE, True)):
        for index, record in enumerate(history):
            kind, path = operations[index]
            keys(record, {"op", "path", "stage", "skip"})
            require(record["op"] == kind and record["path"] == path and
                    type(record["skip"]) is bool, "unreachable operation history")
            wanted = e["before"].get(path, {}).get("image") if restoring else j["proposed"][path]
            skip = restoring and (current[path] is None if wanted is None else
                                  current[path] is not None and current[path]["image"] == wanted)
            if kind == "publish":
                skip = history[index - 1]["skip"]
            require(record["skip"] == skip, "impossible skipped operation")
            if kind == "stage":
                if skip:
                    require(record["stage"] is None, "skip stage has identity")
                else:
                    validate_pin(record["stage"], wanted["mode"])
                    pin = record["stage"]
                    identity = (pin["dev"], pin["ino"])
                    require(pin["ino"] > 0 and identity not in identities and
                            pin["dev"] == e["dirs"][""]["dev"] and
                            pin["mount"] == e["dirs"][""]["mount"], "impossible stage provenance")
                    identities.add(identity)
                    stages[path] = {"image": wanted, "pin": record["stage"]}
            elif kind == "publish":
                require(record["stage"] is None, "publication has new identity")
                if not skip:
                    require(stages[path] is not None, "publication without stage")
                    current[path] = stages[path]
                    stages[path] = None
            else:
                require(record["stage"] is None, "unlink has stage")
                current[path] = None
    if j["phase"] in ("applying", "installed"):
        require(not j["reverse"] and j["cleanup"] is None, "forward phase with recovery")
        if j["phase"] == "installed":
            require(len(j["forward"]) == 6 and j["intent"] is None, "incomplete installed record")
    if j["phase"] in ("restored", "closed"):
        require(len(j["reverse"]) == 5 and j["intent"] is None and
                all(s is None for s in stages.values()), "incomplete restored record")
    if j["phase"] != "closed":
        require(j["cleanup"] is None, "unexpected cleanup digest")
    else:
        require(isinstance(j["cleanup"], str) and len(j["cleanup"]) == 64, "missing closure receipt")
    intent = j["intent"]
    if intent is not None:
        require(j["phase"] in ("applying", "recovering"), "intent in completed phase")
        operations = FORWARD if j["phase"] == "applying" else REVERSE
        history = j["forward"] if j["phase"] == "applying" else j["reverse"]
        require(len(history) < len(operations) and intent == list(operations[len(history)]),
                "impossible outstanding intent")
    return current, stages


def cleanup_record(fs, e, baseline, j, journal):
    obj = fs.read(CLEANUP)
    if obj is None:
        require(j["phase"] != "closed", "closed without receipt")
        return None, []
    validate_pin(obj["pin"], 0o600)
    c = unpack(decode(obj["image"]))
    keys(c, {"schema", "scope", "enrollment_id", "enrollment", "checkpoint", "done", "pending"})
    validate_id(c["enrollment_id"])
    require(type(c["schema"]) is int and c["schema"] == 2 and c["scope"] == SCOPE and
            c["enrollment_id"] == e["enrollment_id"] and
            c["enrollment"] == digest(decode(baseline["image"])) and
            isinstance(c["done"], list) and c["done"] in
            ([], [OUTPUT_DIRS[1]], list(reversed(OUTPUT_DIRS))), "cleanup receipt scope/history")
    if j["phase"] == "closed":
        require(digest(decode(obj["image"])) == j["cleanup"] and
                c["done"] == list(reversed(OUTPUT_DIRS)) and c["pending"] is None,
                "closure receipt differs")
        anchor = {**j, "phase": "restored", "cleanup": None}
        require(c["checkpoint"] == digest(pack(anchor)), "closure checkpoint differs")
    else:
        require(j["phase"] == "restored" and c["checkpoint"] == digest(decode(journal["image"])),
                "cleanup before file-restored checkpoint")
    if c["pending"] is not None:
        require(len(c["done"]) < 2 and c["pending"] == list(reversed(OUTPUT_DIRS))[len(c["done"])],
                "invalid cleanup intent")
    return obj, c["done"]


def verify(fs, e, baseline, j=None, journal=None, *, operator_absence=None):
    require(fs.ns == e["ns"] and namespace() == e["ns"], "namespace binding differs")
    removed = []
    cleanup = None
    if j is not None:
        validate_pin(journal["pin"], 0o600)
        expected, stages = model(j, e, baseline)
        cleanup, removed = cleanup_record(fs, e, baseline, j, journal)
    else:
        expected, stages = {TARGET: None, **e["before"]}, {p: None for p in MANAGED}
        fs.expect(CLEANUP, None)
    if operator_absence is not None:
        require(cleanup is not None and j["phase"] == "restored" and
                unpack(decode(cleanup["image"]))["pending"] == operator_absence and
                operator_absence not in removed, "no durable operator removal intent")
        removed = [*removed, operator_absence]
    for p in ("", *FIXED_DIRS, *OUTPUT_DIRS):
        if p in removed:
            parent, _, name = p.rpartition("/")
            if parent not in removed:
                fd = fs.directory(parent)
                try:
                    os.stat(name, dir_fd=fd, follow_symlinks=False)
                except FileNotFoundError:
                    pass
                else:
                    raise ValueError("removed directory still present")
        else:
            require(fs.pin(fs.directory(p)) == e["dirs"][p], "pinned provenance differs")
    for p, obj in {**e["support"], PROVISION: e["completed_provisioning"], BASELINE: baseline}.items():
        fs.expect(p, obj)
    fs.expect(JOURNAL, journal)
    for p in MANAGED:
        if p == TARGET and OUTPUT_DIRS[1] in removed:
            require(expected[p] is None and stages[p] is None, "removed target parent before rollback")
            continue
        fs.expect(p, expected[p])
        fs.expect(STAGES[p], stages[p])
    for p in (JOURNAL, PROVISION, CLEANUP):
        fs.expect(STAGES[p], None)
    if cleanup is not None:
        fs.expect(CLEANUP, cleanup)
    support = {p.rsplit("/", 1)[1] for p in (*e["support"], PROVISION, BASELINE)}
    if journal is not None:
        support.add(JOURNAL.rsplit("/", 1)[1])
    if cleanup is not None:
        support.add(CLEANUP.rsplit("/", 1)[1])
    fs.entries(SUPPORT, support)
    if OUTPUT_DIRS[0] not in removed:
        fs.entries(OUTPUT_DIRS[0], () if OUTPUT_DIRS[1] in removed else
                   (OUTPUT_DIRS[1].rsplit("/", 1)[1],))
    if OUTPUT_DIRS[1] not in removed:
        names = {p.rsplit("/", 1)[1] for p, obj in
                 ((TARGET, expected[TARGET]), (STAGES[TARGET], stages[TARGET])) if obj is not None}
        fs.entries(OUTPUT_DIRS[1], names)
    return removed


def observe(fs):
    e, baseline = load(fs)
    journal = fs.read(JOURNAL)
    if journal is not None:
        validate_pin(journal["pin"], 0o600)
    j = unpack(decode(journal["image"])) if journal else None
    verify(fs, e, baseline, j, journal)
    return e, baseline, j, journal


@contextmanager
def locked(fs, e):
    fs.expect(LOCK, e["support"][LOCK])
    parent, fd, name = fs.parent(LOCK)
    handle = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NOATIME, dir_fd=fd)
    try:
        require(fs.pin(handle, file=True) == e["support"][LOCK]["pin"], "stale lock descriptor")
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fs.bind(parent, fd)
        fs.expect(LOCK, e["support"][LOCK])
        yield
        _checkpoint("before-unlock")
        fs.expect(LOCK, e["support"][LOCK])
    finally:
        os.close(handle)


def result(status, reason=None):
    value = {"status": status, "scope": SCOPE,
             "warnings": ["Fixture simulation only; no native or GUI validation.",
                          "Cooperative sole-user checks are not an atomic defense against UID peers."]}
    if reason:
        value["reason"] = str(reason)
    return value


def failure(error):
    transient = isinstance(error, OSError) and error.errno in (
        errno.EIO, errno.ENOSPC, errno.EDQUOT, errno.EAGAIN, errno.EBUSY)
    return result("incomplete" if transient else "manual-inspection-required", error)


def status(root):
    try:
        with FS(root) as fs:
            e, baseline, j, journal = observe(fs)
            state = "not-started" if j is None else {
                "applying": "incomplete", "installed": "installed", "recovering": "incomplete",
                "restored": RESTORED, "closed": CLOSED}[j["phase"]]
            current, stages = model(j, e, baseline) if j else (
                {TARGET: None, **e["before"]}, {p: None for p in MANAGED})
            receipt, removed = cleanup_record(fs, e, baseline, j, journal) if j else (None, [])
            missing = set(removed) | {p for p, obj in current.items() if obj is None}
            missing.update(STAGES[p] for p, obj in stages.items() if obj is None)
            missing.update(STAGES[p] for p in (JOURNAL, PROVISION, CLEANUP))
            if journal is None:
                missing.add(JOURNAL)
            if receipt is None:
                missing.add(CLEANUP)
            answer = {**result(state), "provenance": "verified-current-observation",
                    "read_only": True, "durability": "observed-checkpoint-only; recover replays sync",
                    "roles": list(ROLES), "proposed": {p: v["sha256"] for p, v in proposals(e).items()},
                    "baseline": {p: v["image"]["sha256"] for p, v in e["before"].items()},
                    "absent": [p for p in ROLES if p in missing]}
            verify(fs, e, baseline, j, journal)
            return answer
    except (OSError, ValueError, TypeError, KeyError) as error:
        return failure(error)


def preview(root):
    return status(root)


def commit(fs, j, journal):
    model(j, *load(fs))
    return fs.record(JOURNAL, j, journal)


def finish(fs, e, baseline, j, journal):
    removed = verify(fs, e, baseline, j, journal)
    fs.sync(removed)
    _checkpoint("after-final-sync")
    verify(fs, e, baseline, j, journal)


def step(fs, e, baseline, j, journal):
    restoring = j["phase"] == "recovering"
    history = j["reverse"] if restoring else j["forward"]
    operations = REVERSE if restoring else FORWARD
    kind, path = operations[len(history)]
    expected, stages = model(j, e, baseline)
    wanted = e["before"].get(path, {}).get("image") if restoring else j["proposed"][path]
    skip = restoring and (expected[path] is None if wanted is None else
                          expected[path] is not None and expected[path]["image"] == wanted)
    if kind == "publish":
        skip = history[-1]["skip"]
    verify(fs, e, baseline, j, journal)
    j["intent"] = [kind, path]
    journal = commit(fs, j, journal)
    _checkpoint("intent:" + kind + ":" + path)
    verify(fs, e, baseline, j, journal)
    stage_pin = None
    if not skip:
        if kind == "stage":
            stage_pin = fs.create(STAGES[path], wanted)["pin"]
        elif kind == "publish":
            fs.publish(path, stages[path], expected[path])
        else:
            parent, fd, name = fs.parent(path)
            fs.expect(path, expected[path])
            _checkpoint("before-unlink:" + path)
            fs.bind(parent, fd)
            fs.expect(path, expected[path])
            os.unlink(name, dir_fd=fd)
            os.fsync(fd)
            fs.expect(path, None)
            _checkpoint("unlinked:" + path)
    history.append(dict(op=kind, path=path, stage=stage_pin, skip=skip))
    j["intent"] = None
    journal = commit(fs, j, journal)
    _checkpoint("done:" + kind + ":" + path)
    return journal


def install_minimal(root):
    try:
        with FS(root) as fs:
            e, baseline, j, journal = observe(fs)
            require(j is None, "fixture is single use; recover existing transaction")
            with locked(fs, e):
                observe(fs)
                # Replay enrollment durability before creating any transaction
                # artifact, including after a seal publication's sync error.
                fs.sync()
                verify(fs, e, baseline)
                j = new_journal(baseline, proposals(e))
                journal = commit(fs, j, None)
                while len(j["forward"]) < 6:
                    journal = step(fs, e, baseline, j, journal)
                j["phase"] = "installed"
                journal = commit(fs, j, journal)
                finish(fs, e, baseline, j, journal)
            _checkpoint("before-success-return")
            verify(fs, e, baseline, j, journal)
            return result("installed")
    except (OSError, ValueError, TypeError, KeyError) as error:
        return failure(error)


def reconcile(fs, e, baseline, j, journal):
    """Only an attested stage identity authorizes replay of a publication intent.

    An exclusive stage created but never checkpointed is ambiguous and retained.
    Unknown record stages are never adopted or deleted.
    """
    current, stages = model(j, e, baseline)
    if j["intent"] is None:
        verify(fs, e, baseline, j, journal)
        return journal
    kind, path = j["intent"]
    history = j["forward"] if j["phase"] == "applying" else j["reverse"]
    completed = False
    if kind == "publish" and stages[path] is not None:
        actual = fs.read(path)
        staged = fs.read(STAGES[path])
        if actual == stages[path] and staged is None:
            # Validate all other roles against the single reachable post-intent model.
            j["intent"] = None
            history.append(dict(op=kind, path=path, stage=None, skip=False))
            verify(fs, e, baseline, j, journal)
            fs.sync()
            verify(fs, e, baseline, j, journal)
            completed = True
    elif kind == "unlink" and current[path] is not None and fs.read(path) is None:
        j["intent"] = None
        history.append(dict(op=kind, path=path, stage=None, skip=False))
        verify(fs, e, baseline, j, journal)
        fs.sync()
        verify(fs, e, baseline, j, journal)
        completed = True
    if not completed:
        verify(fs, e, baseline, j, journal)
        j["intent"] = None
    return commit(fs, j, journal)


def recover(root):
    try:
        with FS(root) as fs:
            # A persisted publication intent may have its one allowed after-state.
            e, baseline = load(fs)
            journal = fs.read(JOURNAL)
            j = unpack(decode(journal["image"])) if journal else None
            if j is None:
                verify(fs, e, baseline)
                return result("not-started")
            model(j, e, baseline)
            # Pre-lock validation, including reachable post-intent state, must be write-free.
            probe = json.loads(json.dumps(j))
            if probe["intent"]:
                kind, path = probe["intent"]
                current, stages = model(probe, e, baseline)
                if kind == "publish" and stages[path] is not None and fs.read(path) == stages[path] and fs.read(STAGES[path]) is None:
                    history = probe["forward"] if probe["phase"] == "applying" else probe["reverse"]
                    history.append(dict(op=kind, path=path, stage=None, skip=False))
                    probe["intent"] = None
                elif kind == "unlink" and current[path] is not None and fs.read(path) is None:
                    probe["reverse"].append(dict(op=kind, path=path, stage=None, skip=False))
                    probe["intent"] = None
            verify(fs, e, baseline, probe, journal)
            with locked(fs, e):
                removed = verify(fs, e, baseline, probe, journal)
                fs.sync(removed)
                verify(fs, e, baseline, probe, journal)
                if j["phase"] in ("applying", "recovering"):
                    journal = reconcile(fs, e, baseline, j, journal)
                    if j["phase"] == "applying":
                        # Attested stages that were not published are preserved: no directory
                        # authority and no guess about interrupted staging provenance.
                        require(all(s is None for s in model(j, e, baseline)[1].values()),
                                "unpublished staged object; manual inspection required")
                if j["phase"] in ("applying", "installed"):
                    j["phase"] = "recovering"
                    journal = commit(fs, j, journal)
                if j["phase"] == "recovering":
                    while len(j["reverse"]) < 5:
                        journal = step(fs, e, baseline, j, journal)
                    j["phase"] = "restored"
                    journal = commit(fs, j, journal)
                removed = verify(fs, e, baseline, j, journal)
                if j["phase"] == "restored" and removed == list(reversed(OUTPUT_DIRS)):
                    fs.sync(removed)
                    verify(fs, e, baseline, j, journal)
                    receipt = fs.read(CLEANUP)
                    j["phase"] = "closed"
                    j["cleanup"] = digest(decode(receipt["image"]))
                    journal = commit(fs, j, journal)
                finish(fs, e, baseline, j, journal)
            _checkpoint("before-success-return")
            verify(fs, e, baseline, j, journal)
            return result(CLOSED if j["phase"] == "closed" else RESTORED)
    except (OSError, ValueError, TypeError, KeyError) as error:
        return failure(error)


class CleanupProvider:
    """Durable cleanup intent/attestation recorder; the operator performs rmdir.

    Cannot automatically resume a gap between an operator removal and attestation.
    """

    def __init__(self, root):
        self.root = root
        with FS(root) as fs:
            e, baseline, j, journal = observe(fs)
            require(j is not None and j["phase"] == "restored", "files not restored")
            require(fs.read(CLEANUP) is None, "cleanup already started; inspect retained evidence")
            self.enrollment, self.baseline, self.j, self.journal = e, baseline, j, journal
        self.c = None
        self.record = None

    def checkpoint_matches(self, fs):
        require(self.record is not None and unpack(decode(self.record["image"])) == self.c,
                "in-memory cleanup differs from durable checkpoint")
        fs.expect(CLEANUP, self.record)

    def start(self):
        require(self.c is None, "cleanup single use")
        with FS(self.root, self.enrollment["dirs"]) as fs, locked(fs, self.enrollment):
            verify(fs, self.enrollment, self.baseline, self.j, self.journal)
            removed = verify(fs, self.enrollment, self.baseline, self.j, self.journal)
            fs.sync(removed)
            verify(fs, self.enrollment, self.baseline, self.j, self.journal)
            self.c = dict(schema=2, scope=SCOPE, enrollment_id=self.enrollment["enrollment_id"],
                          enrollment=digest(decode(self.baseline["image"])),
                          checkpoint=digest(decode(self.journal["image"])), done=[], pending=None)
            self.record = fs.create(CLEANUP, image(pack(self.c)))

    def directory_intent(self, path):
        require(self.c is not None and self.c["pending"] is None and len(self.c["done"]) < 2 and
                path == list(reversed(OUTPUT_DIRS))[len(self.c["done"])], "invalid cleanup transition")
        with FS(self.root, self.enrollment["dirs"]) as fs, locked(fs, self.enrollment):
            self.checkpoint_matches(fs)
            verify(fs, self.enrollment, self.baseline, self.j, self.journal)
            fd = fs.directory(path)
            require(fs.pin(fd) == self.enrollment["dirs"][path] and not os.listdir(fd),
                    "operator directory not owned/empty")
            self.c["pending"] = path
            self.record = fs.record(CLEANUP, self.c, self.record)

    def attest_absence(self, path):
        require(self.c is not None and self.c["pending"] == path, "no cleanup intent")
        with FS(self.root, self.enrollment["dirs"]) as fs, locked(fs, self.enrollment):
            self.checkpoint_matches(fs)
            # Validate all other objects before certifying the operator's one
            # durably requested removal; a foreign edit must leave receipts intact.
            verify(fs, self.enrollment, self.baseline, self.j, self.journal,
                   operator_absence=path)
            parent, _, name = path.rpartition("/")
            fd = fs.directory(parent)
            try:
                os.stat(name, dir_fd=fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise ValueError("operator removal not witnessed")
            os.fsync(fd)
            self.c["done"].append(path)
            self.c["pending"] = None
            self.record = fs.record(CLEANUP, self.c, self.record)
            verify(fs, self.enrollment, self.baseline, self.j, self.journal)


def main():
    # Frozen fixture-only recovery/observation entry. No provisioning/install CLI.
    if len(sys.argv) != 3 or sys.argv[1] not in ("recover", "preview", "status"):
        print("usage: canary.py {recover|preview|status} /tmp/panda-theme-b3b1-ROOT", file=sys.stderr)
        return 2
    answer = {"recover": recover, "preview": preview, "status": status}[sys.argv[1]](sys.argv[2])
    print(json.dumps(answer, sort_keys=True))
    return 1 if answer["status"] in ("incomplete", "manual-inspection-required") else 0


if __name__ == "__main__":
    sys.exit(main())
