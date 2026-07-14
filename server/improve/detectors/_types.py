"""Shared types and helpers for insight detectors."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from server.analyze.constants import CONTEXT_ROT_WASTE_PCT, CONTEXT_WARNING_PCT


def context_rot_warning_pct() -> float:
    return CONTEXT_WARNING_PCT


def context_rot_waste_pct() -> float:
    return CONTEXT_ROT_WASTE_PCT


@dataclass
class FixPayload:
    kind: Literal["instruction", "settings", "manual"]
    label: str
    value: str

    def as_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "label": self.label, "value": self.value}


@dataclass(frozen=True)
class LiveDetection:
    pattern: str
    count: int
    first_seen_seq: int
    advice: str
    priority: int


@dataclass
class Insight:
    id: str
    severity: str  # info | suggestion | warning | error
    title: str
    body: str
    evidence: dict[str, Any] = field(default_factory=dict)
    savings_estimate: float | None = None
    savings_unavailable_reason: str | None = None
    fix: FixPayload | None = None
    diagnostic: bool = False
    action: str | None = None
    difficulty_aware: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "severity": self.severity,
            "title": self.title,
            "body": self.body,
            "evidence": self.evidence,
            "savings_estimate": self.savings_estimate,
            "savings_unavailable_reason": self.savings_unavailable_reason,
            "fix": self.fix.as_dict() if self.fix else None,
            "diagnostic": self.diagnostic,
            "action": self.action,
            "difficulty_aware": self.difficulty_aware,
            "tier": "2.0" if self.difficulty_aware else "legacy",
        }


def validate_insight_contract(insight: Insight) -> Insight:
    """Reject detector output that cannot answer impact and next action."""
    if insight.savings_estimate is None and not insight.savings_unavailable_reason:
        raise ValueError(f"{insight.id}: null savings requires an explicit reason")
    if insight.fix is None or not insight.fix.value.strip():
        raise ValueError(f"{insight.id}: every insight requires a concrete fix payload")
    return insight


def _weekly_spend(total_cost: float, *, days: int) -> float:
    """Project ``total_cost`` accrued over ``days`` to a 7-day spend."""
    return float(total_cost) * (7.0 / max(1, days))


def _cap_savings(raw: float, weekly_spend: float, *, max_fraction: float = 0.5) -> float:
    return round(min(raw, weekly_spend * max_fraction), 2)


def _data_note(note: str) -> dict[str, Any]:
    return {"data_notes": [note]}
