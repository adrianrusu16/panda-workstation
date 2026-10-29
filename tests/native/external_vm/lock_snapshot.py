"""Resolve snapshot metadata only; never install packages or start a worker.

Regeneration needs an existing Arch vercmp metadata utility. The hosted
preparation workflow consumes the lock and does not run this tool.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile

SNAPSHOT = "2026/10/15"
RUNTIME_ROOTS = ["ksvg", "qt6-base", "qt6-svg", "ttf-dejavu"]
BUILD_ROOTS = ["gcc", "pkgconf"]
PROVIDERS = {"libgl": "libglvnd", "dbus-units": "dbus-broker-units",
             "libz.so": "zlib", "opengl-driver": "mesa"}


def read_index(path, repo):
    if path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError("package index exceeds metadata budget")
    result = {}
    with tarfile.open(path) as archive:
        for member in archive:
            if not member.name.endswith("/desc"):
                continue
            if not member.isfile() or member.size > 1024 * 1024:
                raise ValueError("invalid metadata entry")
            text = archive.extractfile(member).read().decode("utf-8")
            fields = {part.splitlines()[0].strip("%"): part.splitlines()[1:]
                      for part in text.strip().split("\n\n") if part}
            name = fields["NAME"][0]
            if name in result:
                raise ValueError("duplicate package")
            result[name] = dict(fields, REPO=[repo])
    return result


def requirement(text):
    match = re.fullmatch(r"([^<>=]+)(>=|<=|=|>|<)?(.*)", text)
    if not match or (match[2] and not match[3]):
        raise ValueError("malformed dependency")
    return match[1], match[2], match[3]


def satisfies(actual, operator, wanted, compare):
    if not operator:
        return True
    if not actual:
        return False
    order = compare(actual, wanted)
    return {"=": order == 0, ">=": order >= 0, "<=": order <= 0,
            ">": order > 0, "<": order < 0}[operator]


def resolve(rows, roots, compare):
    """One frozen epoch; refuse ambiguous providers rather than choose arbitrarily."""
    selected, edges, pending = set(), [], list(roots)
    while pending:
        name = pending.pop(0)
        if name in selected:
            continue
        if name not in rows:
            raise ValueError("missing package: " + name)
        selected.add(name)
        for dep in rows[name].get("DEPENDS", []):
            target, operator, wanted = requirement(dep)
            if target in rows:
                provider, actual = target, rows[target]["VERSION"][0]
            else:
                matches = []
                for candidate, row in rows.items():
                    for provided in row.get("PROVIDES", []):
                        base, _, version = requirement(provided)
                        if base == target and satisfies(version, operator, wanted, compare):
                            matches.append((candidate, version))
                if target in PROVIDERS:
                    matches = [item for item in matches if item[0] == PROVIDERS[target]]
                if len(matches) != 1:
                    raise ValueError("ambiguous or missing provider: " + dep + " " + str(matches))
                provider, actual = matches[0]
            if not satisfies(actual, operator, wanted, compare):
                raise ValueError("unsatisfied dependency: " + name + " -> " + dep)
            edges.append(dict(origin=name, requirement=dep, provider=provider, provided_version=actual))
            pending.append(provider)
    return selected, sorted(edges, key=lambda e: (e["origin"], e["requirement"]))


def make_lock(core, extra, compare):
    rows, other = read_index(core, "core"), read_index(extra, "extra")
    if rows.keys() & other.keys():
        raise ValueError("duplicate cross-repository package")
    rows.update(other)
    runtime, _ = resolve(rows, RUNTIME_ROOTS, compare)
    all_names, edges = resolve(rows, RUNTIME_ROOTS + BUILD_ROOTS, compare)
    packages = []
    for name in sorted(all_names):
        row = rows[name]
        signature = row["PGPSIG"][0]
        base64.b64decode(signature, validate=True)
        repo, filename = row["REPO"][0], row["FILENAME"][0]
        packages.append(dict(name=name, version=row["VERSION"][0], repo=repo,
            filename=filename, architecture=row["ARCH"][0], sha256=row["SHA256SUM"][0],
            compressed_bytes=int(row["CSIZE"][0]), installed_bytes=int(row["ISIZE"][0]),
            signature_base64=signature, build_epoch=int(row["BUILDDATE"][0]),
            source_base=row["BASE"][0], depends=row.get("DEPENDS", []),
            provides=row.get("PROVIDES", []), role="runtime" if name in runtime else "build-only",
            url=f"https://archive.archlinux.org/repos/{SNAPSHOT}/{repo}/os/x86_64/{filename}"))
    indexes = [dict(repo=repo, sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                    url=f"https://archive.archlinux.org/repos/{SNAPSHOT}/{repo}/os/x86_64/{repo}.db")
               for repo, path in (("core", core), ("extra", extra))]
    return dict(schema_version=1, snapshot=SNAPSHOT, architecture="x86_64",
        approach="signed-distribution-snapshot", execution_enabled=False,
        authentication_status="pending-package-signatures-and-trust-bootstrap",
        indexes=indexes, runtime_roots=RUNTIME_ROOTS, build_roots=BUILD_ROOTS,
        provider_choices=PROVIDERS, packages=packages, dependency_edges=edges,
        totals=dict(package_count=len(packages), runtime_package_count=len(runtime),
            runtime_compressed_bytes=sum(p["compressed_bytes"] for p in packages if p["role"] == "runtime"),
            runtime_installed_bytes=sum(p["installed_bytes"] for p in packages if p["role"] == "runtime"),
            compressed_bytes=sum(p["compressed_bytes"] for p in packages),
            installed_bytes=sum(p["installed_bytes"] for p in packages)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core", type=Path, required=True)
    parser.add_argument("--extra", type=Path, required=True)
    args = parser.parse_args()
    executable = shutil.which("vercmp")
    if not executable:
        parser.error("existing Arch vercmp metadata utility required; no automatic install")

    def compare(actual, wanted):
        return int(subprocess.check_output([executable, actual, wanted], text=True, timeout=5).strip())

    print(json.dumps(make_lock(args.core, args.extra, compare), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
