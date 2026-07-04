"""Analyzer thresholds — all magic numbers live here (Phase 5)."""

CONTEXT_WARNING_PCT: float = 80.0  # warn when peak context exceeds 80%
CONTEXT_ROT_WASTE_PCT: float = 85.0  # context rot error threshold (% of window)
