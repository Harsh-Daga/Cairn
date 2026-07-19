"""Content-addressed storage assessment (T06-06) — no CAS implementation."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from server.store.benchmark import PROFILES, generate_benchmark_ledger
from server.store.dedup_assessment import assess_content_dedup


def test_assess_content_dedup_on_small_fixture(tmp_path: Path) -> None:
    db_path = tmp_path / ".cairn" / "cairn.db"
    generate_benchmark_ledger(db_path, PROFILES["small"])
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    report = assess_content_dedup(conn)
    assert report["schema"] == "cairn.dedup_assessment.v1"
    assert report["span_count"] > 0
    assert report["fts"]["spans_fts"] is False
    assert report["recommendation"]["adopt_cas_in_1_2"] is False
    assert "worthwhile_on_this_ledger" in report["recommendation"]


def test_assess_content_dedup_detects_repeated_inline_text(tmp_path: Path) -> None:
    db_path = tmp_path / "led.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE workspaces (workspace_id TEXT PRIMARY KEY);
        CREATE TABLE traces (
          trace_id TEXT PRIMARY KEY,
          workspace_id TEXT NOT NULL
        );
        CREATE TABLE spans (
          span_id TEXT PRIMARY KEY,
          trace_id TEXT NOT NULL,
          seq INTEGER NOT NULL,
          kind TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'ok',
          text_inline TEXT,
          text_hash TEXT,
          args_hash TEXT
        );
        INSERT INTO workspaces VALUES ('ws1');
        INSERT INTO traces VALUES ('t1', 'ws1');
        """
    )
    blob = "x" * 200
    for i in range(5):
        conn.execute(
            "INSERT INTO spans VALUES (?, 't1', ?, 'tool_result', 'ok', ?, NULL, NULL)",
            (f"s{i}", i, blob),
        )
    conn.commit()
    report = assess_content_dedup(conn, workspace_id="ws1")
    assert report["text_hash"]["rows_with_hash"] == 5
    assert report["text_hash"]["distinct_hashes"] == 1
    assert report["text_hash"]["reuse_ratio"] == 0.8
    assert report["inline_text"]["rough_savings_chars"] == 800
