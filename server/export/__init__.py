"""Export helpers."""

from __future__ import annotations

from typing import Any

__all__ = ["export_static_snapshot"]


def __getattr__(name: str) -> Any:
    if name == "export_static_snapshot":
        from server.export.static import export_static_snapshot

        return export_static_snapshot
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
