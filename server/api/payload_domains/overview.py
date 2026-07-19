"""Build overview and seven-day recap payloads."""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

import numpy as np

from server.analyze.budget_burn import compute_budget_burn
from server.analyze.tail import expected_worst
from server.api.payload_domains.common import bounds as _bounds
from server.api.payload_domains.common import data_notes as _data_notes
from server.api.payload_domains.common import resolved_range as _resolved
from server.api.schemas import (
    BudgetSummary,
    MetricDelta,
    MoneySummary,
    MonthEndProjection,
    NarrativeSentence,
    OverviewAttentionCategory,
    OverviewAttentionItem,
    OverviewEvidence,
    OverviewHero,
    OverviewResponse,
    QualityTrend,
    RecapDecayedRule,
    RecapGuardEvent,
    RecapRecommendedAction,
    RecapResponse,
    RecapSessionHighlight,
    RecapVerdict,
    ShieldSummary,
    TailRisk,
    TrendAnnotation,
    WasteCause,
)
from server.improve.experiments import reevaluate_due_experiments
from server.models.time_range import ResolvedTimeRange
from server.store.pagination import ANALYTICS_TRACE_CAP, fetch_capped
from server.util.resources import build_resource_report, resource_shield_fields

_WASTE_GUIDANCE: dict[str, tuple[str, str]] = {
    "identical_call": (
        "The agent repeated an identical tool call after other work without new inputs.",
        "Add an instruction to reuse the previous result unless the underlying input changed.",
    ),
    "blind_retry": (
        "The agent retried the same operation before using the failure output.",
        "Require the agent to explain the error and change one input before retrying.",
    ),
    "retry_loop": (
        "A failing tool was rerun repeatedly with no effective correction.",
        "Add a retry limit and require a different diagnostic step after the first failure.",
    ),
    "oversize_result": (
        "Large tool output consumed context beyond the useful working set.",
        "Ask for bounded output with a line, result, or file limit.",
    ),
    "stale_context": (
        "An unchanged file was read again after it was already in context.",
        "Tell the agent to reuse its prior summary until the file changes.",
    ),
    "orientation_waste": (
        "Early exploration read broadly without moving toward an edit.",
        "Start with the named files and stop exploring once the change surface is known.",
    ),
    "uncleared_tool_result": (
        "Re-fetchable tool output stayed in context after it stopped being useful.",
        "Summarize large results and discard the raw output before continuing.",
    ),
    "context_rot": (
        "Work continued after the context window entered its high-degradation tail.",
        "Checkpoint the plan and start a fresh session before context saturation.",
    ),
    "rebilling_waste": (
        "Previously supplied context was billed again in later model calls.",
        "Keep stable instructions concise and move large references behind targeted reads.",
    ),
}


def _money_summary(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    since: str,
    end: str,
    days: int,
) -> MoneySummary:
    traces, _trace_total = fetch_capped(
        conn,
        """
        SELECT trace_id, input_tokens, output_tokens, cost, cost_source, waste_tokens
        FROM traces
        WHERE workspace_id = ? AND started_at >= ? AND started_at < ?
        ORDER BY started_at, trace_id
        """,
        (workspace_id, since, end),
        cap=ANALYTICS_TRACE_CAP,
    )
    category_rows, _cat_total = fetch_capped(
        conn,
        """
        SELECT s.trace_id, s.waste_category, SUM(s.waste_tokens) AS waste_tokens
        FROM spans s JOIN traces t ON t.trace_id = s.trace_id
        WHERE t.workspace_id = ? AND t.started_at >= ? AND t.started_at < ?
          AND s.waste_category IS NOT NULL AND s.waste_tokens > 0
        GROUP BY s.trace_id, s.waste_category
        ORDER BY s.trace_id, s.waste_category
        """,
        (workspace_id, since, end),
        cap=ANALYTICS_TRACE_CAP,
    )
    by_trace: dict[str, dict[str, int]] = defaultdict(dict)
    for category_row in category_rows:
        by_trace[str(category_row["trace_id"])][str(category_row["waste_category"])] = int(
            category_row["waste_tokens"] or 0
        )

    category_tokens: dict[str, int] = defaultdict(int)
    category_cost: dict[str, float] = defaultdict(float)
    total_spend = 0.0
    wasted_spend = 0.0
    spend_estimated = False
    for trace in traces:
        cost = float(trace["cost"] or 0.0)
        total_spend += cost
        spend_estimated = spend_estimated or trace["cost_source"] == "priced"
        tokens = int(trace["input_tokens"] or 0) + int(trace["output_tokens"] or 0)
        waste_tokens = int(trace["waste_tokens"] or 0)
        if tokens <= 0 or waste_tokens <= 0 or cost <= 0:
            continue
        priced_waste_tokens = min(tokens, waste_tokens)
        trace_waste_cost = cost * priced_waste_tokens / tokens
        wasted_spend += trace_waste_cost
        categories = dict(by_trace.get(str(trace["trace_id"]), {}))
        attributed = sum(categories.values())
        if waste_tokens > attributed:
            categories["rebilling_waste"] = categories.get("rebilling_waste", 0) + (
                waste_tokens - attributed
            )
        scale = priced_waste_tokens / max(1, sum(categories.values()))
        for category, raw_tokens in categories.items():
            allocated_tokens = int(round(raw_tokens * scale))
            category_tokens[category] += allocated_tokens
            category_cost[category] += (
                trace_waste_cost * raw_tokens / max(1, sum(categories.values()))
            )

    causes: list[WasteCause] = []
    ranked_categories = sorted(category_cost.items(), key=lambda item: item[1], reverse=True)[:3]
    for category, amount in ranked_categories:
        cause, fix = _WASTE_GUIDANCE.get(
            category,
            (
                "Cairn detected avoidable context use in this category.",
                "Review the supporting sessions and add a targeted instruction for this pattern.",
            ),
        )
        evidence_rows = conn.execute(
            """
            SELECT
              s.trace_id, s.span_id, s.name, s.path_rel, s.waste_tokens,
              t.title, COUNT(*) OVER () AS evidence_count
            FROM spans s JOIN traces t ON t.trace_id = s.trace_id
            WHERE t.workspace_id = ? AND t.started_at >= ? AND t.started_at < ?
              AND s.waste_category = ? AND s.waste_tokens > 0
            ORDER BY s.waste_tokens DESC, s.trace_id, s.span_id
            LIMIT 5
            """,
            (workspace_id, since, end, category),
        ).fetchall()
        evidence = [
            OverviewEvidence(
                trace_id=str(evidence_row["trace_id"]),
                span_id=str(evidence_row["span_id"]),
                label=str(
                    evidence_row["name"]
                    or evidence_row["path_rel"]
                    or evidence_row["title"]
                    or category.replace("_", " ")
                ),
                path_rel=(
                    str(evidence_row["path_rel"]) if evidence_row["path_rel"] is not None else None
                ),
                waste_tokens=int(evidence_row["waste_tokens"] or 0),
            )
            for evidence_row in evidence_rows
        ]
        evidence_count = int(evidence_rows[0]["evidence_count"]) if evidence_rows else 0
        medium_confidence = evidence_count >= 3 and not spend_estimated
        causes.append(
            WasteCause(
                category=category,
                waste_tokens=category_tokens[category],
                estimated_savings_usd=round(amount, 4),
                cause=cause,
                fix=fix,
                confidence="medium" if medium_confidence else "low",
                confidence_explanation=(
                    "At least three classified spans support this cause and their session costs "
                    "are observed; the savings allocation remains an estimate."
                    if medium_confidence
                    else "Fewer than three supporting spans or estimated session pricing limits "
                    "confidence in the allocated impact."
                ),
                evidence_count=evidence_count,
                evidence=evidence,
            )
        )
    return MoneySummary(
        period_days=days,
        total_spend_usd=round(total_spend, 4),
        spend_estimated=spend_estimated,
        wasted_spend_usd=round(wasted_spend, 4),
        wasted_spend_pct=round((wasted_spend / total_spend * 100) if total_spend else 0.0, 2),
        waste_estimated=wasted_spend > 0,
        top_causes=causes,
        primary_action="/optimize",
    )


def _metric_delta(current: float | int | None, previous: float | int | None) -> MetricDelta:
    if current is None or previous is None:
        return MetricDelta(current=current, previous=previous, delta_pct=None, state="unavailable")
    if float(previous) == 0:
        return MetricDelta(current=current, previous=previous, delta_pct=None, state="no_previous")
    return MetricDelta(
        current=current,
        previous=previous,
        delta_pct=round((float(current) - float(previous)) / abs(float(previous)) * 100, 2),
        state="available",
    )


def _overview_hero(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    since: str,
    end: str,
    monthly_budget_usd: float | None,
    weekly_budget_usd: float | None = None,
    daily_budget_usd: float | None = None,
    timezone: str = "UTC",
) -> OverviewHero:
    since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
    end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
    duration = end_dt - since_dt
    previous_since = (since_dt - duration).isoformat()
    aggregate = conn.execute(
        """
        SELECT
          COUNT(*) AS traces,
          COALESCE(SUM(t.cost), 0) AS cost,
          COALESCE(SUM(t.input_tokens), 0) AS input_tokens,
          COALESCE(SUM(t.waste_tokens), 0) AS waste_tokens,
          AVG(o.quality_score) AS quality_mean,
          COUNT(o.quality_score) AS quality_n,
          AVG(o.cost_per_success) AS cost_per_success,
          COUNT(o.cost_per_success) AS success_n
        FROM traces t LEFT JOIN outcomes o ON o.trace_id = t.trace_id
        WHERE t.workspace_id = ? AND t.started_at >= ? AND t.started_at < ?
        """,
        (workspace_id, since, end),
    ).fetchone()
    previous = conn.execute(
        """
        SELECT
          COUNT(*) AS traces,
          COALESCE(SUM(t.cost), 0) AS cost,
          COALESCE(SUM(t.input_tokens), 0) AS input_tokens,
          COALESCE(SUM(t.waste_tokens), 0) AS waste_tokens,
          AVG(o.quality_score) AS quality_mean
        FROM traces t LEFT JOIN outcomes o ON o.trace_id = t.trace_id
        WHERE t.workspace_id = ? AND t.started_at >= ? AND t.started_at < ?
        """,
        (workspace_id, previous_since, since),
    ).fetchone()
    current_input = int(aggregate["input_tokens"] or 0)
    previous_input = int(previous["input_tokens"] or 0)
    current_waste_rate = (
        float(aggregate["waste_tokens"] or 0) / current_input * 100 if current_input else 0.0
    )
    previous_waste_rate = (
        float(previous["waste_tokens"] or 0) / previous_input * 100 if previous_input else 0.0
    )

    now = datetime.now(UTC)
    current_period = abs(now - end_dt.astimezone(UTC)) <= timedelta(minutes=5)
    burn = compute_budget_burn(
        conn,
        workspace_id=workspace_id,
        monthly_limit_usd=monthly_budget_usd,
        weekly_limit_usd=weekly_budget_usd,
        daily_limit_usd=daily_budget_usd,
        timezone=timezone,
        now=now,
    )
    projected = burn.linear_projected_usd
    trailing = burn.trailing_7d_projected_usd
    overrun = burn.projected_overrun_date
    projection_state: Literal["available", "insufficient_history", "not_current_period"]
    if not current_period:
        projection_state = "not_current_period"
        projected = None
        trailing = None
        overrun = None
        projection_explanation = "Projection is available only for a range ending now."
    elif burn.projection_state == "insufficient_history":
        projection_state = "insufficient_history"
        projection_explanation = burn.explanation
    else:
        projection_state = "available"
        projection_explanation = burn.explanation
    projection = MonthEndProjection(
        state=projection_state,
        projected_usd=projected,
        trailing_7d_projected_usd=trailing,
        projected_overrun_date=overrun,
        month_spend_usd=burn.month_spend_usd,
        observed_active_days=burn.observed_active_days,
        calendar_days_elapsed=burn.calendar_days_elapsed,
        days_in_month=burn.days_in_month,
        explanation=projection_explanation,
    )
    budget = BudgetSummary(
        state=burn.budget_state,
        monthly_limit_usd=burn.monthly_limit_usd,
        weekly_limit_usd=burn.weekly_limit_usd,
        daily_limit_usd=burn.daily_limit_usd,
        month_spend_usd=burn.month_spend_usd,
        week_spend_usd=burn.week_spend_usd,
        day_spend_usd=burn.day_spend_usd,
        projected_usd=projected,
        trailing_7d_projected_usd=trailing,
        projected_overrun_date=overrun,
        explanation=burn.explanation
        if current_period
        else (
            "Month spend uses the workspace calendar month; projections require a range ending now."
        ),
    )
    quality_mean = (
        round(float(aggregate["quality_mean"]), 2)
        if aggregate["quality_mean"] is not None
        else None
    )
    cost_per_success = (
        round(float(aggregate["cost_per_success"]), 4)
        if aggregate["cost_per_success"] is not None
        else None
    )
    quality_sparkline = [
        round(float(row["quality_mean"]), 2)
        for row in conn.execute(
            """
            SELECT AVG(o.quality_score) AS quality_mean
            FROM outcomes o JOIN traces t ON t.trace_id = o.trace_id
            WHERE t.workspace_id = ? AND t.started_at >= ? AND t.started_at < ?
              AND o.quality_score IS NOT NULL
            GROUP BY substr(t.started_at, 1, 10)
            ORDER BY substr(t.started_at, 1, 10)
            """,
            (workspace_id, since, end),
        ).fetchall()
        if row["quality_mean"] is not None
    ]
    return OverviewHero(
        quality_mean=quality_mean,
        quality_sessions=int(aggregate["quality_n"] or 0),
        cost_per_success_usd=cost_per_success,
        successful_sessions=int(aggregate["success_n"] or 0),
        quality_sparkline=quality_sparkline,
        projection=projection,
        budget=budget,
        deltas={
            "sessions": _metric_delta(int(aggregate["traces"] or 0), int(previous["traces"] or 0)),
            "spend": _metric_delta(float(aggregate["cost"] or 0), float(previous["cost"] or 0)),
            "waste_rate": _metric_delta(current_waste_rate, previous_waste_rate),
            "quality": _metric_delta(
                quality_mean,
                (
                    round(float(previous["quality_mean"]), 2)
                    if previous["quality_mean"] is not None
                    else None
                ),
            ),
        },
    )


def _resource_shield(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    workspace_root: Path | None,
) -> ShieldSummary:
    if workspace_root is None:
        return ShieldSummary(
            shield="resource",
            state="unavailable",
            summary="Detailed process, queue, memory, and disk budgets are not available.",
            facts=["Browser live updates and backend collection are independent controls."],
            limitation=(
                "No healthy resource state is claimed without measured process and storage data."
            ),
            action_label="Review workspace settings",
            action_path="/settings",
        )
    report = build_resource_report(
        conn,
        workspace_root=workspace_root,
        workspace_id=workspace_id,
    )
    fields = resource_shield_fields(report)
    state: Literal[
        "healthy",
        "degraded",
        "paused",
        "quarantined",
        "attention",
        "unknown",
        "unavailable",
    ] = fields["state"]
    return ShieldSummary(
        shield="resource",
        state=state,
        summary=str(fields["summary"]),
        facts=[str(item) for item in fields["facts"]],
        limitation=str(fields["limitation"]),
        action_label="Review resource inventory",
        action_path="/settings",
    )


def _shield_summaries(
    conn: sqlite3.Connection,
    *,
    traces: int,
    quality_sessions: int,
    workspace_id: str,
    workspace_root: Path | None,
) -> list[ShieldSummary]:
    coverage = quality_sessions / traces * 100 if traces else 0.0
    return [
        ShieldSummary(
            shield="verification",
            state="unknown",
            summary=f"{quality_sessions} of {traces} sessions have outcome scores.",
            facts=[f"Outcome coverage: {coverage:.1f}%."],
            limitation=(
                "Receipt v1 covers outcome/span evidence; claim extraction and "
                "final-change ordering remain unavailable."
            ),
            action_label="Review quality evidence",
            action_path="/quality",
        ),
        ShieldSummary(
            shield="scope",
            state="unavailable",
            summary="Workspace-wide scope policy evaluation is not available.",
            facts=["Observed file and tool activity remains available on individual sessions."],
            limitation=(
                "Cairn has not classified allowed paths or destructive actions for this summary."
            ),
            action_label="Review sessions",
            action_path="/sessions",
        ),
        ShieldSummary(
            shield="privacy",
            state="unknown",
            summary="Cairn is local-first and loopback-only by default.",
            facts=["No account or telemetry is required by Cairn."],
            limitation=(
                "This summary has not yet audited file permissions, retention, or provider egress."
            ),
            action_label="Review privacy settings",
            action_path="/settings",
        ),
        _resource_shield(conn, workspace_id=workspace_id, workspace_root=workspace_root),
    ]


def _trend_annotations(conn: sqlite3.Connection, *, since: str, end: str) -> list[TrendAnnotation]:
    annotations: list[TrendAnnotation] = []
    exp_rows = conn.execute(
        """
        SELECT experiment_id, target_file, applied_at
        FROM experiments
        WHERE applied_at IS NOT NULL AND applied_at >= ? AND applied_at < ?
        ORDER BY applied_at, experiment_id
        LIMIT 50
        """,
        (since, end),
    ).fetchall()
    annotations.extend(
        TrendAnnotation(
            occurred_at=str(row["applied_at"]),
            label=f"Experiment applied to {row['target_file']}",
            kind="experiment",
            action_path=f"/optimize?experiment={row['experiment_id']}",
        )
        for row in exp_rows
    )
    keys = {str(row[1]) for row in conn.execute("PRAGMA table_info(guard_events)").fetchall()}
    if "event_id" in keys:
        guard_rows = conn.execute(
            """
            SELECT event_id, path_rel, occurred_at, event_kind
            FROM guard_events
            WHERE occurred_at >= ? AND occurred_at < ?
              AND event_kind NOT IN ('unavailable')
            ORDER BY occurred_at, event_id
            LIMIT 50
            """,
            (since, end),
        ).fetchall()
        annotations.extend(
            TrendAnnotation(
                occurred_at=str(row["occurred_at"]),
                label=f"Instruction {row['event_kind']} · {row['path_rel']}",
                kind="guard",
                action_path=f"/guard?event={row['event_id']}",
            )
            for row in guard_rows
        )
    return sorted(annotations, key=lambda item: item.occurred_at)


def _attention_summary(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    since: str,
    end: str,
    hero: OverviewHero,
) -> list[OverviewAttentionCategory]:
    failed_rows = conn.execute(
        """
        SELECT
          t.trace_id, COALESCE(t.title, t.trace_id) AS title,
          o.tests_failed, o.build_status, o.outcome_label,
          COUNT(*) OVER () AS total
        FROM outcomes o JOIN traces t ON t.trace_id = o.trace_id
        WHERE t.workspace_id = ? AND t.started_at >= ? AND t.started_at < ?
          AND (
            COALESCE(o.tests_failed, 0) > 0
            OR lower(COALESCE(o.build_status, '')) IN ('fail', 'failed', 'error')
            OR lower(COALESCE(o.outcome_label, '')) IN ('fail', 'failed', 'failure')
          )
        ORDER BY t.started_at DESC, t.trace_id
        LIMIT 3
        """,
        (workspace_id, since, end),
    ).fetchall()
    failed_count = int(failed_rows[0]["total"]) if failed_rows else 0
    failed_items = [
        OverviewAttentionItem(
            item_id=str(row["trace_id"]),
            title=str(row["title"]),
            detail=(
                f"{int(row['tests_failed'])} recorded test failure"
                f"{'' if int(row['tests_failed']) == 1 else 's'}."
                if row["tests_failed"]
                else f"Recorded outcome: {row['build_status'] or row['outcome_label']}."
            ),
            action_path=f"/sessions/{row['trace_id']}",
        )
        for row in failed_rows
    ]

    debt_rows = conn.execute(
        """
        SELECT
          t.trace_id, COALESCE(t.title, t.trace_id) AS title,
          COUNT(*) OVER () AS total
        FROM outcomes o JOIN traces t ON t.trace_id = o.trace_id
        WHERE t.workspace_id = ? AND t.started_at >= ? AND t.started_at < ?
          AND lower(COALESCE(o.outcome_label, '')) IN ('success', 'passed', 'pass')
          AND o.tests_run IS NULL AND o.build_status IS NULL
        ORDER BY t.started_at DESC, t.trace_id
        LIMIT 3
        """,
        (workspace_id, since, end),
    ).fetchall()
    debt_count = int(debt_rows[0]["total"]) if debt_rows else 0
    debt_items = [
        OverviewAttentionItem(
            item_id=str(row["trace_id"]),
            title=str(row["title"]),
            detail="A successful outcome label has no recorded test or build evidence.",
            action_path=f"/sessions/{row['trace_id']}",
        )
        for row in debt_rows
    ]

    drift_rows = conn.execute(
        """
        SELECT i.insight_id, i.title, i.body, COUNT(*) OVER () AS total
        FROM insights i JOIN insight_states s ON s.insight_id = i.insight_id
        WHERE i.last_seen_at >= ? AND i.last_seen_at < ?
          AND s.state IN ('new', 'regressed')
          AND lower(i.detector) LIKE '%drift%'
        ORDER BY i.last_seen_at DESC, i.insight_id
        LIMIT 3
        """,
        (since, end),
    ).fetchall()
    drift_count = int(drift_rows[0]["total"]) if drift_rows else 0
    drift_items = [
        OverviewAttentionItem(
            item_id=str(row["insight_id"]),
            title=str(row["title"]),
            detail=str(row["body"]),
            action_path=f"/insights?insight={row['insight_id']}",
        )
        for row in drift_rows
    ]

    retry_rows = conn.execute(
        """
        SELECT
          t.trace_id, COALESCE(t.title, t.trace_id) AS title,
          MIN(s.span_id) AS span_id, COUNT(*) AS retry_count,
          COUNT(*) OVER () AS total
        FROM spans s JOIN traces t ON t.trace_id = s.trace_id
        WHERE t.workspace_id = ? AND t.started_at >= ? AND t.started_at < ?
          AND s.waste_category IN ('retry_loop', 'blind_retry')
        GROUP BY t.trace_id, t.title
        HAVING COUNT(*) >= 2
        ORDER BY retry_count DESC, t.trace_id
        LIMIT 3
        """,
        (workspace_id, since, end),
    ).fetchall()
    retry_count = int(retry_rows[0]["total"]) if retry_rows else 0
    retry_items = [
        OverviewAttentionItem(
            item_id=str(row["trace_id"]),
            title=str(row["title"]),
            detail=f"{int(row['retry_count'])} retry-loop or blind-retry spans were recorded.",
            action_path=f"/sessions/{row['trace_id']}?span={row['span_id']}",
        )
        for row in retry_rows
    ]

    parse_rows = conn.execute(
        """
        SELECT
          adapter_id, attempts, fully_parsed, degraded, skipped,
          COUNT(*) OVER () AS total
        FROM adapter_parse_health
        WHERE workspace_id = ? AND (degraded > 0 OR skipped > 0)
        ORDER BY (degraded + skipped) DESC, adapter_id
        LIMIT 3
        """,
        (workspace_id,),
    ).fetchall()
    parse_count = int(parse_rows[0]["total"]) if parse_rows else 0
    parse_items = [
        OverviewAttentionItem(
            item_id=str(row["adapter_id"]),
            title=f"{row['adapter_id']} parse coverage",
            detail=(
                f"{int(row['fully_parsed'])} fully parsed, {int(row['degraded'])} degraded, "
                f"and {int(row['skipped'])} skipped across {int(row['attempts'])} attempts."
            ),
            action_path="/settings",
        )
        for row in parse_rows
    ]

    budget_attention = hero.budget.state in {"attention", "over"}
    budget_items = (
        [
            OverviewAttentionItem(
                item_id="monthly-budget",
                title="Monthly budget needs attention",
                detail=hero.budget.explanation,
                action_path="/settings",
            )
        ]
        if budget_attention
        else []
    )

    def category(
        *,
        key: Literal[
            "failed_outcomes",
            "verification_debt",
            "unsupported_claims",
            "drift",
            "retry_storms",
            "parse_health",
            "budget",
            "decayed_rules",
        ],
        label: str,
        count: int,
        clear_summary: str,
        items: list[OverviewAttentionItem],
    ) -> OverviewAttentionCategory:
        return OverviewAttentionCategory(
            category=key,
            label=label,
            state="attention" if count else "clear",
            count=count,
            summary=(
                f"{count} item{'' if count == 1 else 's'} need attention."
                if count
                else clear_summary
            ),
            items=items,
        )

    return [
        category(
            key="failed_outcomes",
            label="Failed outcomes",
            count=failed_count,
            clear_summary="No recorded failed outcomes in this range.",
            items=failed_items,
        ),
        category(
            key="verification_debt",
            label="Verification debt",
            count=debt_count,
            clear_summary="No successful outcomes lack all recorded test/build evidence.",
            items=debt_items,
        ),
        OverviewAttentionCategory(
            category="unsupported_claims",
            label="Completion claims",
            state="unavailable",
            count=0,
            summary="Claim-level support is not available yet.",
            limitation=("Receipt v1 has no claim ledger yet; claim:unsupported stays unavailable."),
        ),
        category(
            key="drift",
            label="Behavior drift",
            count=drift_count,
            clear_summary="No active drift insight in this range.",
            items=drift_items,
        ),
        category(
            key="retry_storms",
            label="Retry storms",
            count=retry_count,
            clear_summary="No session has two or more recorded retry-loop spans.",
            items=retry_items,
        ),
        category(
            key="parse_health",
            label="Parse health",
            count=parse_count,
            clear_summary="No adapter currently reports degraded or skipped records.",
            items=parse_items,
        ),
        category(
            key="budget",
            label="Budget projection",
            count=1 if budget_attention else 0,
            clear_summary=hero.budget.explanation,
            items=budget_items,
        ),
        _decayed_rules_attention(conn),
    ]


def _decayed_rules_attention(conn: sqlite3.Connection) -> OverviewAttentionCategory:
    keys = {str(row[1]) for row in conn.execute("PRAGMA table_info(experiments)").fetchall()}
    if "decay_state" not in keys:
        return OverviewAttentionCategory(
            category="decayed_rules",
            label="Decayed rules",
            state="unavailable",
            count=0,
            summary="Rule-decay columns are not migrated yet.",
            limitation="Run migrations so optimize decay_state is available.",
        )
    decay_rows = conn.execute(
        """
        SELECT
          experiment_id, target_file, decay_state, verdict, plain_verdict,
          COUNT(*) OVER () AS total
        FROM experiments
        WHERE decay_state IN ('decaying', 'decayed')
        ORDER BY
          CASE decay_state WHEN 'decayed' THEN 0 ELSE 1 END,
          COALESCE(last_evaluated_at, measured_at, created_at) DESC,
          experiment_id
        LIMIT 3
        """
    ).fetchall()
    decay_count = int(decay_rows[0]["total"]) if decay_rows else 0
    items = [
        OverviewAttentionItem(
            item_id=str(row["experiment_id"]),
            title=f"{row['decay_state']} · {row['target_file']}",
            detail=(
                str(row["plain_verdict"])
                if row["plain_verdict"]
                else f"Verdict {row['verdict'] or 'none'}; decay flag is descriptive, not causal."
            ),
            action_path=f"/optimize?experiment={row['experiment_id']}&tab=portfolio",
        )
        for row in decay_rows
    ]
    return OverviewAttentionCategory(
        category="decayed_rules",
        label="Decayed rules",
        state="attention" if decay_count else "clear",
        count=decay_count,
        summary=(
            f"{decay_count} rule{'' if decay_count == 1 else 's'} flagged decaying or decayed."
            if decay_count
            else "No decaying or decayed optimize rules."
        ),
        items=items,
        limitation=(
            "Decay labels are descriptive (age, confound, revert, regression). "
            "They do not prove the rule caused later metric changes."
        ),
    )


def build_overview(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    days: int = 30,
    time_range: ResolvedTimeRange | None = None,
    monthly_budget_usd: float | None = None,
    weekly_budget_usd: float | None = None,
    daily_budget_usd: float | None = None,
    workspace_root: Path | None = None,
) -> OverviewResponse:
    since, end, days = _bounds(days, time_range)
    row = conn.execute(
        """
        SELECT
          COUNT(*) AS traces,
          COALESCE(SUM(input_tokens), 0) AS input_tokens,
          COALESCE(SUM(output_tokens), 0) AS output_tokens,
          COALESCE(SUM(cost), 0) AS cost,
          COALESCE(SUM(waste_tokens), 0) AS waste_tokens
        FROM traces
        WHERE workspace_id = ? AND started_at >= ? AND started_at < ?
        """,
        (workspace_id, since, end),
    ).fetchone()
    traces = int(row["traces"] or 0) if row else 0
    cost = float(row["cost"] or 0.0) if row else 0.0
    waste = int(row["waste_tokens"] or 0) if row else 0
    kpis: dict[str, float | int | None] = {
        "traces": traces,
        "input_tokens": int(row["input_tokens"] or 0) if row else 0,
        "output_tokens": int(row["output_tokens"] or 0) if row else 0,
        "cost": cost,
        "waste_tokens": waste,
    }
    narrative: list[NarrativeSentence] = []
    if traces:
        narrative.append(
            NarrativeSentence(
                text=(
                    f"{traces} agent {'session' if traces == 1 else 'sessions'} "
                    f"in the last {days} days."
                ),
                filter={"days": str(days)},
            )
        )
    if cost > 0:
        narrative.append(NarrativeSentence(text=f"Total spend ${cost:.2f}."))
    if waste > 0:
        narrative.append(
            NarrativeSentence(
                text=f"Estimated {waste:,} waste tokens flagged.",
                filter={"view": "waste"},
            )
        )
    cost_rows, _cost_total = fetch_capped(
        conn,
        """
        SELECT cost FROM traces
        WHERE workspace_id = ? AND started_at >= ? AND started_at < ? AND cost > 0
        ORDER BY started_at, trace_id
        """,
        (workspace_id, since, end),
        cap=ANALYTICS_TRACE_CAP,
    )
    costs = [float(r["cost"] or 0.0) for r in cost_rows]
    tail = TailRisk()
    if len(costs) >= 5:
        arr = np.array(costs, dtype=float)
        threshold = float(np.quantile(arr, 0.9))
        exceedances = arr[arr > threshold] - threshold
        if exceedances.size >= 5:
            tail = TailRisk(
                expected_worst_cost=expected_worst(exceedances, 7),
                exceedance_count=int(exceedances.size),
                threshold=threshold,
            )
    hero = _overview_hero(
        conn,
        workspace_id=workspace_id,
        since=since,
        end=end,
        monthly_budget_usd=monthly_budget_usd,
        weekly_budget_usd=weekly_budget_usd,
        daily_budget_usd=daily_budget_usd,
        timezone=time_range.timezone if time_range is not None else "UTC",
    )
    return OverviewResponse(
        days=days,
        resolved_range=_resolved(days=days, since=since, end=end, time_range=time_range),
        kpis=kpis,
        money=_money_summary(conn, workspace_id=workspace_id, since=since, end=end, days=days),
        hero=hero,
        shields=_shield_summaries(
            conn,
            traces=traces,
            quality_sessions=hero.quality_sessions,
            workspace_id=workspace_id,
            workspace_root=workspace_root,
        ),
        annotations=_trend_annotations(conn, since=since, end=end),
        attention=_attention_summary(
            conn,
            workspace_id=workspace_id,
            since=since,
            end=end,
            hero=hero,
        ),
        narrative=narrative,
        tail_risk=tail,
        data_notes=_data_notes(conn, workspace_id=workspace_id, since=since, end=end),
    )


def build_recap(conn: sqlite3.Connection, *, workspace_id: str) -> RecapResponse:
    """Build a bounded seven-day return summary from local ledger data."""
    now = datetime.now(UTC)
    end = now.isoformat()
    since = (now - timedelta(days=7)).isoformat()
    previous_since = (now - timedelta(days=14)).isoformat()
    portfolio_reeval = reevaluate_due_experiments(
        conn, workspace_id=workspace_id, force=False, limit=10
    )
    conn.commit()

    quality_trend = _period_metric_trend(
        conn,
        workspace_id=workspace_id,
        since=since,
        previous_since=previous_since,
        column="o.quality_score",
    )
    cps_trend = _period_metric_trend(
        conn,
        workspace_id=workspace_id,
        since=since,
        previous_since=previous_since,
        column="o.cost_per_success",
    )
    verdict_rows = conn.execute(
        """
        SELECT experiment_id, verdict, effect_estimate, effect_ci_low, effect_ci_high, measured_at
        FROM experiments
        WHERE status = 'verdict' AND verdict IS NOT NULL AND measured_at >= ?
        ORDER BY measured_at DESC
        """,
        (since,),
    ).fetchall()
    money = _money_summary(conn, workspace_id=workspace_id, since=since, end=end, days=7)
    decayed = _recap_decayed_rules(conn, since=since)
    guard_events = _recap_guard_events(conn, workspace_id=workspace_id, since=since, end=end)
    best, worst = _recap_session_extremes(conn, workspace_id=workspace_id, since=since, end=end)
    recommended = _recap_recommended_action(
        money=money, decayed=decayed, guard_events=guard_events, best=best
    )
    limitations = [
        "Period is a rolling 7-day UTC window ending at generation time (not a calendar week).",
        "Session titles are privacy-safe labels only; paths and prompts are not shown.",
        "Guard associations remain non-causal; recap lists events without inventing impact.",
        (
            f"Opportunistic portfolio re-eval touched {portfolio_reeval['evaluated_count']} "
            "due rule(s); Cairn does not run a monthly daemon."
        ),
    ]
    return RecapResponse(
        generated_at=end,
        period_days=7,
        period_start=since,
        period_end=end,
        timezone="UTC",
        period_kind="rolling_7d",
        money=money,
        quality_trend=quality_trend,
        cost_per_success_trend=cps_trend,
        experiment_verdicts=[
            RecapVerdict(
                experiment_id=str(row["experiment_id"]),
                verdict=str(row["verdict"]),
                effect_estimate=(
                    float(row["effect_estimate"]) if row["effect_estimate"] is not None else None
                ),
                effect_ci_low=(
                    float(row["effect_ci_low"]) if row["effect_ci_low"] is not None else None
                ),
                effect_ci_high=(
                    float(row["effect_ci_high"]) if row["effect_ci_high"] is not None else None
                ),
                measured_at=str(row["measured_at"]),
            )
            for row in verdict_rows
        ],
        decayed_rules=decayed,
        guard_events=guard_events,
        best_session=best,
        worst_session=worst,
        recommended_action=recommended,
        limitations=limitations,
    )


def _period_metric_trend(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    since: str,
    previous_since: str,
    column: str,
) -> QualityTrend:
    allowed = {"o.quality_score", "o.cost_per_success"}
    if column not in allowed:
        raise ValueError(f"unsupported recap metric column: {column}")
    quality_rows = conn.execute(
        f"""
        SELECT
          AVG(CASE WHEN t.started_at >= ? THEN {column} END) AS current_mean,
          COUNT(CASE WHEN t.started_at >= ? AND {column} IS NOT NULL THEN 1 END) AS current_n,
          AVG(CASE WHEN t.started_at >= ? AND t.started_at < ? THEN {column} END)
            AS previous_mean,
          COUNT(
            CASE WHEN t.started_at >= ? AND t.started_at < ? AND {column} IS NOT NULL THEN 1 END
          ) AS previous_n
        FROM outcomes o JOIN traces t ON t.trace_id = o.trace_id
        WHERE t.workspace_id = ? AND t.started_at >= ?
        """,
        (
            since,
            since,
            previous_since,
            since,
            previous_since,
            since,
            workspace_id,
            previous_since,
        ),
    ).fetchone()
    current_mean = (
        float(quality_rows["current_mean"]) if quality_rows["current_mean"] is not None else None
    )
    previous_mean = (
        float(quality_rows["previous_mean"]) if quality_rows["previous_mean"] is not None else None
    )
    delta = (
        round(current_mean - previous_mean, 4)
        if current_mean is not None and previous_mean is not None
        else None
    )
    return QualityTrend(
        current_mean=round(current_mean, 4) if current_mean is not None else None,
        previous_mean=round(previous_mean, 4) if previous_mean is not None else None,
        delta=delta,
        current_sessions=int(quality_rows["current_n"] or 0),
        previous_sessions=int(quality_rows["previous_n"] or 0),
    )


def _privacy_safe_title(raw: object, trace_id: str) -> str:
    title = str(raw or "").strip()
    if not title or "/" in title or "\\" in title or len(title) > 80:
        return f"Session {trace_id[:8]}"
    return title


def _recap_session_extremes(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    since: str,
    end: str,
) -> tuple[RecapSessionHighlight | None, RecapSessionHighlight | None]:
    params = (workspace_id, since, end)
    best_row = conn.execute(
        """
        SELECT t.trace_id, t.title, t.cost
        FROM traces t
        WHERE t.workspace_id = ? AND t.started_at >= ? AND t.started_at < ?
          AND t.cost IS NOT NULL AND t.cost > 0
        ORDER BY t.cost ASC, t.trace_id
        LIMIT 1
        """,
        params,
    ).fetchone()
    if best_row is None:
        return None, None
    worst_row = conn.execute(
        """
        SELECT t.trace_id, t.title, t.cost
        FROM traces t
        WHERE t.workspace_id = ? AND t.started_at >= ? AND t.started_at < ?
          AND t.cost IS NOT NULL AND t.cost > 0
        ORDER BY t.cost DESC, t.trace_id DESC
        LIMIT 1
        """,
        params,
    ).fetchone()
    assert worst_row is not None
    best = RecapSessionHighlight(
        trace_id=str(best_row["trace_id"]),
        title=_privacy_safe_title(best_row["title"], str(best_row["trace_id"])),
        metric="cost_usd",
        value=float(best_row["cost"]),
        href=f"/sessions/{best_row['trace_id']}",
    )
    worst = RecapSessionHighlight(
        trace_id=str(worst_row["trace_id"]),
        title=_privacy_safe_title(worst_row["title"], str(worst_row["trace_id"])),
        metric="cost_usd",
        value=float(worst_row["cost"]),
        href=f"/sessions/{worst_row['trace_id']}",
    )
    if best.trace_id == worst.trace_id:
        return best, None
    return best, worst


def _recap_decayed_rules(conn: sqlite3.Connection, *, since: str) -> list[RecapDecayedRule]:
    keys = {str(row[1]) for row in conn.execute("PRAGMA table_info(experiments)").fetchall()}
    if "decay_state" not in keys:
        return []
    rows = conn.execute(
        """
        SELECT experiment_id, target_file, decay_state, plain_verdict
        FROM experiments
        WHERE decay_state IN ('decaying', 'decayed')
          AND COALESCE(last_evaluated_at, measured_at, created_at) >= ?
        ORDER BY
          CASE decay_state WHEN 'decayed' THEN 0 ELSE 1 END,
          COALESCE(last_evaluated_at, measured_at, created_at) DESC
        LIMIT 10
        """,
        (since,),
    ).fetchall()
    return [
        RecapDecayedRule(
            experiment_id=str(row["experiment_id"]),
            target_file=str(row["target_file"]) if row["target_file"] else None,
            decay_state=str(row["decay_state"]),
            plain_verdict=str(row["plain_verdict"]) if row["plain_verdict"] else None,
            href=f"/optimize?experiment={row['experiment_id']}&tab=portfolio",
        )
        for row in rows
    ]


def _recap_guard_events(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    since: str,
    end: str,
) -> list[RecapGuardEvent]:
    keys = {str(row[1]) for row in conn.execute("PRAGMA table_info(guard_events)").fetchall()}
    if "event_id" not in keys:
        return []
    rows = conn.execute(
        """
        SELECT event_id, occurred_at, path_rel, event_kind
        FROM guard_events
        WHERE workspace_id = ? AND occurred_at >= ? AND occurred_at < ?
          AND event_kind NOT IN ('unavailable')
        ORDER BY occurred_at DESC, event_id
        LIMIT 10
        """,
        (workspace_id, since, end),
    ).fetchall()
    return [
        RecapGuardEvent(
            event_id=str(row["event_id"]),
            occurred_at=str(row["occurred_at"]),
            path_rel=str(row["path_rel"]),
            event_kind=str(row["event_kind"]),
            href=f"/guard?event={row['event_id']}",
        )
        for row in rows
    ]


def _recap_recommended_action(
    *,
    money: MoneySummary,
    decayed: list[RecapDecayedRule],
    guard_events: list[RecapGuardEvent],
    best: RecapSessionHighlight | None,
) -> RecapRecommendedAction | None:
    if money.top_causes:
        cause = money.top_causes[0]
        return RecapRecommendedAction(
            label=f"Address {cause.category.replace('_', ' ')}",
            href=money.primary_action or "/optimize",
            reason=cause.fix,
        )
    if decayed:
        rule = decayed[0]
        return RecapRecommendedAction(
            label=f"Review {rule.decay_state} rule",
            href=rule.href,
            reason=rule.plain_verdict or "Descriptive decay flag needs a human look.",
        )
    if guard_events:
        event = guard_events[0]
        return RecapRecommendedAction(
            label=f"Review instruction {event.event_kind}",
            href=event.href,
            reason=f"{event.path_rel} changed in this window (association only).",
        )
    if best is not None:
        return RecapRecommendedAction(
            label="Inspect lowest-cost session",
            href=best.href,
            reason="Use a cheap successful session as a comparison baseline.",
        )
    return None
