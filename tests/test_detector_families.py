"""ADR-04 family aggregators and multi-model honesty gates."""

from __future__ import annotations

from server.improve.detectors._types import validate_insight_contract
from server.improve.detectors.families import (
    FAMILY_ALIAS_IDS,
    consolidate_family_insights,
)
from server.improve.detectors.multi_model_spread import rule_multi_model_cost_spread


def test_retry_storm_merges_alias_producers() -> None:
    ctx = {
        "days": 14,
        "retry_loop_events": 8,
        "identical_call_tokens": 20_000,
        "identical_call_events": 5,
        "has_cost_sessions": 1,
        "total_tokens": 100_000,
        "total_cost": 10.0,
        "max_error_streak": 4,
        "failing_commands": [{"name": "pytest", "failures": 3}],
        "retry_storm_attempts": 6,
        "retry_storm_cost_usd": 1.5,
        "retry_storm_span_ids": ["span-a", "span-b"],
    }
    families = consolidate_family_insights(ctx)
    retry = next(item for item in families if item.family == "retry_storm")
    validate_insight_contract(retry)
    assert retry.id == "retry-storm"
    assert set(retry.alias_ids) <= set(FAMILY_ALIAS_IDS)
    assert len(retry.alias_ids) >= 2
    assert retry.span_ids
    assert retry.estimate_kind == "conservative"
    assert retry.savings_estimate is not None


def test_model_mismatch_gates_cheaper_model_advice() -> None:
    ctx = {
        "model_costs_30d": {"small": 1.0, "medium": 2.0, "large": 4.0},
        "model_comparable_samples": 2,
    }
    producer = rule_multi_model_cost_spread(ctx)
    assert producer is not None
    assert producer.fix is not None
    assert producer.fix.kind == "manual"
    assert "cheaper" not in producer.fix.value.lower() or "alone" in producer.fix.value.lower()

    families = consolidate_family_insights(ctx)
    model = next(item for item in families if item.family == "model_mismatch")
    validate_insight_contract(model)
    assert model.diagnostic is True
    assert model.fix is not None
    assert model.fix.kind == "manual"
    assert model.savings_estimate is None


def test_stale_schema_and_context_thrash_families() -> None:
    ctx = {
        "days": 14,
        "unused_tools": [
            {"tool": "browser", "total_turns": 10, "tokens_per_turn": 80, "sessions": 4}
        ],
        "unused_tools_coverage": "fixture",
        "tool_schema_tokens": 5_000,
        "read_rereads": [{"path": "a.py", "content_hash": "h", "reads": 4}],
        "rebilling_tokens_14d": 60_000,
        "rebilling_cost_14d": 0.4,
        "has_cost_sessions": 1,
        "total_cost": 5.0,
        "stale_tool_result_events": 4,
        "stale_tool_result_tokens": 900,
        "context_thrash_file_costs": [
            {"path": "a.py", "waste_tokens": 100, "events": 3, "span_id": "s1"}
        ],
    }
    families = consolidate_family_insights(ctx)
    by_family = {item.family: item for item in families}
    assert "stale_tool_schema" in by_family
    assert "context_thrash" in by_family
    validate_insight_contract(by_family["stale_tool_schema"])
    validate_insight_contract(by_family["context_thrash"])
    assert by_family["stale_tool_schema"].alias_ids == ["unused-tools"]
