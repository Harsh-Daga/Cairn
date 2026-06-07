"""Per-provider retry policy tables (R18.3, R5)."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Literal

BackoffKind = Literal["exponential", "jitter", "from_header"]


@dataclass(frozen=True)
class RetryRule:
    status_codes: frozenset[int]
    max_attempts: int
    backoff: BackoffKind
    base_seconds: float = 1.0
    cap_seconds: float = 30.0
    header: str = "retry-after"


@dataclass(frozen=True)
class RetryPolicy:
    rules: tuple[RetryRule, ...]
    retry_timeouts: bool = True
    retry_5xx: bool = True


_OPENAI_POLICY = RetryPolicy(
    rules=(
        RetryRule(status_codes=frozenset({429}), max_attempts=5, backoff="from_header"),
        RetryRule(
            status_codes=frozenset({502, 503, 504}),
            max_attempts=5,
            backoff="exponential",
        ),
    ),
)

_ANTHROPIC_POLICY = RetryPolicy(
    rules=(
        RetryRule(status_codes=frozenset({429}), max_attempts=5, backoff="from_header"),
        RetryRule(
            status_codes=frozenset({529}),
            max_attempts=5,
            backoff="jitter",
            base_seconds=2.0,
        ),
        RetryRule(
            status_codes=frozenset({502, 503, 504}),
            max_attempts=5,
            backoff="exponential",
        ),
    ),
)

_DEFAULT_POLICY = RetryPolicy(
    rules=(
        RetryRule(status_codes=frozenset({429}), max_attempts=5, backoff="from_header"),
        RetryRule(
            status_codes=frozenset({500, 502, 503, 504}),
            max_attempts=5,
            backoff="exponential",
        ),
    ),
)

_POLICIES: dict[str, RetryPolicy] = {
    "openai": _OPENAI_POLICY,
    "anthropic": _ANTHROPIC_POLICY,
    "ollama-cloud": _DEFAULT_POLICY,
    "ollama": _DEFAULT_POLICY,
}


def retry_policy_for(provider: str) -> RetryPolicy:
    return _POLICIES.get(provider, _DEFAULT_POLICY)


def _parse_retry_after(value: str) -> float:
    try:
        return float(value)
    except ValueError:
        return 30.0


def compute_backoff(rule: RetryRule, attempt: int, headers: dict[str, str]) -> float:
    if rule.backoff == "from_header":
        for key, val in headers.items():
            if key.lower() == rule.header.lower():
                return float(max(_parse_retry_after(val), rule.base_seconds))
        base = rule.base_seconds * (2 ** (attempt - 1))
        return float(min(base, rule.cap_seconds))
    if rule.backoff == "jitter":
        sleep = min(rule.cap_seconds, random.uniform(rule.base_seconds, rule.base_seconds * 3))
        return float(sleep)
    base = rule.base_seconds * (2 ** (attempt - 1))
    jitter = random.uniform(0, base)
    return float(min(jitter, rule.cap_seconds))


def is_fatal_status(status: int) -> bool:
    return 400 <= status < 500 and status not in {408, 429}
