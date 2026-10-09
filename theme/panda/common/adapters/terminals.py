"""Ghostty, Kitty and Konsole fragment models; no live terminal operations."""

from adapters.base import FixtureAdapter


class TerminalAdapter(FixtureAdapter):
    def __init__(self, component):
        if component not in ("ghostty", "kitty", "konsole"):
            raise ValueError("unsupported terminal")
        super().__init__(component)
