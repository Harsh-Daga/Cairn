"""Strict schema for an opt-in anonymized rule-effect export."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

RuleEffectVerdict = Literal["improved", "regressed", "no_effect", "inconclusive", "confounded"]


class RuleEffect(BaseModel):
    """Shareable measured effect with no workspace or trace identifiers."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    rule_text: str = Field(min_length=1, max_length=2000)
    effect_metric: Literal["waste_rate"]
    effect_size: float
    ci: tuple[float, float]
    n_sessions: int = Field(ge=1)
    agent_type: str = Field(min_length=1, max_length=80)
    verdict: RuleEffectVerdict

    @model_validator(mode="after")
    def validate_ci(self) -> RuleEffect:
        if self.ci[0] > self.ci[1]:
            raise ValueError("ci lower bound must not exceed upper bound")
        return self


class RuleEffectExport(BaseModel):
    """Versioned local export envelope; sharing is always a separate user action."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1"] = "1"
    generated_at: str
    effects: list[RuleEffect]
    scrubbed: Literal[True] = True
