"""Guard instruction-event analytics payload builders."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from server.analyze.guard_scan import (
    ASSOCIATION_WINDOW_DAYS,
    MIN_ASSOCIATION_N,
    association_windows,
    scan_instruction_events,
)
from server.api.payload_domains.common import (
    bounds as _bounds,
)
from server.api.payload_domains.common import (
    resolved_range as _resolved,
)
from server.api.schemas import (
    GuardAnalyticsResponse,
    GuardAssociation,
    GuardEventRow,
    GuardLedgerSummary,
)
from server.improve.stats import measure_causal_effect
from server.models.time_range import ResolvedTimeRange
from server.store.repos.guard_events import GuardEventRepo


def build_guard_analytics(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    workspace_root: Path,
    days: int = 30,
    time_range: ResolvedTimeRange | None = None,
    rescan: bool = True,
) -> GuardAnalyticsResponse:
    since, end, days = _bounds(days, time_range)
    scan_notes: list[str] = []
    git_state = "unknown"
    if rescan:
        scan = scan_instruction_events(
            conn,
            workspace_id=workspace_id,
            repo_root=workspace_root,
            since=since,
            until=end,
        )
        conn.commit()
        scan_notes = list(scan.notes)
        git_state = scan.git_state

    events = GuardEventRepo.list_for_workspace(
        conn, workspace_id, since=since, until=end, limit=100
    )
    if events and git_state == "unknown":
        git_state = events[0].git_state

    rows: list[GuardEventRow] = []
    associated_count = 0
    confounded_count = 0
    for event in events:
        association = None
        if event.event_kind not in {"unavailable", "dirty_snapshot"}:
            association = _associate_event(
                conn, workspace_id=workspace_id, occurred_at=event.occurred_at
            )
            if association is not None:
                if association.verdict == "confounded":
                    confounded_count += 1
                elif association.verdict in {"improved", "regressed", "no_effect", "inconclusive"}:
                    associated_count += 1
        rows.append(
            GuardEventRow(
                event_id=event.event_id,
                occurred_at=event.occurred_at,
                path_rel=event.path_rel,
                event_kind=event.event_kind,
                commit_sha=event.commit_sha,
                parent_sha=event.parent_sha,
                before_hash=event.before_hash,
                after_hash=event.after_hash,
                diff_summary=event.diff_summary,
                git_state=event.git_state,
                source=event.source,
                confound_notes=list(event.confound_notes),
                linked_experiment_id=event.linked_experiment_id,
                association=association,
                optimize_href=(
                    f"/optimize?experiment={event.linked_experiment_id}&tab=portfolio"
                    if event.linked_experiment_id
                    else None
                ),
                event_href=f"/guard?event={event.event_id}",
            )
        )

    top = next((row for row in rows if row.event_kind not in {"unavailable"}), None)
    ledger = GuardLedgerSummary(
        conclusion=(
            f"{len(rows)} instruction-file event(s) in range; "
            f"{associated_count} with pre/post association; "
            f"{confounded_count} confounded. Git state: {git_state}."
            if rows
            else f"No instruction-file events in this range (git state: {git_state})."
        ),
        event_count=len(rows),
        associated_count=associated_count,
        confounded_count=confounded_count,
        git_state=git_state,
        next_action=(
            f"Review {top.path_rel} event"
            if top is not None
            else "Edit AGENTS.md / CLAUDE.md / .cursor/rules and rescan"
        ),
        next_action_href=top.event_href if top is not None else "/guard",
        limitation=(
            "Before/after session metrics are associations observed around instruction edits, "
            "not causal proof that the edit caused the shift. "
            f"Windows use ±{ASSOCIATION_WINDOW_DAYS} days around each event."
        ),
    )
    limitations = [
        ledger.limitation,
        "Raw instruction text is scrubbed; only bounded diff summaries are shown.",
        "Renames, merges, reverts, dirty worktrees, and no-git workspaces are first-class states.",
        *scan_notes,
    ]
    return GuardAnalyticsResponse(
        days=days,
        resolved_range=_resolved(days=days, since=since, end=end, time_range=time_range),
        ledger=ledger,
        events=rows,
        limitations=limitations,
    )


def _associate_event(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    occurred_at: str,
) -> GuardAssociation | None:
    windows = association_windows(occurred_at)
    if windows is None:
        return GuardAssociation(
            metric="cost_per_session",
            effect_estimate=None,
            effect_ci_low=None,
            effect_ci_high=None,
            pre_n=0,
            post_n=0,
            verdict="unavailable",
            language="unavailable",
            limitation="Event timestamp could not be parsed.",
        )
    pre_start, event_at, post_end = windows
    pre_ids = _trace_ids(conn, workspace_id, pre_start, event_at)
    post_ids = _trace_ids(conn, workspace_id, event_at, post_end)
    if len(pre_ids) < MIN_ASSOCIATION_N or len(post_ids) < MIN_ASSOCIATION_N:
        return GuardAssociation(
            metric="cost_per_session",
            effect_estimate=None,
            effect_ci_low=None,
            effect_ci_high=None,
            pre_n=len(pre_ids),
            post_n=len(post_ids),
            verdict="inconclusive",
            language="observed_after",
            confound_notes=["Insufficient sessions in the pre or post window."],
            limitation=(
                f"Need at least {MIN_ASSOCIATION_N} sessions on each side of the edit "
                "before reporting an association interval."
            ),
        )

    def metric_fn(trace_id: str) -> float:
        row = conn.execute(
            "SELECT COALESCE(cost, 0) AS cost FROM traces WHERE trace_id = ?",
            (trace_id,),
        ).fetchone()
        return float(row["cost"]) if row else 0.0

    causal = measure_causal_effect(
        conn,
        pre_trace_ids=pre_ids,
        post_trace_ids=post_ids,
        metric_fn=metric_fn,
    )
    language = (
        "associated_with"
        if causal.confound_flag
        or causal.verdict in {"confounded", "improved", "regressed", "no_effect"}
        else "observed_after"
    )
    return GuardAssociation(
        metric="cost_per_session",
        effect_estimate=causal.effect_estimate,
        effect_ci_low=causal.effect_ci_low,
        effect_ci_high=causal.effect_ci_high,
        pre_n=len(pre_ids),
        post_n=len(post_ids),
        verdict=causal.verdict,
        language=language,  # type: ignore[arg-type]
        confound_notes=list(causal.data_notes),
        limitation=(
            "Association uses difference-in-means with anytime-valid intervals and confound "
            "guards. Language stays 'associated with' / 'observed after', never causal."
        ),
    )


def _trace_ids(
    conn: sqlite3.Connection,
    workspace_id: str,
    start: str,
    end: str,
) -> list[str]:
    rows = conn.execute(
        """
        SELECT trace_id FROM traces
        WHERE workspace_id = ? AND started_at >= ? AND started_at < ?
        ORDER BY started_at, trace_id
        LIMIT 500
        """,
        (workspace_id, start, end),
    ).fetchall()
    return [str(row["trace_id"]) for row in rows]
