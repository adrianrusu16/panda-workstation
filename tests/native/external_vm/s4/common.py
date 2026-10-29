"""Offline S4 I/O primitives. Imported code has no side effects."""
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import stat
import subprocess
import tempfile

MIB = 1024**2
LOCK_SHA256 = "f4034660aa04de28123ccaf80fd6d12d2d7eb9c8f2d29e5043f1f4511fe16618"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


class FdPath:
    """An internal path anchored to a held private directory on Linux.

    Python I/O uses dirfds. Reviewed child tools receive this anchor via
    pass_fds and /proc/self/fd, independent of renamed filesystem ancestors.
    Only the root object owns/closes the descriptor; children borrow it.
    """
    def __init__(self, fd, parts=()):
        self.fd, self.parts = fd, parts

    def __truediv__(self, name):
        require(isinstance(name,str) and name not in ("", ".", "..") and
                "/" not in name and "\x00" not in name, "one private path component required")
        return FdPath(self.fd,self.parts+(name,))

    def __fspath__(self):
        return "/proc/self/fd/"+str(self.fd)+("/"+"/".join(self.parts) if self.parts else "")

    def __str__(self):
        return self.__fspath__()

    @property
    def name(self):
        return self.parts[-1] if self.parts else "private"

    def parent_fd(self):
        require(self.parts,"root has no relative parent")
        fd=os.dup(self.fd)
        try:
            for part in self.parts[:-1]:
                child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
                os.close(fd)
                fd=child
            return fd
        except BaseException:
            os.close(fd)
            raise

    def open(self,mode):
        flags={"rb":os.O_RDONLY|os.O_NONBLOCK,"xb":os.O_WRONLY|os.O_CREAT|os.O_EXCL,
               "x":os.O_WRONLY|os.O_CREAT|os.O_EXCL}
        require(mode in flags,"exclusive private creation or bounded reading required")
        parent=self.parent_fd()
        try:
            fd=os.open(self.name,flags[mode]|os.O_NOFOLLOW,0o600,dir_fd=parent)
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                os.close(fd)
                raise ValueError("private regular file required")
            return os.fdopen(fd,mode.replace("x","w"))
        finally:
            os.close(parent)

    def stat(self):
        if not self.parts:
            return os.fstat(self.fd)
        parent=self.parent_fd()
        try:
            return os.stat(self.name,dir_fd=parent,follow_symlinks=False)
        finally:
            os.close(parent)

    def is_dir(self):
        return stat.S_ISDIR(self.stat().st_mode)

    def is_symlink(self):
        return stat.S_ISLNK(self.stat().st_mode)

    def iterdir(self):
        require(not self.parts,"only private root enumeration allowed")
        return iter(os.listdir(self.fd))

    def mkdir(self,mode=0o700):
        parent=self.parent_fd()
        try:
            os.mkdir(self.name,mode,dir_fd=parent)
        finally:
            os.close(parent)

    def chmod(self,mode):
        with self.open("rb") as source:
            os.fchmod(source.fileno(),mode)

    def write_bytes(self,data):
        with self.open("xb") as output:
            output.write(data)

    def __enter__(self):
        require(not self.parts,"only root owns the descriptor")
        return self

    def __exit__(self,*_):
        os.close(self.fd)


def new_private(path):
    """Exclusive directory creation through a held, owned mode-0700 parent."""
    path=Path(os.path.abspath(path))
    directory=os.open("/",os.O_RDONLY|os.O_DIRECTORY)
    try:
        for part in path.parts[1:-1]:
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=directory)
            os.close(directory)
            directory=child
        info=os.fstat(directory)
        require(info.st_uid==os.getuid() and stat.S_IMODE(info.st_mode)==0o700,"private owned output parent required")
        os.mkdir(path.name,0o700,dir_fd=directory)
        result=os.open(path.name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=directory)
        return FdPath(result)
    finally:
        os.close(directory)


def read_json(data):
    def pairs(items):
        value = {}
        for key, item in items:
            require(key not in value, "duplicate JSON key")
            value[key] = item
        return value
    def reject(_):
        raise ValueError("non-finite JSON number")
    return json.loads(data, object_pairs_hook=pairs, parse_constant=reject)


def open_regular(path):
    """Walk absolute components with dirfds; never follow an input symlink."""
    if isinstance(path,FdPath):
        return path.open("rb")
    path = Path(os.path.abspath(path))
    require(path.name not in ("", ".", ".."), "regular input path required")
    directory = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    finally:
        os.close(directory)
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode):
        os.close(fd)
        raise ValueError("regular input required")
    return os.fdopen(fd, "rb")


def read_bounded(path, limit):
    with open_regular(path) as source:
        require(os.fstat(source.fileno()).st_size <= limit, "input exceeds read budget")
        data = source.read(limit + 1)
        require(len(data) <= limit, "input grew beyond read budget")
        return data


def private_copy(path, destination, expected_sha256, limit, expected_bytes=None, executable=False):
    require(isinstance(destination,FdPath),"held private output descriptor required")
    digest = hashlib.sha256()
    count = 0
    with open_regular(path) as source, destination.open("xb") as output:
        require(os.fstat(source.fileno()).st_size <= limit, "input exceeds copy budget")
        while block := source.read(min(MIB, limit - count + 1)):
            count += len(block)
            require(count <= limit, "input grew beyond copy budget")
            digest.update(block)
            output.write(block)
    require(digest.hexdigest() == expected_sha256, "input hash mismatch: " + path.name)
    require(expected_bytes is None or expected_bytes == count, "input size mismatch")
    destination.chmod(0o500 if executable else 0o400)
    return destination


def run_tool(argv, directory, output, output_limit, seconds=30):
    """Reviewed tools only. No shell, inherited env, network fetching or key lookup.

    The future VM parent still must impose whole-process cgroup/disk limits.
    Child limits here bound ordinary tool output and fail closed on overflow.
    """
    def limits():
        resource.setrlimit(resource.RLIMIT_CPU, (seconds, seconds))
        resource.setrlimit(resource.RLIMIT_AS, (1024*MIB, 1024*MIB))
        resource.setrlimit(resource.RLIMIT_FSIZE, (output_limit, output_limit))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    anchors=tuple(sorted({p.fd for p in [*argv,directory,output] if isinstance(p,FdPath)}))
    require(isinstance(directory,FdPath) and isinstance(output,FdPath),"private tool workspace required")
    with output.open("xb") as stdout, tempfile.TemporaryFile(dir=directory) as stderr:
        process = subprocess.Popen([str(arg) for arg in argv], stdin=subprocess.DEVNULL,
            stdout=stdout, stderr=stderr, cwd=directory, close_fds=True,
            pass_fds=anchors,
            env={"LANG":"C", "LC_ALL":"C", "HOME":str(directory),
                 "GNUPGHOME":str(directory), "PATH":"/nonexistent"},
            start_new_session=True, preexec_fn=limits)
        try:
            code = process.wait(timeout=seconds + 5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            raise ValueError("tool wall budget exceeded") from None
        require(code == 0, "reviewed tool failed with exit " + str(code))
        require(output.stat().st_size < output_limit, "tool output budget reached")
        # stderr never enters a success receipt or an unbounded memory buffer.
        require(stderr.seek(0, 2) < min(output_limit, MIB), "tool diagnostic budget exceeded")
    return output
