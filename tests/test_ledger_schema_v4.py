"""Phase 4 storage layer: schema v4 migration and repository helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from cairn.ledger.schema import SCHEMA_VERSION, migrate
from cairn.ledger.storage import (
    get_artifact,
    get_workflow_run,
    list_artifacts_for_run,
    list_context_assets,
    list_lineage_edges,
    record_lineage_edge,
    record_workflow_run,
    register_artifact,
    upsert_context_asset,
)
from cairn.model.artifact import Artifact, LineageEdge
from cairn.model.workflow import WorkflowRun


def _v3_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    migrate(conn)
    conn.execute("PRAGMA user_version = 3")
    conn.commit()
    conn.close()


def test_schema_version_is_four() -> None:
    assert SCHEMA_VERSION == 4


def test_migrate_v3_to_v4_adds_tables(tmp_path: Path) -> None:
    db = tmp_path / "ledger.db"
    _v3_db(db)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    migrate(conn)
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    assert version == 4
    tables = {
        r[0]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    assert {
        "context_assets",
        "artifacts",
        "workflow_runs",
        "lineage_edges",
    } <= tables
    runs_cols = {r[1] for r in conn.execute("PRAGMA table_info(runs)").fetchall()}
    assert {"workflow_ref", "context_digest"} <= runs_cols
    conn.close()


def test_storage_round_trip(tmp_path: Path) -> None:
    conn = sqlite3.connect(tmp_path / "ledger.db")
    conn.row_factory = sqlite3.Row
    migrate(conn)

    asset = upsert_context_asset(
        conn,
        path_rel="docs/brief.md",
        content_hash="hash-brief",
        mime="text/markdown",
        tags=("docs",),
    )
    assert asset.path_rel == "docs/brief.md"
    assert list_context_assets(conn)[0].content_hash == "hash-brief"

    artifact = register_artifact(
        conn,
        Artifact(
            content_hash="out-hash",
            kind="report",
            path_rel="outputs/report.md",
            mime="text/markdown",
            run_id="run-1",
            session_id=None,
            size_bytes=512,
            metadata={"title": "Summary"},
        ),
    )
    loaded = get_artifact(conn, "out-hash")
    assert loaded is not None
    assert loaded.metadata["title"] == "Summary"
    assert len(list_artifacts_for_run(conn, "run-1")) == 1

    record_workflow_run(
        conn,
        WorkflowRun(
            run_id="run-1",
            workflow_ref="docs@v1",
            context_digest="ctx-digest",
            git_commit="abc",
        ),
    )
    wf = get_workflow_run(conn, "run-1")
    assert wf is not None
    assert wf.workflow_ref == "docs@v1"

    record_lineage_edge(
        conn,
        LineageEdge("derived_from", "out-hash", "hash-brief"),
        run_id="run-1",
    )
    edges = list_lineage_edges(conn, run_id="run-1")
    assert len(edges) == 1
    assert edges[0].relation == "derived_from"
    assert artifact.content_hash == "out-hash"
    conn.close()
