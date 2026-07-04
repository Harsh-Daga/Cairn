"""IncrementalView base, scheduler, and view registry."""

from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from collections import defaultdict
from datetime import UTC, datetime

from server.models.evidence import ViewState
from server.store.repos.views import ViewStateRepo
from server.util.hash import hash_obj

VIEW_ORDER: list[str] = [
    "usage",
    "regions",
    "waste",
    "fingerprint",
    "difficulty",
    "diagnose",
    "rollup",
]


class IncrementalView(ABC):
    """Base class for incremental analyzers."""

    view_name: str
    VERSION: int = 1

    @abstractmethod
    def keys_for(self, trace_id: str) -> list[str]:
        """Return view keys affected by a trace."""
        ...

    @abstractmethod
    def input_hash_for(self, conn: sqlite3.Connection, key: str) -> str:
        """Hash source inputs consumed by compute(key)."""
        ...

    @abstractmethod
    def compute(self, conn: sqlite3.Connection, key: str) -> None:
        """Recompute a single view key."""
        ...

    def is_dirty(self, conn: sqlite3.Connection, key: str) -> bool:
        """True when view_state is missing or stale."""
        existing = ViewStateRepo.get(conn, self.view_name, key)
        if existing is None:
            return True
        if existing.version < self.VERSION:
            return True
        return existing.input_hash != self.input_hash_for(conn, key)

    def mark_clean(self, conn: sqlite3.Connection, key: str) -> None:
        """Record successful compute in view_state."""
        ViewStateRepo.upsert(
            conn,
            ViewState(
                view=self.view_name,
                key=key,
                version=self.VERSION,
                input_hash=self.input_hash_for(conn, key),
                computed_at=datetime.now(UTC).isoformat(),
            ),
        )


class ViewScheduler:
    """Run dirty incremental views in dependency order."""

    def __init__(self, conn: sqlite3.Connection, views: list[IncrementalView]) -> None:
        self._conn = conn
        self._views: dict[str, IncrementalView] = {view.view_name: view for view in views}
        self.compute_calls = 0

    def run(self, dirty_keys: list[str]) -> list[str]:
        """Process dirty key strings like 'usage:TRACE_ID'."""
        grouped: dict[str, set[str]] = defaultdict(set)
        for item in dirty_keys:
            if ":" not in item:
                continue
            view_name, key = item.split(":", 1)
            grouped[view_name].add(key)

        computed: list[str] = []
        for view_name in VIEW_ORDER:
            analyzer = self._views.get(view_name)
            if analyzer is None:
                continue
            for key in sorted(grouped.get(view_name, set())):
                if not analyzer.is_dirty(self._conn, key):
                    continue
                analyzer.compute(self._conn, key)
                analyzer.mark_clean(self._conn, key)
                self.compute_calls += 1
                computed.append(f"{view_name}:{key}")
        return computed


def trace_input_hash(conn: sqlite3.Connection, trace_id: str) -> str:
    """Shared hash of trace + span snapshot for analyzers."""
    from server.store.repos.spans import SpanRepo
    from server.store.repos.traces import TraceRepo

    trace = TraceRepo.get(conn, trace_id)
    spans = SpanRepo.list_by_trace(conn, trace_id)
    payload = {
        "trace_id": trace_id,
        "span_count": len(spans),
        "max_seq": max((s.seq for s in spans), default=0),
        "input_tokens": trace.input_tokens if trace else 0,
        "output_tokens": trace.output_tokens if trace else 0,
        "waste_tokens": trace.waste_tokens if trace else 0,
    }
    return hash_obj(payload)
