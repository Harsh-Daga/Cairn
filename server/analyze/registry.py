"""Build registered incremental views for a workspace."""

from __future__ import annotations

from server.analyze.diagnose import DiagnoseView
from server.analyze.difficulty import DifficultyView
from server.analyze.fingerprint import FingerprintView
from server.analyze.outcomes import OutcomesView
from server.analyze.regions import RegionsView
from server.analyze.usage import RollupView, UsageView
from server.analyze.views import IncrementalView
from server.analyze.waste_view import WasteView


def build_views(workspace_id: str) -> list[IncrementalView]:
    """Return analyzers in dependency order."""
    return [
        UsageView(workspace_id),
        RegionsView(),
        WasteView(),
        FingerprintView(),
        DifficultyView(),
        DiagnoseView(),
        OutcomesView(),
        RollupView(workspace_id),
    ]
