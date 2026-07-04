"""Vendored price table loading and longest-prefix model matching."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_PRICES_PATH = Path(__file__).resolve().parent.parent / "data" / "model_prices.json"
_DATE_SUFFIX = re.compile(r"-20\d{6}$")


@dataclass(frozen=True)
class PriceRow:
    match: str
    input_per_mtok: float
    output_per_mtok: float
    cache_read_per_mtok: float
    cache_write_per_mtok: float
    currency: str = "USD"
    cache_write_1h_per_mtok: float = 0.0
    min_cache_prefix: int | None = None

    @classmethod
    def from_dict(cls, d: dict[str, object]) -> PriceRow:
        def _float(key: str) -> float:
            val = d.get(key)
            if isinstance(val, (int, float)):
                return float(val)
            return 0.0

        prefix = d.get("min_cache_prefix")
        return cls(
            match=str(d.get("match", "")).lower(),
            input_per_mtok=_float("input_per_mtok"),
            output_per_mtok=_float("output_per_mtok"),
            cache_read_per_mtok=_float("cache_read_per_mtok"),
            cache_write_per_mtok=_float("cache_write_per_mtok"),
            currency=str(d.get("currency", "USD")),
            cache_write_1h_per_mtok=_float("cache_write_1h_per_mtok"),
            min_cache_prefix=int(prefix) if isinstance(prefix, int) else None,
        )


def _min_prefix_for(match: str) -> int | None:
    m = match.lower()
    if "opus" in m:
        return 4096
    if "sonnet-4-6" in m or "sonnet-4.6" in m:
        return 2048
    if "sonnet" in m:
        return 1024
    if m.startswith("gpt") or m.startswith("o3") or m.startswith("o4"):
        return 1024
    return None


@lru_cache(maxsize=1)
def load_price_table() -> tuple[PriceRow, ...]:
    data = json.loads(_PRICES_PATH.read_text(encoding="utf-8"))
    rows: list[PriceRow] = []
    for m in data.get("models", []):
        row = PriceRow.from_dict(m)
        # Anthropic two-tier cache: 5m write is already 1.25× input in the table;
        # the 1h write is 2.0× input (§2.7D). Backfill when not explicit.
        if row.cache_write_per_mtok > 0 and row.cache_write_1h_per_mtok == 0:
            row = PriceRow(
                match=row.match,
                input_per_mtok=row.input_per_mtok,
                output_per_mtok=row.output_per_mtok,
                cache_read_per_mtok=row.cache_read_per_mtok,
                cache_write_per_mtok=row.cache_write_per_mtok,
                currency=row.currency,
                cache_write_1h_per_mtok=round(2.0 * row.input_per_mtok, 6),
                min_cache_prefix=row.min_cache_prefix,
            )
        # min_cache_prefix is intentionally NOT backfilled here; it is derived
        # per-call from the full model id in ``min_cacheable_prefix`` so a
        # specific Sonnet 4.6 id resolves to 2048, not the generic 1024.
        rows.append(row)
    # Longest match first so prefix matching prefers the most specific entry.
    return tuple(sorted(rows, key=lambda r: len(r.match), reverse=True))


def normalize_model(model: str) -> str:
    """Lowercase, strip provider prefix (``provider/model``) and date suffixes."""
    name = model.strip().lower()
    if "/" in name:
        name = name.split("/", 1)[1]
    name = _DATE_SUFFIX.sub("", name)
    return name


def match_model(
    model: str,
    table: tuple[PriceRow, ...] | None = None,
) -> PriceRow | None:
    """Return the longest-prefix price row for *model*, or None."""
    if not model:
        return None
    rows = table if table is not None else load_price_table()
    name = normalize_model(model)
    best: PriceRow | None = None
    for row in rows:
        if name.startswith(row.match) and (best is None or len(row.match) > len(best.match)):
            best = row
    return best
