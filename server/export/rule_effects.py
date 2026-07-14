"""Local-only anonymized rule-effect export."""

from __future__ import annotations

import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from server.export.scrub import scrub_text
from server.models.rule_effect import RuleEffect, RuleEffectExport
from server.store.repos.experiments import ExperimentRepo

_SAFE_AGENT = re.compile(r"^[a-z0-9_+.-]{1,80}$")
_EXPORTABLE_VERDICTS = {
    "improved",
    "regressed",
    "no_effect",
    "inconclusive",
    "confounded",
}


def build_rule_effect_export(
    conn: sqlite3.Connection, workspace_root: Path
) -> RuleEffectExport:
    """Build an allowlisted payload; incomplete legacy experiments are omitted."""
    effects: list[RuleEffect] = []
    for experiment in ExperimentRepo.list_all(conn, limit=10_000):
        if (
            experiment.status != "verdict"
            or experiment.effect_estimate is None
            or experiment.effect_ci_low is None
            or experiment.effect_ci_high is None
            or experiment.outcome_n_raw is None
            or experiment.agent_type is None
            or experiment.verdict not in _EXPORTABLE_VERDICTS
            or experiment.effect_ci_low > experiment.effect_ci_high
        ):
            continue
        agent_type = (
            experiment.agent_type if _SAFE_AGENT.fullmatch(experiment.agent_type) else "mixed"
        )
        effects.append(
            RuleEffect(
                rule_text=scrub_text(experiment.content, workspace_root),
                effect_metric="waste_rate",
                effect_size=experiment.effect_estimate,
                ci=(experiment.effect_ci_low, experiment.effect_ci_high),
                n_sessions=experiment.outcome_n_raw,
                agent_type=agent_type,
                verdict=experiment.verdict,  # type: ignore[arg-type]
            )
        )
    return RuleEffectExport(
        generated_at=datetime.now(UTC).isoformat(),
        effects=effects,
    )


def export_rule_effects(
    conn: sqlite3.Connection,
    workspace_root: Path,
    output: Path | None = None,
) -> Path:
    """Write the scrubbed payload locally and return its path."""
    if output is None:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        output = workspace_root / ".cairn" / "exports" / f"rule-effects-{stamp}.json"
    destination = output.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = build_rule_effect_export(conn, workspace_root)
    destination.write_text(payload.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return destination
