"""Bounded store queries for trace/span search."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from server.query_filters import ParsedFilter
from server.store.pagination import bounded_page
from server.store.repos.traces import TraceListFilters, trace_list_where


@dataclass(frozen=True)
class SearchRows:
    trace_rows: list[sqlite3.Row]
    span_rows: list[sqlite3.Row]
    total: int


def like_pattern(value: str) -> str:
    """Escape LIKE metacharacters so user input matches literally."""
    escaped = (
        value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    )
    return f"%{escaped}%"


def search_rows(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    parsed_filter: ParsedFilter,
    limit: int,
    offset: int = 0,
) -> SearchRows:
    """Apply the shared trace filter, then page canonical trace/span matches."""
    limit, offset = bounded_page(limit, offset, max_limit=200)
    if not parsed_filter.valid:
        return SearchRows(trace_rows=[], span_rows=[], total=0)

    candidate_where, candidate_params = trace_list_where(
        TraceListFilters(workspace_id=workspace_id, parsed_filter=parsed_filter)
    )
    phrase = parsed_filter.phrase.strip()
    phrase_like = like_pattern(phrase.lower())
    span_specific = any(
        token.field in {"agent", "file", "tool", "status"} for token in parsed_filter.tokens
    )

    trace_extra: list[str] = []
    trace_extra_params: list[object] = []
    if phrase:
        trace_extra.append(
            "(LOWER(COALESCE(title, '')) LIKE ? ESCAPE '\\' "
            "OR LOWER(trace_id) LIKE ? ESCAPE '\\' "
            "OR LOWER(COALESCE(project, '')) LIKE ? ESCAPE '\\')"
        )
        trace_extra_params.extend((phrase_like, phrase_like, phrase_like))
    elif span_specific:
        trace_extra.append("0 = 1")
    trace_where = " AND ".join([f"({candidate_where})", *trace_extra])
    trace_params = [*candidate_params, *trace_extra_params]
    trace_count_row = conn.execute(
        f"SELECT COUNT(*) AS n FROM traces WHERE {trace_where}",
        trace_params,
    ).fetchone()
    trace_total = int(trace_count_row["n"] or 0) if trace_count_row is not None else 0
    trace_rows = conn.execute(
        f"""
        SELECT trace_id, title FROM traces
        WHERE {trace_where}
        ORDER BY started_at DESC, trace_id DESC
        LIMIT ? OFFSET ?
        """,
        (*trace_params, limit, offset),
    ).fetchall()

    span_clauses = [
        f"s.trace_id IN (SELECT trace_id FROM traces WHERE {candidate_where})",
    ]
    span_params: list[object] = list(candidate_params)
    if phrase:
        span_clauses.append(
            "(LOWER(COALESCE(s.text_inline, '')) LIKE ? ESCAPE '\\' "
            "OR LOWER(COALESCE(s.name, '')) LIKE ? ESCAPE '\\' "
            "OR LOWER(COALESCE(s.path_rel, '')) LIKE ? ESCAPE '\\')"
        )
        span_params.extend((phrase_like, phrase_like, phrase_like))
    for token in parsed_filter.tokens:
        value = token.value.lower()
        if token.field == "agent":
            span_clauses.append("LOWER(COALESCE(s.agent_id, '')) = ?")
            span_params.append(value)
        elif token.field == "file":
            span_clauses.append("LOWER(COALESCE(s.path_rel, '')) LIKE ? ESCAPE '\\'")
            span_params.append(like_pattern(value))
        elif token.field == "tool":
            span_clauses.append(
                "s.kind = 'tool_call' AND LOWER(COALESCE(s.name, '')) LIKE ? ESCAPE '\\'"
            )
            span_params.append(like_pattern(value))
        elif token.field == "status":
            span_clauses.append("LOWER(COALESCE(s.status, '')) = ?")
            span_params.append(value)
    materialize_spans = bool(phrase or parsed_filter.tokens)
    span_total = 0
    span_rows: list[sqlite3.Row] = []
    if materialize_spans:
        span_where = " AND ".join(span_clauses)
        span_count_row = conn.execute(
            f"SELECT COUNT(*) AS n FROM spans s WHERE {span_where}",
            span_params,
        ).fetchone()
        span_total = int(span_count_row["n"] or 0) if span_count_row is not None else 0
        remaining = max(0, limit - len(trace_rows))
        span_offset = max(0, offset - trace_total)
        if remaining:
            span_rows = conn.execute(
                f"""
                SELECT s.trace_id, s.span_id, s.text_inline, s.name, s.path_rel
                FROM spans s JOIN traces t ON t.trace_id = s.trace_id
                WHERE {span_where}
                ORDER BY COALESCE(s.started_at, t.started_at) DESC, s.seq DESC
                LIMIT ? OFFSET ?
                """,
                (*span_params, remaining, span_offset),
            ).fetchall()
    return SearchRows(trace_rows=trace_rows, span_rows=span_rows, total=trace_total + span_total)
