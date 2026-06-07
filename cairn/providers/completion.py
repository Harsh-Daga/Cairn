"""Completion validation before caching (Phase 2.1)."""

from __future__ import annotations

from cairn.model.errors import EmptyCompletionError
from cairn.model.messages import CompletionResult

_TRUNCATION_REASONS = frozenset({"length", "max_tokens"})


def ensure_usable_completion(result: CompletionResult) -> CompletionResult:
    """Reject empty or truncated-without-text completions before cache.bind."""
    text = result.text.strip()
    reason = result.finish_reason
    if text:
        return result
    if reason in _TRUNCATION_REASONS:
        msg = (
            f"completion truncated ({reason!r}) with empty text — "
            "increase max_tokens or use a non-reasoning model"
        )
        raise EmptyCompletionError(message=msg)
    msg = "completion returned empty text"
    raise EmptyCompletionError(message=msg)
