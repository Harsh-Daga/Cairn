"""Cairn — build system for LLM computation over files."""

from __future__ import annotations

from typing import Any

__version__ = "1.1.0"

__all__ = [
    "Project",
    "Run",
    "__version__",
]


def __getattr__(name: str) -> Any:
    if name == "Project":
        from cairn.sdk.project import Project

        return Project
    if name == "Run":
        from cairn.sdk.project import Run

        return Run
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
