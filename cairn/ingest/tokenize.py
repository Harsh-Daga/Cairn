"""Token counting with optional tiktoken and per-model calibration (Phase 0)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from cairn.metrics.constants import BYTES_PER_TOKEN, MODEL_CONTEXT_WINDOWS

TokenMethod = Literal["exact", "tiktoken", "heuristic"]

HEURISTIC_FALLBACK_ERROR_PCT = 25.0
CALIBRATED_HEURISTIC_ERROR_PCT = 12.0
TIKTOKEN_ERROR_PCT = 3.0

# model prefix -> rolling bytes-per-token estimate
_bpt_by_model: dict[str, float] = {}
_bpt_samples: dict[str, list[float]] = {}

_tiktoken_encode = None
_tiktoken_checked = False


def reset_calibration() -> None:
    """Clear in-memory calibration (for tests)."""
    _bpt_by_model.clear()
    _bpt_samples.clear()


def _model_prefix(model: str | None) -> str:
    if not model:
        return "default"
    lower = model.lower()
    for prefix in sorted(MODEL_CONTEXT_WINDOWS, key=len, reverse=True):
        if lower.startswith(prefix) or prefix in lower:
            return prefix
    return lower.split("-")[0] if "-" in lower else lower


def record_exact_calibration(model: str | None, text: str, *, exact_tokens: int) -> None:
    """Learn bytes/token from sessions that carry exact counts."""
    if not text or exact_tokens <= 0:
        return
    byte_len = len(text.encode("utf-8"))
    if byte_len <= 0:
        return
    ratio = byte_len / exact_tokens
    key = _model_prefix(model)
    samples = _bpt_samples.setdefault(key, [])
    samples.append(ratio)
    if len(samples) > 50:
        samples.pop(0)
    _bpt_by_model[key] = sum(samples) / len(samples)


def _bytes_per_token(model: str | None) -> float:
    key = _model_prefix(model)
    return _bpt_by_model.get(key, float(BYTES_PER_TOKEN))


def _is_calibrated(model: str | None) -> bool:
    return _model_prefix(model) in _bpt_by_model


def _lazy_tiktoken() -> Callable[[str, str], int] | None:
    global _tiktoken_encode, _tiktoken_checked
    if _tiktoken_checked:
        return _tiktoken_encode
    _tiktoken_checked = True
    try:
        import tiktoken  # type: ignore[import-not-found]
    except ImportError:
        _tiktoken_encode = None
        return None

    def encode(text: str, model: str) -> int:
        try:
            enc = tiktoken.encoding_for_model(model)
        except KeyError:
            enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))

    _tiktoken_encode = encode
    return _tiktoken_encode


def _openai_model(model: str | None) -> bool:
    if not model:
        return False
    lower = model.lower()
    return any(tok in lower for tok in ("gpt", "o1", "o3", "o4", "codex", "chatgpt"))


def count_tokens(text: str, model: str | None = None) -> tuple[int, TokenMethod]:
    """Return (token_count, method). Never raises when optional deps are absent."""
    if not text:
        return 0, "exact"

    if _openai_model(model):
        enc = _lazy_tiktoken()
        if enc is not None:
            return enc(text, model or "gpt-4o"), "tiktoken"

    bpt = _bytes_per_token(model)
    return max(1, int(len(text.encode("utf-8")) / bpt)), "heuristic"


def estimation_error_pct(
    method: TokenMethod,
    *,
    calibrated: bool = False,
) -> float | None:
    """Return expected error % for an estimation method; None for exact counts."""
    if method == "exact":
        return None
    if method == "tiktoken":
        return TIKTOKEN_ERROR_PCT
    return CALIBRATED_HEURISTIC_ERROR_PCT if calibrated else HEURISTIC_FALLBACK_ERROR_PCT
