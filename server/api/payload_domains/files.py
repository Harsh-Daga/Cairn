"""Files analytics payload builders."""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from typing import Any
from zoneinfo import ZoneInfo

from server.analyze.tool_identity import classify_tool
from server.api.payload_domains.common import append_truncation as _append_truncation
from server.api.payload_domains.common import bounds as _bounds
from server.api.payload_domains.common import day_key as _day_key
from server.api.payload_domains.common import resolved_range as _resolved
from server.api.schemas import (
    FileChurnPoint,
    FileEvidence,
    FileHotspot,
    FilesAnalyticsResponse,
    FilesLedgerSummary,
)
from server.ingest.constants import NORM_DELETE, NORM_EDIT, NORM_READ, NORM_SEARCH
from server.models.time_range import ResolvedTimeRange
from server.store.pagination import (
    ANALYTICS_SPAN_CAP,
    ANALYTICS_TRACE_CAP,
    fetch_capped,
    truncation_limitation,
)

_IGNORED_PREFIXES = (
    "node_modules/",
    "vendor/",
    "dist/",
    "build/",
    ".git/",
    "__pycache__/",
    ".venv/",
    "venv/",
)
_IGNORED_PARTS = tuple(f"/{prefix}" for prefix in _IGNORED_PREFIXES)
_REVERT_OUTCOMES = frozenset({"reverted", "partial"})


def scrub_path_rel(path: str | None) -> str | None:
    """Keep only repo-relative display paths; drop absolute/home shapes."""
    if path is None:
        return None
    value = path.strip().replace("\\", "/")
    if not value or value.startswith("/") or value.startswith("~") or ":/" in value[:4]:
        return None
    while value.startswith("./"):
        value = value[2:]
    return value or None


def is_ignored_path(path_rel: str) -> bool:
    lowered = path_rel.lower()
    return lowered.startswith(_IGNORED_PREFIXES) or any(part in lowered for part in _IGNORED_PARTS)


def build_files_analytics(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    days: int = 30,
    time_range: ResolvedTimeRange | None = None,
) -> FilesAnalyticsResponse:
    since, end, days = _bounds(days, time_range)
    zone = ZoneInfo(time_range.timezone if time_range is not None else "UTC")
    rows, span_total = fetch_capped(
        conn,
        """
        SELECT s.span_id, s.trace_id, s.name, s.path_rel, s.waste_category, s.waste_tokens,
               s.input_tokens, s.output_tokens, s.started_at, t.source, t.status AS trace_status
        FROM spans s
        JOIN traces t ON t.trace_id = s.trace_id
        WHERE t.workspace_id = ? AND t.started_at >= ? AND t.started_at < ?
          AND s.path_rel IS NOT NULL AND s.path_rel != ''
        ORDER BY t.started_at, s.seq
        """,
        (workspace_id, since, end),
        cap=ANALYTICS_SPAN_CAP,
    )
    outcome_rows, _outcome_total = fetch_capped(
        conn,
        """
        SELECT o.trace_id, o.outcome_label, o.reverted_within_window, o.fixup_within_window
        FROM outcomes o
        JOIN traces t ON t.trace_id = o.trace_id
        WHERE t.workspace_id = ? AND t.started_at >= ? AND t.started_at < ?
        ORDER BY t.started_at, o.trace_id
        """,
        (workspace_id, since, end),
        cap=ANALYTICS_TRACE_CAP,
    )
    revert_traces = {
        str(row["trace_id"])
        for row in outcome_rows
        if str(row["outcome_label"] or "") in _REVERT_OUTCOMES
        or int(row["reverted_within_window"] or 0) == 1
        or int(row["fixup_within_window"] or 0) == 1
    }

    buckets: dict[str, dict[str, Any]] = {}
    churn_map: dict[str, dict[str, int]] = defaultdict(
        lambda: {"reads": 0, "edits": 0, "re_reads": 0}
    )
    for row in rows:
        path_rel = scrub_path_rel(str(row["path_rel"]))
        if path_rel is None:
            continue
        source = str(row["source"] or "unknown")
        _display, tool_id, _family = classify_tool(row["name"], source=source)
        bucket = buckets.setdefault(
            path_rel,
            {
                "reads": 0,
                "re_reads": 0,
                "edits": 0,
                "deletes": 0,
                "sessions": set(),
                "revert_sessions": set(),
                "tokens": 0,
                "ignored": is_ignored_path(path_rel),
                "evidence": None,
            },
        )
        trace_id = str(row["trace_id"])
        bucket["sessions"].add(trace_id)
        tokens = int(row["input_tokens"] or 0) + int(row["output_tokens"] or 0)
        bucket["tokens"] += tokens
        waste = str(row["waste_category"] or "")
        if tool_id in {NORM_READ, NORM_SEARCH}:
            bucket["reads"] += 1
            if waste == "re_read":
                bucket["re_reads"] += 1
        elif tool_id == NORM_EDIT:
            bucket["edits"] += 1
        elif tool_id == NORM_DELETE:
            bucket["deletes"] += 1
        if trace_id in revert_traces:
            bucket["revert_sessions"].add(trace_id)

        day = _day_key(row["started_at"], zone)
        if day is not None:
            if tool_id in {NORM_READ, NORM_SEARCH}:
                churn_map[day]["reads"] += 1
                if waste == "re_read":
                    churn_map[day]["re_reads"] += 1
            elif tool_id == NORM_EDIT:
                churn_map[day]["edits"] += 1

        score = (
            int(bucket["re_reads"]) + int(bucket["edits"]),
            int(row["waste_tokens"] or 0),
            tokens,
        )
        current = bucket["evidence"]
        if current is None or score > current["score"]:
            bucket["evidence"] = {
                "score": score,
                "value": FileEvidence(
                    trace_id=trace_id,
                    span_id=str(row["span_id"]),
                    label=f"Open activity on {path_rel}",
                ),
            }

    total_tokens = sum(int(bucket["tokens"]) for bucket in buckets.values()) or 1
    files = [
        FileHotspot(
            path_rel=path_rel,
            reads=int(bucket["reads"]),
            re_reads=int(bucket["re_reads"]),
            edits=int(bucket["edits"]),
            deletes=int(bucket["deletes"]),
            revert_fixup_sessions=len(bucket["revert_sessions"]),
            sessions=len(bucket["sessions"]),
            tokens=int(bucket["tokens"]),
            estimated_cost_share=round(int(bucket["tokens"]) / total_tokens * 100, 2),
            estimate_kind="token_share",
            ignored=bool(bucket["ignored"]),
            evidence=bucket["evidence"]["value"] if bucket["evidence"] is not None else None,
            limitation=(
                "Paths are workspace-relative only. Cost share is token-proportional among "
                "path-bearing spans; rename/delete history is incomplete without VCS events."
            ),
        )
        for path_rel, bucket in buckets.items()
    ]
    files.sort(
        key=lambda item: (
            -item.re_reads,
            -item.edits,
            -item.reads,
            item.path_rel,
        )
    )
    # Keep the page bounded for large workspaces.
    files = files[:100]

    churn = [
        FileChurnPoint(
            day=day,
            reads=int(values["reads"]),
            edits=int(values["edits"]),
            re_reads=int(values["re_reads"]),
        )
        for day, values in sorted(churn_map.items())
    ]
    ledger = _files_ledger(files)
    return FilesAnalyticsResponse(
        days=days,
        resolved_range=_resolved(days=days, since=since, end=end, time_range=time_range),
        ledger=ledger,
        files=files,
        churn=churn,
        limitations=_files_limitations(sampled=len(rows), total=span_total, file_cap=100),
    )


def _files_limitations(*, sampled: int, total: int, file_cap: int) -> list[str]:
    limitations = [
        "Only repo-relative paths are shown; absolute and home paths are dropped.",
        "Rename/delete history is incomplete without git instruction events (Guard).",
        "Revert/fixup counts use outcome labels on sessions that touched the path.",
        "Ignored/vendor/generated prefixes are flagged but still listed for transparency.",
        "Estimated cost share is token-proportional among path-bearing spans.",
        f"Hotspot list shows at most {file_cap} paths after aggregation (sorted by re-read/edit).",
    ]
    _append_truncation(limitations, truncation_limitation("File analytics", sampled, total))
    return limitations


def _files_ledger(files: list[FileHotspot]) -> FilesLedgerSummary:
    limitation = (
        "File ledger uses path-bearing spans and outcome labels; it does not prove avoidable spend."
    )
    if not files:
        return FilesLedgerSummary(
            conclusion="No repo-relative file paths were recorded in the selected range.",
            distinct_files=0,
            reads=0,
            re_reads=0,
            edits=0,
            revert_fixup_sessions=0,
            ignored_files=0,
            next_action="Sync adapters that emit tool path metadata.",
            next_action_href="/settings",
            limitation=limitation,
        )
    reads = sum(item.reads for item in files)
    re_reads = sum(item.re_reads for item in files)
    edits = sum(item.edits for item in files)
    revert_sessions = sum(item.revert_fixup_sessions for item in files)
    ignored = sum(1 for item in files if item.ignored)
    top = files[0]
    if re_reads > 0:
        conclusion = (
            f"{top.path_rel} leads re-reads ({top.re_reads}) across {top.sessions} sessions; "
            f"{re_reads} re-read events and {edits} edits were mapped overall."
        )
        next_action = f"Inspect re-read evidence for {top.path_rel}."
        next_action_href = (
            f"/sessions/{top.evidence.trace_id}?span={top.evidence.span_id}"
            if top.evidence is not None
            else f"/sessions?q=file%3A{top.path_rel}"
        )
    elif edits > 0:
        conclusion = (
            f"{len(files)} files touched with {edits} edits and {reads} reads; "
            f"{top.path_rel} is the hottest path."
        )
        next_action = f"Filter sessions that edited {top.path_rel}."
        next_action_href = f"/sessions?q=file%3A{top.path_rel}"
    else:
        conclusion = (
            f"{len(files)} files have path evidence with {reads} reads and no mapped edits."
        )
        next_action = "Review adapter path coverage for edit tools."
        next_action_href = "/settings"

    return FilesLedgerSummary(
        conclusion=conclusion,
        distinct_files=len(files),
        reads=reads,
        re_reads=re_reads,
        edits=edits,
        revert_fixup_sessions=revert_sessions,
        ignored_files=ignored,
        next_action=next_action,
        next_action_href=next_action_href,
        limitation=limitation,
    )
