"""Shared types and helpers for insight detectors."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from server.analyze.constants import CONTEXT_ROT_WASTE_PCT, CONTEXT_WARNING_PCT


def context_rot_warning_pct() -> float:
    return CONTEXT_WARNING_PCT


def context_rot_waste_pct() -> float:
    return CONTEXT_ROT_WASTE_PCT


@dataclass
class Insight:
    id: str
    severity: str  # info | suggestion | warning | error
    title: str
    body: str
    evidence: dict[str, Any] = field(default_factory=dict)
    savings_estimate: float | None = None
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
            "action": self.action,
            "difficulty_aware": self.difficulty_aware,
            "tier": "2.0" if self.difficulty_aware else "legacy",
        }


def _weekly_spend(total_cost: float, *, days: int) -> float:
    """Project ``total_cost`` accrued over ``days`` to a 7-day spend."""
    return float(total_cost) * (7.0 / max(1, days))


def _cap_savings(raw: float, weekly_spend: float, *, max_fraction: float = 0.5) -> float:
    return round(min(raw, weekly_spend * max_fraction), 2)


def _data_note(note: str) -> dict[str, Any]:
    return {"data_notes": [note]}
