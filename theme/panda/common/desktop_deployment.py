"""Deterministic, portable Panda desktop review package; no native executor.

Inputs are explicit synthetic fixtures. Opaque configuration, native identities,
provider labels and launcher names are deliberately absent from the export.
"""
import copy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat

from desktop_clock_candidate import build_clock_candidate, PLASMA_VERSION, SCHEMA_SHA256
from desktop_io import read_regular
from desktop_layout import (CATALOG, ROOT, ROLES, RESOLUTIONS, SCALES, SENSOR_FACES,
                            build_plan, digest, fields, unique_strings,
                            validate_config, validate_fixture)
from desktop_media_candidate import validate_media_settings
from desktop_packages import NAME, package_plan
from desktop_preview import render_svg
from palette import resolve_slug
from plasma_style import build_packages, check_packages

FLAVORS = ("minimal", "cyber", "gothic", "hybrid", "wave")
MAX_FILES = 128
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_BUNDLE_BYTES = 16 * 1024 * 1024
VERSION = re.compile(r"[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}(?:-[0-9]{1,3}(?:\.[0-9]{1,3})?)?", re.ASCII)
PLUGIN = re.compile(r"org\.kde\.[a-z][a-z0-9.-]{0,120}", re.ASCII)


def monitor_fragment(role, *, enabled):
    """Source-proven relative groups; no invented root IDs or CurrentPreset write."""
    if role not in ("cpu", "ram"):
        raise ValueError("monitor role must be cpu or ram")
    face = "org.kde.ksysguard." + ("linechart" if role == "cpu" else "horizontalbars")
    sensors = (dict(totalSensors='["cpu/all/usage"]', highPrioritySensorIds='["cpu/all/usage"]', lowPrioritySensorIds='[]')
        if role == "cpu" else dict(totalSensors='["memory/physical/usedPercent"]',
            highPrioritySensorIds='["memory/physical/used"]', lowPrioritySensorIds='["memory/physical/free","memory/physical/total"]'))
    face_values = (dict(historyAmount=60, rangeAutoY=False, rangeFromY=0.0, rangeToY=100.0, lineChartSmooth=False)
                   if role == "cpu" else dict(rangeAuto=True))
    groups = {"Appearance": dict(chartFace=face, showTitle=True, title="CPU" if role == "cpu" else "Memory", updateRateLimit=1000),
              "Sensors": sensors, face + "/General": face_values}
    return dict(scope="inert-relative-kconfig-controller-fragment", role=role,
        applicable_upstream_plasma="6.8.2", target=f"<new-{role}-instance>/Configuration",
        groups=groups if enabled else {}, status="post-init-source-candidate" if enabled else "blocked-release-or-inventory",
        storage_types=dict(sensor_lists="JSON array encoded as QString, not QStringList or raw list",
            face_groups="controller config base / face ID / XML General group"),
        requires_stock_preset_initialization=True, requires_target_kconfig_revalidation=True,
        applet_root_writes={}, native_verified=False,
        gates=["native config ancestry and IDs observed privately after approved addition",
               "do not apply before stock init/CurrentPreset load; do not write CurrentPreset",
               "target KConfigLoader group nesting and actual sensor availability require approval/revalidation",
               "native missing/stale zero fallbacks remain unverified; stop on inaccurate unknown state"])


def json_bytes(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def inventory_report(inventory):
    """Check supplied inventory claims; never infer loaded plugins from packages."""
    fields(inventory, ("schema_version", "scope", "installed_plasma", "running_plasma",
                       "packages", "plugins", "sensor_faces"), "deployment inventory")
    if type(inventory["schema_version"]) is not int or inventory["schema_version"] != 1 or inventory["scope"] != "panda-deployment-synthetic-inventory":
        raise ValueError("explicit synthetic deployment inventory required")
    for key in ("installed_plasma", "running_plasma"):
        value = inventory[key]
        if value is not None and (not isinstance(value, str) or VERSION.fullmatch(value) is None or "-" in value):
            raise ValueError("explicit upstream Plasma version or null required")
    packages = inventory["packages"]
    if not isinstance(packages, dict) or len(packages) > 256:
        raise ValueError("bounded package/version inventory required")
    for name, version in packages.items():
        if not isinstance(name, str) or NAME.fullmatch(name) is None or not isinstance(version, str) or VERSION.fullmatch(version) is None:
            raise ValueError("invalid package name/version claim")
    for key in ("plugins", "sensor_faces"):
        unique_strings(inventory[key], key)
        if len(inventory[key]) > 256 or any(PLUGIN.fullmatch(name) is None for name in inventory[key]):
            raise ValueError("bounded official KDE plugin inventory required")
    packages_plan = package_plan(ROOT / "packages", list(packages))
    needed_plugins = sorted({value[0] for value in CATALOG.values()} | {"org.kde.plasma.icontasks"})
    missing_plugins = sorted(set(needed_plugins) - set(inventory["plugins"]))
    missing_faces = sorted(SENSOR_FACES - set(inventory["sensor_faces"]))
    version_matches = inventory["installed_plasma"] == inventory["running_plasma"] == PLASMA_VERSION
    package_release_mismatches = sorted(name for name in packages_plan["requirements"]
        if name in packages and packages[name].split("-", 1)[0] != PLASMA_VERSION)
    return dict(scope="offline-synthetic-inventory-check", source_reviewed_plasma=PLASMA_VERSION,
                installed_plasma_claim=inventory["installed_plasma"], running_plasma_claim=inventory["running_plasma"],
                release_matches_reviewed_source=version_matches,
                required_packages=packages_plan["requirements"], packages=packages_plan,
                package_version_claims={name: packages.get(name) for name in packages_plan["requirements"]},
                package_release_mismatches=package_release_mismatches,
                required_plugins=needed_plugins, missing_plugins=missing_plugins,
                required_sensor_faces=sorted(SENSOR_FACES), missing_sensor_faces=missing_faces,
                synthetic_prerequisites_satisfied=bool(version_matches and not package_release_mismatches
                    and not packages_plan["missing"] and not missing_plugins and not missing_faces),
                target_qt_kf_distribution_patch_parity="unverified; record installed and loaded identities before native scope",
                native_verified=False, ready_for_activation=False)


def _portable_plan(plan):
    """Keep model positions; replace all source identities/content with aliases."""
    fixture = plan["preserved_fixture"]
    portable = {key: copy.deepcopy(plan[key]) for key in ("output", "presentation", "top_bar", "dock", "widgets", "palette", "flavor")}
    portable["dock"]["applications"] = [f"preserved-pin-slot-{i+1}" for i in range(len(fixture["applications"]))]
    for widget in portable["widgets"]:
        widget["instance_id"] = f"<existing-{widget['role']}-instance>" if widget["instance_id"] is not None else None
    portable["preserved_fixture"] = dict(desktop_count=fixture["desktop_count"], providers={
        "clock": "24-hour clock · synthetic", "media": "No players · synthetic",
        "weather": "Unconfigured · network off", "cpu": "Unavailable · synthetic", "ram": "Unavailable · synthetic"})
    return portable


def build_bundle(config, fixture, inventory):
    """Build inert files only. Existing instances retain identity and settings.

    All 60 flavor/size/profile decisions use the existing layout validator.
    A model-fit failure is reported; it never turns into clipped native support.
    """
    validate_config(config)
    validate_fixture(fixture)
    for role, face in (("cpu", "org.kde.ksysguard.linechart"), ("ram", "org.kde.ksysguard.horizontalbars")):
        if config["widgets"][role]["face"] != face:
            raise ValueError("deployment presets require the reviewed CPU linechart / RAM horizontalbars combination")
    for role in ROLES:
        matches = [applet for applet in fixture["applets"]
                   if applet["containment_id"] == fixture["desktop_id"] and applet["plugin"] == CATALOG[role][0]]
        if len(matches) > 1:
            raise ValueError("ambiguous existing desktop role requires separate explicit selection: " + role)
    report = inventory_report(inventory)
    check_packages()
    files = {"plasma-styles/" + name: data for name, data in build_packages().items()}
    files["operator-guide.md"] = read_regular(ROOT / "docs/panda-theme/desktop-deployment.md")
    files["sources/layout.toml"] = read_regular(ROOT / "theme/panda/common/desktop/layout.toml")
    files["sources/visual.toml"] = read_regular(ROOT / "theme/panda/common/desktop/visual.toml")
    files["sources/clock-6.8.2.xml"] = read_regular(ROOT / "tests/fixtures/desktop/clock-6.8.2.xml")
    media_contract = read_regular(ROOT / "theme/panda/common/desktop/media-6.8.2.json")
    validate_media_settings({}, plasma_version=PLASMA_VERSION, contract_bytes=media_contract)
    files["sources/media-6.8.2.json"] = media_contract
    files["sources/monitor-6.8.2.json"] = read_regular(ROOT / "theme/panda/common/desktop/deployment-monitor-sources.json")
    # A complete layout override must travel with its actual source values.
    files["plans/layout-input.json"] = json_bytes(config)
    files["plans/prerequisites.json"] = json_bytes(report)
    settings = {}
    if fixture["bindings"]["clock"] is None and report["synthetic_prerequisites_satisfied"]:
        candidate = build_clock_candidate(config, fixture, plasma_version=PLASMA_VERSION,
            schema_xml=files["sources/clock-6.8.2.xml"])
        settings = candidate["settings"]
    files["fragments/clock-appearance.json"] = json_bytes(dict(
        scope="inert-kconfig-fragment-no-writer", target="<new-clock-instance>/Configuration",
        applicable_upstream_version=PLASMA_VERSION, schema_sha256=SCHEMA_SHA256,
        group=["Appearance"], values={key.split("/", 1)[1]: value for key, value in settings.items()},
        excluded="timezone/calendar/locale/font overrides/global settings; preserve existing instances"))
    files["fragments/media.json"] = json_bytes(dict(scope="inert-native-config-contract",
        plugin=CATALOG["media"][0], per_instance_settings={}, preserve_global=["plasmaparc/General/VolumeStep"],
        source_contract="sources/media-6.8.2.json", serialization="no per-instance XML exists in reviewed package"))
    monitor_fragments = {role: monitor_fragment(role, enabled=report["synthetic_prerequisites_satisfied"]
                        and fixture["bindings"][role] is None) for role in ("cpu", "ram")}
    for role, fragment in monitor_fragments.items():
        if fixture["bindings"][role] is not None:
            fragment["status"] = "preserve-existing-controller-settings"
            fragment["target"] = f"<existing-{role}-instance>/Configuration"
        files[f"fragments/{role}-controller.json"] = json_bytes(fragment)
    matrix = []
    dock_properties = None
    for resolution in RESOLUTIONS:
        for scale in SCALES:
            for presentation in config["profiles"]:
                for flavor in FLAVORS:
                    row = dict(resolution=resolution, scale=scale, presentation=presentation, flavor=flavor)
                    try:
                        plan = _portable_plan(build_plan(config, fixture, resolution=resolution, scale=scale,
                            presentation=presentation, flavor=flavor))
                    except ValueError as error:
                        if "does not fit" not in str(error):
                            raise
                        row.update(status="refused-does-not-fit", reason=str(error))
                    else:
                        dock_properties = plan["dock"]["native_properties"]
                        structure = {key: value for key, value in plan.items() if key not in ("palette", "flavor", "preserved_fixture")}
                        name = f"previews/{resolution}-{scale:g}-{presentation}-{flavor}.svg"
                        files[name] = render_svg(plan).encode()
                        row.update(status="accepted-model-only", structure_sha256=digest(structure),
                                   preview=name, logical_output=plan["output"]["logical_size"],
                                   widget_rects={w["role"]: w["rect"] for w in plan["widgets"]},
                                   dock_rect=plan["dock"]["rect"])
                    matrix.append(row)
    files["plans/layout-matrix.json"] = json_bytes(matrix)
    files["fragments/dock-properties.json"] = json_bytes(dict(scope="inert-panel-property-intent",
        target="<new-dock-containment-observed-after-approved-addition>",
        panel_property_intent=dock_properties, native_config_write_set={},
        property_source="existing desktop_layout.build_plan native_properties; no target-release storage keys inferred",
        requires_native_ui_serialization_review=True, native_verified=False,
        unresolved_ui_intent=["floating", "bottom clearance", "icon size", "spacing", "padding"],
        exclusions="no existing panel movement/recreation; no pin copy or applet reparenting"))
    files["previews/gallery.md"] = ("# Five-flavor composition gallery\n\n"
        "Synthetic offline schematics; native minima, fonts, focus and opacity unverified. Hybrid first.\n\n" +
        "\n\n".join(f"## {flavor.title()}\n\n![{flavor} synthetic schematic](qhd-1.25-expanded-{flavor}.svg)"
                     for flavor in ("hybrid", "minimal", "cyber", "gothic", "wave")) + "\n").encode()
    roles = []
    for role in ROLES:
        exists = fixture["bindings"][role] is not None
        config_writes = settings if role == "clock" and not exists else {}
        if role in monitor_fragments and not exists:
            config_writes = {group + "/" + key: value for group, values in monitor_fragments[role]["groups"].items()
                             for key, value in values.items()}
        roles.append(dict(role=role, plugin=CATALOG[role][0], package=CATALOG[role][1],
            identity=f"<existing-{role}-instance>" if exists else f"<new-{role}-instance-observed-after-approved-addition>",
            parent="<operator-selected-desktop-containment>",
            action="retain-identity-and-parent" if exists else "propose-one-additive-instance",
            native_config_write_set=config_writes, geometry="operator-edit-mode-only; no serialized geometry proposed",
            existing_settings="preserve verbatim; no presets copied over existing config",
            native_verified=False))
        data = dict(role=role, plugin=CATALOG[role][0], package=CATALOG[role][1],
                    native_config_write_set=config_writes, network_access=False, backend_activation=False)
        if role in ("cpu", "ram"):
            data.update(face_intent=config["widgets"][role]["face"], native_settings_status="reviewed relative groups; target identity/ancestry/post-init/KConfig and sensor gates remain",
                official_preset_sensor_names=(["cpu/all/usage", "cpu/all/cpuCount", "cpu/all/coreCount"] if role == "cpu"
                    else ["memory/physical/used", "memory/physical/usedPercent", "memory/physical/total"]),
                panda_sensor_names=(["cpu/all/usage"] if role == "cpu" else ["memory/physical/used", "memory/physical/usedPercent", "memory/physical/free", "memory/physical/total"]),
                readings="missing/stale => unknown; do not fill/interpolate gaps; percent only with positive valid denominator",
                contract="official System Monitor infrastructure; effective source keys reviewed at 6.8.2; sensor presence/units/native fidelity unverified on target")
        elif role == "weather":
            data.update(state="unconfigured", provider=None, location=None,
                        policy="no query or location storage; separately approve provider/location/privacy and network scope")
        elif role == "media":
            data.update(state="no-player", policy="preserve stock capability checks; no artwork URI loading or MPRIS calls")
        else:
            data.update(policy="stock clock automatic typography; exact native font metrics unverified")
        files[f"plans/data-{role}.json"] = json_bytes(data)
    write_set = dict(scope="portable-configuration-intent-only", native_operations=[], ready_for_activation=False,
        top_panels=dict(policy="all existing panel IDs/order/settings/children/tray/pins preserved verbatim",
                        proposed_writes=[], native_shape_verified=False,
                        model_header="48 logical pixels is design intent, not permission to move/recreate a panel"),
        dock=dict(action="propose-addition-only", identity="<new-dock-containment-observed-after-approved-addition>",
            plugin=config["dock"]["plugin"], reparent_existing_applets=False, native_config_write_set={},
            ui_intent=copy.deepcopy(config["dock"]),
            pins="retain existing ordered identities privately; new dock pins require explicit per-item approval; none exported",
            serialization="floating/fit/spacing/icon-size/clearance require release-specific UI and storage validation"),
        roles=roles,
        preserve_desktop_count=fixture["desktop_count"],
        style_write_set=[dict(source=f"plasma-styles/panda-{resolve_slug(flavor)}-s1/", target=f"<user-data>/plasma/desktoptheme/panda-{resolve_slug(flavor)}-s1/", files=9) for flavor in FLAVORS],
        style_activation="Hybrid first; operator selects Panda Hybrid S1 in Desktop Theme after scoped approval",
        preserve=["all existing containment/applet IDs and parent relationships", "panel order/settings/tray children and pins",
                  "current desktop count (three-desktop target is deferred)", "wallpaper/activity/output/scaling", "unrelated configurations"],
        native_gates=["explicit scoped activation authorization", "target installed AND loaded release/package/plugin verification",
            "existing top-panel shape/location not represented by fixture; missing/different shape requires separate decision, never reposition",
            "fresh private preservation baseline and exact real identities/pins/output/activity",
            "restorable scoped backup with drift detection and operator-reviewed recovery",
            "Qt/KF/distribution patches and widget controller schemas reviewed for actual target release",
            "native media minimum 14x10 Kirigami units may exceed both model heights; measure before proceeding",
            "native typography/focus/icons/opacity/geometry and floating serialization unverified",
            "sensor/weather/provider initialization and network privacy require separate approval"],
        theme_manager="reuse existing palettes/packages; panda-theme desktop Tier 1 activation remains unimplemented; no bypass")
    files["plans/write-set.json"] = json_bytes(write_set)
    files["manifest.json"] = json_bytes(dict(schema_version=1, scope="offline-deployment-review-package",
        first_flavor="hybrid", flavors=list(FLAVORS), source_reviewed_plasma=PLASMA_VERSION,
        native_verified=False, ready_for_activation=False, activation_script=None,
        style_file_count=45, accepted_model_cases=sum(row["status"] == "accepted-model-only" for row in matrix),
        refused_model_cases=sum(row["status"] == "refused-does-not-fit" for row in matrix),
        generator_source_sha256={name: hashlib.sha256(read_regular(Path(__file__).parent / name)).hexdigest()
            for name in ("desktop_deployment.py", "desktop_cli.py", "desktop_layout.py", "desktop_packages.py",
                         "desktop_preview.py", "plasma_style.py", "palette.py")},
        sha256={name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}))
    _validate_outputs(files)
    return files


def _validate_outputs(files):
    if not isinstance(files, dict) or not files or len(files) > MAX_FILES or "manifest.json" not in files:
        raise ValueError("bounded artifact mapping with manifest required")
    total = 0
    for name, data in files.items():
        if not isinstance(name, str) or not isinstance(data, bytes):
            raise ValueError("artifact names and bytes required")
        path = PurePosixPath(name)
        if (path.is_absolute() or ".." in path.parts or str(path) != name or len(path.parts) > 5 or len(name) > 240
                or any(len(part) > 128 or re.fullmatch(r"[A-Za-z0-9_.-]+", part, re.ASCII) is None for part in path.parts)
                or path.suffix not in (".json", ".svg", ".xml", ".toml", ".md")
                    and path.name not in ("colors", "plasmarc", "LICENSE")):
            raise ValueError("unsafe artifact path/type")
        if len(data) > MAX_FILE_BYTES:
            raise ValueError("artifact exceeds per-file bound")
        total += len(data)
        if total > MAX_BUNDLE_BYTES:
            raise ValueError("artifact bundle exceeds total byte bound")
    # A path cannot be both an artifact and another artifact's parent directory.
    if any(str(parent) in files for name in files for parent in PurePosixPath(name).parents):
        raise ValueError("artifact file/directory collision")
    try:
        manifest = json.loads(files["manifest.json"])
    except (ValueError, UnicodeError) as error:
        raise ValueError("valid artifact manifest required") from error
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in files.items() if name != "manifest.json"}
    if (not isinstance(manifest, dict) or manifest.get("sha256") != hashes
            or manifest.get("native_verified") is not False or manifest.get("ready_for_activation") is not False):
        raise ValueError("artifact hashes or offline-only manifest claims differ")


def export_bundle(destination, files):
    """Create exactly one fresh directory beneath an existing private parent.

    Descriptor-relative mkdir/open and O_EXCL/NOFOLLOW prevent overwrites and
    symlink traversal. A partial failure leaves review evidence, never retries
    against an existing tree. No executable or installable shell script exists.
    """
    _validate_outputs(files)
    destination = Path(destination)
    if destination.anchor != "/" or ".." in destination.parts:
        raise ValueError("explicit absolute artifact path with one root slash and without traversal required")
    home = Path.home()
    protected = [ROOT, Path("/etc"), Path("/usr"), Path("/boot"), Path("/proc"), Path("/sys"), Path("/dev"), Path("/run")]
    for key, default in (("XDG_CONFIG_HOME", home / ".config"), ("XDG_DATA_HOME", home / ".local/share"),
                         ("XDG_STATE_HOME", home / ".local/state"), ("XDG_CACHE_HOME", home / ".cache")):
        value = Path(os.environ.get(key) or default)
        if value.anchor != "/" or ".." in value.parts:
            raise ValueError("absolute XDG roots with one root slash and without traversal required")
        # Block both a configured alias and its real target. Keep the
        # destination unresolved so the descriptor walk still refuses symlinks.
        try:
            resolved = value.resolve()
        except RuntimeError as error:
            raise ValueError("cannot resolve protected XDG root") from error
        protected.extend((value, resolved))
    if any(destination == path or path in destination.parents for path in protected):
        raise ValueError("native/configuration/source destination refused")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    parent_fd = os.open("/", flags)
    try:
        # Sandboxed read-only ancestors may map the root owner to nobody.
        trusted_owners = {0, os.getuid(), os.fstat(parent_fd).st_uid}
        for part in destination.parent.parts[1:]:
            next_fd = os.open(part, flags, dir_fd=parent_fd)
            os.close(parent_fd)
            parent_fd = next_fd
            info = os.fstat(parent_fd)
            sticky_root = info.st_uid in trusted_owners - {os.getuid()} and bool(info.st_mode & stat.S_ISVTX)
            if info.st_uid not in trusted_owners or info.st_mode & 0o022 and not sticky_root:
                raise ValueError("unsafe artifact ancestor ownership/mode")
        info = os.fstat(parent_fd)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise ValueError("artifact parent must be an existing user-owned private 0700 directory")
        os.mkdir(destination.name, 0o700, dir_fd=parent_fd)
        root_fd = os.open(destination.name, flags, dir_fd=parent_fd)
        try:
            root_info = os.fstat(root_fd)
            for name in sorted(files, key=lambda name: (name == "manifest.json", name)):
                binding = os.stat(destination.name, dir_fd=parent_fd, follow_symlinks=False)
                if (binding.st_dev, binding.st_ino) != (root_info.st_dev, root_info.st_ino):
                    raise ValueError("artifact directory identity changed")
                current = os.dup(root_fd)
                try:
                    for part in PurePosixPath(name).parts[:-1]:
                        try:
                            os.mkdir(part, 0o700, dir_fd=current)
                        except FileExistsError:
                            pass
                        next_fd = os.open(part, flags, dir_fd=current)
                        os.close(current)
                        current = next_fd
                    fd = os.open(PurePosixPath(name).name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                                 0o600, dir_fd=current)
                    with os.fdopen(fd, "wb") as stream:
                        stream.write(files[name])
                finally:
                    os.close(current)
            binding = os.stat(destination.name, dir_fd=parent_fd, follow_symlinks=False)
            if (binding.st_dev, binding.st_ino) != (root_info.st_dev, root_info.st_ino):
                raise ValueError("artifact directory identity changed")
        finally:
            os.close(root_fd)
    finally:
        os.close(parent_fd)
