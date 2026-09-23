"""Probe queries, kept as .rq files next to this module.

They are the D2.1 benchmark queries: each file can be read, cited and run on
its own, independently of the code that sends it. Placeholders are written
``%%KEY%%`` because SPARQL already uses braces and ``$``.
"""

from __future__ import annotations

from functools import lru_cache
from importlib import resources


@lru_cache(maxsize=None)
def load(name: str) -> str:
    """The text of ``<name>.rq``."""
    return resources.files(__name__).joinpath(f"{name}.rq").read_text(encoding="utf-8")


def render(name: str, **values: str) -> str:
    """Fill ``%%KEY%%`` placeholders, refusing to return a half-filled query."""
    text = load(name)
    for key, value in values.items():
        text = text.replace(f"%%{key.upper()}%%", value)
    if "%%" in text:
        raise ValueError(f"unfilled placeholder in {name}.rq")
    return text


def names() -> list[str]:
    return sorted(p.name[:-3] for p in resources.files(__name__).iterdir() if p.name.endswith(".rq"))
