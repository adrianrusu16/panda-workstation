"""Adapter lifecycle shared by fixture terminal and shell implementations."""

from dataclasses import dataclass

from fixture_fs import FILENAMES, new_image
from render import render_bytes, validate_rendered


@dataclass(frozen=True)
class Outcome:
    success: bool
    message: str


@dataclass(frozen=True)
class Prepared:
    component: str
    relative: str
    content: bytes
    theme: object


class FixtureAdapter:
    """Models owned fragment replacement, never probes or refreshes real apps.

    The transaction owns journaling and filesystem access. An adapter binds to
    that safe filesystem only during application. No subprocess/shell strings.
    """

    critical = True

    def __init__(self, component):
        if component not in FILENAMES:
            raise ValueError("unsupported fixture adapter")
        self.component = component
        self.fs = None

    def probe(self):
        return Outcome(True, f"{self.component}: fixture model ready; native application unverified")

    def prepare(self, theme, staging):
        return Prepared(self.component, "config/panda/generated/" + FILENAMES[self.component],
                        render_bytes(self.component, theme), theme)

    def validate(self, prepared):
        validate_rendered(self.component, prepared.content, prepared.theme)
        return Outcome(True, "native fragment structure validated; runtime unverified")

    def snapshot(self, backup):
        return self.fs.read("config/panda/generated/" + FILENAMES[self.component])

    def apply(self, prepared):
        entry = self.entries[prepared.relative]
        if entry.before != entry.after:
            self.fs.replace(entry.relative, entry.after, expected=entry.before)
        return Outcome(True, "fixture fragment replaced")

    def verify(self, prepared):
        actual = self.fs.read(prepared.relative)
        if actual != self.entries[prepared.relative].after:
            return Outcome(False, "fixture verification failed")
        return self.validate(prepared)

    def refresh(self):
        return Outcome(True, f"{self.component}: fixture verified; live refresh unverified (Phase 3B)")

    def restore(self, snapshot):
        entry = self.entries["config/panda/generated/" + FILENAMES[self.component]]
        current = self.fs.read(entry.relative)
        if current == snapshot:
            return Outcome(True, "already restored")
        if current != entry.after:
            return Outcome(False, "external modification; refusing restore")
        self.fs.replace(entry.relative, snapshot, expected=current)
        return Outcome(True, "restored")
