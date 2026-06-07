"""Build runs/<id>.json from ledger rows (and the inverse loader)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from cairn.ledger.ledger import Ledger, NodeRecord, RunSummary
from cairn.util.canonical import canonical_json


@dataclass(frozen=True)
class RunRecord:
    run: dict[str, Any]
    nodes: tuple[dict[str, Any], ...]


def _summary_dict(summary: RunSummary) -> dict[str, Any]:
    return {
        "run_id": summary.run_id,
        "started_at": summary.started_at,
        "ended_at": summary.ended_at,
        "status": summary.status,
        "total_cost": summary.total_cost,
        "total_input_tokens": summary.total_input_tokens,
        "total_output_tokens": summary.total_output_tokens,
        "cairn_version": summary.cairn_version,
        "key_version": summary.key_version,
        "git_commit": summary.git_commit,
    }


def _node_dict(node: NodeRecord) -> dict[str, Any]:
    data = asdict(node)
    data["params"] = json.loads(node.params_json)
    del data["params_json"]
    return data


def build_run_record(summary: RunSummary, nodes: list[NodeRecord]) -> RunRecord:
    return RunRecord(
        run=_summary_dict(summary),
        nodes=tuple(_node_dict(n) for n in nodes),
    )


def run_record_to_dict(record: RunRecord) -> dict[str, Any]:
    return {"run": record.run, "nodes": list(record.nodes)}


def run_record_json(record: RunRecord) -> str:
    return canonical_json(run_record_to_dict(record))


def write_run_json(project_root: Path, ledger: Ledger, run_id: str) -> Path:
    summary, nodes = ledger.load_run(run_id)
    record = build_run_record(summary, nodes)
    runs_dir = project_root / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    out_path = runs_dir / f"{run_id}.json"
    out_path.write_text(run_record_json(record) + "\n", encoding="utf-8")
    return out_path


def load_run_record(path: Path) -> RunRecord:
    data = json.loads(path.read_text(encoding="utf-8"))
    return RunRecord(
        run=dict(data["run"]),
        nodes=tuple(dict(n) for n in data["nodes"]),
    )
