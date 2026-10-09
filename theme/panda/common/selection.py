"""Pure Phase 2 candidates: explicit inputs only, no clock reads or I/O."""

from dataclasses import dataclass
from datetime import datetime
import re

from palette import IDENTITIES, PaletteError, resolve_slug
from state import ThemeState


class SelectionError(ValueError):
    """An invalid command, clock or context input."""


def _slug(value: object) -> str:
    try:
        return resolve_slug(value)
    except PaletteError as error:
        raise SelectionError("unknown theme; use a canonical slug or wave") from error


@dataclass(frozen=True)
class ContextSignals:
    special: str | None = None
    project: str | None = None
    gaming: bool | None = False
    focus: bool | None = False

    def __post_init__(self):
        if self.special is not None:
            object.__setattr__(self, "special", _slug(self.special))
        if self.project is not None and (not isinstance(self.project, str) or
                re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", self.project) is None):
            raise SelectionError("project must be a short identifier, never a path")
        for name in ("gaming", "focus"):
            value = getattr(self, name)
            if value is not None and type(value) is not bool:
                raise SelectionError(f"{name} must be boolean or unavailable (None)")


@dataclass(frozen=True)
class Decision:
    slug: str
    reason: str
    source: str

    def __post_init__(self):
        if _slug(self.slug) != self.slug:
            raise SelectionError("decision slug must be canonical")
        if not isinstance(self.reason, str) or not self.reason or any(
                ord(c) < 32 or ord(c) == 127 for c in self.reason):
            raise SelectionError("decision reason must be nonempty plain text")
        if self.source not in ("special", "project", "gaming", "focus", "schedule",
                               "fallback", "manual"):
            raise SelectionError("unknown decision source")


def select_auto(now: datetime | None, signals: ContextSignals) -> Decision:
    """Use the supplied local datetime's hour, including its timezone/DST fold.

    None represents an unavailable clock/provider. Never infer project or game
    state, consult the environment or convert the supplied clock to host time.
    """
    if now is not None and not isinstance(now, datetime):
        raise SelectionError("clock must be a local datetime or unavailable (None)")
    if not isinstance(signals, ContextSignals):
        raise SelectionError("context must be ContextSignals")
    if signals.special is not None:
        return Decision(signals.special, "explicit special flavor", "special")
    if signals.project in ("pandawave", "wave"):
        return Decision("pandawave", "PandaWave project context", "project")
    if signals.gaming:
        return Decision("cyber", "gaming context", "gaming")
    if signals.focus:
        return Decision("minimal", "focus context", "focus")
    if now is None:
        return Decision("hybrid", "time unavailable; safe Hybrid fallback", "fallback")
    if 7 <= now.hour < 18:
        return Decision("hybrid", "local time 07:00–18:00", "schedule")
    if 18 <= now.hour < 21:
        return Decision("cyber", "local time 18:00–21:00", "schedule")
    return Decision("gothic", "local time 21:00–07:00", "schedule")


def effective_decision(state: ThemeState | None, decision: Decision) -> Decision:
    """Evaluate a candidate without implicitly leaving persistent manual mode."""
    if state is not None and state.mode == "manual":
        return Decision(state.active, "persistent manual selection", "manual")
    return decision


def propose_command(state: ThemeState | None, command: str, decision: Decision) -> ThemeState:
    """Return an unapplied state proposal; never persist it or alter the input.

    Only explicit auto changes manual mode to auto. Cycles follow the canonical
    palette order; with no established active flavor next starts at the first
    entry and previous at the last. Existing context is retained verbatim.
    """
    context = state.context if state is not None else ""
    if command == "auto":
        return ThemeState("auto", decision.slug, state.last_manual if state else "", context)
    if command in ("next", "previous"):
        order = tuple(IDENTITIES)
        if state is None:
            slug = order[0 if command == "next" else -1]
        else:
            offset = 1 if command == "next" else -1
            slug = order[(order.index(state.active) + offset) % len(order)]
    else:
        slug = _slug(command)
    return ThemeState("manual", slug, slug, context)
