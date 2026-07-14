"""Fingerprint analyzer tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pytest

from server.analyze.fingerprint import VECTOR_DIM, FingerprintView
from server.analyze.fingerprint_math import detect_drift, ledoit_wolf_covariance
from server.api.sse import EventBus
from server.ingest.adapters.claude_code_adapter import ClaudeCodeAdapter
from server.ingest.pipeline import IngestPipeline
from server.models.workspace import Workspace
from server.store.db import Database
from server.store.repos.fingerprints import FingerprintRepo
from server.store.repos.workspaces import WorkspaceRepo
from server.util.ids import new_ulid

FIXTURES = Path(__file__).parent / "fixtures" / "ingest"


@pytest.fixture
def ingested_trace(tmp_path: Path) -> tuple[Database, str]:
    root = tmp_path / "proj"
    root.mkdir()
    db = Database(tmp_path / "cairn.db")
    workspace_id = new_ulid()
    WorkspaceRepo.create(
        db.reader,
        Workspace(
            workspace_id=workspace_id,
            root_path=str(root),
            name="proj",
            created_at="2026-01-01T00:00:00Z",
        ),
    )
    db.reader.commit()
    pipeline = IngestPipeline(db, workspace_id, root, EventBus())
    adapter = ClaudeCodeAdapter(root, workspace_id)
    fixture = FIXTURES / "wasteful_session.jsonl"
    pipeline._path_adapter[fixture.resolve()] = (adapter, "claude_code")
    result = pipeline.ingest_path(fixture)
    assert result is not None
    return db, result.trace_id


def test_fingerprint_vector_non_empty(ingested_trace: tuple[Database, str]) -> None:
    db, trace_id = ingested_trace

    def _compute(conn: sqlite3.Connection) -> tuple[int, bool]:
        view = FingerprintView()
        view.compute(conn, trace_id)
        row = FingerprintRepo.get(conn, trace_id)
        assert row is not None
        return len(row.vector), any(value > 0 for value in row.vector)

    vector_len, has_signal = db.write(_compute)
    assert vector_len == VECTOR_DIM
    assert has_signal


def test_joint_shock_requires_twenty_baseline_sessions() -> None:
    baseline = [[float(i % 3)] * VECTOR_DIM for i in range(12)]
    result = detect_drift([10.0] * VECTOR_DIM, baseline)

    assert result.kind == "insufficient_baseline"
    assert result.data_notes == ["12/20 sessions collected"]


def test_ledoit_wolf_shrinkage_regularizes_collinear_covariance() -> None:
    base = np.arange(20, dtype=float)
    matrix = np.column_stack([base, base * 2.0, base * 3.0])
    covariance, shrinkage = ledoit_wolf_covariance(matrix)

    assert 0.0 < shrinkage <= 1.0
    assert np.all(np.linalg.eigvalsh(covariance) > 0)


def test_joint_shock_runs_with_twenty_session_shrinkage_baseline() -> None:
    baseline = [
        [float(((sample + 1) * (axis + 3)) % 11) / 10.0 for axis in range(VECTOR_DIM)]
        for sample in range(20)
    ]
    result = detect_drift([8.0] * VECTOR_DIM, baseline)

    assert result.kind == "joint_shock"
    assert result.drift is True
    assert any(note.startswith("Ledoit-Wolf shrinkage=") for note in result.data_notes)
