"""Outcomes incremental analyzer tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from server.analyze.outcomes import (
    OutcomesView,
    agent_quality_score,
    capture_followup_signals,
)
from server.api.sse import EventBus
from server.ingest.adapters.claude_code_adapter import ClaudeCodeAdapter
from server.ingest.pipeline import IngestPipeline
from server.models.workspace import Workspace
from server.store.db import Database
from server.store.repos.outcomes import OutcomeRepo
from server.store.repos.workspaces import WorkspaceRepo
from server.util.ids import new_ulid

FIXTURES = Path(__file__).parent / "fixtures" / "ingest"


@pytest.fixture
def pipeline_bundle(tmp_path: Path) -> tuple[IngestPipeline, Database, str]:
    root = tmp_path / "proj"
    root.mkdir()
    db = Database(tmp_path / "cairn.db")
    ws_id = new_ulid()
    WorkspaceRepo.create(
        db.reader,
        Workspace(
            workspace_id=ws_id,
            root_path=str(root),
            name="proj",
            created_at="2026-01-01T00:00:00Z",
        ),
    )
    db.reader.commit()
    pipeline = IngestPipeline(db, ws_id, root, EventBus())
    return pipeline, db, ws_id


def test_outcome_row_upserted_after_ingest(
    pipeline_bundle: tuple[IngestPipeline, Database, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pipeline, db, ws_id = pipeline_bundle
    adapter = ClaudeCodeAdapter(pipeline.workspace_root, ws_id)
    fixture = FIXTURES / "wasteful_session.jsonl"
    pipeline._path_adapter[fixture.resolve()] = (adapter, "claude_code")
    monkeypatch.setattr("server.analyze.outcomes.test_command_for", lambda _project: None)
    result = pipeline.ingest_path(fixture)
    assert result is not None

    row = OutcomeRepo.get(db.reader, result.trace_id)
    assert row is not None
    assert row.trace_id == result.trace_id
    assert row.build_status == "unknown"
    assert row.captured_at is not None
    assert row.quality_score is not None
    assert row.quality_components is not None
    assert row.quality_weights is not None

    OutcomeRepo.upsert(
        db.reader,
        row.model_copy(
            update={
                "human_label": "up",
                "human_note": "Keep this label",
                "human_labeled_at": "2026-07-14T00:00:00Z",
            }
        ),
    )
    OutcomesView().compute(db.reader, result.trace_id)
    recomputed = OutcomeRepo.get(db.reader, result.trace_id)
    assert recomputed is not None
    assert recomputed.human_label == "up"
    assert recomputed.human_note == "Keep this label"


def test_success_component_is_graded_and_revert_reduces_it() -> None:
    common = {
        "commit_landed": True,
        "tests_run": 8,
        "tests_passed": 8,
        "tests_failed": 0,
        "build_status": "passed",
        "fixup_within_window": False,
        "waste_tokens": 0,
        "total_tokens": 100,
        "peak_context_pct": 20.0,
        "context_rot_penalty": 1.0,
        "retry_rate": 0.0,
        "error_rate": 0.0,
        "mahalanobis_distance": None,
        "drift_threshold": None,
    }
    clean = agent_quality_score(**common, reverted_within_window=False)
    reverted = agent_quality_score(**common, reverted_within_window=True)
    commit_only = agent_quality_score(
        **{
            **common,
            "tests_run": None,
            "tests_passed": None,
            "tests_failed": None,
            "build_status": "unknown",
        },
        reverted_within_window=False,
    )

    assert clean.components["success"] == 1.0
    assert reverted.components["success"] == 0.75
    assert commit_only.components["success"] == 0.25
    assert reverted.score < clean.score


def test_followup_signal_detects_same_file_revert_and_fixup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    responses = iter(
        [
            subprocess.CompletedProcess(
                args=[], returncode=0, stdout="2026-07-14T10:00:00+00:00\n", stderr=""
            ),
            subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="base\x00Original\nrev\x00Revert bad change\nfix\x00fixup! tests\n",
                stderr="",
            ),
        ]
    )
    monkeypatch.setattr(
        "server.analyze.outcomes._run_git", lambda *_args, **_kwargs: next(responses)
    )

    result = capture_followup_signals(
        tmp_path,
        "base",
        ["server/app.py"],
        window_hours=24,
    )

    assert result.reverted is True
    assert result.fixup is True
    assert result.commits == ["rev", "fix"]
    assert "same-file revert detected within 24h" in result.data_notes
