"""Source-only validation and bounded VM preparation receipts. No native launcher."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import sys

RELATIVE = Path("tests/native/external_vm")
MIB = 1024 * 1024
INPUTS = {
    "theme/panda/plasma-styles/panda-cyber-s1/widgets/background.svg":
        "/inputs/data/plasma/desktoptheme/panda-cyber-s1/widgets/background.svg",
    **{"theme/panda/plasma-styles/panda-cyber-s1/" + name:
       "/inputs/data/plasma/desktoptheme/panda-cyber-s1/" + name
       for name in ("colors", "metadata.json", "plasmarc", "LICENSE")},
    "tests/native/external_vm/fonts.conf": "/inputs/fonts.conf",
}
PRESERVED = (
    ".github/workflows/validate.yml", "tests/fixtures/desktop/native-frame-contract.json",
    "tests/native/plasma_frame_worker.cpp", "tests/native/sandbox_supervisor.py",
    "tests/native/inert-profile.json", "tests/native/inert_probe.c",
    "tests/native/isolation-attestation.schema.json", "tests/test_sandbox_supervisor.py",
    "theme/panda/common/native_frame_plan.py",
)
PACKET = ("candidate.json", "packages.lock.json", "single_frame_candidate.cpp",
          "CMakeLists.txt", "fonts.conf", "capture.schema.json", "artifact.schema.json",
          "prepare.py", "lock_snapshot.py")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def bounded_read(path):
    require(not path.is_symlink() and path.is_file(), "regular source required: " + str(path))
    require(path.stat().st_size <= 4 * MIB, "source exceeds read budget")
    with path.open("rb") as source:
        value = source.read(4 * MIB + 1)
    require(len(value) <= 4 * MIB, "source grew beyond read budget")
    return value


def no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def read_json(path):
    def reject(value):
        raise ValueError("non-finite JSON number: " + value)
    return json.loads(bounded_read(path), object_pairs_hook=no_duplicates, parse_constant=reject)


def check_candidate(root, value):
    fixed = dict(schema_version=1, candidate_id="cyber-widget-288x88-dpr1", flavor="cyber",
        asset="widgets/background.svg", logical_size=[288, 88], device_pixel_ratio=1,
        renderer="KSvg::FrameSvg", execution_enabled=False, native_worker_executed=False,
        expected_margin_trbl=[12, 12, 12, 12], qt_version="6.12.0", ksvg_version="6.31.0")
    require(set(value) == set(fixed) | {"inputs", "preserved_sources", "dependency_lock_sha256",
                                      "runtime_inputs_pending"}, "unexpected candidate fields")
    for key, expected in fixed.items():
        require(type(value[key]) is type(expected) and value[key] == expected, "candidate scope drift: " + key)
    for key, expected in (("inputs", INPUTS), ("preserved_sources", {p: p for p in PRESERVED})):
        rows = value[key]
        require(isinstance(rows, list) and len(rows) == len(expected), "input receipt count drift")
        require({r["source"] for r in rows} == set(expected), "input receipt paths drift")
        for row in rows:
            require(set(row) == {"source", "destination", "sha256", "bytes"}, "invalid input receipt")
            raw = bounded_read(root / row["source"])
            require(row["destination"] == expected[row["source"]] and
                    type(row["bytes"]) is int and row["bytes"] == len(raw) and
                    row["sha256"] == digest(raw), "input receipt mismatch: " + row["source"])
    require(value["runtime_inputs_pending"] == ["font-file-sha256", "offscreen-plugin-sha256",
            "elf-loader-and-shared-library-file-manifest", "authenticated-package-build-origins"],
            "unresolved runtime gates must remain explicit")
    require(value["dependency_lock_sha256"] == digest(bounded_read(root / RELATIVE / "packages.lock.json")),
            "dependency lock receipt mismatch")


def check_lock(value):
    require(value["schema_version"] == 1 and value["snapshot"] == "2026/10/15" and
            value["architecture"] == "x86_64" and value["execution_enabled"] is False and
            value["approach"] == "signed-distribution-snapshot" and
            value["authentication_status"] == "pending-package-signatures-and-trust-bootstrap",
            "snapshot contract drift")
    rows = value["packages"]
    by_name = {p["name"]: p for p in rows}
    require(len(by_name) == len(rows) and list(by_name) == sorted(by_name), "duplicate/unordered packages")
    for name, version in {"qt6-base": "6.12.0-3", "qt6-svg": "6.12.0-1", "ksvg": "6.31.0-1"}.items():
        require(name in by_name and by_name[name]["version"] == version, "required renderer package drift")
    require(all(n in by_name for n in value["runtime_roots"] + value["build_roots"]), "missing root package")
    edge_map = {}
    for edge in value["dependency_edges"]:
        origin, provider = edge["origin"], edge["provider"]
        require(origin in by_name and provider in by_name, "dependency closure is incomplete")
        key = (origin, edge["requirement"])
        require(key not in edge_map, "duplicate dependency edge")
        edge_map[key] = edge
        match = re.fullmatch(r"([^<>=]+)(>=|<=|=|>|<)?(.*)", edge["requirement"])
        require(match is not None, "malformed dependency requirement")
        target = match[1]
        row = by_name[provider]
        if target == provider:
            require(edge["provided_version"] == row["version"], "provider version drift")
        else:
            provided = target + ("=" + edge["provided_version"] if edge["provided_version"] else "")
            require(provided in row["provides"], "virtual provider drift")
        # Arch version constraints were checked with vercmp during lock generation.
        # The candidate pins the entire lock; this checker does not substitute a
        # Python version ordering for libalpm or claim package authentication.
    for row in rows:
        require(not row["name"].startswith(("plasma-", "kwin", "nvidia")) and
                (not row["name"].startswith("linux-") or row["name"] == "linux-api-headers"),
                "out-of-scope package")
        require(re.fullmatch(r"[a-z0-9][a-z0-9+_.:-]*\.pkg\.tar\.zst", row["filename"]), "unsafe package filename")
        require(re.fullmatch(r"[0-9a-f]{64}", row["sha256"]), "invalid package hash")
        require(row["repo"] in ("core", "extra") and row["architecture"] in ("x86_64", "any"), "wrong repository/architecture")
        expected = (f"https://archive.archlinux.org/repos/2026/10/15/{row['repo']}/os/x86_64/" + row["filename"])
        require(row["url"] == expected, "unpinned package origin")
        require(100 <= len(base64.b64decode(row["signature_base64"], validate=True)) <= 8192, "invalid signature material")
        require(row["role"] in ("runtime", "build-only"), "invalid package role")
        require(type(row["compressed_bytes"]) is int and 0 < row["compressed_bytes"] < 1024 * MIB and
                type(row["installed_bytes"]) is int and 0 <= row["installed_bytes"] < 1024 * MIB,
                "invalid package size")  # Dependency-only metapackages may install zero bytes.
        require(all((row["name"], dep) in edge_map for dep in row["depends"]), "unresolved dependency")
    require(len(edge_map) == sum(len(p["depends"]) for p in rows), "extra dependency edges")
    runtime = [p for p in rows if p["role"] == "runtime"]
    totals = dict(package_count=len(rows), runtime_package_count=len(runtime),
        compressed_bytes=sum(p["compressed_bytes"] for p in rows),
        installed_bytes=sum(p["installed_bytes"] for p in rows),
        runtime_compressed_bytes=sum(p["compressed_bytes"] for p in runtime),
        runtime_installed_bytes=sum(p["installed_bytes"] for p in runtime))
    require(totals == value["totals"] and totals["installed_bytes"] <= 2 * 1024 * MIB,
            "closure size/count drift")
    return totals


def check_sources(root):
    base = root / RELATIVE
    check_candidate(root, read_json(base / "candidate.json"))
    totals = check_lock(read_json(base / "packages.lock.json"))
    for name in ("capture.schema.json", "artifact.schema.json"):
        require(read_json(base / name)["$schema"] == "https://json-schema.org/draft/2020-12/schema",
                "evidence schema dialect drift")
    source = bounded_read(base / "single_frame_candidate.cpp").decode()
    main = source[source.index("int main()") :]
    require(main == 'int main()\n{\n    std::fputs("D4C3-S3 source candidate is sealed; execution requires a reviewed source change.\\n", stderr);\n    return 78;\n}\n',
            "native execution seal changed")
    return dict(schema_version=1, frame_count=1, execution_enabled=False,
                native_worker_executed=False, package_count=totals["package_count"],
                dependency_authentication_verified=False, runtime_compatibility_verified=False,
                dependency_lock_sha256=digest(bounded_read(base / "packages.lock.json")))


def encode(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def runner_image_links(image_version):
    # Match runner-images configure-image-data.sh, which omits the patch
    # component from the release tag even though ImageVersion includes it.
    require(re.fullmatch(r"[0-9]{8}\.[0-9]+\.[0-9]+", image_version), "runner image version unavailable")
    tag = ".".join(image_version.split(".")[:2])
    return dict(image_release_url="https://github.com/actions/runner-images/releases/tag/ubuntu24%2F" + tag,
                included_software_url="https://github.com/actions/runner-images/blob/ubuntu24/" + tag +
                "/images/ubuntu/Ubuntu2404-Readme.md")


def prepare_packet(root):
    # Only the independently hosted preparation job may create this receipt.
    require(all(os.environ.get(k) == v for k, v in {
        "GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "github-hosted",
        "RUNNER_OS": "Linux", "RUNNER_ARCH": "X64", "ImageOS": "ubuntu24",
        "GITHUB_EVENT_NAME": "workflow_dispatch"}.items()), "standard hosted Ubuntu VM context required")
    import resource
    resource.setrlimit(resource.RLIMIT_CPU, (60, 60))
    resource.setrlimit(resource.RLIMIT_AS, (MIB * 1024, MIB * 1024))
    resource.setrlimit(resource.RLIMIT_FSIZE, (4 * MIB, 4 * MIB))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    release = dict(line.split("=", 1) for line in Path("/etc/os-release").read_text().splitlines() if "=" in line)
    require(release.get("ID", "").strip('"') == "ubuntu" and
            release.get("VERSION_ID", "").strip('"') == "24.04", "runner distribution drift")
    result = check_sources(root)
    image_version = os.environ.get("ImageVersion", "")
    image_links = runner_image_links(image_version)
    # Explicit allowlist only. Never export environment/event payloads or credentials.
    provenance = {k: os.environ.get(k, "") for k in (
        "ImageOS", "ImageVersion", "RUNNER_OS", "RUNNER_ARCH", "RUNNER_ENVIRONMENT",
        "GITHUB_REPOSITORY", "GITHUB_SHA", "GITHUB_WORKFLOW_SHA", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT")}
    require(re.fullmatch(r"[0-9a-f]{40}", provenance["GITHUB_SHA"]), "immutable source SHA required")
    provenance.update(schema_version=1, runner_label="ubuntu-24.04", kernel=os.uname().release,
        boundary_evidence="provider-documentation-and-recorded-runner-context",
        hardware_vm_attestation=False, native_worker_executed=False,
        cpu_count_limit=1, cpu_seconds_limit=60, address_space_bytes_limit=1024 * MIB,
        output_bytes_limit=8 * MIB)
    provenance.update(image_links)
    dependency = dict(schema_version=1, lock_sha256=result["dependency_lock_sha256"],
        packages_downloaded=False, packages_installed=False, signatures_verified=False,
        runtime_file_manifest_available=False, runner_tools_are_image_provided=True)
    packet = {name: bounded_read(root / RELATIVE / name) for name in PACKET}
    for source in INPUTS:
        if source.startswith("theme/"):
            packet["input-" + Path(source).name] = bounded_read(root / source)
    packet.update({"source-verification.json": encode(result), "runner-provenance.json": encode(provenance),
                   "dependency-provenance.json": encode(dependency)})
    inventory = {name: dict(sha256=digest(raw), bytes=len(raw)) for name, raw in packet.items()}
    packet["preparation-receipt.json"] = encode(dict(schema_version=1, status="prepared-not-executed", files=inventory))
    require(len(packet) <= 24 and sum(map(len, packet.values())) <= 8 * MIB, "packet exceeds export budget")
    directory = Path(os.environ["RUNNER_TEMP"]) / "panda-native-vm-preparation"
    directory.mkdir(mode=0o700, exist_ok=False)
    for name, raw in packet.items():
        with (directory / name).open("xb") as output:
            output.write(raw)
    print("Prepared source-only packet; native execution is sealed.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true")
    group.add_argument("--prepare", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    try:
        if args.prepare:
            prepare_packet(root)
        else:
            print(encode(check_sources(root)).decode(), end="")
    except (OSError, ValueError, KeyError, TypeError) as error:
        print("External VM preparation refused: " + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
