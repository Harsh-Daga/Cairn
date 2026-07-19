"""Difficulty-aware agent comparison payload builders."""

from __future__ import annotations

import math
import sqlite3
from collections import defaultdict
from typing import Any

from server.api.payload_domains.common import append_truncation as _append_truncation
from server.api.payload_domains.common import bounds as _bounds
from server.api.payload_domains.common import resolved_range as _resolved
from server.api.schemas import (
    CompareAnalyticsResponse,
    CompareCell,
    CompareLedgerSummary,
    CompareMetricInterval,
    ComparePairwise,
)
from server.improve.stats import anytime_valid_radius
from server.models.time_range import ResolvedTimeRange
from server.store.pagination import ANALYTICS_TRACE_CAP, fetch_capped, truncation_limitation

MIN_SAMPLE = 5
WINNER_SAMPLE = 20
_SUCCESS_LABELS = frozenset({"success", "passed", "pass", "landed"})
_BUCKET_ORDER = ("trivial", "standard", "hard", "epic", "unknown")
_PAIR_METRIC = "cost_per_session"


def _sample_std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    return math.sqrt(max(variance, 0.0))


def build_compare_analytics(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    days: int = 30,
    time_range: ResolvedTimeRange | None = None,
) -> CompareAnalyticsResponse:
    since, end, days = _bounds(days, time_range)
    rows, row_total = fetch_capped(
        conn,
        """
        WITH agent_trace AS (
          SELECT s.trace_id,
                 COALESCE(NULLIF(s.agent_id, ''), t.actor_id, '(default)') AS agent_id,
                 SUM(COALESCE(s.input_tokens, 0) + COALESCE(s.output_tokens, 0)) AS agent_tokens
          FROM spans s
          JOIN traces t ON t.trace_id = s.trace_id
          WHERE t.workspace_id = ? AND t.started_at >= ? AND t.started_at < ?
          GROUP BY s.trace_id, COALESCE(NULLIF(s.agent_id, ''), t.actor_id, '(default)')
        ), ranked AS (
          SELECT *,
                 ROW_NUMBER() OVER (
                   PARTITION BY trace_id
                   ORDER BY agent_tokens DESC, agent_id ASC
                 ) AS rn
          FROM agent_trace
        )
        SELECT t.trace_id, t.cost, t.waste_tokens, t.model, t.source, t.status,
               COALESCE(NULLIF(t.difficulty_bucket, ''), 'unknown') AS difficulty_bucket,
               COALESCE(t.input_tokens, 0) + COALESCE(t.output_tokens, 0) AS total_tokens,
               r.agent_id,
               o.quality_score, o.outcome_label, o.tests_run, o.tests_failed, o.build_status,
               o.reverted_within_window, o.fixup_within_window,
               EXISTS(
                 SELECT 1 FROM spans s
                 WHERE s.trace_id = t.trace_id
                   AND COALESCE(s.waste_category, '') IN (
                     'retry_loop', 'identical_call', 're_read', 'rebilling_waste'
                   )
               ) AS has_retry
        FROM traces t
        JOIN ranked r ON r.trace_id = t.trace_id AND r.rn = 1
        LEFT JOIN outcomes o ON o.trace_id = t.trace_id
        WHERE t.workspace_id = ? AND t.started_at >= ? AND t.started_at < ?
        ORDER BY t.started_at
        """,
        (workspace_id, since, end, workspace_id, since, end),
        cap=ANALYTICS_TRACE_CAP,
    )

    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (str(row["agent_id"]), str(row["difficulty_bucket"]))
        bucket = groups.setdefault(
            key,
            {
                "costs": [],
                "tokens": [],
                "waste": [],
                "quality": [],
                "retry": [],
                "debt": [],
                "verified": [],
                "correction": [],
                "success_costs": [],
                "models": set(),
                "sources": set(),
                "trace_ids": [],
            },
        )
        cost = float(row["cost"] or 0.0)
        tokens = float(row["total_tokens"] or 0.0)
        waste = float(row["waste_tokens"] or 0.0)
        bucket["costs"].append(cost)
        bucket["tokens"].append(tokens)
        bucket["waste"].append(waste)
        bucket["retry"].append(1.0 if int(row["has_retry"] or 0) else 0.0)
        state = _verification_state(row)
        bucket["debt"].append(1.0 if state == "debt" else 0.0)
        verified = 1.0 if state == "verified" else 0.0
        bucket["verified"].append(verified)
        correction = 1.0 if _correction_burden(row) else 0.0
        bucket["correction"].append(correction)
        if row["quality_score"] is not None:
            bucket["quality"].append(float(row["quality_score"]))
        if verified or str(row["outcome_label"] or "").lower() in _SUCCESS_LABELS:
            bucket["success_costs"].append(cost)
        if row["model"]:
            bucket["models"].add(str(row["model"]))
        if row["source"]:
            bucket["sources"].add(str(row["source"]))
        bucket["trace_ids"].append(str(row["trace_id"]))

    cells: list[CompareCell] = []
    for (agent_id, difficulty_bucket), bucket in sorted(
        groups.items(),
        key=lambda item: (_bucket_rank(item[0][1]), item[0][0]),
    ):
        sessions = len(bucket["costs"])
        cell_limit = (
            f"n={sessions} below minimum sample {MIN_SAMPLE}; intervals are descriptive only."
            if sessions < MIN_SAMPLE
            else "Descriptive association within difficulty bucket; not a causal ranking."
        )
        cells.append(
            CompareCell(
                agent_id=agent_id,
                difficulty_bucket=difficulty_bucket,
                sessions=sessions,
                cost_per_session=_interval(bucket["costs"], kind="mean"),
                tokens_per_session=_interval(bucket["tokens"], kind="mean"),
                quality_mean=_interval(bucket["quality"], kind="mean"),
                waste_tokens_per_session=_interval(bucket["waste"], kind="mean"),
                retry_rate=_interval(bucket["retry"], kind="rate"),
                cost_per_success=_cost_per_success(bucket["success_costs"], sessions),
                verification_debt_rate=_interval(bucket["debt"], kind="rate"),
                verified_success_rate=_interval(bucket["verified"], kind="rate"),
                correction_burden_rate=_interval(bucket["correction"], kind="rate"),
                models=sorted(bucket["models"]),
                sources=sorted(bucket["sources"]),
                limitation=cell_limit,
            )
        )

    pairwise = _pairwise(cells, groups)
    confound_warnings = _global_confounds(cells)
    ledger = _compare_ledger(cells, confound_warnings)
    limitations = [
        "Primary agent is the highest token-share agent in each session; co-agents are not ranked.",
        (
            f"Intervals use an anytime-valid mean radius; cells need n≥{MIN_SAMPLE} "
            "to count as sufficient."
        ),
        (
            f"No overall winner is declared unless one agent has n≥{WINNER_SAMPLE} in a shared "
            "difficulty bucket with non-overlapping cost-per-session intervals and no confound "
            "warnings."
        ),
        "Verification debt requires success labels without test/build evidence; correction burden "
        "uses revert/fixup flags and reverted/partial labels.",
        *confound_warnings,
    ]
    _append_truncation(limitations, truncation_limitation("Compare sessions", len(rows), row_total))
    return CompareAnalyticsResponse(
        days=days,
        resolved_range=_resolved(days=days, since=since, end=end, time_range=time_range),
        ledger=ledger,
        cells=cells,
        pairwise=pairwise,
        confound_warnings=confound_warnings,
        limitations=limitations,
    )


def _bucket_rank(bucket: str) -> int:
    try:
        return _BUCKET_ORDER.index(bucket)
    except ValueError:
        return len(_BUCKET_ORDER)


def _verification_state(row: sqlite3.Row) -> str:
    if (
        row["tests_failed"] is None
        and row["tests_run"] is None
        and row["build_status"] is None
        and row["outcome_label"] is None
        and row["quality_score"] is None
    ):
        return "unknown"
    if int(row["tests_failed"] or 0) > 0 or str(row["build_status"] or "").lower() in {
        "fail",
        "failed",
        "error",
    }:
        return "failed"
    if int(row["tests_run"] or 0) > 0 or str(row["build_status"] or "").lower() in {
        "pass",
        "passed",
        "success",
    }:
        return "verified"
    if str(row["outcome_label"] or "").lower() in _SUCCESS_LABELS:
        return "debt"
    return "unverified"


def _correction_burden(row: sqlite3.Row) -> bool:
    if int(row["reverted_within_window"] or 0) or int(row["fixup_within_window"] or 0):
        return True
    return str(row["outcome_label"] or "").lower() in {"reverted", "partial"}


def _interval(values: list[float], *, kind: str) -> CompareMetricInterval:
    n = len(values)
    if n == 0:
        return CompareMetricInterval(
            value=None,
            ci_low=None,
            ci_high=None,
            sample_size=0,
            sufficient=False,
            limitation="No observations in this cell.",
        )
    mean = sum(values) / n
    sigma = _sample_std(values) if n >= 2 else 0.0
    radius = anytime_valid_radius(float(n), sigma) if n >= 2 else float("inf")
    if not math.isfinite(radius):
        low = high = None if n < MIN_SAMPLE else round(mean, 6)
    else:
        low = round(mean - radius, 6)
        high = round(mean + radius, 6)
        if kind == "rate":
            low = max(0.0, low)
            high = min(1.0, high)
    sufficient = n >= MIN_SAMPLE and low is not None and high is not None
    return CompareMetricInterval(
        value=round(mean, 6),
        ci_low=low,
        ci_high=high,
        sample_size=n,
        sufficient=sufficient,
        limitation=(
            f"n={n} below minimum sample {MIN_SAMPLE}."
            if n < MIN_SAMPLE
            else "Anytime-valid interval for the cell mean; not a causal effect."
        ),
    )


def _cost_per_success(success_costs: list[float], sessions: int) -> CompareMetricInterval:
    successes = len(success_costs)
    if successes == 0:
        return CompareMetricInterval(
            value=None,
            ci_low=None,
            ci_high=None,
            sample_size=sessions,
            sufficient=False,
            limitation="No verified or labeled successes in this cell.",
        )
    # Cost per success is total cost on success sessions / successes (mean of success costs).
    return _interval(success_costs, kind="mean")


def _pairwise(
    cells: list[CompareCell],
    groups: dict[tuple[str, str], dict[str, Any]],
) -> list[ComparePairwise]:
    by_bucket: dict[str, list[CompareCell]] = defaultdict(list)
    for cell in cells:
        by_bucket[cell.difficulty_bucket].append(cell)
    pairs: list[ComparePairwise] = []
    for bucket, bucket_cells in sorted(by_bucket.items(), key=lambda item: _bucket_rank(item[0])):
        ordered = sorted(bucket_cells, key=lambda cell: cell.agent_id)
        for index, left in enumerate(ordered):
            for right in ordered[index + 1 :]:
                metric_a = left.cost_per_session
                metric_b = right.cost_per_session
                sample_a = metric_a.sample_size
                sample_b = metric_b.sample_size
                warnings = _pair_confounds(
                    groups.get((left.agent_id, bucket), {}),
                    groups.get((right.agent_id, bucket), {}),
                )
                if (
                    metric_a.value is None
                    or metric_b.value is None
                    or sample_a < MIN_SAMPLE
                    or sample_b < MIN_SAMPLE
                    or metric_a.ci_low is None
                    or metric_a.ci_high is None
                    or metric_b.ci_low is None
                    or metric_b.ci_high is None
                ):
                    pairs.append(
                        ComparePairwise(
                            agent_a=left.agent_id,
                            agent_b=right.agent_id,
                            difficulty_bucket=bucket,
                            metric=_PAIR_METRIC,
                            delta=None,
                            ci_low=None,
                            ci_high=None,
                            verdict="insufficient",
                            sample_a=sample_a,
                            sample_b=sample_b,
                            confound_warnings=warnings,
                            limitation=(
                                f"Need n≥{MIN_SAMPLE} on both sides before pairwise ranking."
                            ),
                        )
                    )
                    continue
                delta = round(float(metric_a.value) - float(metric_b.value), 6)
                # Conservative overlap of independent anytime intervals.
                ci_low = round(float(metric_a.ci_low) - float(metric_b.ci_high), 6)
                ci_high = round(float(metric_a.ci_high) - float(metric_b.ci_low), 6)
                if warnings:
                    verdict = "inconclusive"
                elif ci_high < 0:
                    verdict = "a_better"
                elif ci_low > 0:
                    verdict = "b_better"
                else:
                    verdict = "inconclusive"
                pairs.append(
                    ComparePairwise(
                        agent_a=left.agent_id,
                        agent_b=right.agent_id,
                        difficulty_bucket=bucket,
                        metric=_PAIR_METRIC,
                        delta=delta,
                        ci_low=ci_low,
                        ci_high=ci_high,
                        verdict=verdict,
                        sample_a=sample_a,
                        sample_b=sample_b,
                        confound_warnings=warnings,
                        limitation=(
                            "Pairwise cost-per-session delta uses overlapping anytime intervals; "
                            "negative delta favors agent_a on spend."
                        ),
                    )
                )
    return pairs


def _pair_confounds(left: dict[str, Any], right: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    left_models = set(left.get("models") or ())
    right_models = set(right.get("models") or ())
    if left_models and right_models and left_models != right_models:
        warnings.append("model mix differs between agents")
    left_sources = set(left.get("sources") or ())
    right_sources = set(right.get("sources") or ())
    if left_sources and right_sources and left_sources != right_sources:
        warnings.append("adapter/source mix differs between agents")
    return warnings


def _global_confounds(cells: list[CompareCell]) -> list[str]:
    warnings: list[str] = []
    by_bucket: dict[str, list[CompareCell]] = defaultdict(list)
    for cell in cells:
        by_bucket[cell.difficulty_bucket].append(cell)
    multi_model_buckets = 0
    multi_source_buckets = 0
    for bucket_cells in by_bucket.values():
        models = {model for cell in bucket_cells for model in cell.models}
        sources = {source for cell in bucket_cells for source in cell.sources}
        if len(models) > 1:
            multi_model_buckets += 1
        if len(sources) > 1:
            multi_source_buckets += 1
    if multi_model_buckets:
        warnings.append(
            f"{multi_model_buckets} difficulty bucket(s) mix multiple models across agents."
        )
    if multi_source_buckets:
        warnings.append(
            f"{multi_source_buckets} difficulty bucket(s) mix multiple adapters/sources."
        )
    return warnings


def _compare_ledger(
    cells: list[CompareCell],
    confound_warnings: list[str],
) -> CompareLedgerSummary:
    buckets = {cell.difficulty_bucket for cell in cells}
    sufficient = [cell for cell in cells if cell.sessions >= MIN_SAMPLE]
    declared_winner: str | None = None
    if not confound_warnings:
        # Prefer a shared hard/epic/standard bucket with large samples and clear cost separation.
        by_bucket: dict[str, list[CompareCell]] = defaultdict(list)
        for cell in cells:
            by_bucket[cell.difficulty_bucket].append(cell)
        for bucket in ("hard", "epic", "standard", "trivial"):
            bucket_cells = [
                cell for cell in by_bucket.get(bucket, []) if cell.sessions >= WINNER_SAMPLE
            ]
            if len(bucket_cells) < 2:
                continue
            ranked = sorted(
                bucket_cells,
                key=lambda cell: (
                    float("inf")
                    if cell.cost_per_session.value is None
                    else float(cell.cost_per_session.value)
                ),
            )
            best = ranked[0]
            second = ranked[1]
            if (
                best.cost_per_session.ci_high is not None
                and second.cost_per_session.ci_low is not None
                and float(best.cost_per_session.ci_high) < float(second.cost_per_session.ci_low)
            ):
                declared_winner = best.agent_id
                break

    if not cells:
        conclusion = "No sessions in range to compare across agents and difficulty."
        next_action = "Sync sessions, then reopen Compare"
        next_action_href = "/sessions"
    elif declared_winner:
        conclusion = (
            f"{declared_winner} shows the lowest cost/session with non-overlapping intervals "
            f"in a difficulty bucket with n≥{WINNER_SAMPLE}."
        )
        next_action = "Inspect that agent's sessions for task mix"
        next_action_href = f"/sessions?q=agent:{declared_winner}"
    elif sufficient:
        conclusion = (
            f"{len(sufficient)} agent×difficulty cell(s) meet n≥{MIN_SAMPLE}; "
            "no overall winner clears confounds and interval separation."
        )
        next_action = "Review pairwise cells or open Session Diff for matched pairs"
        next_action_href = "/sessions"
    else:
        conclusion = (
            f"Every agent×difficulty cell is below n≥{MIN_SAMPLE}; "
            "Cairn will not declare a performance winner."
        )
        next_action = "Accumulate more sessions in the same difficulty buckets"
        next_action_href = "/sessions"

    limitation = (
        "Difficulty-aware comparisons are descriptive. Model, adapter, time, and task mix can "
        "confound rankings; insufficient samples never produce a leaderboard winner."
    )
    return CompareLedgerSummary(
        conclusion=conclusion,
        buckets_with_evidence=len(buckets),
        cells_total=len(cells),
        cells_sufficient=len(sufficient),
        min_sample=MIN_SAMPLE,
        declared_winner=declared_winner,
        next_action=next_action,
        next_action_href=next_action_href,
        limitation=limitation,
    )
