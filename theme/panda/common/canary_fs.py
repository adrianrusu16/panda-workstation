"""B3-B0 descriptor-relative private fixtures. Never a live filesystem backend."""

import base64
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat

SOURCE = "source/home/dot_config/ghostty/config.ghostty"
DEPLOYED = "config/ghostty/config.ghostty"
TARGET = "config/panda/generated/ghostty.conf"
MANAGED = (TARGET, SOURCE, DEPLOYED)
SUPPORT = "state/canary"
JOURNAL = SUPPORT + "/journal.json"
LOCK = SUPPORT + "/lock"
MARKER = ".panda-b3b-fixture.json"
OUTPUT_DIRS = ("config/panda", "config/panda/generated")
FIXED_DIRS = ("home", "config", "data", "state", "cache", "runtime", "source",
              "source/home", "source/home/dot_config", "source/home/dot_config/ghostty",
              "config/ghostty", SUPPORT)
STAGES = {path: path.rsplit("/", 1)[0] + "/." + path.rsplit("/", 1)[1] + ".b3b-stage"
          for path in (*MANAGED, JOURNAL)}
READABLE = frozenset((*MANAGED, JOURNAL, LOCK, MARKER, *STAGES.values()))
DIR_FIELDS = frozenset(("device", "inode", "uid", "gid", "mode", "mount"))
STAMP_FIELDS = DIR_FIELDS | {"mtime_ns", "ctime_ns"}
IMAGE_FIELDS = frozenset(("content", "mode", "uid", "gid", "mtime_ns", "atime_ns"))
LIMIT = 1024 * 1024
SCOPE = "b3b-private-fixture-only"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n"


def pack(payload):
    raw = canonical({"payload": payload, "sha256": digest(canonical(payload))})
    if len(raw) > LIMIT:
        raise ValueError("fixture record exceeds bound")
    return raw


def unpack(raw):
    if not isinstance(raw, bytes) or len(raw) > LIMIT:
        raise ValueError("fixture record exceeds bound")
    data = json.loads(raw, object_pairs_hook=_unique)
    if (not isinstance(data, dict) or set(data) != {"payload", "sha256"} or
            data["sha256"] != digest(canonical(data["payload"])) or pack(data["payload"]) != raw):
        raise ValueError("noncanonical or corrupt fixture record")
    return data["payload"]


def validate_identity(value, *, stamp=False):
    fields = STAMP_FIELDS if stamp else DIR_FIELDS
    if (not isinstance(value, dict) or set(value) != fields or
            any(type(v) is not int or not 0 <= v <= 2**63 - 1 for v in value.values()) or
            value["uid"] != os.getuid() or value["gid"] != os.getgid() or value["mode"] != 0o700):
        raise ValueError("invalid fixture directory identity")


def validate_image(image):
    if image is None:
        return
    if (not isinstance(image, dict) or set(image) != IMAGE_FIELDS or
            not isinstance(image["content"], bytes) or len(image["content"]) > LIMIT or
            type(image["mode"]) is not int or image["mode"] not in (0o600, 0o644) or
            image["uid"] != os.getuid() or image["gid"] != os.getgid() or
            any(type(image[k]) is not int or not 0 <= image[k] <= 2**63 - 1
                for k in ("uid", "gid", "mtime_ns", "atime_ns"))):
        raise ValueError("unsupported fixture file image")


def image_data(image):
    validate_image(image)
    if image is None:
        return None
    return {**image, "content": base64.b64encode(image["content"]).decode(),
            "sha256": digest(image["content"])}


def image_from(value):
    if value is None:
        return None
    if (not isinstance(value, dict) or set(value) != IMAGE_FIELDS | {"sha256"} or
            not isinstance(value["content"], str) or len(value["content"]) > 90000):
        raise ValueError("invalid bounded recovery image")
    raw = base64.b64decode(value["content"], validate=True)
    image = {k: v for k, v in value.items() if k != "sha256"}
    image["content"] = raw
    validate_image(image)
    if len(raw) > 65536 or digest(raw) != value["sha256"] or image_data(image) != value:
        raise ValueError("corrupt recovery image")
    return image


def mount_id(fd):
    # Linux fdinfo distinguishes visible bind mounts; same-user namespace races
    # and aliases invisible to this namespace remain outside the guarantee.
    fields = Path(f"/proc/self/fdinfo/{fd}").read_text().splitlines()
    for line in fields:
        if line.startswith("mnt_id:"):
            return int(line.split()[1])
    raise ValueError("mount identity unavailable")


def directory_identity(fd, *, stamp=False):
    info = os.fstat(fd)
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or
            info.st_gid != os.getgid() or stat.S_IMODE(info.st_mode) != 0o700 or os.listxattr(fd)):
        raise ValueError("unsafe fixture ancestor ownership, mode, type or xattrs")
    result = dict(device=info.st_dev, inode=info.st_ino, uid=info.st_uid,
                  gid=info.st_gid, mode=stat.S_IMODE(info.st_mode), mount=mount_id(fd))
    if stamp:
        result.update(mtime_ns=info.st_mtime_ns, ctime_ns=info.st_ctime_ns)
    return result


def write_all(fd, content):
    offset = 0
    while offset < len(content):
        count = os.write(fd, content[offset:])
        if count <= 0:
            raise OSError("short fixture write")
        offset += count


class CanaryFS:
    """Exact B3B root, fixed paths, descriptor traversal, pinned fixture ancestors."""

    def __init__(self, root):
        raw = os.fspath(root)
        self.root = Path(raw)
        if (not self.root.is_absolute() or ".." in self.root.parts or
                self.root.parent != Path("/tmp") or
                not self.root.name.startswith("panda-theme-b3b-") or
                len(self.root.name) <= len("panda-theme-b3b-")):
            raise ValueError("B3B requires a private direct /tmp/panda-theme-b3b-* fixture")
        self.fd = None
        self.pins = {}
        self.directories = []
        self.on_intent = None
        self.on_done = None
        self.lock_fd = None
        try:
            self.fd = self._root_fd()
            self.identity = directory_identity(self.fd)
            self.marker = self.read(MARKER)
            if self.marker is None:
                raise ValueError("fresh fixture manifest missing")
            self.manifest = unpack(self.marker["content"])
            data = self.manifest
            if (not isinstance(data, dict) or set(data) != {
                    "schema", "scope", "root", "parents", "entries", "lock_identity", "bootstrap_intent"} or
                    type(data["schema"]) is not int or data["schema"] != 1 or data["scope"] != SCOPE or
                    data["bootstrap_intent"] != "initialize-private-journal" or
                    data["root"] != self.identity or not isinstance(data["parents"], dict) or
                    set(data["parents"]) != set(FIXED_DIRS)):
                raise ValueError("invalid fixture manifest capability")
            self.pins = data["parents"]
            for identity in self.pins.values():
                validate_identity(identity)
            lock_identity = data["lock_identity"]
            if (not isinstance(lock_identity, dict) or set(lock_identity) != {"device", "inode", "ctime_ns"} or
                    any(type(v) is not int or not 0 <= v <= 2**63 - 1 for v in lock_identity.values())):
                raise ValueError("invalid initial lock identity")
            self.guard()
        except BaseException:
            if self.fd is not None:
                os.close(self.fd)
            raise

    def _root_fd(self):
        tmp = os.open("/tmp", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            fd = os.open(self.root.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NOATIME,
                         dir_fd=tmp)
            try:
                if mount_id(tmp) != mount_id(fd):
                    raise ValueError("fixture root is a mount alias")
            except BaseException:
                os.close(fd)
                raise
            return fd
        finally:
            os.close(tmp)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        os.close(self.fd)

    def open_dir(self, path):
        if path not in ("", *FIXED_DIRS, *OUTPUT_DIRS):
            raise ValueError("directory outside exact fixture scope")
        fd = os.dup(self.fd)
        try:
            prefix = []
            for part in path.split("/") if path else ():
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NOATIME,
                                dir_fd=fd)
                os.close(fd)
                fd = child
                prefix.append(part)
                identity = directory_identity(fd)
                if identity["mount"] != self.identity["mount"]:
                    raise ValueError("nested mount alias refused")
                expected = self.pins.get("/".join(prefix))
                if expected is not None and identity != expected:
                    raise ValueError("fixture ancestor replaced")
            return fd
        except BaseException:
            os.close(fd)
            raise

    def parent(self, path):
        if path not in READABLE:
            raise ValueError("path outside exact fixture allowlist")
        if "/" not in path:
            return os.dup(self.fd), path
        parent, name = path.rsplit("/", 1)
        return self.open_dir(parent), name

    def read(self, path):
        parent = None
        try:
            parent, name = self.parent(path)
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_NOATIME, dir_fd=parent)
            try:
                info = os.fstat(fd)
                limit = LIMIT if path in (MARKER, JOURNAL, STAGES[JOURNAL]) else 65536
                allowed_modes = ((0o644,) if path in (SOURCE, DEPLOYED) else
                                 (0o600, 0o644) if path in (STAGES[SOURCE], STAGES[DEPLOYED]) else (0o600,))
                if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid() or
                        info.st_gid != os.getgid() or stat.S_IMODE(info.st_mode) not in allowed_modes or
                        info.st_size > limit or os.listxattr(fd) or
                        mount_id(fd) != self.identity["mount"]):
                    raise ValueError("unsafe fixture file type, links, metadata or alias")
                chunks = []
                remaining = limit + 1
                while remaining:
                    chunk = os.read(fd, min(remaining, 65536))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    remaining -= len(chunk)
                content = b"".join(chunks)
                fresh = os.fstat(fd)
                if (len(content) > limit or
                        (info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns) !=
                        (fresh.st_ino, fresh.st_mode, fresh.st_size, fresh.st_mtime_ns, fresh.st_ctime_ns)):
                    raise ValueError("fixture image changed during read")
                return dict(content=content, mode=stat.S_IMODE(info.st_mode), uid=info.st_uid,
                            gid=info.st_gid, mtime_ns=info.st_mtime_ns, atime_ns=info.st_atime_ns)
            finally:
                os.close(fd)
        except FileNotFoundError:
            return None
        finally:
            if parent is not None:
                os.close(parent)

    def guard(self):
        fresh = self._root_fd()
        try:
            if directory_identity(fresh) != self.identity:
                raise ValueError("fixture root replaced")
        finally:
            os.close(fresh)
        for path in self.pins:
            fd = self.open_dir(path)
            os.close(fd)
        if self.read(MARKER) != self.marker:
            raise ValueError("fixture manifest changed")
        parent, name = self.parent(LOCK)
        try:
            current = os.stat(name, dir_fd=parent, follow_symlinks=False)
            if dict(device=current.st_dev, inode=current.st_ino, ctime_ns=current.st_ctime_ns) != self.manifest["lock_identity"]:
                raise ValueError("initial fixture lock changed")
        finally:
            os.close(parent)
        if self.lock_fd is not None:
            parent, name = self.parent(LOCK)
            try:
                current = os.stat(name, dir_fd=parent, follow_symlinks=False)
                held = os.fstat(self.lock_fd)
                if (current.st_dev, current.st_ino) != (held.st_dev, held.st_ino):
                    raise ValueError("fixture lock replaced")
            finally:
                os.close(parent)

    def directory_stamp(self, path):
        try:
            fd = self.open_dir(path)
        except FileNotFoundError:
            return None
        try:
            return directory_identity(fd, stamp=True)
        finally:
            os.close(fd)

    def check_directories(self):
        for record in self.directories:
            current = self.directory_stamp(record["path"])
            if current != record["identity"]:
                raise ValueError("unknown or changed directory provenance; manual inspection")
            if record["state"] == "removed" and current is not None:
                raise ValueError("removed directory reappeared")

    def stages_absent(self):
        for path in STAGES.values():
            if self.read(path) is not None:
                raise ValueError("staging evidence exists; manual inspection")

    def _refresh(self, path):
        for record in self.directories:
            if record["path"] == path and record["state"] == "created":
                current = self.directory_stamp(path)
                if current is None or any(current[k] != record["identity"][k] for k in DIR_FIELDS):
                    raise ValueError("created directory identity changed; provenance preserved")
                record["identity"] = current

    def _intent(self, kind, path):
        self.guard()
        self.check_directories()
        if self.on_intent is None:
            raise ValueError("durable transaction intent required")
        self.on_intent(kind, path)
        self.guard()
        self.check_directories()

    def _done(self):
        if self.on_done is not None:
            self.on_done()

    @contextmanager
    def locked(self):
        self.guard()
        image = self.read(LOCK)
        if image is None or image["content"] or image["mode"] != 0o600:
            raise ValueError("private lock invalid")
        parent, name = self.parent(LOCK)
        fd = None
        try:
            fd = os.open(name, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            info = os.fstat(fd)
            current = os.stat(name, dir_fd=parent, follow_symlinks=False)
            if ((info.st_dev, info.st_ino) != (current.st_dev, current.st_ino) or
                    info.st_uid != os.getuid() or info.st_gid != os.getgid() or
                    not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or
                    stat.S_IMODE(info.st_mode) != 0o600 or info.st_size or os.listxattr(fd)):
                raise ValueError("private lock unsafe")
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.lock_fd = fd
            self.guard()
            yield
        finally:
            self.lock_fd = None
            if fd is not None:
                os.close(fd)
            os.close(parent)

    def mkdir(self, path):
        if path not in OUTPUT_DIRS:
            raise ValueError("mkdir outside output scope")
        self._intent("mkdir", path)
        parent_path, name = path.rsplit("/", 1)
        parent = self.open_dir(parent_path)
        try:
            parent_identity = directory_identity(parent)
            os.mkdir(name, 0o700, dir_fd=parent)
            self.guard()
            current_parent = self.directory_stamp(parent_path)
            if (directory_identity(parent) != parent_identity or current_parent is None or
                    any(current_parent[k] != parent_identity[k] for k in DIR_FIELDS)):
                raise ValueError("mkdir parent binding changed; unknown child preserved")
            self._refresh(parent_path)
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NOATIME,
                            dir_fd=parent)
            try:
                identity = directory_identity(child, stamp=True)
                if identity["mount"] != self.identity["mount"] or self.directory_stamp(path) != identity:
                    raise ValueError("mkdir child binding changed; unknown child preserved")
                os.fsync(child)
                os.fsync(parent)
                self.guard()
                if (directory_identity(parent) != parent_identity or
                        self.directory_stamp(parent_path) != current_parent or
                        directory_identity(child, stamp=True) != identity or self.directory_stamp(path) != identity):
                    raise ValueError("mkdir identity drift before checkpoint; unknown child preserved")
                record = next(r for r in self.directories if r["path"] == path)
                record.update(state="created", identity=identity)
                self._done()
            finally:
                os.close(child)
        finally:
            os.close(parent)

    def write_journal(self, content, *, expected):
        """Metadata bootstrap is bound to the durable immutable fixture manifest."""
        self.guard()
        if self.read(JOURNAL) != expected or self.read(STAGES[JOURNAL]) is not None:
            raise ValueError("journal changed or journal stage already exists")
        parent, name = self.parent(JOURNAL)
        stage = STAGES[JOURNAL].rsplit("/", 1)[1]
        try:
            fd = os.open(stage, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
            try:
                write_all(fd, content)
                os.fsync(fd)
            finally:
                os.close(fd)
            self.guard()
            if self.read(JOURNAL) != expected:
                raise ValueError("journal changed during staging")
            os.replace(stage, name, src_dir_fd=parent, dst_dir_fd=parent)
            os.fsync(parent)
            current = self.read(JOURNAL)
            if current is None or current["content"] != content:
                raise ValueError("journal replacement verification failed")
        finally:
            os.close(parent)

    def replace(self, path, image, *, expected):
        if path not in MANAGED:
            raise ValueError("replacement outside managed fixture paths")
        validate_image(image)
        if image is not None and len(image["content"]) > 65536:
            raise ValueError("managed image exceeds bound")
        if self.read(path) != expected:
            raise ValueError("external edit preserved")
        parent, name = self.parent(path)
        parent_path = path.rsplit("/", 1)[0]
        stage = STAGES[path].rsplit("/", 1)[1]
        try:
            if image is not None:
                if self.read(STAGES[path]) is not None:
                    raise ValueError("existing stage preserved")
                self._intent("stage", path)
                fd = os.open(stage, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
                try:
                    self._refresh(parent_path)
                    write_all(fd, image["content"])
                    os.fchmod(fd, image["mode"])
                    os.utime(fd, ns=(image["atime_ns"], image["mtime_ns"]))
                    os.fsync(fd)
                finally:
                    os.close(fd)
                os.fsync(parent)
                self._done()
            self._intent("unlink" if image is None else "replace", path)
            if self.read(path) != expected:
                raise ValueError("late edit during staging preserved")
            if image is not None and self.read(STAGES[path]) != image:
                raise ValueError("foreign staged image preserved; destination untouched")
            if image is None:
                os.unlink(name, dir_fd=parent)
            else:
                os.replace(stage, name, src_dir_fd=parent, dst_dir_fd=parent)
            self._refresh(parent_path)
            os.fsync(parent)
            if self.read(path) != image:
                raise ValueError("fixture replacement verification failed")
            self._done()
        finally:
            os.close(parent)

    def remove_dir(self, path):
        if path not in OUTPUT_DIRS:
            raise ValueError("cleanup outside fixture scope")
        record = next(r for r in self.directories if r["path"] == path)
        if record["state"] != "created":
            return
        self._intent("rmdir", path)
        child = self.open_dir(path)
        try:
            if os.listdir(child):
                raise ValueError("populated directory preserved")
        finally:
            os.close(child)
        parent_path, name = path.rsplit("/", 1)
        parent = self.open_dir(parent_path)
        try:
            self.guard()
            self.check_directories()
            os.rmdir(name, dir_fd=parent)
            record.update(state="removed", identity=None)
            self._refresh(parent_path)
            os.fsync(parent)
            self._done()
        finally:
            os.close(parent)

    def sync_parents(self):
        """Replay every deterministic obligation, even for completed-looking records."""
        for path in ("", *FIXED_DIRS, *OUTPUT_DIRS):
            self.guard()
            self.check_directories()
            parent = path
            while True:
                try:
                    fd = self.open_dir(parent)
                    break
                except FileNotFoundError:
                    parent = parent.rsplit("/", 1)[0] if "/" in parent else ""
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        self.guard()
        self.check_directories()
