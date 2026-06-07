"""Cost estimation (R4)."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cairn.util.tokens import estimate_tokens_from_text

_PRICES_PATH = Path(__file__).resolve().parent.parent / "data" / "prices.toml"
_BUILTIN_PRICES: dict[str, dict[str, Any]] | None = None


@dataclass(frozen=True)
class CostEstimate:
    cost: float | None
    unpriced: bool
    input_tokens: int
    output_tokens: int


def _load_builtin_prices() -> dict[str, dict[str, Any]]:
    global _BUILTIN_PRICES
    if _BUILTIN_PRICES is None:
        data = tomllib.loads(_PRICES_PATH.read_text(encoding="utf-8"))
        _BUILTIN_PRICES = {str(k): dict(v) for k, v in data.get("prices", data).items()}
    return _BUILTIN_PRICES


def _strip_model_prefix(model: str) -> str:
    if "/" in model:
        return model.split("/", 1)[1]
    return model


def estimate_node_cost(
    model: str,
    rendered_prompt: str,
    params: dict[str, Any],
    project_prices: dict[str, dict[str, Any]],
) -> CostEstimate:
    prices = {**_load_builtin_prices(), **project_prices}
    wire_model = _strip_model_prefix(model)
    price_row = prices.get(model) or prices.get(wire_model)
    est_in = estimate_tokens_from_text(rendered_prompt)
    est_out = int(params.get("max_tokens", 1000))
    if price_row is None:
        return CostEstimate(cost=None, unpriced=True, input_tokens=est_in, output_tokens=est_out)
    cost = (
        est_in * float(price_row.get("input_per_mtok", 0)) / 1_000_000
        + est_out * float(price_row.get("output_per_mtok", 0)) / 1_000_000
    )
    return CostEstimate(cost=cost, unpriced=False, input_tokens=est_in, output_tokens=est_out)


def actual_node_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    project_prices: dict[str, dict[str, Any]],
) -> float | None:
    """Post-run cost from token usage (R4 actuals)."""
    prices = {**_load_builtin_prices(), **project_prices}
    wire_model = _strip_model_prefix(model)
    price_row = prices.get(model) or prices.get(wire_model)
    if price_row is None:
        return None
    return (
        input_tokens * float(price_row.get("input_per_mtok", 0)) / 1_000_000
        + output_tokens * float(price_row.get("output_per_mtok", 0)) / 1_000_000
    )
