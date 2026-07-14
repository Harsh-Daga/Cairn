"""Regression coverage for detector rules registered in the insight engine."""

from __future__ import annotations

import pytest

from server.improve.detectors._types import validate_insight_contract
from server.improve.detectors.behavioral_drift import rule_behavioral_drift
from server.improve.detectors.cache_misuse import rule_cache_misuse
from server.improve.detectors.context_pressure import rule_context_window_pressure
from server.improve.detectors.cost_anomaly import rule_cost_anomaly
from server.improve.detectors.error_streak import rule_error_streak
from server.improve.detectors.failing_command import rule_failing_command
from server.improve.detectors.high_file_churn import rule_high_file_churn
from server.improve.detectors.identical_calls import rule_identical_tool_calls
from server.improve.detectors.multi_model_spread import rule_multi_model_cost_spread
from server.improve.detectors.oversize_results import rule_oversize_tool_results
from server.improve.detectors.quality_regression import rule_quality_regression
from server.improve.detectors.rebilling_waste import rule_rebilling_waste
from server.improve.detectors.registry import detect_live_stop_pattern
from server.improve.detectors.reread_hotspot import rule_reread_hotspot
from server.improve.detectors.retry_loops import rule_retry_loops_detected
from server.improve.detectors.runaway_sessions import rule_runaway_sessions
from server.improve.detectors.stale_tool_results import rule_stale_tool_results
from server.improve.detectors.subagent_heavy import rule_subagent_heavy
from server.improve.detectors.unused_tools import rule_unused_tools


@pytest.mark.parametrize(
    ("rule", "context", "expected_id"),
    [
        (
            rule_behavioral_drift,
            {"behavioral_drift": {"drift": True, "top_dims": [{"axis": "tools", "delta": 1.2}]}},
            "behavioral-drift",
        ),
        (rule_cache_misuse, {"cache_stats_7d": {"cache_creation": 10}}, "cache-misuse"),
        (
            rule_context_window_pressure,
            {"high_context_sessions": [{"peak_context_pct": 90, "run_id": "run-1"}]},
            "context-window-pressure",
        ),
        (
            rule_cost_anomaly,
            {"cost_anomalies": [{"trace_id": "t1", "cost": 10, "threshold": 5}]},
            "cost-anomaly",
        ),
        (rule_error_streak, {"max_error_streak": 4}, "error-streak"),
        (
            rule_failing_command,
            {"failing_commands": [{"name": "pytest", "failures": 3}]},
            "failing-command",
        ),
        (rule_high_file_churn, {"file_churn": {"server/app.py": 6}}, "high-file-churn"),
        (
            rule_identical_tool_calls,
            {"identical_call_tokens": 10_001, "identical_call_events": 3},
            "identical-tool-calls",
        ),
        (
            rule_multi_model_cost_spread,
            {"model_costs_30d": {"small": 1.0, "medium": 2.0, "large": 4.0}},
            "multi-model-cost-spread",
        ),
        (
            rule_oversize_tool_results,
            {"oversize_result_tokens": 20_001, "has_cost_sessions": 0},
            "oversize-tool-results",
        ),
        (
            rule_quality_regression,
            {
                "quality_regression": {
                    "regressed": True,
                    "recent_mean": 70.0,
                    "prior_mean": 90.0,
                    "drop_pct": 22.0,
                }
            },
            "quality-regression",
        ),
        (
            rule_rebilling_waste,
            {"rebilling_tokens_14d": 50_001, "days": 0, "has_cost_sessions": 0},
            "rebilling-waste",
        ),
        (rule_retry_loops_detected, {"retry_loop_events": 6}, "retry-loops-detected"),
        (
            rule_reread_hotspot,
            {"read_rereads": [{"path": "a.py", "reads": 3, "content_hash": "h"}]},
            "reread-hotspot",
        ),
        (
            rule_runaway_sessions,
            {"runaway_sessions": [{"ratio": 2.0, "run_id": "run-123456789"}]},
            "runaway-sessions",
        ),
        (
            rule_subagent_heavy,
            {"subagent_heavy": {"share_pct": 70.0, "run_id": "run-123", "subagent_tokens": 10}},
            "subagent-heavy",
        ),
        (
            rule_stale_tool_results,
            {"stale_tool_result_events": 3, "stale_tool_result_tokens": 100},
            "stale-tool-results",
        ),
        (
            rule_unused_tools,
            {"unused_tools": [{"tool": "browser", "total_turns": 10, "tokens_per_turn": 80}]},
            "unused-tools",
        ),
    ],
)
def test_detector_emits_expected_insight(
    rule: object, context: dict[str, object], expected_id: str
) -> None:
    result = rule(context)  # type: ignore[operator]
    assert result is not None
    assert result.id == expected_id
    validate_insight_contract(result)
    assert result.fix is not None
    assert result.savings_estimate is not None or result.savings_unavailable_reason


@pytest.mark.parametrize(
    ("spans", "pattern", "count", "first_seq"),
    [
        (
            [
                {"seq": 1, "kind": "tool_call", "name": "read", "status": "ok", "args_hash": "x"},
                {"seq": 2, "kind": "tool_call", "name": "read", "status": "ok", "args_hash": "x"},
            ],
            "identical_calls",
            2,
            1,
        ),
        (
            [
                {"seq": 1, "kind": "tool_call", "name": "npm test", "status": "ok"},
                {"seq": 2, "kind": "tool_result", "name": "npm test", "status": "error"},
                {"seq": 3, "kind": "tool_call", "name": "npm test", "status": "ok"},
                {"seq": 4, "kind": "tool_result", "name": "npm test", "status": "error"},
                {"seq": 5, "kind": "tool_call", "name": "npm test", "status": "ok"},
            ],
            "retry_loops",
            3,
            1,
        ),
        (
            [
                {"seq": seq, "kind": "tool_result", "name": f"tool-{seq}", "status": "error"}
                for seq in range(4, 8)
            ],
            "error_streak",
            4,
            4,
        ),
        (
            [
                {"seq": seq, "kind": "tool_call", "name": "pytest", "status": "error"}
                for seq in range(10, 13)
            ],
            "failing_command",
            3,
            10,
        ),
    ],
)
def test_live_stop_registry_reuses_all_four_loop_detectors(
    spans: list[dict[str, object]], pattern: str, count: int, first_seq: int
) -> None:
    result = detect_live_stop_pattern(spans)
    assert result is not None
    assert (result.pattern, result.count, result.first_seen_seq) == (pattern, count, first_seq)
    assert result.advice
