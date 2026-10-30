"""Test operator: the only B3B1 component allowed to provision/remove directories."""

import json
import os
from pathlib import Path
import stat
import tempfile
from contextlib import contextmanager, ExitStack
import re


# Injected by the creation-time supervisor, never learned from an existing tree.
# Ordinary discovery has no capability and refuses before making a test root.
fixture_cleanup = None


def identity(path):
    s = path.lstat()
    return (s.st_dev, s.st_ino, s.st_uid, s.st_gid, s.st_mode)


@contextmanager
def runner_registry():
    """Require explicit creation-time runner identities, never ambient XDG authority.

    This test-only capability does not enroll or redirect any engine destination.
    The invoking supervisor creates the registry exclusively and supplies identities.
    Ordinary unsanitized discovery refuses before creating any fixture.
    """
    try:
        capability = json.loads(os.environ["PANDA_TEST_RUNNER"])
        root = capability["root"]
        runtime = os.environ["XDG_RUNTIME_DIR"]
        if (set(capability) != {"root", "root_identity", "runtime_identity", "registry_identity"}
                or not re.fullmatch(r"/tmp/panda-theme-b3b1-[A-Za-z0-9_-]+", root)
                or runtime != root + "/runtime"):
            raise ValueError("unsafe/unregistered test runner")
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("explicit private test runner capability required") from error

    def check(fd, expected, directory):
        s = os.fstat(fd)
        actual = (s.st_dev, s.st_ino, s.st_uid, s.st_gid, s.st_mode)
        if (actual != tuple(expected) or s.st_uid != os.getuid() or s.st_gid != os.getgid()
                or stat.S_IMODE(s.st_mode) != (0o700 if directory else 0o600)
                or not (stat.S_ISDIR(s.st_mode) if directory else stat.S_ISREG(s.st_mode))
                or (not directory and s.st_nlink != 1) or os.listxattr(fd)):
            raise ValueError("test runner identity/metadata differs")

    with ExitStack() as held:
        def opened(name, flags, parent=None):
            fd = os.open(name, flags | os.O_NOFOLLOW, dir_fd=parent)
            held.callback(os.close, fd)
            return fd
        root_fd = opened(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOATIME)
        check(root_fd, capability["root_identity"], True)
        runtime_fd = opened("runtime", os.O_RDONLY | os.O_DIRECTORY | os.O_NOATIME, root_fd)
        check(runtime_fd, capability["runtime_identity"], True)
        registry_fd = opened("owned-fixtures.jsonl", os.O_WRONLY | os.O_APPEND, runtime_fd)
        check(registry_fd, capability["registry_identity"], False)
        check(opened(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOATIME),
              capability["root_identity"], True)
        if (identity(Path(runtime)) != tuple(capability["runtime_identity"])
                or identity(Path(runtime) / "owned-fixtures.jsonl") !=
                tuple(capability["registry_identity"])):
            raise ValueError("test runner path binding differs")
        yield registry_fd


class Operator:
    def __init__(self, api, baseline, register):
        self.api = api
        if not callable(fixture_cleanup):
            raise ValueError("prospective fixture cleanup supervisor required")
        self.cleanup_capability = fixture_cleanup
        with runner_registry() as fd:
            self.root = Path(tempfile.mkdtemp(prefix="panda-theme-b3b1-", dir="/tmp"))
            self.initial = identity(self.root)
            self.removed = False
            self.provider = None
            self.custody = None
            self.creation = {}
            register(self.teardown)
            # Register ownership immediately, before subsequent setup can fail.
            raw = (json.dumps({"root": str(self.root), "identity": self.initial}) + "\n").encode()
            position = 0
            while position < len(raw):
                written = os.write(fd, raw[position:])
                if written <= 0:
                    raise OSError("short ownership registry write")
                position += written
            os.fsync(fd)
        self.custody = api.FS(self.root)
        s = os.fstat(self.custody.fd)
        if (s.st_dev, s.st_ino, s.st_uid, s.st_gid, s.st_mode) != self.initial:
            raise ValueError("fixture root differs from creation identity")
        self.creation[""] = self.custody.pin(self.custody.fd)
        self.custody.pins[""] = dict(self.creation[""])
        for path in api.FIXED_DIRS:
            self.create_directory(path)
        for index, path in enumerate((api.SOURCE, api.DEPLOYED)):
            target = self.root / path
            target.write_bytes(baseline)
            target.chmod(0o644)
            os.utime(target, ns=(1700000000000000000 + index,
                                1700000001000000000 + index))
        self.provider = api.Provider(self.root, self.witnesses())

    def witnesses(self):
        return self.creation_witnesses(self.api.FIXED_DIRS)

    def create_directory(self, path):
        """Controlled cooperative creation; retain evidence before later attestation.

        mkdir/first-open is not atomic against same-UID substitution. The accepted
        primitive requires quiescent writers in that interval; later observation
        never replaces missing creation evidence.
        """
        if path not in (*self.api.FIXED_DIRS, *self.api.OUTPUT_DIRS) or path in self.creation:
            raise ValueError("invalid operator creation role")
        parent, _, name = path.rpartition("/")
        self.creation_witnesses((parent,))
        parent_fd = self.custody.directory(parent)
        os.mkdir(name, mode=0o700, dir_fd=parent_fd)
        fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NOATIME,
                     dir_fd=parent_fd)
        # Hold the first child FD even if a subsequent path check fails. It is
        # evidence of this controlled operation, never permission to adopt a replacement.
        self.custody.fds[path] = fd
        witness = self.custody.pin(fd)
        self.creation[path] = dict(witness)
        self.custody.pins[path] = dict(witness)
        self.custody.bind(parent, parent_fd)
        self.custody.bind(path, fd)
        if os.listdir(fd):
            raise ValueError("created directory has unexpected contents")

    def creation_witnesses(self, paths):
        roles = ("", *paths)
        if any(p not in self.creation or p not in self.custody.fds for p in roles):
            raise ValueError("missing retained creation evidence")
        for path in roles:
            fd = self.custody.fds[path]
            if self.custody.pin(fd) != self.creation[path] or self.custody.pins[path] != self.creation[path]:
                raise ValueError("creation evidence differs from held descriptor")
            self.custody.bind(path, fd)
        # A separate fresh observation is checked against the original evidence.
        # This deliberately cannot learn a replacement inode from enrollment.
        with self.api.FS(self.root, self.creation) as fs:
            observed = fs.directory_witnesses(paths)
        expected = {p: dict(self.creation[p]) for p in roles}
        if observed != expected:
            raise ValueError("late observation differs from creation evidence")
        for path in roles:
            self.custody.bind(path, self.custody.fds[path])
        return expected

    def seal(self):
        self.creation_witnesses((*self.api.FIXED_DIRS, *self.api.OUTPUT_DIRS))
        self.provider.seal()

    def provision(self, stop=None):
        self.provider.start()
        if stop == "support":
            return
        for path in self.api.OUTPUT_DIRS:
            self.provider.directory_intent(path)
            if stop == path + ":intent":
                return
            self.create_directory(path)
            if stop == path + ":created":
                return
            witness = self.creation_witnesses((path,))[path]
            self.provider.attest_directory(path, witness)
            if stop == path + ":attested":
                return
        self.seal()

    def cleanup_outputs(self, stop=None):
        receipt = self.api.CleanupProvider(self.root)
        receipt.start()
        for path in reversed(self.api.OUTPUT_DIRS):
            receipt.directory_intent(path)
            if stop == path + ":intent":
                return
            expected = receipt.enrollment["dirs"][path]
            with self.api.FS(self.root, receipt.enrollment["dirs"]) as fs:
                fd = fs.directory(path)
                if fs.pin(fd) != expected or os.listdir(fd):
                    raise ValueError("operator refuses foreign/nonempty directory")
                fs.bind(path, fd)
                parent = path.rsplit("/", 1)[0]
                parent_fd = fs.directory(parent)
                os.rmdir(path.rsplit("/", 1)[1], dir_fd=parent_fd)
                os.fsync(parent_fd)
            if stop == path + ":removed":
                return
            receipt.attest_absence(path)
            if stop == path + ":attested":
                return

    def teardown(self):
        if self.provider is not None:
            self.provider.close()
        if self.custody is not None:
            # Verify root/parent custody before releasing held creation descriptors.
            self.custody.bind("", self.custody.fd)
            self.custody.close()
            self.custody = None
        if self.removed:
            return
        if identity(self.root) != self.initial or not stat.S_ISDIR(self.initial[-1]):
            raise RuntimeError("preserving ambiguous fixture root: " + str(self.root))
        self.cleanup_capability(str(self.root), self.initial)
        self.removed = True
