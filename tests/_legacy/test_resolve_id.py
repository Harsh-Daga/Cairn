"""Tests for cairn.ledger.resolve.resolve_id."""

from __future__ import annotations

from pathlib import Path

import pytest

from cairn.ledger.ledger import Ledger
from cairn.ledger.resolve import (
    AmbiguousIdError,
    IdNotFoundError,
    resolve_id,
)


def _make_ledger(tmp_path: Path) -> Ledger:
    db = tmp_path / ".cairn" / "ledger.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    ledger = Ledger(db)
    conn = ledger.connection
    rows = [
        ("run-aaaa1111", "sess-claude-001", "claude-code", "2026-06-01T10:00:00"),
        ("run-aaaa2222", "sess-claude-002", "claude-code", "2026-06-02T10:00:00"),
        ("run-bbbb3333", None, "build", "2026-06-03T10:00:00"),
    ]
    for run_id, ext, source, started in rows:
        conn.execute(
            "INSERT INTO runs (run_id, external_id, source, started_at, status, "
            "total_input_tokens, total_output_tokens) VALUES (?, ?, ?, ?, 'ok', 0, 0)",
            (run_id, ext, source, started),
        )
    conn.commit()
    return ledger


def test_resolve_last(tmp_path: Path) -> None:
    ledger = _make_ledger(tmp_path)
    try:
        resolved = resolve_id(ledger, "last")
        assert resolved.run_id == "run-bbbb3333"
    finally:
        ledger.close()


def test_resolve_full_run_id(tmp_path: Path) -> None:
    ledger = _make_ledger(tmp_path)
    try:
        assert resolve_id(ledger, "run-aaaa1111").external_id == "sess-claude-001"
    finally:
        ledger.close()


def test_resolve_full_external_id(tmp_path: Path) -> None:
    ledger = _make_ledger(tmp_path)
    try:
        assert resolve_id(ledger, "sess-claude-002").run_id == "run-aaaa2222"
    finally:
        ledger.close()


def test_resolve_unique_prefix(tmp_path: Path) -> None:
    ledger = _make_ledger(tmp_path)
    try:
        assert resolve_id(ledger, "run-bbbb").run_id == "run-bbbb3333"
        assert resolve_id(ledger, "sess-claude-001").run_id == "run-aaaa1111"
    finally:
        ledger.close()


def test_resolve_ambiguous_prefix(tmp_path: Path) -> None:
    ledger = _make_ledger(tmp_path)
    try:
        with pytest.raises(AmbiguousIdError) as exc:
            resolve_id(ledger, "run-aaaa")
        assert len(exc.value.candidates) == 2
    finally:
        ledger.close()


def test_resolve_not_found(tmp_path: Path) -> None:
    ledger = _make_ledger(tmp_path)
    try:
        with pytest.raises(IdNotFoundError):
            resolve_id(ledger, "nope-zzzz")
    finally:
        ledger.close()
