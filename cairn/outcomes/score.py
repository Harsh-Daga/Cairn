"""Pillar 3 — Agent Quality Score + AgentLens process scoring (Part 11 + §2.7B)."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

# Agent Quality Score weights (configurable via ``weights`` override).
DEFAULT_WEIGHTS = {
    "success": 0.40,
    "efficiency": 0.25,
    "context_efficiency": 0.15,
    "stability": 0.10,
    "fingerprint_stability": 0.10,
}

# AgentLens process-quality weights (behavioral 65% blend baseline).
AGENTLENS_WEIGHTS = {
    "structural": 0.20,
    "coverage": 0.15,
    "coherence": 0.30,
    "temporal": 0.35,
}

TIER_IDEAL = 70
TIER_LUCKY = 47

_EXPLORE = frozenset({"read", "search"})
_IMPLEMENT = frozenset({"edit", "delete", "bash"})
_ORCHESTRATE = frozenset({"sub_agent"})


@dataclass
class ProcessScore:
    score: float  # 0..100
    tier: str  # "Ideal" | "Solid" | "Lucky"
    structural: float
    coverage: float
    coherence: float
    temporal: float
    intent_stages: dict[str, int]
    signals: dict[str, int] = field(default_factory=dict)


@dataclass
class QualityScore:
    score: float  # 0..100
    components: dict[str, float] = field(default_factory=dict)
    weights: dict[str, float] = field(default_factory=dict)


def agent_quality_score(
    *,
    commit_landed: bool,
    tests_passed: int | None,
    tests_failed: int | None,
    build_status: str | None,
    waste_tokens: int,
    total_tokens: int,
    peak_context_pct: float | None,
    context_rot_penalty: float,
    retry_rate: float,
    error_rate: float,
    mahalanobis_distance: float | None,
    drift_threshold: float | None,
    weights: dict[str, float] | None = None,
) -> QualityScore:
    """Composite outcome score 0..100."""
    w = {**DEFAULT_WEIGHTS, **(weights or {})}

    tests_unknown = (
        tests_passed is None and tests_failed is None and build_status in (None, "unknown")
    )
    success = (
        1.0
        if (commit_landed and (tests_unknown or (tests_passed or 0) > (tests_failed or 0)))
        else 0.0
    )

    efficiency = 1.0 - _clamp01(waste_tokens / max(1, total_tokens)) if total_tokens > 0 else 0.0

    if peak_context_pct is not None:
        context_efficiency = 1.0 - _clamp01((peak_context_pct / 100.0) * context_rot_penalty)
    else:
        context_efficiency = 0.0

    stability = 1.0 - _clamp01(retry_rate + error_rate)

    if mahalanobis_distance is not None and drift_threshold:
        fingerprint_stability = 1.0 - _clamp01(mahalanobis_distance / drift_threshold)
    else:
        fingerprint_stability = 0.0

    components = {
        "success": success,
        "efficiency": efficiency,
        "context_efficiency": context_efficiency,
        "stability": stability,
        "fingerprint_stability": fingerprint_stability,
    }
    total = sum(w[k] * components[k] for k in w)
    return QualityScore(score=round(total * 100, 2), components=components, weights=w)


# ---------------------------------------------------------------------------
# AgentLens process scoring
# ---------------------------------------------------------------------------


def label_intent_stages(events: list[dict[str, Any]]) -> list[tuple[int, str]]:
    """Label each tool_call seq with Exploration/Implementation/Verification/Orchestration.

    A ``read``/``search`` before any edit in the session is Exploration; after
    the first edit it is Verification (checking the change). Edits/deletes/bash
    are Implementation. ``sub_agent`` is Orchestration.
    """
    labels: list[tuple[int, str]] = []
    seen_edit = False
    for e in events:
        if e.get("type") != "tool_call":
            continue
        norm = str(e.get("tool_norm_name") or "")
        seq = int(e.get("seq", 0))
        if norm in _ORCHESTRATE:
            stage = "Orchestration"
        elif norm in _IMPLEMENT:
            stage = "Implementation"
            if norm in ("edit", "delete"):
                seen_edit = True
        elif norm in _EXPLORE:
            stage = "Verification" if seen_edit else "Exploration"
        else:
            stage = "Implementation" if seen_edit else "Exploration"
        labels.append((seq, stage))
    return labels


def process_quality_score(events: list[dict[str, Any]]) -> ProcessScore:
    """AgentLens behavioral process score 0..100 + tier."""
    labels = label_intent_stages(events)
    stage_seq = [s for _, s in labels]
    stage_counts = Counter(stage_seq)
    distinct_stages = len(stage_counts)

    # structural: coverage of the 4 intent stages.
    structural = distinct_stages / 4.0

    # coverage: fraction of edited files that were read before editing.
    coverage = _coverage(events)

    # coherence: penalize backtracks, blind retries, redundant steps, cycles.
    signals = _process_signals(events, labels)
    penalty = (
        signals["backtrack"]
        + signals["blind_retry"]
        + signals["redundant_step"]
        + signals["cyclic"]
    )
    coherence = 1.0 - _clamp01(penalty / max(10, len(labels)))

    # temporal: reward forward stage transitions (E→I, I→V, E→V), penalize backward.
    temporal = _temporal_score(stage_seq)

    weights = AGENTLENS_WEIGHTS
    score = (
        weights["structural"] * structural
        + weights["coverage"] * coverage
        + weights["coherence"] * coherence
        + weights["temporal"] * temporal
    ) * 100.0
    score = round(_clamp01(score / 100.0) * 100, 2)
    tier = _tier(score)
    return ProcessScore(
        score=score,
        tier=tier,
        structural=round(structural, 3),
        coverage=round(coverage, 3),
        coherence=round(coherence, 3),
        temporal=round(temporal, 3),
        intent_stages=dict(stage_counts),
        signals=signals,
    )


def _tier(score: float) -> str:
    if score >= TIER_IDEAL:
        return "Ideal"
    if score >= TIER_LUCKY:
        return "Solid"
    return "Lucky"


def is_lucky_pass(process: ProcessScore, commit_landed: bool) -> bool:
    """A session that lands a commit but scores Lucky → brittle pass."""
    return bool(commit_landed and process.tier == "Lucky")


def _coverage(events: list[dict[str, Any]]) -> float:
    """Fraction of edited files that were read *before their first edit*."""
    first_edit_seq: dict[str, int] = {}
    first_read_seq: dict[str, int] = {}
    edited_files: set[str] = set()
    for e in events:
        path = e.get("path_rel")
        if not path:
            continue
        seq = int(e.get("seq", 0))
        norm = e.get("tool_norm_name")
        if e.get("type") == "tool_call" and norm in _EXPLORE:
            first_read_seq.setdefault(str(path), seq)
        elif e.get("type") == "tool_call" and norm in ("edit", "delete"):
            edited_files.add(str(path))
            first_edit_seq.setdefault(str(path), seq)
    if not edited_files:
        return 0.0
    read_first = sum(
        1
        for f in edited_files
        if f in first_read_seq and f in first_edit_seq and first_read_seq[f] < first_edit_seq[f]
    )
    return read_first / len(edited_files)


def _temporal_score(stage_seq: list[str]) -> float:
    if len(stage_seq) < 2:
        return 0.0
    rank = {"Exploration": 0, "Implementation": 1, "Verification": 2, "Orchestration": 1}
    forward = backward = 0
    for a, b in zip(stage_seq, stage_seq[1:], strict=False):
        if a == b:
            continue
        if rank.get(b, 1) >= rank.get(a, 1):
            forward += 1
        else:
            backward += 1
    total = forward + backward
    if total == 0:
        return 0.0
    return forward / total


def _process_signals(events: list[dict[str, Any]], labels: list[tuple[int, str]]) -> dict[str, int]:
    """Backtrack / blind-retry / redundant-step / cyclic-pattern counts."""
    # blind_retry + redundant_step from waste tags (structural, no cost).
    from cairn.metrics.waste import compute_waste

    waste = compute_waste(events, has_cost=False, peak_context_pct=None)
    blind_retry = sum(1 for _, cat, _ in waste.tags if cat == "blind_retry")
    redundant_step = sum(
        1 for _, cat, _ in waste.tags if cat in ("identical_call", "stale_context")
    )

    # backtrack: edit a file, then read it again, then edit it again.
    backtrack = 0
    last_edit: dict[str, int] = {}
    last_read_after_edit: set[str] = set()
    for e in events:
        path = e.get("path_rel")
        if not path:
            continue
        norm = e.get("tool_norm_name")
        seq = int(e.get("seq", 0))
        if e.get("type") == "tool_call" and norm in ("edit", "delete"):
            if str(path) in last_read_after_edit:
                backtrack += 1
                last_read_after_edit.discard(str(path))
            last_edit[str(path)] = seq
        elif e.get("type") == "tool_call" and norm in _EXPLORE:
            if str(path) in last_edit:
                last_read_after_edit.add(str(path))

    # cyclic: repeated 2-grams of tool_norm_name.
    norms = [str(e.get("tool_norm_name") or "") for e in events if e.get("type") == "tool_call"]
    two_grams = [tuple(norms[i : i + 2]) for i in range(len(norms) - 1)]
    counts = Counter(two_grams)
    cyclic = sum(1 for g, c in counts.items() if c >= 3 and all(g))

    return {
        "backtrack": backtrack,
        "blind_retry": blind_retry,
        "redundant_step": redundant_step,
        "cyclic": cyclic,
    }


# ---------------------------------------------------------------------------
# cost_per_success (cohort)
# ---------------------------------------------------------------------------


def cost_per_success(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate cost-per-success using non-Lucky successes only.

    Each row: ``{"total_cost": float, "commit_landed": bool, "lucky_pass": bool}``.
    Returns ``{"cost_per_success": float|null, "non_lucky_successes": int,
    "total_cost": float, "variance": float|null, "data_notes": [...]}``.
    """
    successes = [
        r
        for r in rows
        if r.get("commit_landed")
        and not r.get("lucky_pass")
        and isinstance(r.get("total_cost"), (int, float))
    ]
    if not successes:
        return {
            "cost_per_success": None,
            "non_lucky_successes": 0,
            "total_cost": 0.0,
            "variance": None,
            "data_notes": ["no non-Lucky successes: cost_per_success is null (div0 guard)"],
        }
    costs = [float(r["total_cost"]) for r in successes]
    total = sum(costs)
    cps = total / len(costs)
    variance = sum((c - cps) ** 2 for c in costs) / len(costs) if len(costs) > 1 else 0.0
    return {
        "cost_per_success": round(cps, 6),
        "non_lucky_successes": len(costs),
        "total_cost": round(total, 6),
        "variance": round(variance, 6),
        "data_notes": [],
    }


def _clamp01(x: float) -> float:
    if math.isnan(x):
        return 0.0
    return max(0.0, min(1.0, float(x)))
