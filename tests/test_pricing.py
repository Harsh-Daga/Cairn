"""Tests for the pricing engine and override wiring."""

from __future__ import annotations

from pathlib import Path

from cairn.pricing.engine import (
    cache_hit_rate,
    estimate_cost,
    load_overrides,
    min_cacheable_prefix,
)


def test_estimate_cost_matches_longest_prefix() -> None:
    usage = {"input_tokens": 1_000_000, "output_tokens": 500_000}
    breakdown = estimate_cost("claude-3-5-sonnet-20241022", usage)
    assert breakdown.model_matched == "claude-3-5-sonnet"
    assert breakdown.input_cost == 3.0
    assert breakdown.output_cost == 7.5
    assert breakdown.total == 10.5


def test_unknown_model_returns_zero_none_breakdown() -> None:
    usage = {"input_tokens": 1_000_000, "output_tokens": 500_000}
    breakdown = estimate_cost("not-a-real-model-v1", usage)
    assert breakdown.total == 0.0
    assert breakdown.estimated is True
    assert breakdown.model_matched is None


def test_estimate_cost_with_cache() -> None:
    usage = {
        "input_tokens": 1_000_000,
        "output_tokens": 500_000,
        "cache_read_tokens": 2_000_000,
        "cache_creation_tokens": 500_000,
    }
    breakdown = estimate_cost("claude-3-5-sonnet", usage)
    assert breakdown.input_cost == 3.0
    assert breakdown.output_cost == 7.5
    assert breakdown.cache_read_cost == 0.6
    assert breakdown.cache_write_cost == 1.875


def test_local_override_wins(tmp_path: Path) -> None:
    cairn_dir = tmp_path / ".cairn"
    cairn_dir.mkdir()
    (cairn_dir / "prices.local.toml").write_text(
        """
        [prices."claude-test"]
        input_per_mtok = 1.0
        output_per_mtok = 2.0
        cache_read_per_mtok = 0.5
        cache_write_per_mtok = 0.75
        """,
        encoding="utf-8",
    )
    usage = {
        "input_tokens": 1_000_000,
        "output_tokens": 500_000,
        "cache_read_tokens": 1_000_000,
        "cache_creation_tokens": 500_000,
    }
    overrides = load_overrides(tmp_path)
    breakdown = estimate_cost("claude-test", usage, overrides=overrides)
    assert breakdown.model_matched == "claude-test"
    assert breakdown.input_cost == 1.0
    assert breakdown.output_cost == 1.0
    assert breakdown.cache_read_cost == 0.5
    assert breakdown.cache_write_cost == 0.375


def test_estimate_cost_loads_overrides_from_root(tmp_path: Path) -> None:
    cairn_dir = tmp_path / ".cairn"
    cairn_dir.mkdir()
    (cairn_dir / "prices.local.toml").write_text(
        """
        [prices."gpt-test"]
        input_per_mtok = 0.1
        output_per_mtok = 0.2
        cache_read_per_mtok = 0.0
        cache_write_per_mtok = 0.0
        """,
        encoding="utf-8",
    )
    usage = {"input_tokens": 1_000_000, "output_tokens": 500_000}
    breakdown = estimate_cost("gpt-test", usage, root=tmp_path)
    assert breakdown.model_matched == "gpt-test"
    assert breakdown.input_cost == 0.1
    assert breakdown.output_cost == 0.1


def test_cache_read_is_one_tenth_input_anthropic() -> None:
    """§2.7D: Anthropic cache read = 0.10× input."""
    usage = {"cache_read_tokens": 1_000_000}
    breakdown = estimate_cost("claude-sonnet", usage)
    assert breakdown.cache_read_cost == 0.3  # 0.10 × 3.0


def test_cache_5m_write_is_1_25x_input() -> None:
    """§2.7D: Anthropic 5m cache write = 1.25× input."""
    usage = {"cache_creation_tokens": 1_000_000}
    breakdown = estimate_cost("claude-sonnet", usage)
    assert breakdown.cache_write_cost == 3.75  # 1.25 × 3.0


def test_cache_1h_write_is_2x_input() -> None:
    """§2.7D: Anthropic 1h cache write = 2.0× input; billed via ephemeral_1h."""
    usage = {"cache_creation_1h_tokens": 1_000_000}
    breakdown = estimate_cost("claude-sonnet", usage)
    assert breakdown.cache_write_1h_cost == 6.0  # 2.0 × 3.0
    assert breakdown.cache_write_cost == 0.0  # 5m tier untouched


def test_cache_1h_via_ephemeral_field_name() -> None:
    usage = {"ephemeral_1h_input_tokens": 1_000_000}
    breakdown = estimate_cost("claude-opus", usage)
    assert breakdown.cache_write_1h_cost == 30.0  # 2.0 × 15.0


def test_cache_two_tier_combined() -> None:
    usage = {
        "input_tokens": 1_000_000,
        "cache_read_tokens": 2_000_000,
        "cache_creation_tokens": 500_000,  # 5m
        "cache_creation_1h_tokens": 200_000,  # 1h
    }
    b = estimate_cost("claude-sonnet", usage)
    assert b.cache_read_cost == 0.6
    assert b.cache_write_cost == 1.875
    assert b.cache_write_1h_cost == 1.2  # 200k × 6.0 / 1e6
    assert b.total == b.input_cost + 0.0 + 0.6 + 1.875 + 1.2


def test_cache_hit_rate_helper() -> None:
    assert cache_hit_rate({"cache_read_tokens": 90, "cache_creation_tokens": 10}) == 0.9
    assert cache_hit_rate({"cache_read_tokens": 0, "cache_creation_tokens": 100}) == 0.0


def test_cache_hit_rate_div0_returns_none() -> None:
    """div0 / missing cache data → None (never fabricate 0)."""
    assert cache_hit_rate({"cache_read_tokens": 0, "cache_creation_tokens": 0}) is None
    assert cache_hit_rate({}) is None


def test_min_cacheable_prefix_per_model() -> None:
    """§2.7D per-model min cacheable prefix."""
    assert min_cacheable_prefix("claude-opus-4-5") == 4096
    assert min_cacheable_prefix("claude-sonnet-4-6") == 2048
    assert min_cacheable_prefix("claude-sonnet-4-5") == 1024
    assert min_cacheable_prefix("gpt-4o") == 1024
    # Gemini uses explicit caching — no minimum prefix.
    assert min_cacheable_prefix("gemini-2.5-pro") is None


def test_openai_cache_read_is_half_input() -> None:
    """§2.7D: OpenAI cache read = 0.5× input."""
    usage = {"cache_read_tokens": 1_000_000}
    breakdown = estimate_cost("gpt-4o", usage)
    # gpt-4o input 2.5, read 1.25 = 0.5×
    assert breakdown.cache_read_cost == 1.25
    assert breakdown.cache_write_cost == 0.0  # OpenAI: automatic, no write tier
