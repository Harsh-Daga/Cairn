"""Privacy and schema tests for local rule-effect exports."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from server.cli import app
from server.export.rule_effects import build_rule_effect_export, export_rule_effects
from server.export.scrub import scrub_export_value
from server.models.evidence import Evidence
from server.models.experiment import Experiment
from server.models.rule_effect import RuleEffect
from server.models.workspace import Workspace
from server.store.db import Database
from server.store.repos.evidence import EvidenceRepo
from server.store.repos.experiments import ExperimentRepo
from server.store.repos.workspaces import WorkspaceRepo


def _seed_effect(root: Path) -> Database:
    db = Database(root / ".cairn" / "cairn.db")
    WorkspaceRepo.create(
        db.reader,
        Workspace(
            workspace_id="ws-effect",
            root_path=str(root),
            name=root.name,
            created_at="2026-01-01T00:00:00Z",
        ),
    )
    EvidenceRepo.create(
        db.reader,
        Evidence(
            evidence_id="evidence-effect",
            producer="test",
            produced_at="2026-01-01T00:00:00Z",
        ),
    )
    ExperimentRepo.create(
        db.reader,
        Experiment(
            experiment_id="experiment-effect",
            created_at="2026-01-01T00:00:00Z",
            target_file="AGENTS.md",
            block_key="rule/private",
            kind="instruction",
            content=(
                "In secret-repo, inspect /Users/alice/secret-repo/src/private.py and "
                "https://internal.example/repo.\n```python\nprint('private')\n```"
            ),
            evidence_id="evidence-effect",
            status="verdict",
            outcome_n_raw=24,
            outcome_n_effective=12.5,
            effect_estimate=-0.18,
            effect_ci_low=-0.30,
            effect_ci_high=-0.06,
            test_method="difference_in_means+anytime_valid_cs",
            verdict="improved",
            measured_at="2026-01-02T00:00:00Z",
            agent_type="claude_code",
        ),
    )
    db.reader.commit()
    return db


def test_rule_effect_export_is_strictly_scrubbed(tmp_path: Path) -> None:
    root = tmp_path / "secret-repo"
    root.mkdir()
    db = _seed_effect(root)

    payload = build_rule_effect_export(db.reader, root)
    output = export_rule_effects(db.reader, root, root / "effects.json")
    serialized = output.read_text(encoding="utf-8")

    assert len(payload.effects) == 1
    effect = json.loads(serialized)["effects"][0]
    assert set(effect) == {
        "rule_text",
        "effect_metric",
        "effect_size",
        "ci",
        "n_sessions",
        "agent_type",
        "verdict",
    }
    assert effect["n_sessions"] == 24
    assert effect["effect_metric"] == "waste_rate"
    for secret in ("secret-repo", "/Users/alice", "private.py", "print(", "internal.example"):
        assert secret not in serialized
    if os.name != "nt":
        assert output.parent.stat().st_mode & 0o777 == 0o700
        assert output.stat().st_mode & 0o777 == 0o600
    db.close()


def test_rule_effect_schema_rejects_extra_fields_and_invalid_ci() -> None:
    base = {
        "rule_text": "Read the failure before retrying.",
        "effect_metric": "waste_rate",
        "effect_size": -0.1,
        "ci": (-0.2, -0.01),
        "n_sessions": 20,
        "agent_type": "codex",
        "verdict": "improved",
    }
    with pytest.raises(ValidationError):
        RuleEffect.model_validate({**base, "repo": "private"})
    with pytest.raises(ValidationError):
        RuleEffect.model_validate({**base, "ci": (0.2, -0.2)})


def test_generic_export_scrubber_removes_sensitive_fields(tmp_path: Path) -> None:
    root = tmp_path / "private-project"
    root.mkdir()
    scrubbed = scrub_export_value(
        {
            "project": "private-project",
            "cwd": str(root),
            "cost": 1.25,
            "note": "See src/secret.py at https://private.example/repo",
        },
        root,
    )
    assert scrubbed == {
        "project": "<redacted>",
        "cwd": "<redacted>",
        "cost": 1.25,
        "note": "See <path> at <url>",
    }


def test_generic_export_scrubber_removes_common_credentials(tmp_path: Path) -> None:
    root = tmp_path / "private-project"
    root.mkdir()
    scrubbed = scrub_export_value(
        {
            "note": (
                "Authorization: Bearer private-token-123456 "
                "api_key=sk-super-secret-value "
                "AWS=AKIA1234567890ABCDEF"
            )
        },
        root,
    )
    serialized = str(scrubbed)
    for value in ("private-token-123456", "sk-super-secret-value", "AKIA1234567890ABCDEF"):
        assert value not in serialized


def test_generic_export_scrubber_preserves_safe_relational_ids_only(tmp_path: Path) -> None:
    root = tmp_path / "private-project"
    root.mkdir()
    scrubbed = scrub_export_value(
        {
            "trace_id": "ca435ab4-d3a6-57bc-9453-0a88236c2030",
            "span_id": "SPAN_123",
            "parent_span_id": None,
            "event_id": "sk-super-secret-value",
        },
        root,
    )
    assert scrubbed["trace_id"] == "ca435ab4-d3a6-57bc-9453-0a88236c2030"
    assert scrubbed["span_id"] == "SPAN_123"
    assert scrubbed["parent_span_id"] is None
    assert scrubbed["event_id"] == "<redacted credential>"


def test_optimize_export_effects_cli_writes_only_local_file(tmp_path: Path) -> None:
    root = tmp_path / "secret-repo"
    root.mkdir()
    db = _seed_effect(root)
    db.close()
    output = root / "chosen" / "effects.json"

    result = CliRunner().invoke(
        app,
        [
            "optimize",
            "export-effects",
            "--workspace",
            str(root),
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0
    assert result.stdout.strip() == str(output.resolve())
    assert output.is_file()
