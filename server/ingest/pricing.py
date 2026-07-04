"""Cost engine: turn token usage into a CostBreakdown using the price table."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from server.ingest.pricing_data import PriceRow, _min_prefix_for, match_model


@dataclass(frozen=True)
class CostBreakdown:
    input_cost: float
    output_cost: float
    cache_read_cost: float
    cache_write_cost: float
    cache_write_1h_cost: float
    total: float
    estimated: bool
    model_matched: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "input_cost": self.input_cost,
            "output_cost": self.output_cost,
            "cache_read_cost": self.cache_read_cost,
            "cache_write_cost": self.cache_write_cost,
            "cache_write_1h_cost": self.cache_write_1h_cost,
            "total": self.total,
            "estimated": self.estimated,
            "model_matched": self.model_matched,
        }


_EMPTY = CostBreakdown(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, True, None)


def _usage_field(usage: Any, name: str) -> int:
    val = usage.get(name, 0) if isinstance(usage, dict) else getattr(usage, name, 0)
    try:
        return int(val or 0)
    except (TypeError, ValueError):
        return 0


def cache_hit_rate(usage: Any) -> float | None:
    """``cache_read / (cache_read + cache_creation)``; None on div0 / missing.

    Used by the cache-health insight (§2.7D): healthy >90%, prefix-mismatch
    warning when sustained <80%.
    """
    cr = _usage_field(usage, "cache_read_tokens")
    cw = _usage_field(usage, "cache_creation_tokens")
    if cr + cw == 0:
        return None
    return cr / (cr + cw)


def min_cacheable_prefix(model: str) -> int | None:
    """Per-model minimum cacheable prefix (§2.7D). None = no minimum / explicit.

    Computed from the full model id (not the matched price-row prefix) so a
    specific Sonnet 4.6 id resolves to 2048 even though it price-matches the
    generic ``claude-sonnet`` row.
    """
    row = match_model(model)
    if row is None:
        return None
    if row.min_cache_prefix is not None:
        return row.min_cache_prefix
    return _min_prefix_for(model)


def estimate_cost(
    model: str,
    usage: Any,
    *,
    overrides: dict[str, dict[str, Any]] | None = None,
    estimated: bool = True,
    root: Path | None = None,
) -> CostBreakdown:
    """Cost from token usage. *usage* may be a dict or an object with token fields.

    Two-tier cache billing (§2.7D):
    - ``cache_creation_tokens`` → 5m write at ``cache_write_per_mtok`` (1.25× input).
    - ``cache_creation_1h_tokens`` (``ephemeral_1h_input_tokens``) → 1h write at
      ``cache_write_1h_per_mtok`` (2.0× input).

    Returns a zero breakdown (estimated=True, model_matched=None) when the model
    is unknown.
    """
    if overrides is None and root is not None:
        overrides = load_overrides(root)
    row = _resolve_row(model, overrides)
    if row is None:
        return CostBreakdown(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, estimated, None)

    inp = _usage_field(usage, "input_tokens")
    out = _usage_field(usage, "output_tokens")
    cr = _usage_field(usage, "cache_read_tokens")
    cw = _usage_field(usage, "cache_creation_tokens")
    cw_1h = _usage_field(usage, "cache_creation_1h_tokens") or _usage_field(
        usage, "ephemeral_1h_input_tokens"
    )

    input_cost = inp * row.input_per_mtok / 1_000_000
    output_cost = out * row.output_per_mtok / 1_000_000
    cache_read_cost = cr * row.cache_read_per_mtok / 1_000_000
    cache_write_cost = cw * row.cache_write_per_mtok / 1_000_000
    cache_write_1h_cost = cw_1h * row.cache_write_1h_per_mtok / 1_000_000
    total = input_cost + output_cost + cache_read_cost + cache_write_cost + cache_write_1h_cost
    return CostBreakdown(
        input_cost=input_cost,
        output_cost=output_cost,
        cache_read_cost=cache_read_cost,
        cache_write_cost=cache_write_cost,
        cache_write_1h_cost=cache_write_1h_cost,
        total=total,
        estimated=estimated,
        model_matched=row.match,
    )


def _resolve_row(
    model: str,
    overrides: dict[str, dict[str, Any]] | None,
) -> PriceRow | None:
    if overrides:
        from server.ingest.pricing_data import normalize_model

        name = normalize_model(model)
        # Overrides win: accept exact model, normalized name, or a prefix key.
        candidates = [model, name]
        for key in candidates:
            if key in overrides:
                return PriceRow.from_dict({"match": name, **overrides[key]})
        best_key: str | None = None
        for key in overrides:
            kl = key.lower()
            if name.startswith(kl) and (best_key is None or len(kl) > len(best_key)):
                best_key = key
        if best_key is not None:
            return PriceRow.from_dict({"match": best_key.lower(), **overrides[best_key]})
    return match_model(model)


def load_overrides(root: Path | None) -> dict[str, dict[str, Any]]:
    """Merge ``~/.cairn/prices.toml`` then ``<root>/.cairn/prices.local.toml``.

    The project-local file wins over the user-global one.
    """
    merged: dict[str, dict[str, Any]] = {}
    home = Path.home() / ".cairn" / "prices.toml"
    if home.is_file():
        merged.update(_load_toml_prices(home))
    if root is not None:
        local = Path(root) / ".cairn" / "prices.local.toml"
        if local.is_file():
            merged.update(_load_toml_prices(local))
    return merged


def _load_toml_prices(path: Path) -> dict[str, dict[str, Any]]:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    prices = data.get("prices", data)
    return {str(k): dict(v) for k, v in prices.items() if isinstance(v, dict)}
