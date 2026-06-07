"""Extract observed token usage from raw transcript lines (R19)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ObservedUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float | None = None

    def add(self, other: ObservedUsage) -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        if other.cost is not None:
            self.cost = (self.cost or 0.0) + other.cost


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
    cost = _float_field(raw, "cost_usd", "cost", "total_cost")
    return ObservedUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost=cost,
    )


def _int_field(raw: dict[str, Any], *keys: str) -> int:
    for key in keys:
        val = raw.get(key)
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
