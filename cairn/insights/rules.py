"""Deterministic insight rules with conservative savings estimates."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Insight:
    id: str
    severity: str  # info | suggestion | warning | error
    title: str
    body: str
    evidence: dict[str, Any] = field(default_factory=dict)
    savings_estimate: float | None = None
    action: str | None = None
    difficulty_aware: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "severity": self.severity,
            "title": self.title,
            "body": self.body,
            "evidence": self.evidence,
            "savings_estimate": self.savings_estimate,
            "action": self.action,
            "difficulty_aware": self.difficulty_aware,
            "tier": "2.0" if self.difficulty_aware else "legacy",
        }


def _weekly_spend(total_cost: float, *, days: int) -> float:
    """Project ``total_cost`` accrued over ``days`` to a 7-day spend."""
    return float(total_cost) * (7.0 / max(1, days))


def _cap_savings(raw: float, weekly_spend: float, *, max_fraction: float = 0.5) -> float:
    return round(min(raw, weekly_spend * max_fraction), 2)


def _data_note(note: str) -> dict[str, Any]:
    return {"data_notes": [note]}


# ---------------------------------------------------------------------------
# 1. CONTEXT_WINDOW_PRESSURE
# ---------------------------------------------------------------------------


def rule_context_window_pressure(ctx: dict[str, Any]) -> Insight | None:
    sessions = ctx.get("high_context_sessions", [])
    if not sessions:
        return None
    top = max(sessions, key=lambda s: s["peak_context_pct"])
    pct = top["peak_context_pct"]
    from cairn.metrics.waste import context_rot_warning_pct, context_rot_waste_pct

    warn_pct = context_rot_warning_pct()
    severity = "error" if pct > context_rot_waste_pct() else "warning"
    if pct < warn_pct:
        return None
    sid = top["run_id"][:12]
    return Insight(
        id="context-window-pressure",
        severity=severity,
        title="Context window pressure",
        body=(
            f"Session {sid} peaked at {pct:.0f}% of context window — "
            "context rot is setting in; compaction, clearing consumed tool "
            "results, or task splitting would reduce cost."
        ),
        evidence={"run_id": top["run_id"], "peak_context_pct": pct},
        savings_estimate=None,
        action="cairn show last",
    )


# ---------------------------------------------------------------------------
# 2. IDENTICAL_TOOL_CALLS
# ---------------------------------------------------------------------------


def rule_identical_tool_calls(ctx: dict[str, Any]) -> Insight | None:
    waste = int(ctx.get("identical_call_tokens", 0))
    if waste <= 10_000:
        return None
    total_tokens = int(ctx.get("total_tokens", 0))
    total_cost = float(ctx.get("total_cost", 0))
    days = int(ctx.get("days", 14))
    has_cost = ctx.get("has_cost_sessions", 0) > 0
    savings: float | None = None
    evidence: dict[str, Any] = {
        "waste_tokens": waste,
        "events": int(ctx.get("identical_call_events", 0)),
    }
    if has_cost and total_tokens > 0 and total_cost > 0:
        weekly_spend = _weekly_spend(total_cost, days=days)
        raw = (waste / total_tokens) * weekly_spend * 0.5
        savings = _cap_savings(raw, weekly_spend)
    else:
        evidence.update(_data_note("no cost data: savings estimate unavailable (div0 guard)"))
    return Insight(
        id="identical-tool-calls",
        severity="warning",
        title="Duplicate tool calls",
        body=(
            f"{evidence['events']} duplicate tool calls detected in last {days} days. "
            "Agent is repeating reads/searches it already has results for."
        ),
        evidence=evidence,
        savings_estimate=savings,
        action="cairn optimize",
    )


# ---------------------------------------------------------------------------
# 3. OVERSIZE_TOOL_RESULTS
# ---------------------------------------------------------------------------


def rule_oversize_tool_results(ctx: dict[str, Any]) -> Insight | None:
    waste = int(ctx.get("oversize_result_tokens", 0))
    if waste <= 20_000:
        return None
    total_tokens = int(ctx.get("total_tokens", 0))
    total_cost = float(ctx.get("total_cost", 0))
    days = int(ctx.get("days", 14))
    has_cost = ctx.get("has_cost_sessions", 0) > 0
    savings: float | None = None
    evidence: dict[str, Any] = {"waste_tokens": waste}
    if has_cost and total_tokens > 0 and total_cost > 0:
        weekly_spend = _weekly_spend(total_cost, days=days)
        raw = (waste / total_tokens) * weekly_spend * 0.4
        savings = _cap_savings(raw, weekly_spend)
    else:
        evidence.update(_data_note("no cost data: savings estimate unavailable (div0 guard)"))
    return Insight(
        id="oversize-tool-results",
        severity="info",
        title="Oversized tool results",
        body=(
            f"{waste:,} tokens went to oversized tool results. "
            "Use more targeted file reads and narrower grep patterns."
        ),
        evidence=evidence,
        savings_estimate=savings,
        action="cairn optimize",
    )


# ---------------------------------------------------------------------------
# 4. HIGH_FILE_CHURN
# ---------------------------------------------------------------------------


def rule_high_file_churn(ctx: dict[str, Any]) -> Insight | None:
    churn = ctx.get("file_churn", {})
    if not churn:
        return None
    path, count = max(churn.items(), key=lambda kv: kv[1])
    if count <= 5:
        return None
    return Insight(
        id="high-file-churn",
        severity="info",
        title=f"High edit churn: {path}",
        body=(
            f"{path}: {count} edits across sessions. "
            "Consider writing tests before making multiple edit attempts."
        ),
        evidence={"path": path, "edits": count},
        savings_estimate=None,
        action="cairn optimize",
    )


# ---------------------------------------------------------------------------
# 5. RETRY_LOOPS_DETECTED
# ---------------------------------------------------------------------------


def rule_retry_loops_detected(ctx: dict[str, Any]) -> Insight | None:
    count = int(ctx.get("retry_loop_events", 0))
    if count <= 5:
        return None
    return Insight(
        id="retry-loops-detected",
        severity="warning",
        title="Tool retry loops",
        body=(
            f"{count} tool retry loops detected. "
            "Agent is hitting errors and retrying the same tool call."
        ),
        evidence={"events": count},
        savings_estimate=None,
        action="cairn optimize",
    )


# ---------------------------------------------------------------------------
# 6. CACHE_MISUSE (§2.7D cache health)
# ---------------------------------------------------------------------------


def rule_cache_misuse(ctx: dict[str, Any]) -> Insight | None:
    cache = ctx.get("cache_stats_7d")
    if not cache:
        return None
    cache_read = int(cache.get("cache_read", 0))
    cache_creation = int(cache.get("cache_creation", 0))
    spike_count = int(cache.get("spike_count", 0))
    daily = cache.get("daily", []) or []
    if cache_creation <= 0 and spike_count <= 0:
        return None

    denom = cache_read + cache_creation
    hit_rate = cache_read / denom if denom > 0 else None

    writes_no_reads = cache_creation > 0 and cache_read == 0
    low_hit = hit_rate is not None and hit_rate < 0.70
    # Prefix mismatch: hit rate <80% sustained over a full day.
    prefix_mismatch_days = [
        d
        for d in daily
        if d.get("hit_rate") is not None
        and float(d["hit_rate"]) < 0.80
        and (int(d.get("cache_creation", 0)) + int(d.get("cache_read", 0))) > 0
    ]
    prefix_mismatch = bool(prefix_mismatch_days)
    cache_thrash = spike_count > 0

    if not (writes_no_reads or low_hit or prefix_mismatch or cache_thrash):
        return None

    parts: list[str] = []
    if writes_no_reads:
        parts.append("Prompt caching is writing but not reading — add cache_control breakpoints.")
    if low_hit and hit_rate is not None:
        parts.append(f"Cache hit rate {hit_rate * 100:.0f}% is below 70%.")
    if prefix_mismatch:
        parts.append(
            "Cache prefix mismatch — likely a tool-schema or system-prompt change "
            "broke the prefix (hit rate <80% sustained over a day)."
        )
    if cache_thrash:
        parts.append(
            f"{spike_count} cache-creation spike(s) — >50% of a turn's input went to "
            "cache writes (cache thrash)."
        )

    evidence: dict[str, Any] = {
        "cache_read": cache_read,
        "cache_creation": cache_creation,
        "hit_rate": round(hit_rate, 4) if hit_rate is not None else None,
        "spike_count": spike_count,
        "prefix_mismatch_days": len(prefix_mismatch_days),
        "daily": daily,
    }
    return Insight(
        id="cache-misuse",
        severity="info",
        title="Prompt cache misuse",
        body=" ".join(parts),
        evidence=evidence,
        savings_estimate=None,
        action=None,
    )


# ---------------------------------------------------------------------------
# 7. MULTI_MODEL_COST_SPREAD
# ---------------------------------------------------------------------------


def rule_multi_model_cost_spread(ctx: dict[str, Any]) -> Insight | None:
    models = ctx.get("model_costs_30d", {})
    if len(models) <= 2:
        return None
    if not all(v > 0 for v in models.values()):
        return None
    sorted_models = sorted(models.items(), key=lambda kv: kv[1])
    cheap_name, cheap_cost = sorted_models[0]
    expensive_name, expensive_cost = sorted_models[-1]
    if cheap_cost <= 0:
        return None
    ratio = expensive_cost / cheap_cost
    names = ", ".join(m for m, _ in sorted(models.items(), key=lambda kv: -kv[1]))
    return Insight(
        id="multi-model-cost-spread",
        severity="info",
        title="Multiple models in use",
        body=(
            f"Using {len(models)} models: {names}. "
            f"{expensive_name} sessions cost {ratio:.1f}x more than {cheap_name} for similar work."
        ),
        evidence={"models": models, "ratio": ratio},
        savings_estimate=None,
        action=None,
    )


# ---------------------------------------------------------------------------
# 8. RUNAWAY_SESSIONS
# ---------------------------------------------------------------------------


def rule_runaway_sessions(ctx: dict[str, Any]) -> Insight | None:
    runaways = ctx.get("runaway_sessions", []) or []
    if not runaways:
        return None
    top = max(runaways, key=lambda r: r["ratio"])
    return Insight(
        id="runaway-sessions",
        severity="warning",
        title="Runaway sessions",
        body=(
            f"{len(runaways)} session(s) exceeded difficulty-adjusted expectations "
            f"(worst: {top['ratio']:.1f}x per-turn growth in {top['run_id'][:12]}). "
            "Context is growing unbounded — split tasks or compact sooner."
        ),
        evidence={"count": len(runaways), "worst_ratio": top["ratio"], "run_id": top["run_id"]},
        savings_estimate=None,
        action="cairn show last",
        difficulty_aware=True,
    )


# ---------------------------------------------------------------------------
# 9. REBILLING_WASTE (NEW — from cairn/profile)
# ---------------------------------------------------------------------------


def rule_rebilling_waste(ctx: dict[str, Any]) -> Insight | None:
    rebilled = int(ctx.get("rebilling_tokens_14d", 0))
    if rebilled <= 50_000:
        return None
    days = int(ctx.get("days", 14))
    total_cost = float(ctx.get("total_cost", 0))
    has_cost = ctx.get("has_cost_sessions", 0) > 0
    rebilling_cost = float(ctx.get("rebilling_cost_14d", 0.0) or 0.0)
    savings: float | None = None
    evidence: dict[str, Any] = {
        "rebilled_tokens": rebilled,
        "rebilled_cost_usd": rebilling_cost or None,
    }
    if has_cost and total_cost > 0 and rebilling_cost > 0:
        weekly_spend = _weekly_spend(total_cost, days=days)
        raw = rebilling_cost * (7.0 / days) * 0.6
        savings = _cap_savings(raw, weekly_spend)
    else:
        evidence.update(
            _data_note("no input price for re-billed tokens: savings null (div0 guard)")
        )
    return Insight(
        id="rebilling-waste",
        severity="info",
        title="Re-billed stale context tokens",
        body=(
            f"{rebilled:,} stale tool-result tokens were re-billed across sessions in the last "
            f"{days} days. Clearing consumed tool results from the window stops the re-billing."
        ),
        evidence=evidence,
        savings_estimate=savings,
        action="cairn profile",
        difficulty_aware=True,
    )


# ---------------------------------------------------------------------------
# 10. BEHAVIORAL_DRIFT (NEW — from cairn/metrics/fingerprint)
# ---------------------------------------------------------------------------


def rule_behavioral_drift(ctx: dict[str, Any]) -> Insight | None:
    drift = ctx.get("behavioral_drift")
    if not drift or not drift.get("drift"):
        return None
    kind = str(drift.get("kind", "joint_shock"))
    top_dims = drift.get("top_dims", []) or []
    dim_text = ", ".join(f"{d['axis']}={d['delta']:+.2f}" for d in top_dims[:5]) or "n/a"
    evidence: dict[str, Any] = {
        "kind": kind,
        "project": drift.get("project"),
        "model": drift.get("model"),
        "d_squared": drift.get("d_squared"),
        "threshold": drift.get("threshold"),
        "top_dims": top_dims,
    }
    return Insight(
        id="behavioral-drift",
        severity="warning",
        title="Behavioral drift detected",
        body=(
            f"Your agent's behavior changed this week ({kind}). Top dimension deltas: {dim_text}."
        ),
        evidence=evidence,
        savings_estimate=None,
        action="cairn behavior",
        difficulty_aware=True,
    )


# ---------------------------------------------------------------------------
# 11. QUALITY_REGRESSION (NEW — from cairn/outcomes)
# ---------------------------------------------------------------------------


def rule_quality_regression(ctx: dict[str, Any]) -> Insight | None:
    q = ctx.get("quality_regression")
    if not q or not q.get("regressed"):
        return None
    recent = q.get("recent_mean")
    prior = q.get("prior_mean")
    drop = q.get("drop_pct")
    evidence: dict[str, Any] = {
        "recent_mean": recent,
        "prior_mean": prior,
        "drop_pct": drop,
        "recent_n": q.get("recent_n"),
        "prior_n": q.get("prior_n"),
    }
    body = f"Agent Quality Score dropped {drop:.0f}% week-over-week ({prior:.1f} → {recent:.1f})."
    return Insight(
        id="quality-regression",
        severity="warning",
        title="Quality regression",
        body=body,
        evidence=evidence,
        savings_estimate=None,
        action="cairn outcomes",
        difficulty_aware=True,
    )


# ---------------------------------------------------------------------------
# 12. UNUSED_TOOLS (NEW — from cairn/profile/detectors UNUSED_TOOL_SCHEMA)
# ---------------------------------------------------------------------------


def rule_unused_tools(ctx: dict[str, Any]) -> Insight | None:
    tools = ctx.get("unused_tools", []) or []
    if not tools:
        return None
    tool = max(tools, key=lambda t: int(t.get("total_turns", 0)))
    name = tool["tool"]
    turns_per_week = int(tool.get("total_turns", 0)) // max(1, 2)  # 14d → 7d
    tokens_per_turn = int(tool.get("tokens_per_turn", 60))
    return Insight(
        id="unused-tools",
        severity="info",
        title=f"Unused MCP tool: {name}",
        body=(
            f"Remove `{name}` — ~{tokens_per_turn} tokens/turn × {turns_per_week} turns/wk "
            f"of schema overhead across {tool.get('sessions', 0)} session(s)."
        ),
        evidence=tool,
        savings_estimate=None,
        action="cairn optimize",
        difficulty_aware=True,
    )


# ---------------------------------------------------------------------------
# 13. SUBAGENT_HEAVY
# ---------------------------------------------------------------------------

# Subagent/sidechain lanes above this share of run tokens trigger the insight.
SUBAGENT_HEAVY_THRESHOLD = 0.60


def rule_subagent_heavy(ctx: dict[str, Any]) -> Insight | None:
    hit = ctx.get("subagent_heavy")
    if not hit:
        return None
    share_pct = float(hit.get("share_pct", 0))
    run_id = str(hit.get("run_id", ""))
    sid = run_id[:12] if run_id else "session"
    return Insight(
        id="subagent-heavy",
        severity="warning",
        title="Subagent-heavy session",
        body=(
            f"Subagents consumed {share_pct:.0f}% of tokens in session {sid} "
            f"without a success outcome — review delegation before retrying."
        ),
        evidence={
            "run_id": run_id,
            "share_pct": share_pct,
            "subagent_tokens": hit.get("subagent_tokens"),
        },
        savings_estimate=None,
        action=f"cairn show {sid}",
    )


# ---------------------------------------------------------------------------


ALL_RULES = (
    rule_context_window_pressure,
    rule_identical_tool_calls,
    rule_oversize_tool_results,
    rule_high_file_churn,
    rule_retry_loops_detected,
    rule_cache_misuse,
    rule_multi_model_cost_spread,
    rule_runaway_sessions,
    rule_rebilling_waste,
    rule_behavioral_drift,
    rule_quality_regression,
    rule_unused_tools,
    rule_subagent_heavy,
)
