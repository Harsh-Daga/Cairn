"""Ledger schema, migration, and run recording tests (R14)."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from cairn.cache.action_cache import ActionCache
from cairn.ledger.ledger import Ledger
from cairn.ledger.schema import SCHEMA_VERSION, migrate
from tests.test_invariants import _build


def _legacy_ac_only_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE action_cache (
          action_key TEXT PRIMARY KEY,
          output_hash TEXT NOT NULL,
          kind TEXT NOT NULL,
          created_at TEXT NOT NULL,
          last_used_at TEXT NOT NULL,
          model TEXT
        );
        INSERT INTO action_cache VALUES (
          'legacy-key', 'abc123', 'chat', '2020-01-01T00:00:00+00:00',
          '2020-01-01T00:00:00+00:00', 'gpt-4o-mini'
        );
        PRAGMA user_version = 1;
        """
    )
    conn.commit()
    conn.close()


def test_schema_version_is_two() -> None:
    assert SCHEMA_VERSION == 2


def test_migrate_from_ac_only_preserves_rows(tmp_path: Path) -> None:
    db = tmp_path / "ledger.db"
    _legacy_ac_only_db(db)
    conn = sqlite3.connect(db)
    migrate(conn)
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    assert version == 2
    row = conn.execute(
        "SELECT output_hash FROM action_cache WHERE action_key = 'legacy-key'"
    ).fetchone()
    assert row[0] == "abc123"
    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert {"runs", "nodes", "tool_calls", "cas_refs", "action_cache"} <= tables
    conn.close()


def test_ledger_begin_finish_run(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "ledger.db")
    try:
        run_id = ledger.begin_run(tmp_path)
        ledger.record_node(
            run_id,
            node_id="n1",
            step="s",
            item_id=None,
            kind="single",
            action_key="k",
            output_hash="h",
            status="ran",
            model="m",
            params={"max_tokens": 100},
            input_tokens=1,
            output_tokens=2,
            cost=0.001,
            duration_ms=10,
            started_at=datetime.now(UTC).isoformat(),
            ended_at=datetime.now(UTC).isoformat(),
            rendered_prompt="p",
            system_prompt="sys",
        )
        ledger.record_cas_ref("h", run_id, "n1")
        ledger.finish_run(
            run_id,
            "success",
            total_cost=0.001,
            total_input_tokens=1,
            total_output_tokens=2,
        )
        summary, nodes = ledger.load_run(run_id)
        assert summary.status == "success"
        assert len(nodes) == 1
        assert nodes[0].node_id == "n1"
    finally:
        ledger.close()


def test_build_writes_run_and_nodes(project_dir: Path, fixtures_dir: Path) -> None:
    result = _build(project_dir, fixtures_dir)
    assert result.run_id is not None
    run_json = project_dir / "runs" / f"{result.run_id}.json"
    assert run_json.is_file()

    ledger = Ledger(project_dir / ".cairn" / "ledger.db")
    try:
        assert ledger.node_count(result.run_id) == len(result.nodes)
        _, nodes = ledger.load_run(result.run_id)
        statuses = {n.node_id: n.status for n in nodes}
        assert all(s in ("ran", "cached") for s in statuses.values())
    finally:
        ledger.close()


def test_cached_build_still_records_nodes(project_dir: Path, fixtures_dir: Path) -> None:
    first = _build(project_dir, fixtures_dir)
    second = _build(project_dir, fixtures_dir)
    assert second.run_id != first.run_id
    ledger = Ledger(project_dir / ".cairn" / "ledger.db")
    try:
        _, nodes = ledger.load_run(second.run_id)
        assert all(n.status == "cached" for n in nodes)
    finally:
        ledger.close()


def test_action_cache_uses_ledger_connection(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "ledger.db")
    try:
        ac = ActionCache(ledger.connection)
        ac.put("k", "h", kind="chat", model="m")
        assert ledger.ac.get("k") == "h"
    finally:
        ledger.close()
