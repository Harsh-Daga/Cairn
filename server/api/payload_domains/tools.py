"""Tools analytics payload builders."""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from typing import Any
from zoneinfo import ZoneInfo

from server.analyze.tool_identity import classify_tool, percentile
from server.api.payload_domains.common import append_truncation as _append_truncation
from server.api.payload_domains.common import bounds as _bounds
from server.api.payload_domains.common import day_key as _day_key
from server.api.payload_domains.common import resolved_range as _resolved
from server.api.schemas import (
    ToolAggregate,
    ToolCoverage,
    ToolEvidence,
    ToolFailureSample,
    ToolsAnalyticsResponse,
    ToolsLedgerSummary,
    ToolTrendPoint,
)
from server.ingest.constants import is_mapped_tool
from server.models.time_range import ResolvedTimeRange
from server.store.pagination import (
    ANALYTICS_SPAN_CAP,
    fetch_capped,
    truncation_limitation,
)

_RETRY_WASTE = frozenset({"retry_loop", "identical_call", "re_read", "rebilling_waste"})


def build_tools_analytics(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    days: int = 30,
    time_range: ResolvedTimeRange | None = None,
) -> ToolsAnalyticsResponse:
    since, end, days = _bounds(days, time_range)
    zone = ZoneInfo(time_range.timezone if time_range is not None else "UTC")
    rows, span_total = fetch_capped(
        conn,
        """
        SELECT s.span_id, s.trace_id, s.name, s.status, s.duration_ms, s.output_tokens,
               s.input_tokens, s.waste_category, s.waste_tokens, s.started_at, t.source,
               t.title
        FROM spans s
        JOIN traces t ON t.trace_id = s.trace_id
        WHERE t.workspace_id = ? AND t.started_at >= ? AND t.started_at < ?
          AND s.kind = 'tool_call'
        ORDER BY t.started_at, s.seq
        """,
        (workspace_id, since, end),
        cap=ANALYTICS_SPAN_CAP,
    )

    schema_row = conn.execute(
        """
        SELECT COALESCE(SUM(cr.tokens), 0) AS tokens
        FROM context_regions cr
        JOIN spans s ON s.span_id = cr.span_id
        JOIN traces t ON t.trace_id = s.trace_id
        WHERE t.workspace_id = ? AND t.started_at >= ? AND t.started_at < ?
          AND cr.region = 'tool_schema'
        """,
        (workspace_id, since, end),
    ).fetchone()
    schema_overhead_tokens = int(schema_row["tokens"] or 0) if schema_row is not None else 0

    session_rows = conn.execute(
        """
        SELECT t.source, COUNT(*) AS sessions,
               SUM(EXISTS(
                 SELECT 1 FROM spans s
                 WHERE s.trace_id = t.trace_id AND s.kind = 'tool_call'
               )) AS tool_sessions
        FROM traces t
        WHERE t.workspace_id = ? AND t.started_at >= ? AND t.started_at < ?
        GROUP BY t.source
        ORDER BY sessions DESC, t.source
        """,
        (workspace_id, since, end),
    ).fetchall()

    buckets: dict[str, dict[str, Any]] = {}
    for row in rows:
        source = str(row["source"] or "unknown")
        display, tool_id, family = classify_tool(row["name"], source=source)
        bucket = buckets.setdefault(
            tool_id,
            {
                "display_name": display,
                "family": family,
                "invocations": 0,
                "sessions": set(),
                "success": 0,
                "error": 0,
                "cancelled": 0,
                "retry": 0,
                "latencies": [],
                "result_tokens": 0,
                "token_weight": 0,
                "trend": defaultdict(lambda: {"invocations": 0, "errors": 0}),
                "worst": None,
                "sources": set(),
            },
        )
        if len(display) < len(str(bucket["display_name"])):
            bucket["display_name"] = display
        bucket["invocations"] += 1
        bucket["sessions"].add(str(row["trace_id"]))
        bucket["sources"].add(source)
        status = str(row["status"] or "ok")
        if status == "error":
            bucket["error"] += 1
        elif status == "cancelled":
            bucket["cancelled"] += 1
        else:
            bucket["success"] += 1
        waste = str(row["waste_category"] or "")
        if waste in _RETRY_WASTE:
            bucket["retry"] += 1
        duration = row["duration_ms"]
        if duration is not None:
            bucket["latencies"].append(int(duration))
        result_tokens = int(row["output_tokens"] or 0)
        bucket["result_tokens"] += result_tokens
        bucket["token_weight"] += int(row["input_tokens"] or 0) + result_tokens
        day = _day_key(row["started_at"], zone)
        if day is not None:
            trend_day = bucket["trend"][day]
            trend_day["invocations"] += 1
            if status == "error":
                trend_day["errors"] += 1
        worst = bucket["worst"]
        score = (
            2 if status == "error" else 0,
            int(row["waste_tokens"] or 0),
            int(duration or 0),
        )
        if worst is None or score > worst["score"]:
            bucket["worst"] = {
                "score": score,
                "evidence": ToolEvidence(
                    trace_id=str(row["trace_id"]),
                    span_id=str(row["span_id"]),
                    label=f"Open {display} in session",
                ),
            }

    total_token_weight = sum(int(bucket["token_weight"]) for bucket in buckets.values()) or 1
    tools: list[ToolAggregate] = []
    for tool_id, bucket in buckets.items():
        invocations = int(bucket["invocations"])
        error_count = int(bucket["error"])
        retry_count = int(bucket["retry"])
        latencies = list(bucket["latencies"])
        tools.append(
            ToolAggregate(
                tool_id=tool_id,
                display_name=str(bucket["display_name"]),
                family=str(bucket["family"]),
                invocations=invocations,
                sessions=len(bucket["sessions"]),
                success_count=int(bucket["success"]),
                error_count=error_count,
                cancelled_count=int(bucket["cancelled"]),
                success_rate=round(int(bucket["success"]) / max(1, invocations) * 100, 2),
                error_rate=round(error_count / max(1, invocations) * 100, 2),
                retry_rate=round(retry_count / max(1, invocations) * 100, 2),
                median_latency_ms=percentile(latencies, 50),
                p95_latency_ms=percentile(latencies, 95),
                result_tokens=int(bucket["result_tokens"]),
                estimated_cost_share=round(
                    int(bucket["token_weight"]) / total_token_weight * 100, 2
                ),
                estimate_kind="token_share",
                trend=[
                    ToolTrendPoint(
                        day=day,
                        invocations=int(values["invocations"]),
                        errors=int(values["errors"]),
                    )
                    for day, values in sorted(bucket["trend"].items())
                ],
                worst_session=(
                    bucket["worst"]["evidence"] if bucket["worst"] is not None else None
                ),
                limitation=(
                    "Cost share is proportional to recorded tool input/output tokens, not "
                    "provider invoice lines. Latency uses span duration_ms when present."
                ),
            )
        )
    tools.sort(key=lambda item: (-item.invocations, item.tool_id))

    failures: list[ToolFailureSample] = []
    for row in rows:
        if str(row["status"] or "ok") != "error":
            continue
        source = str(row["source"] or "unknown")
        display, tool_id, _family = classify_tool(row["name"], source=source)
        failures.append(
            ToolFailureSample(
                tool_id=tool_id,
                display_name=display,
                status="error",
                duration_ms=int(row["duration_ms"]) if row["duration_ms"] is not None else None,
                evidence=ToolEvidence(
                    trace_id=str(row["trace_id"]),
                    span_id=str(row["span_id"]),
                    label="Open failing tool call",
                ),
                detail=(str(row["title"]) or "Tool call recorded as error")[:160],
            )
        )
        if len(failures) >= 20:
            break

    coverage: list[ToolCoverage] = []
    source_tools: dict[str, set[str]] = defaultdict(set)
    source_mapped: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        source = str(row["source"] or "unknown")
        _display, tool_id, _family = classify_tool(row["name"], source=source)
        source_tools[source].add(tool_id)
        if is_mapped_tool(str(row["name"] or ""), source=source):
            source_mapped[source].add(tool_id)
    for row in session_rows:
        source = str(row["source"])
        sessions = int(row["sessions"] or 0)
        tool_sessions = int(row["tool_sessions"] or 0)
        coverage.append(
            ToolCoverage(
                source=source,
                sessions=sessions,
                tool_sessions=tool_sessions,
                tool_coverage_pct=round(tool_sessions / max(1, sessions) * 100, 2),
                distinct_tools=len(source_tools.get(source, set())),
                mapped_tools=len(source_mapped.get(source, set())),
                limitation=(
                    "Coverage counts tool_call spans and taxonomy mapping, not semantic "
                    "correctness of tool arguments or results."
                ),
            )
        )

    sessions_total = sum(int(row["sessions"] or 0) for row in session_rows)
    sessions_with_tools = sum(int(row["tool_sessions"] or 0) for row in session_rows)
    invocations = sum(tool.invocations for tool in tools)
    errors = sum(tool.error_count for tool in tools)
    retries = sum(int(round(tool.retry_rate * tool.invocations / 100)) for tool in tools)
    ledger = _tools_ledger(
        invocations=invocations,
        distinct_tools=len(tools),
        sessions_with_tools=sessions_with_tools,
        sessions_total=sessions_total,
        error_rate=round(errors / max(1, invocations) * 100, 2),
        retry_rate=round(retries / max(1, invocations) * 100, 2),
        schema_overhead_tokens=schema_overhead_tokens,
        tools=tools,
        failures=failures,
    )
    return ToolsAnalyticsResponse(
        days=days,
        resolved_range=_resolved(days=days, since=since, end=end, time_range=time_range),
        ledger=ledger,
        tools=tools,
        failures=failures,
        coverage=coverage,
        schema_overhead_tokens=schema_overhead_tokens,
        limitations=_tools_limitations(sampled=len(rows), total=span_total),
    )


def _tools_limitations(*, sampled: int, total: int) -> list[str]:
    limitations = [
        "Tool identity is normalized through the shared ingest taxonomy; unknown names stay "
        "visible instead of being dropped.",
        "Retry rate counts recorded waste categories associated with repetition, not every "
        "logical retry policy.",
        "Unused-schema tax uses mapped tool_schema region tokens when present; it is not "
        "allocated per tool unless a declared tool inventory exists.",
        "Estimated cost share is token-proportional among tool_call spans.",
    ]
    _append_truncation(limitations, truncation_limitation("Tool analytics", sampled, total))
    return limitations


def _tools_ledger(
    *,
    invocations: int,
    distinct_tools: int,
    sessions_with_tools: int,
    sessions_total: int,
    error_rate: float,
    retry_rate: float,
    schema_overhead_tokens: int,
    tools: list[ToolAggregate],
    failures: list[ToolFailureSample],
) -> ToolsLedgerSummary:
    limitation = "Tool ledger ratios use recorded tool_call spans and mapped schema regions only."
    if sessions_total == 0:
        return ToolsLedgerSummary(
            conclusion="No sessions fall in the selected range, so tool analytics are empty.",
            invocations=0,
            distinct_tools=0,
            sessions_with_tools=0,
            sessions_total=0,
            error_rate=0.0,
            retry_rate=0.0,
            schema_overhead_tokens=0,
            schema_tax_estimated=False,
            next_action="Widen the selected range or sync local agent logs.",
            next_action_href="/sessions",
            limitation=limitation,
        )
    if invocations == 0:
        return ToolsLedgerSummary(
            conclusion=(
                f"None of {sessions_total} sessions recorded tool_call spans in this range."
            ),
            invocations=0,
            distinct_tools=0,
            sessions_with_tools=0,
            sessions_total=sessions_total,
            error_rate=0.0,
            retry_rate=0.0,
            schema_overhead_tokens=schema_overhead_tokens,
            schema_tax_estimated=schema_overhead_tokens > 0,
            next_action="Review adapter coverage for tool call extraction.",
            next_action_href="/settings",
            limitation=limitation,
        )

    top = tools[0]
    if error_rate >= 10.0 and failures:
        conclusion = (
            f"{distinct_tools} tools across {invocations} calls; error rate is "
            f"{error_rate:.1f}% and {top.display_name} leads volume."
        )
        next_action = f"Inspect failing {failures[0].display_name} evidence."
        next_action_href = (
            f"/sessions/{failures[0].evidence.trace_id}?span={failures[0].evidence.span_id}"
        )
    elif retry_rate >= 15.0:
        conclusion = (
            f"{top.display_name} leads volume; about {retry_rate:.0f}% of tool calls carry "
            "repetition waste categories."
        )
        next_action = f"Open the worst {top.display_name} session and reduce repeated calls."
        next_action_href = (
            f"/sessions/{top.worst_session.trace_id}?span={top.worst_session.span_id}"
            if top.worst_session is not None
            else f"/sessions?q=tool%3A{top.tool_id}"
        )
    elif schema_overhead_tokens > 0:
        conclusion = (
            f"{distinct_tools} tools across {invocations} calls in "
            f"{sessions_with_tools}/{sessions_total} sessions; tool-schema overhead is "
            f"{schema_overhead_tokens} mapped tokens."
        )
        next_action = "Compare schema overhead on Context and trim unused MCP tools."
        next_action_href = "/context"
    else:
        conclusion = (
            f"{top.display_name} leads {invocations} tool calls across "
            f"{sessions_with_tools} sessions."
        )
        next_action = f"Filter sessions that used {top.display_name}."
        next_action_href = f"/sessions?q=tool%3A{top.tool_id}"

    return ToolsLedgerSummary(
        conclusion=conclusion,
        invocations=invocations,
        distinct_tools=distinct_tools,
        sessions_with_tools=sessions_with_tools,
        sessions_total=sessions_total,
        error_rate=error_rate,
        retry_rate=retry_rate,
        schema_overhead_tokens=schema_overhead_tokens,
        schema_tax_estimated=schema_overhead_tokens > 0,
        next_action=next_action,
        next_action_href=next_action_href,
        limitation=limitation,
    )
