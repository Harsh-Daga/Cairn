"""Compatibility facade for the ingest cost engine (Phase 4 / v1.2 offline pricing)."""

from server.ingest.pricing import (
    CostBreakdown,
    cache_hit_rate,
    estimate_cost,
    load_overrides,
    min_cacheable_prefix,
    pricing_refresh_preview,
    pricing_status,
)
from server.ingest.pricing_data import (
    PriceRow,
    PriceTableMeta,
    load_price_table,
    load_price_table_meta,
    match_model,
    normalize_model,
)

__all__ = [
    "CostBreakdown",
    "PriceRow",
    "PriceTableMeta",
    "cache_hit_rate",
    "estimate_cost",
    "load_overrides",
    "load_price_table",
    "load_price_table_meta",
    "match_model",
    "min_cacheable_prefix",
    "normalize_model",
    "pricing_refresh_preview",
    "pricing_status",
]
