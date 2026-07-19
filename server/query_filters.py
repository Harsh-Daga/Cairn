"""Typed, bounded filter grammar shared by Sessions and Search."""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from datetime import date
from typing import Literal

FilterField = Literal[
    "agent",
    "source",
    "status",
    "cost",
    "outcome",
    "file",
    "tool",
    "after",
    "claim",
    "verification",
    "corrected",
    "risk",
]
Comparison = Literal["eq", "gt", "gte", "lt", "lte"]

FILTER_SPECS: dict[FilterField, dict[str, object]] = {
    "agent": {"kind": "text", "example": "agent:codex", "available": True},
    "source": {"kind": "text", "example": "source:claude_code", "available": True},
    "status": {"kind": "text", "example": "is:error", "available": True},
    "cost": {"kind": "number", "example": "cost:>1", "available": True},
    "outcome": {"kind": "text", "example": "outcome:fail", "available": True},
    "file": {"kind": "text", "example": "file:src/", "available": True},
    "tool": {"kind": "text", "example": "tool:read", "available": True},
    "after": {"kind": "date", "example": "after:2026-07-01", "available": True},
    "claim": {
        "kind": "enum",
        "values": ["unsupported"],
        "example": "claim:unsupported",
        "available": False,
        "unavailable_reason": "Claim-level verification receipts are not available yet.",
    },
    "verification": {
        "kind": "enum",
        "values": ["debt", "failed", "verified", "unverified"],
        "example": "verification:debt",
        "available": True,
    },
    "corrected": {
        "kind": "boolean",
        "example": "corrected:true",
        "available": True,
    },
    "risk": {
        "kind": "enum",
        "values": ["high"],
        "example": "risk:high",
        "available": True,
    },
}

_COST_RE = re.compile(r"^(>=|<=|>|<|=)?(\d+(?:\.\d+)?)$")


@dataclass(frozen=True, slots=True)
class FilterToken:
    raw: str
    field: FilterField
    value: str
    comparison: Comparison = "eq"
    available: bool = True


@dataclass(frozen=True, slots=True)
class FilterError:
    token: str
    message: str


@dataclass(frozen=True, slots=True)
class ParsedFilter:
    raw: str
    phrase: str
    tokens: tuple[FilterToken, ...]
    errors: tuple[FilterError, ...]

    @property
    def valid(self) -> bool:
        return not self.errors

    def values(self, field: FilterField) -> tuple[FilterToken, ...]:
        return tuple(token for token in self.tokens if token.field == field)


def _comparison(raw: str | None) -> Comparison:
    if raw == ">":
        return "gt"
    if raw == ">=":
        return "gte"
    if raw == "<":
        return "lt"
    if raw == "<=":
        return "lte"
    return "eq"


def parse_filter(raw: str) -> ParsedFilter:
    """Parse a shell-like filter without executing or interpreting its text."""
    if len(raw) > 500:
        return ParsedFilter(
            raw=raw,
            phrase="",
            tokens=(),
            errors=(FilterError(token="", message="Filter must be at most 500 characters."),),
        )
    try:
        parts = shlex.split(raw, posix=True)
    except ValueError as exc:
        return ParsedFilter(
            raw=raw,
            phrase="",
            tokens=(),
            errors=(FilterError(token=raw, message=f"Invalid quoting: {exc}."),),
        )

    phrases: list[str] = []
    tokens: list[FilterToken] = []
    errors: list[FilterError] = []
    for part in parts:
        if ":" not in part:
            phrases.append(part)
            continue
        raw_field, value = part.split(":", 1)
        field = raw_field.lower()
        if field == "is":
            field = "status"
        if field not in FILTER_SPECS:
            errors.append(
                FilterError(
                    token=part,
                    message=f"Unknown filter '{raw_field}'.",
                )
            )
            continue
        typed_field = field
        spec = FILTER_SPECS[typed_field]
        if not value:
            errors.append(FilterError(token=part, message=f"{field}: requires a value."))
            continue
        comparison: Comparison = "eq"
        kind = spec["kind"]
        if kind == "number":
            match = _COST_RE.fullmatch(value)
            if match is None:
                errors.append(
                    FilterError(
                        token=part,
                        message=(
                            "cost: expects a non-negative number with optional >, >=, <, <=, or =."
                        ),
                    )
                )
                continue
            comparison = _comparison(match.group(1))
            value = match.group(2)
        elif kind == "date":
            try:
                date.fromisoformat(value)
            except ValueError:
                errors.append(
                    FilterError(token=part, message="after: expects an ISO date like 2026-07-01.")
                )
                continue
        elif kind == "boolean":
            value = value.lower()
            if value not in {"true", "false"}:
                errors.append(FilterError(token=part, message=f"{field}: expects true or false."))
                continue
        elif kind == "enum":
            value = value.lower()
            raw_values = spec.get("values")
            allowed = (
                tuple(str(item) for item in raw_values) if isinstance(raw_values, list) else ()
            )
            if value not in allowed:
                errors.append(
                    FilterError(
                        token=part,
                        message=f"{field}: expects one of {', '.join(allowed)}.",
                    )
                )
                continue
        available = bool(spec["available"])
        tokens.append(
            FilterToken(
                raw=part,
                field=typed_field,
                value=value,
                comparison=comparison,
                available=available,
            )
        )
        if not available:
            errors.append(
                FilterError(
                    token=part,
                    message=str(spec["unavailable_reason"]),
                )
            )
    return ParsedFilter(
        raw=raw,
        phrase=" ".join(phrases),
        tokens=tuple(tokens),
        errors=tuple(errors),
    )


def sql_comparison(comparison: Comparison) -> str:
    """Return a fixed SQL operator for a validated comparison."""
    return {"eq": "=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}[comparison]
