"""Sealed hosted-only adapter. No real authentication is authorized by this source."""
import os
from pathlib import Path
import platform
import re
import resource
import signal
import ssl
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

# Also supports a future isolated `/usr/bin/python3 -I -S -B` invocation.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ubuntu_verification as protocol
import ubuntu_packets as packets
from common import MIB, read_bounded, require, sha256
from ubuntu_artifacts import LIB_DIRS, elf_info

AUTHENTICATION_ENABLED = False  # Source seal; never controlled by argv or environment.
SNAPSHOT = "https://snapshot.ubuntu.com/ubuntu/20261029T000000Z/"
KEYRING = "/usr/share/keyrings/ubuntu-archive-keyring.gpg"
TOOLS = {"gpgv": "/usr/bin/gpgv", "zstd": "/usr/bin/zstd"}
POLICY_SHA256 = "7c43bbbf0fc1ca9ba9450121402fe8e07c2aa851aaf6fc49bd01933f9f713c2b"
ENV_KEYS = ("GITHUB_ACTIONS", "RUNNER_ENVIRONMENT", "RUNNER_OS", "RUNNER_ARCH", "ImageOS", "ImageVersion",
            "GITHUB_REPOSITORY", "GITHUB_REF", "GITHUB_EVENT_NAME", "GITHUB_SHA", "REVIEWED_SOURCE_SHA",
            "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_JOB", "RUNNER_NAME")


class SnapshotRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, prefix): self.prefix = prefix

    def check(self, url):
        parsed = urllib.parse.urlsplit(url)
        require(url.startswith(self.prefix) and parsed.scheme == "https" and parsed.netloc == "snapshot.ubuntu.com" and
                not parsed.query and not parsed.fragment and not parsed.username and
                not any(part in (".", "..") for part in urllib.parse.unquote(parsed.path).split("/")), "snapshot redirect/source identity")

    def redirect_request(self, request, response, code, message, headers, newurl):
        self.check(newurl)
        return super().redirect_request(request, response, code, message, headers, newurl)


def download(url, expected_size, opener):
    SnapshotRedirect(SNAPSHOT).check(url)
    require(type(expected_size) is int and 0 < expected_size <= 32*MIB, "download size budget")
    request = urllib.request.Request(url, headers={"Accept-Encoding": "identity", "User-Agent": "Panda-Ubuntu-Provenance/1"})
    with opener.open(request, timeout=30) as response:
        SnapshotRedirect(SNAPSHOT).check(response.geturl())
        raw = response.read(expected_size+1)
    require(len(raw) == expected_size, "download size mismatch")
    return raw


def system_file(path, limit, *, optional=False):
    """Root-owned preinstalled data only; no candidate path is admitted here."""
    original = Path(path)
    try: resolved = original.resolve(strict=True)
    except FileNotFoundError:
        if optional: return None
        raise
    require(str(resolved).startswith(("/usr/", "/etc/", "/var/lib/dpkg/")), "preinstalled path boundary")
    for ancestor in (resolved.parent, *resolved.parents):
        info = ancestor.stat()
        require(info.st_uid == 0 and not info.st_mode & 0o022, "preinstalled ancestor ownership/mode")
    fd = os.open(resolved, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as source:
        before = os.fstat(source.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_uid == 0 and not before.st_mode & 0o7022 and
                before.st_size <= limit, "preinstalled regular file ownership/budget")
        require(not os.getxattr(resolved, "security.capability") if "security.capability" in os.listxattr(resolved) else True,
                "preinstalled file capabilities")
        raw = source.read(limit+1)
        after = os.fstat(source.fileno())
        require(len(raw) <= limit and (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
                (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns), "preinstalled file changed/budget")
    return dict(path=str(resolved), raw=raw, mode=stat.S_IMODE(before.st_mode), uid=before.st_uid)


def package_metadata():
    raw = system_file("/var/lib/dpkg/status", 32*MIB)["raw"]
    wanted = {"gpgv", "zstd", "ubuntu-keyring", "python3.12-minimal", "libpython3.12-stdlib"}
    result = {}
    for paragraph in raw.decode("utf-8").split("\n\n"):
        values = {}
        for line in paragraph.split("\n"):
            if not line or line.startswith((" ", "\t")): continue
            name, separator, value = line.partition(":")
            if name in ("Package", "Version", "Architecture", "Status"):
                require(separator and name not in values, "dpkg metadata duplicate")
                values[name] = value.strip()
        if values.get("Status") == "install ok installed":
            name = values["Package"]
            if values["Architecture"] not in ("amd64", "all"): name += ":"+values["Architecture"]
            require(name not in result and len(result) < 4096, "preinstalled dpkg identity/budget")
            result[name] = dict(version=values["Version"], architecture=values["Architecture"])
    require(wanted <= set(result), "preinstalled package metadata incomplete")
    return result


def package_owners(aliases, packages, manifests):
    """Match bounded installed dpkg file lists, including explicitly observed usr aliases."""
    require(type(manifests) is dict and len(manifests) <= 4096 and
            sum(len(raw) for raw in manifests.values()) <= 32*MIB, "dpkg file list budget")
    owners = {}
    for name, raw in manifests.items():
        require(re.fullmatch(r"[a-z0-9][a-z0-9+.-]*(?::[a-z0-9-]+)?\.list", name), "dpkg list name")
        identity = name.removesuffix(".list").split(":")
        package = identity[0] if len(identity) == 1 or identity[1] in ("amd64", "all") else ":".join(identity)
        for line in raw.decode("utf-8").splitlines():
            require(len(line) <= 4096 and not re.search(r"[\x00-\x1f\x7f]", line), "dpkg list path")
            if line not in aliases: continue
            path = aliases[line]
            require(path not in owners and package in packages, "missing/ambiguous installed file owner")
            require(":" not in name or name.removesuffix(".list").split(":")[1] == packages[package]["architecture"],
                    "dpkg owner architecture conflict")
            owners[path] = package
    require(set(owners) == set(aliases.values()), "incomplete installed file ownership")
    return owners


def inventory_owners(paths, packages):
    aliases = {path: path for path in paths}
    for path in paths:
        for prefix in ("/lib/", "/lib64/", "/bin/", "/sbin/"):
            if path.startswith("/usr"+prefix):
                alias = path.removeprefix("/usr")
                if str(Path(alias).resolve(strict=True)) == path: aliases[alias] = path
    directory = Path("/var/lib/dpkg/info")
    lists = sorted(directory.glob("*.list"))
    require(len(lists) <= 4096, "dpkg list count budget")
    manifests, total = {}, 0
    for path in lists:
        raw = system_file(path, 8*MIB)["raw"]
        total += len(raw); require(total <= 32*MIB, "aggregate dpkg list budget")
        manifests[path.name] = raw
    return package_owners(aliases, packages, manifests)


def inventory_toolchain():
    roots = {**TOOLS, "python": str(Path(sys.executable).resolve())}
    require(roots["python"].startswith("/usr/bin/python3"), "system Python required")
    # Include the native stdlib modules loaded by the verifier, transport and readers.
    extensions = sorted({str(Path(module.__file__).resolve()) for module in list(sys.modules.values())
                         if isinstance(getattr(module, "__file__", None), str) and module.__file__.endswith(".so")})
    require(len(extensions) <= 32 and all(path.startswith("/usr/lib/python3.12/") for path in extensions), "unreviewed Python extension origin")
    files, pending, total = {}, list(roots.values())+extensions, 0
    def read(path):
        return system_file(path, 32*MIB)
    def resolve_library(name):
        candidates = set()
        for directory in LIB_DIRS:
            try: value = read(directory+"/"+name)
            except FileNotFoundError: continue
            candidates.add(value["path"])
        require(len(candidates) == 1, "preinstalled library missing/ambiguous")
        return next(iter(candidates))
    while pending:
        value = read(pending.pop())
        path, raw = value["path"], value["raw"]
        if path in files: continue
        total += len(raw)
        require(len(files) < 128 and total <= 64*MIB, "preinstalled closure budget")
        info = elf_info(raw)
        interpreter = read(info["interpreter"])["path"] if info["interpreter"] else None
        needed = {name: resolve_library(name) for name in info["needed"]}
        files[path] = dict(sha256=sha256(raw), bytes=len(raw), mode=value["mode"], uid=value["uid"],
                           elf=info, interpreter=interpreter, needed=needed)
        pending.extend(needed.values())
        if interpreter: pending.append(interpreter)
    roots = {name: read(path)["path"] for name, path in roots.items()}
    config = {path: (row["raw"] if (row := system_file(path, 8*MIB, optional=path=="/etc/ld.so.preload")) else None)
              for path in ("/etc/ld.so.preload", "/etc/ld.so.cache", "/etc/ld.so.conf", "/etc/ssl/certs/ca-certificates.crt")}
    directory = Path("/etc/ld.so.conf.d")
    require(directory.is_dir() and not directory.is_symlink(), "loader include directory")
    children = sorted(directory.glob("*.conf")); require(len(children) <= 60, "loader include budget")
    for path in children: config[str(path)] = system_file(path, MIB)["raw"]
    hwcaps = []
    for base in LIB_DIRS:
        path = Path(base)/"glibc-hwcaps"
        if path.exists():
            # Any populated variant tree requires another reviewed resolution model.
            require(not path.is_symlink(), "hwcaps directory alias")
            hwcaps.extend(str(child) for child in path.iterdir())
    source_hashes = {name: sha256(read_bounded(Path(__file__).with_name(name), 128*1024)) for name in protocol.SOURCE_NAMES}
    packages = package_metadata()
    keyring = system_file(KEYRING, 128*1024)
    owners = inventory_owners([*files, keyring["path"]], packages)
    for path, row in files.items(): row["package"] = owners[path]
    keyring_record = dict(path=keyring["path"], mode=keyring["mode"], uid=keyring["uid"],
                          bytes=len(keyring["raw"]), sha256=sha256(keyring["raw"]), package=owners[keyring["path"]])
    selected = set(owners.values()) | {"gpgv", "zstd", "ubuntu-keyring", "python3.12-minimal", "libpython3.12-stdlib"}
    result = dict(tools=roots, extensions=extensions, files=files, keyring=keyring_record,
                  packages={name: packages[name] for name in sorted(selected)},
                  loader=protocol.loader_configuration(config, hwcaps), source_hashes=source_hashes)
    pins, _ = protocol.load_references()
    return protocol.verify_toolchain(result, pins)


def runner_application(executables):
    require(type(executables) is list and len(executables) <= 16, "runner ancestry budget")
    versions = set()
    for path in executables:
        require(type(path) is str and len(path) <= 4096, "runner ancestor path budget")
        match = re.fullmatch(r"/home/runner/runners/([0-9]+\.[0-9]+\.[0-9]+)/bin/Runner\.(?:Worker|Listener)", path)
        if match: versions.add(match[1])
    require(len(versions) <= 1, "conflicting runner application versions")
    return dict(version=next(iter(versions)) if versions else None,
                basis="observed runner ancestor executable path", hardware_attested=False)


def observe_runner_application():
    paths, seen, pid = [], set(), os.getppid()
    for _ in range(16):
        if pid <= 1 or pid in seen: break
        seen.add(pid)
        try:
            paths.append(os.readlink("/proc/"+str(pid)+"/exe"))
            with open("/proc/"+str(pid)+"/stat", "rb") as value: raw = value.read(4097)
            require(len(raw) <= 4096 and b") " in raw, "runner process metadata budget")
            pid = int(raw.rsplit(b") ", 1)[1].split()[1])
        except (FileNotFoundError, PermissionError, ProcessLookupError): break
    return runner_application(paths)


def capture_host():
    env = {name: os.environ[name] for name in ENV_KEYS if name in os.environ}
    env.update({key: value for key, value in os.environ.items() if key.startswith("LD_") or
                key in ("GCONV_PATH", "PYTHONPATH", "PYTHONHOME", "GNUPGHOME")})
    os_release = system_file("/etc/os-release", 16384)["raw"]
    identity = protocol.runner_identity(env, os_release)  # Reject image before inventory/download/tools.
    require(platform.machine() == "x86_64", "host CPU architecture")
    application = observe_runner_application()
    require(application["version"] is not None, "runner application version requires provider log corroboration")
    identity["job"]["runner_application_version"] = application["version"]
    context = dict(job=identity["job"], observed_image_version=env.get("ImageVersion"),
                   assessment_epoch=int(time.time()), kernel_release=platform.release(),
                   python_version=sys.version.split()[0], hardware_attested=False,
                   runner_application=application,
                   unresolved_context=["runner version/path should be corroborated by the provider Set up job log",
                                       "identity/image environment is delegated provider evidence, not hardware attestation"])
    return env, os_release, context, inventory_toolchain(), system_file(KEYRING, 128*1024)["raw"]


def invoke(tool, arguments, directory, stdin, limit):
    require(tool in TOOLS and type(arguments) is list and 0 < limit <= 64*MIB, "preinstalled process allowlist/budget")
    require(all(type(arg) is str and "\0" not in arg for arg in arguments), "tool argument identity")
    def limits():
        resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
        resource.setrlimit(resource.RLIMIT_AS, (512*MIB, 512*MIB))
        resource.setrlimit(resource.RLIMIT_FSIZE, (limit, limit))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    with tempfile.TemporaryFile(dir=directory) as output, tempfile.TemporaryFile(dir=directory) as errors:
        process = subprocess.Popen([TOOLS[tool], *arguments], stdin=stdin if stdin is not None else subprocess.DEVNULL,
            stdout=output, stderr=errors, cwd=directory, close_fds=True, start_new_session=True, preexec_fn=limits,
            env={"LANG": "C", "LC_ALL": "C", "TZ": "UTC", "PATH": "/nonexistent", "HOME": str(directory), "GNUPGHOME": str(directory)})
        try: code = process.wait(timeout=25)
        except BaseException:
            try: os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            process.wait()
            raise
        require(output.seek(0, 2) <= limit and errors.seek(0, 2) <= 65536, "tool output/diagnostic budget")
        output.seek(0); errors.seek(0)
        return code, output.read(limit+1), errors.read(65537)


def gpgv_verifier(work, toolchain):
    """The real adapter callback; tests replace only preinstalled I/O/processes."""
    def verifier(raw, ring):
        row = system_file(TOOLS["gpgv"], 32*MIB)
        require(sha256(row["raw"]) == toolchain["files"][toolchain["tools"]["gpgv"]]["sha256"], "preinstalled tool changed")
        with tempfile.TemporaryDirectory(dir=work) as name:
            directory = Path(name)
            for filename, data in (("input", raw), ("keyring.gpg", ring)):
                with (directory/filename).open("xb") as value: value.write(data)
            code, status, _ = invoke("gpgv", ["--homedir", str(directory), "--keyring", "./keyring.gpg",
                "--status-fd", "1", "--output", "plain", "input"], directory, None, 2*MIB)
            plain = read_bounded(directory/"plain", 2*MIB) if (directory/"plain").exists() else b""
            require(len(status) <= 16384, "GPG status stream budget")
            return code, status, plain
    return verifier


def authenticate_hosted():
    require(AUTHENTICATION_ENABLED, "Ubuntu authentication adapter remains source-sealed")
    # This path is implemented for a separately authorized source-unsealing change.
    root = Path(__file__).resolve().parents[4]
    require(str(root) == os.environ.get("GITHUB_WORKSPACE"), "reviewed workspace identity")
    require(read_bounded(root/".git/HEAD", 128).decode().strip() == os.environ.get("GITHUB_SHA"), "checkout immutable head identity")
    policy = root/"tests/native/external_vm/s4/trust-policy.json"
    require(sha256(read_bounded(policy, 16384)) == POLICY_SHA256, "pending trust policy changed")
    parent = Path(os.environ.get("RUNNER_TEMP", ""))
    require(parent.is_absolute() and parent.resolve() == parent and parent.is_dir(), "runner private output parent")
    output = parent/packets.DESTINATION
    context = dict(observed_image_version=os.environ.get("ImageVersion"), hardware_attested=False,
                   job={key: os.environ.get(key) for key in ENV_KEYS if key not in ("GITHUB_ACTIONS", "REVIEWED_SOURCE_SHA")})
    phase = "runner-admission"
    try:
        env, os_release, context, toolchain, keyring = capture_host()
        resource.setrlimit(resource.RLIMIT_AS, (2*1024*MIB, 2*1024*MIB))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        tls = ssl.create_default_context(cafile="/etc/ssl/certs/ca-certificates.crt")
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=tls), SnapshotRedirect(SNAPSHOT))
        network_bytes = 0
        def acquire(name, url, size):
            nonlocal network_bytes
            network_bytes += size
            require(network_bytes <= 64*MIB, "aggregate network byte budget")
            return download(url, size, opener)
        with tempfile.TemporaryDirectory(prefix="panda-ubuntu-auth-", dir=parent) as work:
            work = Path(work)
            def unchanged(tool):
                row = system_file(TOOLS[tool], 32*MIB)
                require(sha256(row["raw"]) == toolchain["files"][toolchain["tools"][tool]]["sha256"], "preinstalled tool changed")
            verifier = gpgv_verifier(work, toolchain)
            def inflate(raw, limit):
                unchanged("zstd")
                with tempfile.TemporaryFile(dir=work) as source:
                    source.write(raw); source.seek(0)
                    code, output, _ = invoke("zstd", ["--decompress", "--stdout", "--no-progress"], work, source, limit)
                    require(code == 0, "preinstalled zstd decoder failed")
                    return output
            phase = "authentication-and-membership"
            bundle = protocol.verify_ubuntu(env, os_release, context["assessment_epoch"], keyring, toolchain, acquire, verifier, inflate)
        for path, row in toolchain["files"].items():
            require(sha256(system_file(path, 32*MIB)["raw"]) == row["sha256"], "post-verification toolchain drift")
        require(sha256(read_bounded(policy, 16384)) == POLICY_SHA256, "trust policy mutated")
        documents = {name+".json": protocol.canonical(row) for name, row in bundle["receipts"].items()}
    except Exception as error:
        # Error class/phase only: never expose arbitrary diagnostics, env or payload data.
        return packets.publish_with_fallback(output, None, context, failure=error, phase=phase)
    return packets.publish_with_fallback(output, documents, context)


def main(argv=None):
    if not AUTHENTICATION_ENABLED:
        print(protocol.canonical(dict(schema_version=1, status="source-sealed", accepted=False,
            execution_authorized=False, trust_policy_activation_allowed=False)).decode(), end="")
        return 78
    require(not (sys.argv[1:] if argv is None else argv), "runner accepts no arbitrary paths or commands")
    result = authenticate_hosted()
    if result["packet_token"] is not None: packets.github_publication_handoff(result["packet_token"])
    return result["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
