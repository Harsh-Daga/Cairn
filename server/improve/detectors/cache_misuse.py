"""Prompt cache misuse detector."""

from __future__ import annotations

from typing import Any

from server.improve.detectors._types import Insight


def rule_cache_misuse(ctx: dict[str, Any]) -> Insight | None:
    cache = ctx.get("cache_stats_7d")
    if not cache:
        return None
    cache_read = int(cache.get("cache_read", 0))
    cache_creation = int(cache.get("cache_creation", 0))
    spike_count = int(cache.get("spike_count", 0))
    daily = cache.get("daily", []) or []
    if cache_creation <= 0 and spike_count <= 0:
        return None

    denom = cache_read + cache_creation
    hit_rate = cache_read / denom if denom > 0 else None

    writes_no_reads = cache_creation > 0 and cache_read == 0
    low_hit = hit_rate is not None and hit_rate < 0.70
    prefix_mismatch_days = [
        d
        for d in daily
        if d.get("hit_rate") is not None
        and float(d["hit_rate"]) < 0.80
        and (int(d.get("cache_creation", 0)) + int(d.get("cache_read", 0))) > 0
    ]
    prefix_mismatch = bool(prefix_mismatch_days)
    cache_thrash = spike_count > 0

    if not (writes_no_reads or low_hit or prefix_mismatch or cache_thrash):
        return None

    parts: list[str] = []
    if writes_no_reads:
        parts.append("Prompt caching is writing but not reading — add cache_control breakpoints.")
    if low_hit and hit_rate is not None:
        parts.append(f"Cache hit rate {hit_rate * 100:.0f}% is below 70%.")
    if prefix_mismatch:
        parts.append(
            "Cache prefix mismatch — likely a tool-schema or system-prompt change "
            "broke the prefix (hit rate <80% sustained over a day)."
        )
    if cache_thrash:
        parts.append(
            f"{spike_count} cache-creation spike(s) — >50% of a turn's input went to "
            "cache writes (cache thrash)."
        )

    evidence: dict[str, Any] = {
        "cache_read": cache_read,
        "cache_creation": cache_creation,
        "hit_rate": round(hit_rate, 4) if hit_rate is not None else None,
        "spike_count": spike_count,
        "prefix_mismatch_days": len(prefix_mismatch_days),
        "daily": daily,
    }
    return Insight(
        id="cache-misuse",
        severity="info",
        title="Prompt cache misuse",
        body=" ".join(parts),
        evidence=evidence,
        savings_estimate=None,
        action=None,
    )
