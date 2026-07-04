"""Build registered incremental views for a workspace."""

from __future__ import annotations

from server.analyze.usage import RollupView, UsageView
from server.analyze.views import IncrementalView
from server.analyze.waste_view import WasteView


def build_views(workspace_id: str) -> list[IncrementalView]:
    """Return analyzers in dependency order."""
    return [
        UsageView(workspace_id),
        WasteView(),
        RollupView(workspace_id),
    ]
