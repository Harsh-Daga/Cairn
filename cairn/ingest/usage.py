"""Extract observed token usage from raw transcript lines (R19)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from cairn.ingest.tokenize import (
    TokenMethod,
    _is_calibrated,
    count_tokens,
    estimation_error_pct,
    record_exact_calibration,
)

EstimationMethod = Literal["exact", "tiktoken", "heuristic"]


@dataclass
class ObservedUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    reasoning_tokens: int = 0
    cost: float | None = None
    input_estimated: bool = False
    output_estimated: bool = False
    input_estimation_method: EstimationMethod = "exact"
    output_estimation_method: EstimationMethod = "exact"
    input_estimation_error_pct: float | None = None
    output_estimation_error_pct: float | None = None

    def add(self, other: ObservedUsage) -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cache_read_tokens += other.cache_read_tokens
        self.cache_creation_tokens += other.cache_creation_tokens
        self.reasoning_tokens += other.reasoning_tokens
        if other.input_estimated:
            self.input_estimated = True
            self.input_estimation_method = other.input_estimation_method
            self.input_estimation_error_pct = other.input_estimation_error_pct
        if other.output_estimated:
            self.output_estimated = True
            self.output_estimation_method = other.output_estimation_method
            self.output_estimation_error_pct = other.output_estimation_error_pct
        if other.cost is not None:
            self.cost = (self.cost or 0.0) + other.cost


def _estimate_text_tokens(
    text: str,
    model: str | None,
) -> tuple[int, TokenMethod, float | None]:
    count, method = count_tokens(text, model)
    calibrated = method == "heuristic" and _is_calibrated(model)
    return count, method, estimation_error_pct(method, calibrated=calibrated)


def estimate_claude_turn(
    usage: dict[str, Any],
    *,
    assistant_text: str = "",
    user_text: str = "",
    model: str | None = None,
) -> ObservedUsage:
    """Apply §2.1 bug mitigations to a Claude Code assistant turn.

    - ``input_tokens`` is a streaming placeholder (0–2) in ~75% of entries;
      derive real input = cache_read + cache_creation + est_fresh, and set
      ``input_estimated`` when the raw value is not trustworthy (≤2).
    - ``output_tokens`` is a placeholder (1–2); estimate via tokenize and set
      ``output_estimated``.
    - ``cache_read_input_tokens`` and ``cache_creation_input_tokens`` are the
      trusted backbone (kept verbatim).
    """
    raw_input = _int_field(usage, "input_tokens", "inputTokens", "prompt_tokens")
    raw_output = _int_field(usage, "output_tokens", "outputTokens", "completion_tokens")
    cache_read = _int_field(
        usage,
        "cache_read_input_tokens",
        "cacheReadInputTokens",
        "cache_read_tokens",
        "prompt_tokens_details.cached_tokens",
    )
    cache_creation = _int_field(
        usage,
        "cache_creation_input_tokens",
        "cacheCreationInputTokens",
        "cache_creation_tokens",
    )
    reasoning = _int_field(
        usage,
        "reasoning_tokens",
        "completion_tokens_details.reasoning_tokens",
        "thinking_tokens",
    )
    cost = _float_field(usage, "cost_usd", "cost", "total_cost")

    input_estimated = False
    output_estimated = False
    input_method: EstimationMethod = "exact"
    output_method: EstimationMethod = "exact"
    input_err: float | None = None
    output_err: float | None = None

    if raw_input <= 2:
        est_fresh, fresh_method, fresh_err = _estimate_text_tokens(user_text, model)
        input_tokens = cache_read + cache_creation + est_fresh
        input_estimated = True
        input_method = fresh_method
        input_err = fresh_err
    else:
        input_tokens = raw_input
        if user_text:
            record_exact_calibration(
                model, user_text, exact_tokens=max(raw_input - cache_read - cache_creation, 1)
            )

    combined_output = assistant_text
    est_output, out_method, out_err = _estimate_text_tokens(combined_output, model)
    if raw_output <= 2:
        output_tokens = max(raw_output, est_output)
        output_estimated = True
        output_method = out_method
        output_err = out_err
    elif est_output > raw_output * 2:
        # Placeholder substantially below content size (common with thinking blocks).
        output_tokens = max(raw_output, est_output)
        output_estimated = True
        output_method = out_method
        output_err = out_err
    else:
        output_tokens = raw_output
        if combined_output:
            record_exact_calibration(model, combined_output, exact_tokens=raw_output)

    return ObservedUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read,
        cache_creation_tokens=cache_creation,
        reasoning_tokens=reasoning,
        cost=cost,
        input_estimated=input_estimated,
        output_estimated=output_estimated,
        input_estimation_method=input_method,
        output_estimation_method=output_method,
        input_estimation_error_pct=input_err,
        output_estimation_error_pct=output_err,
    )


@dataclass
class UsageAccumulator:
    usage: ObservedUsage = field(default_factory=ObservedUsage)

    def absorb_message_usage(self, message: dict[str, Any]) -> None:
        raw = message.get("usage")
        if not isinstance(raw, dict):
            return
        self.usage.add(extract_usage_dict(raw))


def extract_usage_dict(raw: dict[str, Any]) -> ObservedUsage:
    input_tokens = _int_field(raw, "input_tokens", "inputTokens", "prompt_tokens")
    output_tokens = _int_field(raw, "output_tokens", "outputTokens", "completion_tokens")
    cache_read_tokens = _int_field(
        raw,
        "cache_read_input_tokens",
        "cacheReadInputTokens",
        "cache_read_tokens",
        "prompt_tokens_details.cached_tokens",
    )
    cache_creation_tokens = _int_field(
        raw,
        "cache_creation_input_tokens",
        "cacheCreationInputTokens",
        "cache_creation_tokens",
    )
    reasoning_tokens = _int_field(
        raw,
        "reasoning_tokens",
        "completion_tokens_details.reasoning_tokens",
        "thinking_tokens",
    )
    cost = _float_field(raw, "cost_usd", "cost", "total_cost")
    input_estimated = bool(raw.get("input_estimated"))
    output_estimated = bool(raw.get("output_estimated"))
    input_method: EstimationMethod = "heuristic" if input_estimated else "exact"
    output_method: EstimationMethod = "heuristic" if output_estimated else "exact"
    input_err = raw.get("input_estimation_error_pct")
    output_err = raw.get("output_estimation_error_pct")
    if input_estimated and input_err is None:
        input_err = estimation_error_pct("heuristic")
    if output_estimated and output_err is None:
        output_err = estimation_error_pct("heuristic")
    return ObservedUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read_tokens,
        cache_creation_tokens=cache_creation_tokens,
        reasoning_tokens=reasoning_tokens,
        cost=cost,
        input_estimated=input_estimated,
        output_estimated=output_estimated,
        input_estimation_method=input_method,
        output_estimation_method=output_method,
        input_estimation_error_pct=float(input_err) if input_err is not None else None,
        output_estimation_error_pct=float(output_err) if output_err is not None else None,
    )


def _nested(raw: dict[str, Any], dotted: str) -> Any:
    """Resolve one level of nesting, e.g. ``prompt_tokens_details.cached_tokens``."""
    if "." not in dotted:
        return raw.get(dotted)
    head, tail = dotted.split(".", 1)
    inner = raw.get(head)
    if isinstance(inner, dict):
        return inner.get(tail)
    return None


def _int_field(raw: dict[str, Any], *keys: str) -> int:
    for key in keys:
        val = _nested(raw, key) if "." in key else raw.get(key)
        if isinstance(val, bool):
            continue
        if isinstance(val, int):
            return val
        if isinstance(val, float):
            return int(val)
    return 0


def _float_field(raw: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        val = raw.get(key)
        if isinstance(val, (int, float)):
            return float(val)
    return None
