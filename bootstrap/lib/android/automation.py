"""Source-only Android automation entry point; mutation requires interactive consent.

Python 3.11+ standard library only. Never installs Studio, Java, plugins or dotfiles.
"""

import datetime
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import urllib.parse
import uuid

from android_archive import ArchiveError, download, publish, rename_noreplace, stage_archive, validate_url
import android_cli


ROOT = Path(__file__).resolve().parents[3]
BASELINE = ("platform-tools", "cmdline-tools;latest", "platforms;android-36.1", "build-tools;36.0.0")
PACKAGE_PATHS = {"platform-tools": "platform-tools", "platforms;android-36.1": "platforms/android-36.1",
                 "build-tools;36.0.0": "build-tools/36.0.0"}


class Error(Exception):
    def __init__(self, message, code=1):
        super().__init__(message)
        self.code = code


def validate_manifest(data):
    if (data.get("schema_version") != 1 or data.get("jdk", {}).get("required_major") != 21
            or data.get("jdk", {}).get("change_system_java_default") is not False
            or data.get("studio", {}).get("manual_install") is not True
            or data.get("studio", {}).get("allow_automated_replacement") is not False):
        raise Error("Unsupported manifest schema or unsafe JDK/Studio policy")
    packages = data.get("sdk", {}).get("packages", [])
    if sorted(packages) != sorted(BASELINE):
        raise Error("Manifest must select precisely the four approved baseline SDK packages")
    if any(data.get("optional", {}).values()):
        raise Error("Optional NDK/Rust/AAOS profiles are deferred and must remain disabled")
    if any(data.get("ide", {}).get(k) is not False for k in ("apply_plugins", "apply_preferences")):
        raise Error("IDE automation is unsupported; use the manual preview workflow")
    relative = Path(data["sdk"].get("default_home_relative", ""))
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise Error("Invalid default SDK path")
    cli = data.get("android_cli", {})
    if (cli.get("preferred") != "bundled" or cli.get("preferred_tools_revision") != "22.0"
            or cli.get("fallback") != "explicit-sdkmanager" or cli.get("timeout_seconds") != 120
            or cli.get("required_commands") != ["info sdk", "sdk list", "sdk install"]
            or any(cli.get("features", {}).values())):
        raise Error("Unsupported Android CLI selection, runtime or optional-feature policy")


def load_manifest(path):
    with Path(path).open("rb") as source:
        data = tomllib.load(source)
    validate_manifest(data)
    return data


def safe_path(path):
    """Refuse traversal, non-directory or symlinked SDK paths before mutation."""
    path = Path(path)
    if not path.is_absolute() or any(p in ("..",) for p in path.parts) or \
            any(ord(c) < 32 for c in str(path)) or path == Path("/"):
        raise Error("SDK path must be a non-root absolute path without traversal/control characters")
    for component in [*reversed(path.parents), path]:
        if component.is_symlink():
            raise Error(f"Unsafe SDK symlink: {component}")
        if component.exists() and not component.is_dir():
            raise Error(f"SDK path component is not a directory: {component}")
    return path


def properties(path):
    if not path.is_file() or path.is_symlink():
        return {}
    result = {}
    for line in path.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith(("#", "!")):
            key, value = line.split("=", 1)
            result[key.strip()] = value.strip()
    return result


def executable(path):
    return path.is_file() and not path.is_symlink() and os.access(path, os.X_OK)


def tools_ok(path):
    return (executable(path / "bin/sdkmanager")
            and bool(re.fullmatch(r"\d+(?:\.\d+)*", properties(path / "source.properties").get("Pkg.Revision", "")))
            and (path / "lib/sdkmanager-classpath.jar").is_file()
            and not (path / "lib/sdkmanager-classpath.jar").is_symlink())


def inventory(sdk):
    """Metadata/layout checks only; a healthy entry is not a runtime guarantee."""
    result = {}
    for package, relative in PACKAGE_PATHS.items():
        path = sdk / relative
        safe_path(path)
        meta = properties(path / "source.properties")
        revision = meta.get("Pkg.Revision", "")
        healthy = bool(re.fullmatch(r"\d+(?:\.\d+)*", revision))
        if package == "platform-tools":
            healthy &= executable(path / "adb")
        elif package == "platforms;android-36.1":
            # Google uses a dotted API identifier; retain the original split form.
            api = meta.get("AndroidVersion.ApiLevel", "").split(".")
            if "AndroidVersion.ApiMinorLevel" in meta:
                api.append(meta["AndroidVersion.ApiMinorLevel"])
            healthy &= ((path / "android.jar").is_file() and not (path / "android.jar").is_symlink()
                        and api == ["36", "1"])
        else:
            healthy &= executable(path / "aapt2") and revision == "36.0.0"
        result[package] = {"path": path, "healthy": bool(healthy), "revision": revision,
                           "occupied": path.exists()}
    cli_root = safe_path(sdk / "cmdline-tools")
    candidates = []
    if cli_root.is_dir():
        for path in cli_root.iterdir():
            if path.name == "latest" or re.fullmatch(r"\d+(?:\.\d+)*", path.name):
                safe_path(path)
                if tools_ok(path):
                    safe_path(path / "bin")
                    safe_path(path / "lib")
                    candidates.append(path)
    candidates.sort(key=lambda p: (p.name == "latest", tuple(
        int(x) for x in properties(p / "source.properties")["Pkg.Revision"].split("."))), reverse=True)
    selected = candidates[0] if candidates else cli_root / "latest"
    result["cmdline-tools;latest"] = {"path": selected, "healthy": bool(candidates),
        "revision": properties(selected / "source.properties").get("Pkg.Revision", ""),
        "occupied": selected.exists()}
    return result


def studio_info(data, env):
    candidates = [env.get("ANDROID_STUDIO_HOME", ""), data["studio"]["preferred_path"],
                  str(Path(env.get("HOME", str(Path.home()))) / "Applications/android-studio"),
                  "/opt/android-studio", "/usr/share/android-studio"]
    for name in filter(None, candidates):
        path = Path(name)
        if not path.is_absolute() or any(p.is_symlink() for p in [path, *path.parents]):
            continue
        info = path / "product-info.json"
        if info.is_file() and not info.is_symlink():
            try:
                product = json.loads(info.read_text())
                if product.get("name") == "Android Studio":
                    return f"{path}: version={product.get('version', 'unknown')} build={product.get('buildNumber', 'unknown')} (metadata only)"
            except (ValueError, OSError):
                pass
    return "manual checkpoint: no trusted Android Studio product-info.json found"


def inspect(data, env):
    validate_manifest(data)
    sdk = safe_path(env.get("ANDROID_HOME") or str(Path(env.get("HOME", str(Path.home()))) /
                                                   data["sdk"]["default_home_relative"]))
    legacy = env.get("ANDROID_SDK_ROOT")
    if legacy and Path(legacy) != sdk:
        raise Error("ANDROID_SDK_ROOT conflicts with ANDROID_HOME; review inherited selection")
    jdk = Path(env.get("JAVA_HOME") or "/nonexistent-jdk")
    jdk_ok = (jdk.is_absolute() and (jdk / "release").is_file()
              and executable(jdk / "bin/java") and executable(jdk / "bin/javac")
              and re.search(r'^JAVA_VERSION="21([.+"-]|$)', (jdk / "release").read_text(), re.M) is not None)
    return {"sdk": sdk, "jdk": jdk, "jdk_ok": jdk_ok, "packages": inventory(sdk),
            "studio": studio_info(data, env), "env": dict(env)}


def archive_metadata(data):
    meta = data.get("command_line_tools", {})
    if meta.get("verified") is not True:
        raise Error("UNCONFIGURED official Command-Line Tools metadata; bootstrap disabled")
    try:
        validate_url(meta["url"])
        source = urllib.parse.urlsplit(meta["publisher_source"])
        date = datetime.date.fromisoformat(meta["verified_on"])
        if (not re.fullmatch(r"\d+(?:\.\d+)*", meta["revision"])
                or not re.fullmatch(r"https://dl\.google\.com/android/repository/commandlinetools-linux-\d+_latest\.zip", meta["url"])
                or not re.fullmatch(r"[0-9a-f]{64}", meta["sha256"])
                or meta["sha256"] == "0" * 64 or date > datetime.date.today()
                or source.scheme != "https" or source.hostname not in ("developer.android.com", "dl.google.com")
                or source.username or source.password or source.port not in (None, 443)):
            raise ValueError("metadata fields")
    except (KeyError, ValueError, ArchiveError) as exc:
        raise Error("UNCONFIGURED/invalid official archive metadata or provenance; source review required") from exc
    return meta


def ide_plan(data, studio):
    print(f"Studio: {studio}; application installation/replacement is manual")
    with (ROOT / "config/android/studio-plugins.toml").open("rb") as source:
        plugins = tomllib.load(source)
    if plugins.get("schema_version") != 1 or not isinstance(plugins.get("plugins"), list):
        raise Error("Invalid plugin allowlist schema")
    for plugin in plugins["plugins"]:
        if (not isinstance(plugin, dict) or not all(isinstance(plugin.get(k), str) and plugin[k]
                for k in ("id", "name", "version", "source")) or plugin.get("desired") != "installed"):
            raise Error("Invalid plugin allowlist entry; explicit ID/name/version/source required")
        print(f"Manual plugin request: {plugin['name']} id={plugin['id']} version={plugin['version']} source={plugin['source']}; restart may be required")
    print(f"Plugin allowlist: {len(plugins['plugins'])}; compatibility/installer UNVERIFIED; automation partial/manual")
    print("Installed plugin inventory: not read (no verified Studio-specific interface); review in IDE Settings > Plugins")
    ide = data["ide"]
    print(f"Preferences preview: theme={ide['theme']}, font={ide['editor_font']}, size={ide['editor_font_size']} (0=preserve), keymap={ide['keymap']}")
    print("Manual reviewed settings export/import only; preserve accounts, existing plugins and preferences. Project formatting remains project-owned.")


def plan(data, state):
    print("Android automation plan — read-only; no vendor executable started")
    print(f"JAVA_HOME: {state['jdk']} — JDK 21 metadata/layout {'OK' if state['jdk_ok'] else 'MISSING/INVALID; manual jdk21-openjdk checkpoint'}")
    print(f"ANDROID_HOME: {state['sdk']}")
    try:
        candidate = android_cli.discover(state["sdk"], data["android_cli"]["preferred_tools_revision"])
        if candidate:
            print(f"Preferred Android CLI candidate: {candidate['path']} SHA-256={candidate['sha256']}")
            print(f"Bundled source: Command-Line Tools package revision={candidate['package_revision']}; "
                  f"launcher version={candidate['launcher_version']}; product version/capabilities pending --cli-check")
            shadow = shutil.which("android", path=state["env"].get("PATH", ""))
            if shadow and Path(shadow) != candidate["path"]:
                print(f"PATH shadow ignored: {shadow}; use the explicit SDK-local candidate")
            print("Launcher may download a separate application and write caches even for version/help; runtime approval required")
        else:
            print("Android CLI unavailable; legacy SDK Manager requires explicit fallback approval; no standalone installer")
    except android_cli.CliError as exc:
        print(f"Android CLI candidate refused: {exc}; runtime validation pending")
    for package in BASELINE:
        item = state["packages"][package]
        action = "reuse" if item["healthy"] else "repair (occupied)" if item["occupied"] else "install missing"
        print(f"{package}: {action}; revision={item['revision'] or 'unknown'}; path={item['path']}")
    platform = state["packages"]["platforms;android-36.1"]
    if platform["healthy"] and not android_cli.revisions_equal(platform["revision"], "1"):
        print("Platform 36.1 revision differs from approved revision 1; manual review, never automatic downgrade")
    try:
        meta = archive_metadata(data)
        print(f"Pinned CLI revision={meta['revision']} URL={meta['url']} SHA-256={meta['sha256']}")
        print(f"Publisher provenance: {meta['publisher_source']} verified_on={meta['verified_on']} (operator-reviewed source assertion)")
    except Error as exc:
        print(str(exc))
    print("Approvals: Android CLI runtime/network/cache validation or explicit SDK Manager fallback, exact package changes, interactive licenses; separate archive download and SDK publication when missing")
    print("Repair retains corrupt package backups; occupied CLI slots are never replaced. No disk-size estimate available before approved repository listing.")
    ide_plan(data, state["studio"])
    print("NDK/Rust targets/AAOS/emulator: disabled. No OS packages, IDE, dotfiles or system policy changes.")
    print("Evidence level: metadata/layout only; Java runtime, SDK runtime and PandaWave Gradle success are unverified.")


def confirm(message):
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise Error("Interactive terminal required; piped/noninteractive approval and terms acceptance refused", 2)
    try:
        return input(message + " [type yes]: ") == "yes"
    except EOFError:
        return False


def require(approve, message):
    if not approve(message):
        raise Error("Operator declined: " + message, 20)


def run_vendor(args, capture=False):
    # Licenses/install inherit the real terminal. Never supply stdin or accept terms.
    try:
        output = android_cli.run_command(args, capture=capture, timeout=600, label="SDK Manager")
    except android_cli.ProcessCleanupError:
        raise  # Keep the no-rollback signal intact across the legacy adapter.
    except android_cli.CliError as exc:
        print(f"SDK Manager exit={exc.code}", flush=True)
        raise Error(str(exc), exc.code) from exc
    print("SDK Manager exit=0", flush=True)
    return output


def bootstrap(data, sdk, approve):
    meta = archive_metadata(data)
    destination = safe_path(sdk / "cmdline-tools" / meta["revision"])
    if destination.exists():
        raise Error(f"CLI destination occupied: {destination}; manual recovery required; never overwritten")
    require(approve, f"Download {meta['url']} SHA-256={meta['sha256']} to a private temporary directory?")
    with tempfile.TemporaryDirectory(prefix="panda-android-download-") as temporary:
        archive = Path(temporary) / "tools.zip"
        download(meta["url"], archive)
        # Verify/extract before asking for SDK writes. Private staging starts outside SDK.
        staged = stage_archive(archive, Path(temporary) / "stage", meta["sha256"], meta["revision"])
        if not tools_ok(staged):
            raise Error("Invalid staged CLI layout; nothing published")
        require(approve, f"Publish verified CLI revision {meta['revision']} to {destination}? No overwrite")
        safe_path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Same filesystem staging is required for atomic rename publication.
        with tempfile.TemporaryDirectory(prefix=".panda-android-stage-", dir=destination.parent) as local:
            local_tools = Path(local) / "tools"
            shutil.copytree(staged, local_tools, symlinks=False)
            publish(local_tools, destination)
        if not tools_ok(destination):
            raise Error(f"Published CLI layout invalid at {destination}; stop for manual recovery")
    print(f"Published CLI: {destination}; resolved revision={meta['revision']}; runtime not yet verified")


def available_packages(output):
    available, in_available = set(), False
    for line in output.splitlines():
        if line.strip() == "Available Packages:":
            in_available = True
            continue
        if line.strip().endswith(":"):
            in_available = False
        if in_available and "|" in line:
            available.add(line.split("|", 1)[0].strip())
    return available


def legacy_platform_revision(output):
    revisions, available = set(), False
    for line in output.splitlines():
        if line.strip() == "Available Packages:":
            available = True
            continue
        if line.strip().endswith(":"):
            available = False
        if available and "|" in line:
            fields = [field.strip() for field in line.split("|")]
            if fields[0] == "platforms;android-36.1":
                revisions.add(fields[1])
    return revisions


def cli_runner(state, run):
    if run is not run_vendor:
        return run
    def execute(args, capture=False):
        env = android_cli.runtime_env(state["env"], state["sdk"], args[0])
        return android_cli.run_command(args, capture=capture, env=env, timeout=120 if capture else 600)
    return execute


def cli_check(data, state, approve=confirm, run=run_vendor):
    candidate = android_cli.discover(state["sdk"], data["android_cli"]["preferred_tools_revision"])
    result = android_cli.verify(candidate, state["sdk"], cli_runner(state, run), approve)
    check_cli_inventory(result, state["packages"], data)
    if not all(item["healthy"] for item in state["packages"].values()):
        raise Error("Local SDK baseline metadata/layout is incomplete or conflicting; inspect --plan")
    print(f"Android CLI product version={result['version']}; explicit SDK root and supported SDK inventory verified for this invocation only")
    return result


def check_unknown_tools_identity(result, item, data):
    """A narrow local-evidence cross-check, never a claimed CLI revision.

    The source-reviewed archive and launcher digests are trust inputs. No ZIP is
    fetched, read from an arbitrary cache, or executed to fill an unknown.
    """
    try:
        if not data:
            raise Error("trusted source identity missing")
        pin = archive_metadata(data)
        policy = data.get("android_cli", {})
        candidate = result.get("candidate", {})
        sdk = candidate.get("sdk")
        if not isinstance(sdk, Path):
            raise Error("SDK candidate identity missing")
        slot = sdk / "cmdline-tools/22.0"
        if (pin["revision"] != "22.0" or pin["sha256"] != policy.get("bundled_archive_sha256")
                or not re.fullmatch(r"[0-9a-f]{64}", policy.get("bundled_launcher_sha256", ""))
                or item["path"] != slot or item["revision"] != "22.0"
                or candidate.get("path") != slot / "bin/android"
                or candidate.get("package_revision") != "22.0" or candidate.get("launcher") is not True
                or candidate.get("sha256") != policy["bundled_launcher_sha256"]):
            raise Error("pinned archive/launcher/candidate identity differs")
        safe_path(slot / "bin")
        safe_path(slot / "lib")
        for path in (slot / "source.properties", slot / "bin/sdkmanager", slot / "lib/sdkmanager-classpath.jar"):
            android_cli.safe(path, sdk)
        meta = properties(slot / "source.properties")
        if not tools_ok(slot) or meta.get("Pkg.Revision") != "22.0" or meta.get("Pkg.Path") != "cmdline-tools;22.0":
            raise Error("healthy pinned source metadata/layout not established")
        android_cli.unchanged(candidate)
    except (Error, android_cli.CliError, OSError, ValueError, TypeError) as exc:
        raise android_cli.CliError(f"Command-Line Tools installed CLI revision is unknown/unverified; local identity check inconclusive: {exc}") from exc
    print("WARNING: cmdline-tools/22.0 CLI installed revision remains unknown/unverified; "
          "using healthy pinned source metadata revision 22.0 after archive/launcher identity cross-check. "
          "Arrow target is an update suggestion, never installed-version evidence; no package changes.")


def check_cli_inventory(result, items, data=None):
    for package, item in items.items():
        path = ("cmdline-tools/" + item["path"].name if package == "cmdline-tools;latest"
                else android_cli.package_id(package))
        if item["healthy"]:
            if path not in result["installed"]:
                raise android_cli.CliError(f"Android CLI installed inventory missing baseline package: {path}")
            revision = result["installed"][path]
            if revision is None and package == "cmdline-tools;latest":
                check_unknown_tools_identity(result, item, data)
            elif not android_cli.revisions_equal(revision, item["revision"]):
                raise android_cli.CliError(f"Android CLI installed inventory disagrees with local metadata or is unverified: {path}")
        if package == "platforms;android-36.1" and item["healthy"] and not android_cli.revisions_equal(item["revision"], "1"):
            raise android_cli.CliError("Platform 36.1 must have approved revision 1; manual review required")


def install(data, state, mode, approve=confirm, run=run_vendor):
    validate_manifest(data)
    if not state["jdk_ok"]:
        raise Error("Select a complete JDK 21; Java installation/system default changes are manual")
    sdk = state["sdk"]
    safe_path(sdk)
    items = inventory(sdk)
    platform = items["platforms;android-36.1"]
    if platform["healthy"] and not android_cli.revisions_equal(platform["revision"], "1"):
        raise Error("Installed platform 36.1 revision differs from approved revision 1; manual review, no downgrade")
    missing = [p for p in BASELINE if not items[p]["healthy"]]
    if not missing:
        print("No changes: all baseline packages have expected metadata/layout; runtime not verified")
        return
    if not items["cmdline-tools;latest"]["healthy"]:
        archive_metadata(data)  # Fail before any consent, SDK directory creation or network.
    corrupt = [p for p in missing if p in PACKAGE_PATHS and items[p]["occupied"]]
    if corrupt and mode != "--repair":
        raise Error("Occupied/corrupt packages require --repair: " + ", ".join(corrupt))
    if not items["cmdline-tools;latest"]["healthy"]:
        bootstrap(data, sdk, approve)
        items = inventory(sdk)
        missing = [p for p in BASELINE if not items[p]["healthy"]]
    if not missing:
        print("CLI bootstrap complete; remaining baseline packages already present")
        return
    preferred = None
    try:
        candidate = android_cli.discover(sdk, data["android_cli"]["preferred_tools_revision"])
        if candidate:
            preferred = android_cli.verify(candidate, sdk, cli_runner(state, run), approve, all_versions=True)
            check_cli_inventory(preferred, items, data)
    except android_cli.CliError as exc:
        preferred = None
        if isinstance(exc, android_cli.ProcessCleanupError) or exc.code in (20, 124, 130):
            raise Error(str(exc), exc.code) from exc
        print(f"Android CLI runtime contract failed: {exc}; no package changes; explicit fallback is required")
    if preferred:
        command = [str(candidate["path"]), f"--sdk={sdk}", "sdk", "--ignore-outdated-xmls", "install", "--no-downgrade"]
        package_args = [android_cli.install_id(p) for p in missing]
        unavailable = set()
        for package in missing:
            path, _, revision = android_cli.install_id(package).partition("@")
            offered = preferred["available"].get(path, set())
            if not offered or revision and not any(android_cli.revisions_equal(version, revision) for version in offered):
                unavailable.add(package)
        vendor = cli_runner(state, run)
    else:
        manager = items["cmdline-tools;latest"]["path"] / "bin/sdkmanager"
        android_cli.safe(manager, sdk)
        command = [str(manager), f"--sdk_root={sdk}"]
        require(approve, f"Explicitly approve deprecated SDK Manager fallback, startup/network/cache writes for repository listing at {sdk}?")
        listing = run([*command, "--list"], capture=True)
        unavailable = set(missing) - available_packages(listing)
        if "platforms;android-36.1" in missing and "platforms;android-36.1" not in unavailable:
            revisions = legacy_platform_revision(listing)
            if not revisions or not all(android_cli.revisions_equal(version, "1") for version in revisions):
                raise Error("Exact SDK platform revision 1 unavailable or ambiguous in legacy listing; manual review required")
        package_args = missing
        vendor = run
    if unavailable:
        raise Error("Exact SDK packages unavailable (no substitutions): " + ", ".join(sorted(unavailable)))
    require(approve, "Install only missing approved packages: " + ", ".join(package_args) +
            ("; quarantine/retain corrupt directories: " + ", ".join(str(items[p]["path"]) for p in corrupt) if corrupt else ""))
    require(approve, "Review interactive Google licenses? Decline unwanted terms; never accept automatically")
    if not preferred:
        run([*command, "--licenses"])
    require(approve, "Proceed with these exact package changes after license review? Further terms stay interactive")
    # A separate installer/IDE may have changed the SDK while consent was open.
    # Replan rather than pass a now-healthy package to SDK Manager for replacement.
    if inventory(sdk) != items:
        raise Error("SDK state changed during approval; rerun --plan before making package changes")
    if preferred:
        android_cli.unchanged(candidate)
    backups = []
    try:
        for package in corrupt:
            path = items[package]["path"]
            safe_path(path)
            backup = path.with_name(".panda-android-backup-" + uuid.uuid4().hex)
            rename_noreplace(path, backup)
            backups.append((path, backup))
            print(f"Retained pre-repair backup: {backup}")
        vendor([*command, *package_args])
        final = inventory(sdk)
        broken = [p for p in BASELINE if not final[p]["healthy"]]
        if broken:
            raise Error("Post-install metadata/layout check failed: " + ", ".join(broken))
        if "platforms;android-36.1" in missing and not android_cli.revisions_equal(final["platforms;android-36.1"]["revision"], "1"):
            raise Error("Post-install platform revision mismatch: expected 36.1 revision 1")
    except BaseException as failure:
        if isinstance(failure, android_cli.ProcessCleanupError):
            print("MANUAL RECOVERY REQUIRED: vendor cleanup unconfirmed; rollback withheld. "
                  "Do not restore or retry while its process group may still be active.")
            for path, backup in backups:
                print(f"Retained pre-repair backup: {backup}; rollback target not restored: {path}")
            raise
        for path, backup in reversed(backups):
            try:
                # Rename the directory entry itself, including a dangling or
                # external symlink, without following the replacement target.
                safe_path(path.parent)
                if path.exists() or path.is_symlink():
                    failed = path.with_name(".panda-android-failed-" + uuid.uuid4().hex)
                    rename_noreplace(path, failed)
                    print(f"Retained failed repair output (do not follow untrusted links): {failed}")
                rename_noreplace(backup, path)
                print(f"Restored pre-repair directory: {path}")
            except (Error, OSError, ArchiveError) as recovery_error:
                # A recovery error must not mask the vendor status or prevent
                # independent restoration of other retained package backups.
                print(f"MANUAL RECOVERY REQUIRED: recorded backup={backup}, target={path}; {recovery_error}")
        print("Partial failure: SDK Manager may retain new packages/licenses/cache. No healthy package removed; inspect --plan then retry --repair.")
        raise
    for package in BASELINE:
        print(f"Installed metadata: {package} revision={final[package]['revision']} path={final[package]['path']}")
    print("Metadata/layout verified; PandaWave build and runtime tools still require operator checks")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv not in (["--plan"], ["--install"], ["--repair"], ["--cli-check"]):
        print("Use setup-android.fish --plan | --install | --repair | --cli-check", file=sys.stderr)
        return 2
    try:
        data = load_manifest(ROOT / "config/android/toolchain.toml")
        state = inspect(data, os.environ)
        plan(data, state)
        if argv[0] == "--cli-check":
            cli_check(data, state)
        elif argv[0] != "--plan":
            install(data, state, argv[0])
        return 0
    except (Error, ArchiveError, android_cli.CliError, OSError, ValueError) as exc:
        print(f"Android automation stopped: {exc}", file=sys.stderr)
        return exc.code if isinstance(exc, (Error, android_cli.CliError)) else 1
    except KeyboardInterrupt:
        print("Android automation interrupted; inspect --plan before retry; healthy tools were not replaced", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
