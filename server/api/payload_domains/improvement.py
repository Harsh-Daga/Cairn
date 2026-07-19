"""Insight evidence and experiment payload builders."""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any, Literal, cast

from pydantic import JsonValue

from server.api.schemas import (
    EvidenceChainResponse,
    ExperimentDetailResponse,
    ExperimentRow,
    ExperimentsResponse,
    InsightFix,
    InsightRow,
    InsightsLedgerSummary,
    InsightsResponse,
    OptimizeLedgerSummary,
    VerdictPreviewData,
)
from server.improve.experiments import plain_verdict_text
from server.improve.experiments import preview as experiment_preview
from server.models.insight import InsightLifecycle
from server.models.span import Span
from server.store.repos.evidence import EvidenceRepo
from server.store.repos.experiments import ExperimentRepo
from server.store.repos.insights import InsightRepo
from server.store.repos.spans import SpanRepo

_WRITE_SAFETY = (
    "Cairn only writes managed blocks in AGENTS.md, CLAUDE.md, and .cursor/rules. "
    "Apply creates an experiment-specific backup under .cairn/backups/; revert restores "
    "that backup and leaves edits outside the managed block untouched. A checksum conflict "
    "refuses overwrite so user edits inside the block are never clobbered."
)
_GUARD_LIMITATION = (
    "Guard links appear when a matching instruction-file event is recorded for this rule. "
    "Before/after associations on Guard remain non-causal."
)
_PORTFOLIO_STATUSES = frozenset({"applied", "measuring", "verdict", "reverted"})
_ACTIVE_STATUSES = frozenset({"applied", "measuring"})
_SEVERITY_WEIGHT = {"error": 1.0, "warning": 0.75, "suggestion": 0.45, "info": 0.2}


def build_insights(
    conn: sqlite3.Connection,
    *,
    state: str | None = None,
    limit: int = 100,
) -> InsightsResponse:
    lifecycle: InsightLifecycle | None = None
    if state is not None:
        lifecycle = state  # type: ignore[assignment]
    rows = InsightRepo.list_by_state(conn, lifecycle, limit=max(limit, 200))
    now = datetime.now(UTC).isoformat()
    drafted: list[InsightRow] = []
    snoozed_count = 0

    for row in rows:
        evidence = EvidenceRepo.get(conn, row.insight.evidence_id)
        contract_raw = evidence.metrics.get("insight_contract", {}) if evidence else {}
        contract = contract_raw if isinstance(contract_raw, dict) else {}
        fix_raw = contract.get("fix")
        fix = fix_raw if isinstance(fix_raw, dict) else {}
        if not fix.get("value"):
            fix = {
                "kind": "manual",
                "label": "Review supporting evidence",
                "value": row.insight.action or row.insight.body,
            }
        unavailable_reason = contract.get("savings_unavailable_reason")
        if row.insight.savings_estimate is None and not unavailable_reason:
            unavailable_reason = "Legacy insight without a defensible savings estimate."

        lifecycle_state = row.state.state
        snoozed_until = row.state.snoozed_until
        if lifecycle_state == "muted" and snoozed_until and snoozed_until <= now:
            lifecycle_state = "new"
            snoozed_until = None
        if lifecycle_state == "muted":
            snoozed_count += 1

        confidence = _confidence(evidence.metrics if evidence else {}, row.state.see_count)
        impact = (
            float(row.insight.savings_estimate)
            if row.insight.savings_estimate is not None
            else None
        )
        recurrence = max(1, int(row.state.see_count))
        rank_score = _rank_score(
            severity=str(row.insight.severity),
            impact=impact,
            confidence=confidence,
            last_seen_at=row.insight.last_seen_at,
            recurrence=recurrence,
            now=now,
        )
        drafted.append(
            InsightRow(
                insight_id=row.insight.insight_id,
                fingerprint=row.insight.fingerprint,
                detector=row.insight.detector,
                severity=row.insight.severity,
                title=row.insight.title,
                body=row.insight.body,
                state=lifecycle_state,
                savings_estimate=row.insight.savings_estimate,
                savings_unavailable_reason=(
                    str(unavailable_reason) if unavailable_reason else None
                ),
                fix=InsightFix(
                    kind=str(fix.get("kind", "manual")),
                    label=str(fix.get("label", "Review supporting evidence")),
                    value=str(fix["value"]),
                ),
                diagnostic=bool(contract.get("diagnostic", not contract)),
                action=row.insight.action,
                last_seen_at=row.insight.last_seen_at,
                rank_score=rank_score,
                impact=impact,
                confidence=confidence,
                recurrence=recurrence,
                snoozed_until=snoozed_until,
            )
        )

    insights, suppressed = _suppress_overlapping(drafted, conn)
    insights = sorted(
        insights,
        key=lambda item: (
            -item.rank_score,
            0 if item.state in {"new", "regressed"} else 1,
            -(
                datetime.fromisoformat(item.last_seen_at.replace("Z", "+00:00")).timestamp()
                if item.last_seen_at
                else 0.0
            ),
        ),
    )[:limit]

    open_count = sum(1 for item in insights if item.state in {"new", "regressed", "ack"})
    top = next((item for item in insights if item.state in {"new", "regressed"}), None)
    ledger = InsightsLedgerSummary(
        conclusion=(
            f"{open_count} open insight(s) ranked by impact, confidence, severity, recency, "
            f"and recurrence; {suppressed} overlapping duplicate(s) suppressed."
            if insights
            else "No insights in this workspace yet."
        ),
        open_count=open_count,
        ranked_count=len(insights),
        snoozed_count=snoozed_count,
        suppressed_duplicates=suppressed,
        top_insight_id=top.insight_id if top else None,
        next_action=(f"Review {top.title}" if top is not None else "Run detectors via Optimize"),
        next_action_href=(
            f"/insights?insight={top.insight_id}" if top is not None else "/optimize"
        ),
        limitation=(
            "Rank scores are descriptive prioritization, not causal impact. Savings estimates "
            "remain unavailable when detectors cannot defend a number. Snoozed insights hide for "
            "14 days unless severity/savings worsen."
        ),
    )
    limitations = [
        ledger.limitation,
        "Cross-detector duplicates sharing the same primary evidence trace are suppressed.",
        "Muted/snoozed insights auto-return when the snooze window expires or impact worsens.",
        "Verification/misalignment findings stay in Diagnostics when marked diagnostic.",
    ]
    return InsightsResponse(
        ledger=ledger,
        insights=insights,
        total=InsightRepo.count_by_state(conn, lifecycle),
        limitations=limitations,
    )


def _confidence(metrics: dict[str, Any], see_count: int) -> Literal["low", "medium"]:
    raw = metrics.get("confidence")
    if isinstance(raw, (int, float)) and float(raw) >= 0.8 and see_count >= 2:
        return "medium"
    if see_count >= 3:
        return "medium"
    return "low"


def _rank_score(
    *,
    severity: str,
    impact: float | None,
    confidence: Literal["low", "medium"],
    last_seen_at: str,
    recurrence: int,
    now: str,
) -> float:
    severity_part = _SEVERITY_WEIGHT.get(severity, 0.2)
    impact_part = min(max(float(impact or 0.0), 0.0) / 10.0, 1.0)
    confidence_part = 0.7 if confidence == "medium" else 0.35
    try:
        last = datetime.fromisoformat(last_seen_at.replace("Z", "+00:00"))
        current = datetime.fromisoformat(now.replace("Z", "+00:00"))
        age_days = max((current - last).total_seconds() / 86400.0, 0.0)
    except ValueError:
        age_days = 30.0
    recency_part = max(0.0, 1.0 - min(age_days, 30.0) / 30.0)
    recurrence_part = min(recurrence / 5.0, 1.0)
    return round(
        0.30 * severity_part
        + 0.25 * impact_part
        + 0.15 * confidence_part
        + 0.15 * recency_part
        + 0.15 * recurrence_part,
        4,
    )


def _suppress_overlapping(
    insights: list[InsightRow],
    conn: sqlite3.Connection,
) -> tuple[list[InsightRow], int]:
    """Keep highest-ranked insight per primary evidence trace for overlapping detectors."""
    by_trace: dict[str, list[InsightRow]] = defaultdict(list)
    untouched: list[InsightRow] = []
    for insight in insights:
        stored = InsightRepo.get(conn, insight.insight_id)
        evidence = EvidenceRepo.get(conn, stored.evidence_id) if stored is not None else None
        primary = evidence.trace_ids[0] if evidence and evidence.trace_ids else None
        if primary is None:
            untouched.append(insight)
            continue
        by_trace[primary].append(insight)

    visible: list[InsightRow] = list(untouched)
    suppressed = 0
    for group in by_trace.values():
        ordered = sorted(group, key=lambda item: (-item.rank_score, item.detector))
        visible.append(ordered[0])
        suppressed += max(0, len(ordered) - 1)
    return visible, suppressed


def build_evidence_chain(conn: sqlite3.Connection, insight_id: str) -> EvidenceChainResponse | None:
    insight = InsightRepo.get(conn, insight_id)
    if insight is None:
        return None
    evidence = EvidenceRepo.get(conn, insight.evidence_id)
    if evidence is None:
        return None
    spans: list[Span] = []
    if evidence.span_ids:
        for span_id in evidence.span_ids:
            span = SpanRepo.get(conn, span_id)
            if span is not None:
                spans.append(span)
    return EvidenceChainResponse(
        insight_id=insight_id,
        evidence_id=evidence.evidence_id,
        producer=evidence.producer,
        produced_at=evidence.produced_at,
        trace_ids=evidence.trace_ids,
        span_ids=evidence.span_ids,
        metrics=cast(dict[str, JsonValue], evidence.metrics),
        spans=spans,
    )


def build_experiments(conn: sqlite3.Connection) -> ExperimentsResponse:
    rows = ExperimentRepo.list_all(conn)
    experiments = [
        ExperimentRow(
            experiment_id=experiment.experiment_id,
            status=experiment.status,
            target_file=experiment.target_file,
            created_at=experiment.created_at,
            applied_at=experiment.applied_at,
            min_holdout=experiment.min_holdout,
            outcome_n_effective=experiment.outcome_n_effective,
            outcome_n_raw=experiment.outcome_n_raw,
            sample_size=experiment.outcome_n_effective,
            verdict=experiment.verdict,
            plain_verdict=experiment.plain_verdict
            or (
                plain_verdict_text(
                    verdict=experiment.verdict,
                    effect_estimate=experiment.effect_estimate,
                    confound_flag=experiment.confound_flag,
                    confound_notes=list(experiment.confound_notes),
                )
                if experiment.verdict is not None or experiment.confound_flag
                else None
            ),
            lift_pct=experiment.effect_estimate,
            effect_ci_low=experiment.effect_ci_low,
            effect_ci_high=experiment.effect_ci_high,
            measured_at=experiment.measured_at,
            last_evaluated_at=experiment.last_evaluated_at,
            eval_interval_days=experiment.eval_interval_days,
            proposal_source=experiment.proposal_source,
            decay_state=experiment.decay_state,
            confound_flag=experiment.confound_flag,
            confound_notes=list(experiment.confound_notes),
            effect_history=list(experiment.effect_history),
            verdict_history=list(experiment.verdict_history),
            regression_outside_interval=experiment.regression_outside_interval,
            guard_event_id=experiment.guard_event_id,
            in_portfolio=experiment.status in _PORTFOLIO_STATUSES,
        )
        for experiment in rows
    ]
    proposed_count = sum(1 for item in experiments if item.status == "proposed")
    active_count = sum(1 for item in experiments if item.status in _ACTIVE_STATUSES)
    portfolio_count = sum(1 for item in experiments if item.in_portfolio)
    decayed_count = sum(1 for item in experiments if item.decay_state in {"decaying", "decayed"})
    next_proposed = next((item for item in experiments if item.status == "proposed"), None)
    next_decayed = next(
        (item for item in experiments if item.decay_state in {"decaying", "decayed"}),
        None,
    )
    if next_proposed is not None:
        next_action = f"Review proposal for {next_proposed.target_file or 'managed file'}"
        next_action_href = f"/optimize?experiment={next_proposed.experiment_id}&tab=board"
    elif next_decayed is not None:
        next_action = f"Review decayed rule {next_decayed.experiment_id[:12]}…"
        next_action_href = f"/optimize?experiment={next_decayed.experiment_id}&tab=portfolio"
    elif portfolio_count:
        next_action = "Review portfolio effect intervals"
        next_action_href = "/optimize?tab=portfolio"
    else:
        next_action = "Generate proposals from open insights"
        next_action_href = "/insights"

    ledger = OptimizeLedgerSummary(
        conclusion=(
            f"{proposed_count} proposal(s), {active_count} measuring, "
            f"{portfolio_count} in portfolio, {decayed_count} decaying/decayed."
            if experiments
            else "No optimize experiments in this workspace yet."
        ),
        proposed_count=proposed_count,
        active_count=active_count,
        portfolio_count=portfolio_count,
        decayed_count=decayed_count,
        next_action=next_action,
        next_action_href=next_action_href,
        limitation=(
            "Verdicts use holdout difference-in-means with confound guards; they are not "
            "guaranteed savings. Decay labels are descriptive age/confound/interval-drift "
            "flags, not causal health scores. Guard links appear when an applied experiment "
            "matches an instruction-file event window."
        ),
    )
    limitations = [
        ledger.limitation,
        _WRITE_SAFETY,
        (
            "Guard links use associated instruction-file events when present; absence means "
            "no matching Guard event, not a failed measurement."
        ),
        "Proposal source is local (deterministic) unless an opt-in provider reflector was used.",
        (
            "Portfolio re-evaluation is opportunistic on sync, recap, or "
            "`cairn optimize evaluate` — there is no monthly daemon."
        ),
        (
            "Outside-interval flags compare a new estimate to the prior CI and preserve "
            "historical verdicts; they do not invent causality."
        ),
    ]
    return ExperimentsResponse(
        ledger=ledger,
        experiments=experiments,
        limitations=limitations,
    )


def build_experiment_detail(
    conn: sqlite3.Connection,
    experiment_id: str,
    *,
    workspace_id: str,
) -> ExperimentDetailResponse | None:
    experiment = ExperimentRepo.get(conn, experiment_id)
    if experiment is None:
        return None
    preview = experiment_preview(conn, experiment, workspace_id=workspace_id)
    return ExperimentDetailResponse(
        experiment=experiment,
        preview=VerdictPreviewData(
            expected_days_to_verdict=preview.expected_days_to_verdict,
            traces_per_day=preview.traces_per_day,
            n_effective_needed=preview.n_effective_needed,
            traffic_unknown=preview.traffic_unknown,
        ),
        write_safety=_WRITE_SAFETY,
        guard_limitation=_GUARD_LIMITATION,
    )
