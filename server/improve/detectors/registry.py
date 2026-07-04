"""Registry of all insight detector rules."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from server.improve.detectors._types import Insight
from server.improve.detectors.behavioral_drift import rule_behavioral_drift
from server.improve.detectors.cache_misuse import rule_cache_misuse
from server.improve.detectors.context_pressure import rule_context_window_pressure
from server.improve.detectors.high_file_churn import rule_high_file_churn
from server.improve.detectors.identical_calls import rule_identical_tool_calls
from server.improve.detectors.multi_model_spread import rule_multi_model_cost_spread
from server.improve.detectors.oversize_results import rule_oversize_tool_results
from server.improve.detectors.quality_regression import rule_quality_regression
from server.improve.detectors.rebilling_waste import rule_rebilling_waste
from server.improve.detectors.retry_loops import rule_retry_loops_detected
from server.improve.detectors.runaway_sessions import rule_runaway_sessions
from server.improve.detectors.subagent_heavy import rule_subagent_heavy
from server.improve.detectors.unused_tools import rule_unused_tools

RuleFn = Callable[[dict[str, Any]], Insight | None]

ALL_RULES: tuple[RuleFn, ...] = (
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
