"""Token counting — Phase 0 foundation."""

from __future__ import annotations

import pytest

from cairn.ingest import tokenize


def test_count_tokens_empty_returns_zero_exact() -> None:
    count, method = tokenize.count_tokens("", model="claude-sonnet")
    assert count == 0
    assert method == "exact"


def test_count_tokens_heuristic_fallback_without_calibration() -> None:
    text = "hello world" * 10
    count, method = tokenize.count_tokens(text, model="unknown-model")
    assert count >= 1
    assert method == "heuristic"
    err = tokenize.estimation_error_pct(method, calibrated=False)
    assert err is not None
    assert err >= 20.0


def test_count_tokens_uses_calibration_when_available() -> None:
    text = "x" * 400
    tokenize.reset_calibration()
    tokenize.record_exact_calibration("claude-sonnet", text, exact_tokens=100)
    count, method = tokenize.count_tokens(text, model="claude-sonnet-4-5")
    assert count == 100
    assert method == "heuristic"
    err = tokenize.estimation_error_pct(method, calibrated=True)
    assert err is not None
    assert err < 20.0


def test_tiktoken_used_for_openai_when_available() -> None:
    pytest.importorskip("tiktoken")
    text = "Refactor the parser module carefully."
    count, method = tokenize.count_tokens(text, model="gpt-4o")
    assert count >= 5
    assert method == "tiktoken"
    assert tokenize.estimation_error_pct(method) == pytest.approx(3.0)


def test_tiktoken_absent_degrades_to_heuristic() -> None:
    """Without tiktoken installed, OpenAI models use heuristic — never crash."""
    original = tokenize._tiktoken_encode
    tokenize._tiktoken_encode = None  # type: ignore[attr-defined]
    try:
        count, method = tokenize.count_tokens("hello world", model="gpt-4o")
        assert count >= 1
        assert method == "heuristic"
    finally:
        tokenize._tiktoken_encode = original  # type: ignore[attr-defined]


def test_record_calibration_ignored_for_empty_text() -> None:
    tokenize.reset_calibration()
    tokenize.record_exact_calibration("gpt-4o", "", exact_tokens=10)
    tokenize.record_exact_calibration("gpt-4o", "text", exact_tokens=0)
    original = tokenize._tiktoken_encode
    tokenize._tiktoken_encode = None  # type: ignore[attr-defined]
    try:
        count, method = tokenize.count_tokens("abc", model="gpt-4o")
        assert count >= 1
        assert method == "heuristic"
    finally:
        tokenize._tiktoken_encode = original  # type: ignore[attr-defined]
