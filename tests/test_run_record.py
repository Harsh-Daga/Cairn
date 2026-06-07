"""run.json mirror and golden stability tests."""

from __future__ import annotations

import json
from pathlib import Path

from cairn.ledger.ledger import Ledger
from cairn.ledger.run_record import load_run_record, write_run_json
from cairn.util.canonical import canonical_json
from tests.test_invariants import _build


def test_run_json_mirrors_ledger(project_dir: Path, fixtures_dir: Path) -> None:
    result = _build(project_dir, fixtures_dir)
    assert result.run_id
    path = project_dir / "runs" / f"{result.run_id}.json"
    record = load_run_record(path)
    ledger = Ledger(project_dir / ".cairn" / "ledger.db")
    try:
        summary, nodes = ledger.load_run(result.run_id)
    finally:
        ledger.close()
    assert record.run["run_id"] == summary.run_id
    assert len(record.nodes) == len(nodes)
    assert {n["node_id"] for n in record.nodes} == {n.node_id for n in nodes}


def test_run_json_is_canonical_and_stable(project_dir: Path, fixtures_dir: Path) -> None:
    result = _build(project_dir, fixtures_dir)
    path = project_dir / "runs" / f"{result.run_id}.json"
    text = path.read_text(encoding="utf-8")
    parsed = json.loads(text)
    assert text.strip() == canonical_json(parsed)
    second = _build(project_dir, fixtures_dir)
    second_path = project_dir / "runs" / f"{second.run_id}.json"
    # Structure keys stable; run_id/timestamps differ
    first_keys = set(json.loads(path.read_text(encoding="utf-8"))["nodes"][0].keys())
    second_keys = set(json.loads(second_path.read_text(encoding="utf-8"))["nodes"][0].keys())
    assert first_keys == second_keys


def test_write_run_json_roundtrip(project_dir: Path, fixtures_dir: Path) -> None:
    result = _build(project_dir, fixtures_dir)
    ledger = Ledger(project_dir / ".cairn" / "ledger.db")
    try:
        out = write_run_json(project_dir, ledger, result.run_id)
        reloaded = load_run_record(out)
        assert reloaded.run["run_id"] == result.run_id
    finally:
        ledger.close()
