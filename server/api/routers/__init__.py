"""Aggregate and export API routers."""

from __future__ import annotations

from server.api.routers import (
    actions,
    analytics,
    experiments,
    insights,
    live,
    overview,
    search,
    traces,
    workspace,
)

ALL_ROUTERS = [
    overview.router,
    traces.router,
    analytics.router,
    insights.router,
    experiments.router,
    search.router,
    workspace.router,
    actions.router,
    live.router,
]

__all__ = ["ALL_ROUTERS"]
