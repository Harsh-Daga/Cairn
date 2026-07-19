"""Search and workspace payload builders."""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any

from server.analyze.gauge import compute_gauge
from server.api.schemas import (
    CollectionStatus,
    PlanWindowGauge,
    QueryFilterError,
    QueryFilterToken,
    ResourceStatus,
    SearchFacet,
    SearchHit,
    SearchResponse,
    WorkspaceAdapter,
    WorkspaceHealth,
    WorkspaceResponse,
)
from server.ingest.parse_health import adapter_issue_url, health_payload
from server.query_filters import parse_filter
from server.store.repos.ingest_cursors import IngestCursorRepo
from server.store.repos.workspaces import WorkspaceRepo
from server.store.search import search_rows
from server.util.resources import build_resource_report, resource_status_payload


def _search_facets(conn: sqlite3.Connection, workspace_id: str) -> dict[str, list[SearchFacet]]:
    queries = {
        "agent": """
            SELECT s.agent_id AS value, COUNT(DISTINCT s.trace_id) AS n
            FROM spans s JOIN traces t ON t.trace_id = s.trace_id
            WHERE t.workspace_id = ? AND s.agent_id IS NOT NULL AND s.agent_id != ''
            GROUP BY s.agent_id ORDER BY n DESC, value LIMIT 10
        """,
        "outcome": """
            SELECT o.outcome_label AS value, COUNT(*) AS n
            FROM outcomes o JOIN traces t ON t.trace_id = o.trace_id
            WHERE t.workspace_id = ? AND o.outcome_label IS NOT NULL AND o.outcome_label != ''
            GROUP BY o.outcome_label ORDER BY n DESC, value LIMIT 10
        """,
        "after": """
            SELECT substr(started_at, 1, 10) AS value, COUNT(*) AS n
            FROM traces
            WHERE workspace_id = ? AND started_at IS NOT NULL
            GROUP BY substr(started_at, 1, 10) ORDER BY value DESC LIMIT 10
        """,
        "file": """
            SELECT substr(s.path_rel, 1, 200) AS value, COUNT(DISTINCT s.trace_id) AS n
            FROM spans s JOIN traces t ON t.trace_id = s.trace_id
            WHERE t.workspace_id = ? AND s.path_rel IS NOT NULL AND s.path_rel != ''
            GROUP BY s.path_rel ORDER BY n DESC, value LIMIT 10
        """,
        "tool": """
            SELECT substr(s.name, 1, 100) AS value, COUNT(DISTINCT s.trace_id) AS n
            FROM spans s JOIN traces t ON t.trace_id = s.trace_id
            WHERE t.workspace_id = ? AND s.kind = 'tool_call'
              AND s.name IS NOT NULL AND s.name != ''
            GROUP BY s.name ORDER BY n DESC, value LIMIT 10
        """,
    }
    return {
        field: [
            SearchFacet(value=str(row["value"]), count=int(row["n"] or 0))
            for row in conn.execute(sql, (workspace_id,)).fetchall()
        ]
        for field, sql in queries.items()
    }


def build_search(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    q: str,
    limit: int = 20,
    offset: int = 0,
) -> SearchResponse:
    parsed_filter = parse_filter(q)
    filter_tokens = [
        QueryFilterToken(
            raw=token.raw,
            field=token.field,
            value=token.value,
            comparison=token.comparison,
            available=token.available,
        )
        for token in parsed_filter.tokens
    ]
    filter_errors = [
        QueryFilterError(token=error.token, message=error.message) for error in parsed_filter.errors
    ]
    if not q.strip():
        return SearchResponse(
            q=q,
            filter_phrase=parsed_filter.phrase,
            hits=[],
            total=0,
            limit=limit,
            offset=offset,
            filter_tokens=filter_tokens,
            filter_errors=filter_errors,
        )
    rows = search_rows(
        conn,
        workspace_id=workspace_id,
        parsed_filter=parsed_filter,
        limit=limit,
        offset=offset,
    )

    hits: list[SearchHit] = []
    for row in rows.trace_rows:
        hits.append(
            SearchHit(
                trace_id=str(row["trace_id"]),
                span_id=None,
                title=row["title"],
                snippet=str(row["title"] or ""),
                kind="trace",
            )
        )

    for row in rows.span_rows:
        snippet = row["text_inline"] or row["path_rel"] or row["name"] or ""
        hits.append(
            SearchHit(
                trace_id=str(row["trace_id"]),
                span_id=str(row["span_id"]),
                title=None,
                snippet=str(snippet)[:200],
                kind="span",
            )
        )
    return SearchResponse(
        q=q,
        filter_phrase=parsed_filter.phrase,
        hits=hits,
        total=rows.total,
        limit=limit,
        offset=offset,
        filter_tokens=filter_tokens,
        filter_errors=filter_errors,
        facets=_search_facets(conn, workspace_id),
    )


def build_workspace(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    root_path: str,
    collection: CollectionStatus | None = None,
    resources: ResourceStatus | None = None,
) -> WorkspaceResponse:
    ws = WorkspaceRepo.get(conn, workspace_id)
    if ws is None:
        msg = "workspace not found"
        raise ValueError(msg)
    cursors = IngestCursorRepo.list_all(conn)
    by_source: dict[str, list[Any]] = defaultdict(list)
    for cursor in cursors:
        adapter_id = "gemini_cli" if cursor.source == "gemini" else cursor.source
        by_source[adapter_id].append(cursor)
    health_rows = conn.execute(
        "SELECT * FROM adapter_parse_health WHERE workspace_id = ? ORDER BY adapter_id",
        (workspace_id,),
    ).fetchall()
    health_by_adapter = {str(row["adapter_id"]): health_payload(row) for row in health_rows}
    adapter_ids = sorted(set(by_source) | set(health_by_adapter))
    adapters = [
        WorkspaceAdapter(
            source=source,
            streams=len(by_source.get(source, [])),
            cursor_updated_at=max((c.updated_at for c in by_source.get(source, [])), default=None),
            attempts=int(health_by_adapter.get(source, {}).get("attempts", 0)),
            fully_parsed=int(health_by_adapter.get(source, {}).get("fully_parsed", 0)),
            degraded=int(health_by_adapter.get(source, {}).get("degraded", 0)),
            skipped=int(health_by_adapter.get(source, {}).get("skipped", 0)),
            parse_coverage=health_by_adapter.get(source, {}).get("parse_coverage"),
            unknown_fields={
                str(key): int(value)
                for key, value in health_by_adapter.get(source, {})
                .get("unknown_fields", {})
                .items()
            },
            last_success_at=health_by_adapter.get(source, {}).get("last_success_at"),
            warning=bool(health_by_adapter.get(source, {}).get("warning", False)),
            issue_url=adapter_issue_url(source),
        )
        for source in adapter_ids
    ]
    trace_count = conn.execute(
        "SELECT COUNT(*) AS n FROM traces WHERE workspace_id = ?",
        (workspace_id,),
    ).fetchone()
    insight_count = conn.execute("SELECT COUNT(*) AS n FROM insights").fetchone()
    agreement_rows = conn.execute(
        """
        SELECT o.quality_score, o.human_label
        FROM outcomes o
        JOIN traces t ON t.trace_id = o.trace_id
        WHERE t.workspace_id = ? AND o.human_label IS NOT NULL
          AND o.quality_score IS NOT NULL
        """,
        (workspace_id,),
    ).fetchall()
    agreement_count = sum(
        1
        for row in agreement_rows
        if (float(row["quality_score"]) >= 50.0) == (str(row["human_label"]) == "up")
    )
    agreement_rate = agreement_count / len(agreement_rows) if agreement_rows else None
    raw_gauge = compute_gauge(Path(root_path)).as_dict()
    gauge: PlanWindowGauge | None = None
    if raw_gauge.get("total_tokens") or raw_gauge.get("limit") is not None:
        gauge = PlanWindowGauge(
            window_hours=int(raw_gauge.get("window_hours") or 5),
            total_tokens=int(raw_gauge.get("total_tokens") or 0),
            by_source={str(k): int(v) for k, v in (raw_gauge.get("by_source") or {}).items()},
            limit=raw_gauge.get("limit"),
            exceeded=bool(raw_gauge.get("exceeded")),
        )
    if resources is None:
        report = build_resource_report(
            conn,
            workspace_root=Path(root_path),
            workspace_id=workspace_id,
        )
        resources = ResourceStatus.model_validate(resource_status_payload(report))
    return WorkspaceResponse(
        workspace_id=workspace_id,
        root_path=root_path,
        name=ws.name,
        adapters=adapters,
        collection=collection,
        resources=resources,
        health=WorkspaceHealth.model_validate(
            {
                "trace_count": int(trace_count["n"] or 0) if trace_count else 0,
                "insight_count": int(insight_count["n"] or 0) if insight_count else 0,
                "fts_available": False,
                "adapter_warnings": [
                    {
                        "adapter_id": adapter.source,
                        "message": (
                            f"{adapter.source} log format may have changed; "
                            "numbers may be incomplete."
                        ),
                        "issue_url": adapter.issue_url,
                    }
                    for adapter in adapters
                    if adapter.warning
                ],
                "human_label_agreement": {
                    "labeled_sessions": len(agreement_rows),
                    "agreements": agreement_count,
                    "rate": agreement_rate,
                },
            }
        ),
        gauge=gauge,
    )
