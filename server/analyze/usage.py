"""Token/cost rollups and daily rollup maintenance."""

from __future__ import annotations

import sqlite3
from collections import defaultdict

from server.analyze.dirty import trace_day_key
from server.analyze.views import IncrementalView, trace_input_hash
from server.models.rollup import RollupDaily
from server.models.trace import Trace
from server.store.repos.rollup import RollupRepo
from server.store.repos.spans import SpanRepo
from server.store.repos.traces import TraceRepo
from server.util.hash import hash_obj


class UsageView(IncrementalView):
    """Maintain trace denormalized rollups and rollup_daily rows."""

    view_name = "usage"
    VERSION = 1

    def __init__(self, workspace_id: str) -> None:
        self.workspace_id = workspace_id

    def keys_for(self, trace_id: str) -> list[str]:
        return [trace_id]

    def input_hash_for(self, conn: sqlite3.Connection, key: str) -> str:
        return trace_input_hash(conn, key)

    def compute(self, conn: sqlite3.Connection, key: str) -> None:
        trace = TraceRepo.get(conn, key)
        if trace is None:
            return
        spans = SpanRepo.list_by_trace(conn, key)
        tool_calls = sum(1 for s in spans if s.kind == "tool_call")
        tool_errors = sum(
            1 for s in spans if s.kind in {"tool_call", "tool_result"} and s.status == "error"
        )
        updated = trace.model_copy(
            update={
                "span_count": len(spans),
                "tool_calls": tool_calls,
                "tool_errors": tool_errors,
            }
        )
        TraceRepo.update(conn, updated)
        if trace.started_at:
            self._upsert_rollup(conn, updated)

    def _upsert_rollup(self, conn: sqlite3.Connection, trace: Trace) -> None:
        day = trace_day_key(trace.started_at)
        project = trace.project or ""
        source = trace.source
        model = trace.model or ""
        row = conn.execute(
            """
            SELECT
              COUNT(*) AS traces,
              SUM(tool_calls) AS tool_calls,
              SUM(tool_errors) AS tool_errors,
              SUM(input_tokens) AS input_tokens,
              SUM(output_tokens) AS output_tokens,
              SUM(cache_read_tokens) AS cache_read_tokens,
              SUM(cache_creation_tokens) AS cache_creation_tokens,
              SUM(cost) AS cost,
              SUM(waste_tokens) AS waste_tokens
            FROM traces
            WHERE workspace_id = ?
              AND substr(started_at, 1, 10) = ?
              AND COALESCE(project, '') = ?
              AND source = ?
              AND COALESCE(model, '') = ?
            """,
            (self.workspace_id, day, project, source, model),
        ).fetchone()
        if row is None:
            return
        RollupRepo.upsert(
            conn,
            RollupDaily(
                day=day,
                workspace_id=self.workspace_id,
                project=project,
                source=source,
                model=model,
                traces=int(row["traces"] or 0),
                tool_calls=int(row["tool_calls"] or 0),
                tool_errors=int(row["tool_errors"] or 0),
                input_tokens=int(row["input_tokens"] or 0),
                output_tokens=int(row["output_tokens"] or 0),
                cache_read_tokens=int(row["cache_read_tokens"] or 0),
                cache_creation_tokens=int(row["cache_creation_tokens"] or 0),
                cost=float(row["cost"] or 0.0),
                waste_tokens=int(row["waste_tokens"] or 0),
            ),
        )


class RollupView(IncrementalView):
    """Incremental rollup view keyed by day:project."""

    view_name = "rollup"
    VERSION = 1

    def __init__(self, workspace_id: str) -> None:
        self.workspace_id = workspace_id
        self._usage = UsageView(workspace_id)

    def keys_for(self, trace_id: str) -> list[str]:
        return []

    def input_hash_for(self, conn: sqlite3.Connection, key: str) -> str:
        return hash_obj({"rollup": key, "workspace_id": self.workspace_id})

    def compute(self, conn: sqlite3.Connection, key: str) -> None:
        if ":" not in key:
            return
        day, project = key.split(":", 1)
        traces = conn.execute(
            """
            SELECT * FROM traces
            WHERE workspace_id = ?
              AND substr(started_at, 1, 10) = ?
              AND COALESCE(project, '') = ?
            """,
            (self.workspace_id, day, project),
        ).fetchall()
        groups: dict[tuple[str, str], list[sqlite3.Row]] = defaultdict(list)
        for row in traces:
            groups[(str(row["source"]), str(row["model"] or ""))].append(row)
        for (source, model), rows in groups.items():
            rollup = RollupDaily(
                day=day,
                workspace_id=self.workspace_id,
                project=project,
                source=source,
                model=model,
                traces=len(rows),
                tool_calls=sum(int(r["tool_calls"] or 0) for r in rows),
                tool_errors=sum(int(r["tool_errors"] or 0) for r in rows),
                input_tokens=sum(int(r["input_tokens"] or 0) for r in rows),
                output_tokens=sum(int(r["output_tokens"] or 0) for r in rows),
                cache_read_tokens=sum(int(r["cache_read_tokens"] or 0) for r in rows),
                cache_creation_tokens=sum(int(r["cache_creation_tokens"] or 0) for r in rows),
                cost=sum(float(r["cost"] or 0.0) for r in rows),
                waste_tokens=sum(int(r["waste_tokens"] or 0) for r in rows),
            )
            RollupRepo.upsert(conn, rollup)
