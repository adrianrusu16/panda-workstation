"""Strict Google archive transport and no-overwrite Linux SDK tools publication."""

import ctypes
import errno
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import urllib.parse
import urllib.request
import zipfile


class ArchiveError(Exception):
    pass


def validate_url(url):
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname != "dl.google.com"
            or parsed.username or parsed.password or parsed.port not in (None, 443)
            or not parsed.path.startswith("/android/repository/")
            or parsed.query or parsed.fragment or "/../" in parsed.path):
        raise ArchiveError("Archive URL/redirect must use HTTPS on dl.google.com/android/repository/")
    return url


class GoogleRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download(url, destination):
    """No proxy-supplied archive source, no credential headers, bounded download."""
    validate_url(url)
    destination = Path(destination)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), GoogleRedirect())
    created = False
    try:
        with destination.open("xb") as output:
            created = True
            with opener.open(url, timeout=60) as response:
                validate_url(response.geturl())
                total = 0
                while chunk := response.read(1024 * 1024):
                    total += len(chunk)
                    if total > 1024 * 1024 * 1024:
                        raise ArchiveError("Archive exceeds 1 GiB download limit")
                    output.write(chunk)
    except BaseException as exc:
        if created:
            destination.unlink(missing_ok=True)
        if isinstance(exc, (KeyboardInterrupt, SystemExit, ArchiveError)):
            raise
        raise ArchiveError(f"Download failed ({type(exc).__name__}); retry after reviewing connectivity") from exc


def stage_archive(archive_path, staging, sha256, revision):
    """Inspect every member before extraction; never trust ZIP paths or modes."""
    archive_path, staging = Path(archive_path), Path(staging)
    if not re.fullmatch(r"[0-9a-f]{64}", sha256):
        raise ArchiveError("Missing/invalid publisher SHA-256 checksum")
    with archive_path.open("rb") as source:
        actual = hashlib.file_digest(source, "sha256").hexdigest()
    if actual != sha256:
        raise ArchiveError("Archive checksum mismatch; nothing extracted")
    if staging.exists() or staging.is_symlink():
        raise ArchiveError("Staging destination already exists")
    created = False
    try:
        with zipfile.ZipFile(archive_path) as archive:
            entries, names, regular_files, total = archive.infolist(), set(), set(), 0
            if not entries or len(entries) > 50000:
                raise ArchiveError("Unexpected archive member count")
            for entry in entries:
                name = entry.filename
                parts = PurePosixPath(name).parts
                mode = entry.external_attr >> 16
                kind = stat.S_IFMT(mode)
                if (not parts or parts[0] != "cmdline-tools" or name.startswith("/")
                        or "\\" in name or "\x00" in name or ":" in name
                        or any(p in ("", ".", "..") for p in name.rstrip("/").split("/"))
                        or name.rstrip("/") in names
                        or kind not in (0, stat.S_IFREG, stat.S_IFDIR)
                        or bool(entry.flag_bits & 1)):
                    raise ArchiveError(f"Unsafe archive member: {name!r}")
                if not entry.is_dir() and len(parts) < 2:
                    raise ArchiveError("Unexpected top-level file")
                # Google's authenticated 22.0 ZIP marks every regular file 0755,
                # including JARs, source.properties, NOTICE.txt and lib/README.
                # Accept only those expected data locations outside direct bin
                # launchers, and always strip their execute bits on extraction.
                launcher = len(parts) == 3 and parts[1] == "bin"
                known_data = (name in ("cmdline-tools/source.properties", "cmdline-tools/NOTICE.txt",
                                       "cmdline-tools/lib/README")
                              or (len(parts) >= 3 and parts[1] == "lib" and parts[-1].endswith(".jar")))
                if not entry.is_dir() and mode & 0o111 and not (launcher or known_data):
                    raise ArchiveError("Unexpected executable outside cmdline-tools/bin or known SDK data locations")
                names.add(name.rstrip("/"))
                if not entry.is_dir() and kind in (0, stat.S_IFREG):
                    regular_files.add(name)
                total += entry.file_size
                if total > 2 * 1024 * 1024 * 1024:
                    raise ArchiveError("Archive exceeds 2 GiB extraction limit")
            required = {"cmdline-tools/bin/sdkmanager", "cmdline-tools/source.properties",
                        "cmdline-tools/lib/sdkmanager-classpath.jar"}
            if not required.issubset(regular_files):
                raise ArchiveError("Incomplete Command-Line Tools archive layout; required members must be regular files")
            staging.mkdir(mode=0o700)
            created = True
            for entry in entries:
                target = staging / entry.filename
                if entry.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(entry) as source, target.open("xb") as output:
                        shutil.copyfileobj(source, output)
                    executable = len(PurePosixPath(entry.filename).parts) == 3 and \
                        PurePosixPath(entry.filename).parts[1] == "bin"
                    target.chmod(0o755 if executable else 0o644)
            root = staging / "cmdline-tools"
            if not (root / "bin/sdkmanager").is_file() or not os.access(root / "bin/sdkmanager", os.X_OK):
                raise ArchiveError("Invalid staged SDK Manager executable layout")
            properties = (root / "source.properties").read_text()
            if not re.search(r"^Pkg\.Revision\s*=\s*" + re.escape(revision) + r"\s*$",
                             properties, re.M):
                raise ArchiveError("Archive revision differs from pinned manifest")
            return root
    except BaseException as exc:
        if created:
            shutil.rmtree(staging)
        if isinstance(exc, (KeyboardInterrupt, SystemExit, ArchiveError)):
            raise
        raise ArchiveError(f"Extraction failed ({type(exc).__name__}); no tools published") from exc


def rename_noreplace(source, destination):
    """Linux renameat2(RENAME_NOREPLACE); fail closed on unsupported platforms/FS."""
    libc = ctypes.CDLL(None, use_errno=True)
    try:
        rename = libc.renameat2
    except AttributeError as exc:
        raise OSError(errno.ENOSYS, "Atomic no-replace rename unavailable") from exc
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(-100, os.fsencode(source), -100, os.fsencode(destination), 1) != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))


def publish(staged, destination):
    """Caller supplies private staging on the destination filesystem."""
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ArchiveError("Refusing to replace occupied Command-Line Tools destination")
    try:
        rename_noreplace(staged, destination)
    except OSError as exc:
        raise ArchiveError(f"Atomic publication failed ({exc.errno}); previous tools preserved") from exc
