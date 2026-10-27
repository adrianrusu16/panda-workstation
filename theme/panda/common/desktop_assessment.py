"""D4C1 saved-file assessment only: no discovery, commands, writes or KDE APIs."""
import errno
import hashlib
import os
from pathlib import Path
import re
import stat


class AccessRefused(ValueError):
    """A non-mutating read could not be established or remained unstable."""


def _stat(s):
    return dict(dev=s.st_dev, ino=s.st_ino, mode=s.st_mode, uid=s.st_uid,
                gid=s.st_gid, nlink=s.st_nlink, size=s.st_size,
                atime_ns=s.st_atime_ns, mtime_ns=s.st_mtime_ns, ctime_ns=s.st_ctime_ns)


def _identity(s):
    return s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid


def _attrs(fd):
    try:
        return {key: hashlib.sha256(os.getxattr(fd, key)).hexdigest()
                for key in sorted(os.listxattr(fd))}
    except OSError as error:
        if error.errno in (errno.ENOTSUP, errno.EOPNOTSUPP):
            return {"unsupported": "filesystem xattrs unavailable"}
        raise


def read_preserved(path, *, max_bytes=8 * 1024 * 1024, expected_uid=None):
    """Return bytes and receipt, or refuse; never fall back from O_NOATIME.

    Every path component is opened without following symlinks. Directory fds
    remain open until parent bindings, file metadata and xattrs are rechecked.
    This is not a backup, KConfig evaluator or live-session inventory.
    """
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts or path.name in ("", "."):
        raise AccessRefused("an absolute, non-traversing file path is required")
    if type(max_bytes) is not int or not 0 < max_bytes <= 64 * 1024 * 1024:
        raise AccessRefused("invalid read bound")
    if expected_uid is None:
        expected_uid = os.getuid()
    if not all(hasattr(os, flag) for flag in ("O_PATH", "O_NOATIME", "O_NOFOLLOW")):
        raise AccessRefused("required non-mutating Linux flags unavailable")
    fds, bindings = [], []
    try:
        current = os.open("/", os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW)
        fds.append(current)
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=current)
            fds.append(child)
            info = os.fstat(child)
            # Root-owned sticky temporary roots are allowed for disposable tests.
            if info.st_uid not in (0, os.getuid()):
                raise AccessRefused("unexpected parent owner")
            if info.st_mode & stat.S_IWOTH and not (info.st_uid == 0 and info.st_mode & stat.S_ISVTX):
                raise AccessRefused("unsafe writable parent")
            bindings.append((current, part, child, _identity(info)))
            current = child
        before_path = os.stat(path.name, dir_fd=current, follow_symlinks=False)
        if (not stat.S_ISREG(before_path.st_mode) or before_path.st_uid != expected_uid
                or before_path.st_nlink != 1 or before_path.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
                or before_path.st_size > max_bytes):
            raise AccessRefused("regular, singly linked, safely owned bounded file required")
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NOATIME | os.O_NONBLOCK,
                     dir_fd=current)
        fds.append(fd)
        before = _stat(os.fstat(fd))
        if before != _stat(before_path):
            raise AccessRefused("file identity changed before reading")
        attrs = _attrs(fd)
        chunks, length = [], 0
        while True:
            data = os.read(fd, min(65536, max_bytes + 1 - length))
            if not data:
                break
            chunks.append(data)
            length += len(data)
            if length > max_bytes:
                raise AccessRefused("file grew beyond read bound")
        after = _stat(os.fstat(fd))
        if (before != after or after != _stat(os.stat(path.name, dir_fd=current, follow_symlinks=False))
                or attrs != _attrs(fd)):
            raise AccessRefused("file bytes, metadata or binding changed during read")
        parents = []
        for parent, name, child, identity in bindings:
            if (_identity(os.fstat(child)) != identity or
                    _identity(os.stat(name, dir_fd=parent, follow_symlinks=False)) != identity):
                raise AccessRefused("parent binding changed during read")
            parents.append(dict(component=name, dev=identity[0], ino=identity[1],
                                mode=identity[2], uid=identity[3], gid=identity[4]))
        payload = b"".join(chunks)
        return payload, dict(path=str(path), before=before, after=after,
                             sha256=hashlib.sha256(payload).hexdigest(),
                             xattr_sha256=attrs, parents=parents,
                             parent_bindings_verified=True)
    except (OSError, ValueError) as error:
        if isinstance(error, AccessRefused):
            raise
        raise AccessRefused(f"non-mutating access refused ({type(error).__name__})") from error
    finally:
        for fd in reversed(fds):
            os.close(fd)


def parse_groups(payload):
    """Parse a strict saved KConfig subset; preserve raw keys/values verbatim.

    No expression, escape, include or environment expansion is performed.
    Repeated sections/keys and unsupported syntax cause a refusal. Callers
    must treat KConfig flags and unrecognized fields as unassessed.
    """
    if not isinstance(payload, bytes) or len(payload) > 8 * 1024 * 1024:
        raise ValueError("bounded bytes required")
    text = payload.decode("utf-8")
    if "\x00" in text:
        raise ValueError("NUL in configuration")
    groups, group = {}, ()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", ";")):
            continue
        if stripped.startswith("["):
            if not re.fullmatch(r"(?:\[[^\[\]\r\n]+\])+", stripped):
                raise ValueError("unsupported group syntax")
            group = tuple(re.findall(r"\[([^\]]+)\]", stripped))
            if group in groups:
                raise ValueError("duplicate group")
            groups[group] = {}
        else:
            if "=" not in line:
                raise ValueError("unsupported entry syntax")
            key, value = line.split("=", 1)
            key = key.strip()
            if not key or key in groups.setdefault(group, {}):
                raise ValueError("empty or duplicate key")
            groups[group][key] = value
    return groups


def classify_instances(groups, plugin, desktop_id):
    """Explicit target binding; matching panel/tray applets are never repurposed."""
    if type(desktop_id) is not int or desktop_id <= 0:
        raise ValueError("explicit desktop containment ID required")
    # KConfig flags/escapes can alter identity lookup. They are deliberately not
    # evaluated by this subset parser, so absence cannot be established from them.
    for group, values in groups.items():
        # An escaped root/key may itself encode an otherwise matching identity.
        # Refuse rather than attempting KConfig decoding or silently skipping it.
        if any("\\" in part for part in group) or any("\\" in key for key in values):
            raise ValueError("unassessed escaped group or key syntax")
        if group and group[0] == "Containments":
            if any(part.startswith("$") for part in group):
                raise ValueError("unassessed containment identity syntax")
            if any(key.startswith("plugin[") for key in values):
                raise ValueError("unassessed plugin key flags")
            if "\\" in values.get("plugin", ""):
                raise ValueError("unassessed plugin value escapes")
    parent = groups.get(("Containments", str(desktop_id)), {})
    if parent.get("plugin") not in ("org.kde.plasma.folder", "org.kde.desktopcontainment"):
        raise ValueError("target is not a supported desktop containment")
    matches, other = [], []
    for group, values in groups.items():
        if (len(group) < 4 or group[0] != "Containments" or group[-2] != "Applets"
                or values.get("plugin") != plugin):
            continue
        if not group[-3].isdigit() or not group[-1].isdigit():
            raise ValueError("non-numeric applet identity")
        item = dict(id=int(group[-1]), parent_id=int(group[-3]), plugin=plugin,
                    parent_kind="containment" if len(group) == 4 else "applet",
                    group_path=list(group))
        (matches if len(group) == 4 and item["parent_id"] == desktop_id else other).append(item)
    matches.sort(key=lambda item: item["id"])
    other.sort(key=lambda item: (item["parent_id"], item["id"]))
    status = "absent" if not matches else "existing" if len(matches) == 1 else "ambiguous"
    return dict(status=status, matches=matches, other_instances=other)


CLOCK_SETTINGS = {
    "Appearance/showDate": True,
    "Appearance/dateFormat": "custom",
    "Appearance/customDateFormat": "dddd, d MMMM",
    "Appearance/use24hFormat": 2,
    "Appearance/dateDisplayFormat": 2,
    "Appearance/showSeconds": 0,
    "Appearance/autoFontAndSize": True,
}
BASE_STOPS = [
    "separate-native-authorization-required",
    "running-version-and-output-unobserved",
    "recovery-prerequisites-unresolved",
    "native-minima-and-font-metrics-unmeasured",
    "widget-geometry-script-setter-is-no-op-in-baseline",
    "runtime-task-pins-not-established",
]


def build_candidate(config, fixture, *, installed_plasma):
    """Pure fixture-only proposal; never emit an executable operation or new ID."""
    import copy
    from desktop_layout import build_plan, digest
    if not isinstance(installed_plasma, str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+|unobserved", installed_plasma):
        raise ValueError("explicit installed-version observation required")
    plan = build_plan(config, fixture, presentation="compact")
    stops = list(BASE_STOPS)
    if installed_plasma != "6.7.5":
        stops.append("installed-version-differs-from-baseline")
    roles = []
    for item in plan["widgets"][:2]:
        existing = item["instance_id"] is not None
        if not existing:
            stops.append(item["role"] + "-new-instance-authorization-required")
        roles.append(dict(role=item["role"], plugin=item["plugin"],
                          instance_id=item["instance_id"],
                          binding="reuse_existing_desktop_instance" if existing else "new_instance_proposed",
                          rect=item["rect"], geometry_method="future-operator-edit-mode-only",
                          settings=dict(CLOCK_SETTINGS) if item["role"] == "clock" else {},
                          background_request="StandardBackground" if item["role"] == "clock" else "stock-style-inheritance"))
    return dict(schema_version=1, scope="offline-clock-media-candidate",
                native_verified=False, ready_for_native_test=False,
                baseline_plasma="6.7.5", installed_plasma=installed_plasma,
                fixture_sha256=digest(fixture), preserved_fixture=copy.deepcopy(fixture),
                roles=roles, stop_conditions=stops)


def validate_candidate(value, config):
    """Strict non-executable candidate schema; claims/settings cannot be widened."""
    from desktop_layout import fields, validate_fixture, digest, CATALOG, build_plan
    fields(value, ("schema_version","scope","native_verified","ready_for_native_test",
                   "baseline_plasma","installed_plasma","fixture_sha256","preserved_fixture",
                   "roles","stop_conditions"), "candidate")
    if (type(value["schema_version"]) is not int or value["schema_version"] != 1
            or value["scope"] != "offline-clock-media-candidate"
            or value["native_verified"] is not False or value["ready_for_native_test"] is not False
            or value["baseline_plasma"] != "6.7.5"
            or not isinstance(value["installed_plasma"],str)
            or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+|unobserved",value["installed_plasma"])):
        raise ValueError("only an explicitly gated offline candidate is supported")
    validate_fixture(value["preserved_fixture"])
    if value["fixture_sha256"] != digest(value["preserved_fixture"]):
        raise ValueError("preservation fixture fingerprint mismatch")
    if not isinstance(value["roles"],list) or len(value["roles"]) != 2:
        raise ValueError("exactly clock and media are assessed")
    geometry=build_plan(config,value["preserved_fixture"],presentation="compact")["widgets"][:2]
    expected_stops=list(BASE_STOPS)
    if value["installed_plasma"] != "6.7.5":
        expected_stops.append("installed-version-differs-from-baseline")
    for role,item,model in zip(("clock","media"),value["roles"],geometry):
        fields(item,("role","plugin","instance_id","binding","rect","geometry_method","settings","background_request"),role)
        ident=value["preserved_fixture"]["bindings"][role]
        if item["role"] != role or item["plugin"] != CATALOG[role][0] or item["instance_id"] != ident:
            raise ValueError("instance/plugin identity mismatch")
        if ident is not None and type(item["instance_id"]) is not int:
            raise ValueError("integer instance ID required")
        binding="reuse_existing_desktop_instance" if ident is not None else "new_instance_proposed"
        if item["binding"] != binding or item["geometry_method"] != "future-operator-edit-mode-only":
            raise ValueError("binding or geometry implementation claim rejected")
        if ident is None:expected_stops.append(role+"-new-instance-authorization-required")
        settings=CLOCK_SETTINGS if role=="clock" else {}
        if (not isinstance(item["settings"],dict) or set(item["settings"]) != set(settings)
                or any(type(item["settings"][key]) is not type(v) or item["settings"][key] != v for key,v in settings.items())):
            raise ValueError("unreviewed native settings")
        if item["background_request"] != ("StandardBackground" if role=="clock" else "stock-style-inheritance"):
            raise ValueError("unreviewed background request")
        if item["rect"] != model["rect"]:
            raise ValueError("candidate geometry differs from validated D4A model")
        rect=item["rect"]
        if not isinstance(rect,list) or len(rect)!=4 or any(type(x) not in (int,float) or not 0<=x<=16384 for x in rect) or rect[2]<=0 or rect[3]<=0:
            raise ValueError("bounded model rectangle required")
    if value["stop_conditions"] != expected_stops:
        raise ValueError("required stop conditions changed")
    return value
