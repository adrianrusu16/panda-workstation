"""Offline package inventory; does not invoke pacman or install anything."""
from pathlib import Path
import re

from desktop_io import read_regular

REQUIRED = ("plasma-desktop", "plasma-workspace", "kdeplasma-addons", "libksysguard", "ksystemstats")
NAME = re.compile(r"[a-z0-9][a-z0-9@+_.-]*", re.ASCII)


def read_manifests(directory: Path) -> dict[str, str]:
    paths = sorted(Path(directory).glob("*.txt"))
    if not paths:
        raise ValueError("no package manifests found")
    inventory = {}
    for path in paths:
        for number, line in enumerate(read_regular(path).decode("utf-8").splitlines(), 1):
            name = line.strip()
            if not name or name.startswith("#"):
                continue
            if NAME.fullmatch(name) is None:
                raise ValueError(f"{path.name}:{number}: invalid package entry")
            if name in inventory:
                raise ValueError(f"duplicate package {name} in {inventory[name]} and {path.name}:{number}")
            inventory[name] = f"{path.name}:{number}"
    return inventory


def package_plan(directory: Path, installed: list[str]) -> dict:
    inventory = read_manifests(directory)
    if not isinstance(installed, list) or any(not isinstance(p, str) or NAME.fullmatch(p) is None for p in installed):
        raise ValueError("invalid installed package fixture")
    if len(installed) != len(set(installed)):
        raise ValueError("duplicate installed package fixture")
    absent = sorted(set(REQUIRED) - set(inventory))
    if absent:
        raise ValueError("required KDE packages absent from manifests: " + ", ".join(absent))
    return dict(scope="offline-only", source="synthetic installed-package inventory",
                requirements=sorted(REQUIRED), missing=sorted(set(REQUIRED) - set(installed)),
                already_installed=sorted(set(REQUIRED) & set(installed)),
                manifest_entry_count=len(inventory), install_executed=False,
                service_activation_executed=False, third_party_default=[])
