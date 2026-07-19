"""Trace repository (Phase 1)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from server.models.trace import Trace
from server.query_filters import ParsedFilter, sql_comparison
from server.store.pagination import bounded_page
from server.store.repos._crud import delete_where, fetch_all, fetch_one, insert, update, upsert

_TABLE = "traces"
_PK = ("trace_id",)


@dataclass(frozen=True, slots=True)
class TraceListFilters:
    """Filters for GET /api/traces."""

    days: int | None = None
    start: str | None = None
    end: str | None = None
    source: str | None = None
    project: str | None = None
    actor: str | None = None
    agent: str | None = None
    q: str | None = None
    parsed_filter: ParsedFilter | None = None
    sort: str = "recent"
    workspace_id: str | None = None
    limit: int = 50
    offset: int = 0


def _days_cutoff(days: int) -> str:
    return (datetime.now(UTC) - timedelta(days=days)).isoformat()


def trace_list_where(filters: TraceListFilters) -> tuple[str, list[object]]:
    clauses: list[str] = []
    params: list[object] = []
    if filters.workspace_id is not None:
        clauses.append("workspace_id = ?")
        params.append(filters.workspace_id)
    if filters.days is not None:
        clauses.append("(started_at IS NULL OR started_at >= ?)")
        params.append(_days_cutoff(filters.days))
    if filters.start is not None:
        clauses.append("started_at >= ?")
        params.append(filters.start)
    if filters.end is not None:
        clauses.append("started_at < ?")
        params.append(filters.end)
    if filters.source is not None:
        clauses.append("source = ?")
        params.append(filters.source)
    if filters.project is not None:
        clauses.append("project = ?")
        params.append(filters.project)
    if filters.actor is not None:
        clauses.append("actor_id = ?")
        params.append(filters.actor)
    if filters.agent is not None:
        clauses.append(
            "EXISTS (SELECT 1 FROM spans s WHERE s.trace_id = traces.trace_id AND s.agent_id = ?)"
        )
        params.append(filters.agent)
    parsed = filters.parsed_filter
    if parsed is not None and not parsed.valid:
        clauses.append("0 = 1")
    phrase = parsed.phrase if parsed is not None else filters.q
    if phrase is not None and phrase.strip():
        clauses.append(
            "(LOWER(COALESCE(title, '')) LIKE ? "
            "OR LOWER(trace_id) LIKE ? "
            "OR LOWER(COALESCE(project, '')) LIKE ? "
            "OR EXISTS ("
            "  SELECT 1 FROM spans s WHERE s.trace_id = traces.trace_id "
            "  AND (LOWER(COALESCE(s.text_inline, '')) LIKE ? "
            "    OR LOWER(COALESCE(s.name, '')) LIKE ? "
            "    OR LOWER(COALESCE(s.path_rel, '')) LIKE ?)"
            "))"
        )
        needle = f"%{phrase.strip().lower()}%"
        params.extend((needle, needle, needle, needle, needle, needle))
    if parsed is not None:
        for token in parsed.tokens:
            value = token.value.lower()
            if token.field == "agent":
                clauses.append(
                    "EXISTS (SELECT 1 FROM spans s WHERE s.trace_id = traces.trace_id "
                    "AND LOWER(COALESCE(s.agent_id, '')) = ?)"
                )
                params.append(value)
            elif token.field == "source":
                clauses.append("LOWER(source) = ?")
                params.append(value)
            elif token.field == "status":
                clauses.append(
                    "(LOWER(status) = ? OR EXISTS ("
                    "SELECT 1 FROM spans s WHERE s.trace_id = traces.trace_id "
                    "AND LOWER(COALESCE(s.status, '')) = ?))"
                )
                params.extend((value, value))
            elif token.field == "cost":
                clauses.append(f"cost {sql_comparison(token.comparison)} ?")
                params.append(float(token.value))
            elif token.field == "outcome":
                clauses.append(
                    "EXISTS (SELECT 1 FROM outcomes o WHERE o.trace_id = traces.trace_id "
                    "AND (LOWER(COALESCE(o.outcome_label, '')) LIKE ? "
                    "OR LOWER(COALESCE(o.build_status, '')) LIKE ?))"
                )
                params.extend((f"%{value}%", f"%{value}%"))
            elif token.field == "file":
                clauses.append(
                    "EXISTS (SELECT 1 FROM spans s WHERE s.trace_id = traces.trace_id "
                    "AND LOWER(COALESCE(s.path_rel, '')) LIKE ?)"
                )
                params.append(f"%{value}%")
            elif token.field == "tool":
                clauses.append(
                    "EXISTS (SELECT 1 FROM spans s WHERE s.trace_id = traces.trace_id "
                    "AND s.kind = 'tool_call' AND LOWER(COALESCE(s.name, '')) LIKE ?)"
                )
                params.append(f"%{value}%")
            elif token.field == "after":
                clauses.append("started_at >= ?")
                params.append(token.value)
            elif token.field == "verification":
                if value == "debt":
                    clauses.append(
                        "EXISTS (SELECT 1 FROM outcomes o WHERE o.trace_id = traces.trace_id "
                        "AND LOWER(COALESCE(o.outcome_label, '')) IN ('success','pass','passed') "
                        "AND o.tests_run IS NULL AND o.build_status IS NULL)"
                    )
                elif value == "failed":
                    clauses.append(
                        "EXISTS (SELECT 1 FROM outcomes o WHERE o.trace_id = traces.trace_id "
                        "AND (COALESCE(o.tests_failed, 0) > 0 "
                        "OR LOWER(COALESCE(o.build_status, '')) IN ('fail','failed','error')))"
                    )
                elif value == "verified":
                    clauses.append(
                        "EXISTS (SELECT 1 FROM outcomes o WHERE o.trace_id = traces.trace_id "
                        "AND COALESCE(o.tests_failed, 0) = 0 "
                        "AND (o.tests_run > 0 OR LOWER(COALESCE(o.build_status, '')) "
                        "IN ('pass','passed','success')))"
                    )
                elif value == "unverified":
                    clauses.append(
                        "NOT EXISTS (SELECT 1 FROM outcomes o WHERE o.trace_id = traces.trace_id "
                        "AND (o.tests_run > 0 OR o.build_status IS NOT NULL))"
                    )
            elif token.field == "corrected":
                # Phrase-matched user corrections (same conservative signals as the classifier).
                corrected_exists = (
                    "EXISTS (SELECT 1 FROM spans s WHERE s.trace_id = traces.trace_id "
                    "AND s.kind = 'user_msg' AND ("
                    "LOWER(COALESCE(s.text_inline, '')) LIKE '%that''s not what i%' "
                    "OR LOWER(COALESCE(s.text_inline, '')) LIKE '%thats not what i%' "
                    "OR LOWER(COALESCE(s.text_inline, '')) LIKE '%you misunderstood%' "
                    "OR LOWER(COALESCE(s.text_inline, '')) LIKE '%out of scope%' "
                    "OR LOWER(COALESCE(s.text_inline, '')) LIKE '%do not touch%' "
                    "OR LOWER(COALESCE(s.text_inline, '')) LIKE '%don''t touch%' "
                    "OR LOWER(COALESCE(s.text_inline, '')) LIKE '%tests still fail%' "
                    "OR LOWER(COALESCE(s.text_inline, '')) LIKE '%still broken%' "
                    "OR LOWER(COALESCE(s.text_inline, '')) LIKE '%try again%' "
                    "OR LOWER(COALESCE(s.text_inline, '')) LIKE '%follow the rules%'"
                    "))"
                )
                if value == "true":
                    clauses.append(corrected_exists)
                else:
                    clauses.append(f"NOT {corrected_exists}")
            elif token.field == "risk" and value == "high":
                # Conservative high-risk proxies until a persisted review-risk column lands:
                # auth/secret/migrations paths or destructive-looking tool names.
                clauses.append(
                    "("
                    "EXISTS (SELECT 1 FROM spans s WHERE s.trace_id = traces.trace_id AND ("
                    "LOWER(COALESCE(s.path_rel, '')) LIKE '%/auth/%' "
                    "OR LOWER(COALESCE(s.path_rel, '')) LIKE '%secret%' "
                    "OR LOWER(COALESCE(s.path_rel, '')) LIKE '%migrat%' "
                    "OR LOWER(COALESCE(s.name, '')) LIKE '%rm -rf%' "
                    "OR LOWER(COALESCE(s.name, '')) LIKE '%drop table%'"
                    ")) OR EXISTS ("
                    "SELECT 1 FROM outcomes o WHERE o.trace_id = traces.trace_id "
                    "AND LOWER(COALESCE(o.files_changed_json, '')) LIKE '%auth%'"
                    ")"
                    ")"
                )
    where = " AND ".join(clauses) if clauses else "1 = 1"
    return where, params


class TraceRepo:
    """CRUD and list queries for the traces table."""

    @staticmethod
    def create(conn: sqlite3.Connection, trace: Trace) -> None:
        insert(conn, _TABLE, trace)

    @staticmethod
    def upsert(conn: sqlite3.Connection, trace: Trace) -> None:
        upsert(conn, _TABLE, trace, _PK)

    @staticmethod
    def get(conn: sqlite3.Connection, trace_id: str) -> Trace | None:
        return fetch_one(conn, _TABLE, "trace_id = ?", (trace_id,), Trace)

    @staticmethod
    def get_by_external(
        conn: sqlite3.Connection,
        source: str,
        external_id: str,
    ) -> Trace | None:
        return fetch_one(
            conn,
            _TABLE,
            "source = ? AND external_id = ?",
            (source, external_id),
            Trace,
        )

    @staticmethod
    def list(conn: sqlite3.Connection, filters: TraceListFilters) -> list[Trace]:
        limit, offset = bounded_page(filters.limit, filters.offset)
        where, params = trace_list_where(filters)
        order_by = {
            "cost": "cost DESC, started_at DESC, trace_id DESC",
            "waste": "waste_tokens DESC, started_at DESC, trace_id DESC",
            "duration": (
                "(julianday(ended_at) - julianday(started_at)) DESC, started_at DESC, trace_id DESC"
            ),
            "tokens": "(input_tokens + output_tokens) DESC, started_at DESC, trace_id DESC",
            "quality": (
                "(SELECT o.quality_score FROM outcomes o WHERE o.trace_id = traces.trace_id) "
                "DESC, started_at DESC, trace_id DESC"
            ),
        }.get(filters.sort, "started_at DESC, trace_id DESC")
        sql = f"SELECT * FROM {_TABLE} WHERE {where} ORDER BY {order_by} LIMIT ? OFFSET ?"
        return fetch_all(conn, sql, (*params, limit, offset), Trace)

    @staticmethod
    def count(conn: sqlite3.Connection, filters: TraceListFilters) -> int:
        where, params = trace_list_where(filters)
        row = conn.execute(
            f"SELECT COUNT(*) AS n FROM {_TABLE} WHERE {where}",
            params,
        ).fetchone()
        return int(row["n"]) if row is not None else 0

    @staticmethod
    def update(conn: sqlite3.Connection, trace: Trace) -> bool:
        return update(conn, _TABLE, trace, _PK)

    @staticmethod
    def delete(conn: sqlite3.Connection, trace_id: str) -> bool:
        return delete_where(conn, _TABLE, "trace_id = ?", (trace_id,))
