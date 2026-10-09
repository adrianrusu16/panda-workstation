"""Starship, Fastfetch and Fish fragment models; no real shell hooks."""

from adapters.base import FixtureAdapter


class ShellAdapter(FixtureAdapter):
    def __init__(self, component):
        if component not in ("starship", "fastfetch", "fish"):
            raise ValueError("unsupported shell component")
        super().__init__(component)
