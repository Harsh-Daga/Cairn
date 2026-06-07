"""Assemble the cairn-data JSON payload from a run + project + CAS (R15)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cairn.cache.cas import ContentAddressableStore
from cairn.graph.builder import BuiltGraph, build_graph
from cairn.ledger.run_record import RunRecord, load_run_record
from cairn.loader.refs import parse_dep_expr
from cairn.loader.sources import resolve_source_files
from cairn.loader.toml import load_project
from cairn.model.project import Project
from cairn.util.canonical import canonical_json

DEFAULT_INLINE_CAP_BYTES = 256 * 1024


def _rel_path(project_root: Path, path: str | Path) -> str:
    root = project_root.resolve()
    p = Path(path)
    resolved = p.resolve() if p.is_absolute() else (root / p).resolve()
    try:
        return str(resolved.relative_to(root))
    except ValueError as exc:
        msg = f"source path {resolved!s} is outside project root {root!s}"
        raise ValueError(msg) from exc


def _node_inputs(
    project: Project,
    graph: BuiltGraph,
    node_id: str,
    nodes_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    node = next(n for n in graph.nodes if n.node_id == node_id)
    inputs: list[dict[str, Any]] = []

    if node.kind == "map" and node.item is not None:
        inputs.append(
            {
                "kind": "source",
                "path": _rel_path(project.root, node.item.path),
                "content_hash": node.item.content_hash,
            }
        )
        return inputs

    step = project.steps[node.step]
    if step.inputs is None:
        return inputs

    for expr in step.inputs:
        dep = parse_dep_expr(expr)
        if dep.kind == "source":
            for sf in resolve_source_files(project, dep.name):
                inputs.append(
                    {
                        "kind": "source",
                        "path": _rel_path(project.root, sf.path),
                        "content_hash": sf.content_hash,
                    }
                )
        else:
            upstream = [n for n in graph.nodes if n.step == dep.name]
            for up in sorted(upstream, key=lambda n: n.node_id):
                up_data = nodes_by_id.get(up.node_id, {})
                inputs.append(
                    {
                        "kind": "upstream",
                        "node_id": up.node_id,
                        "output_hash": up_data.get("output_hash"),
                    }
                )
    return inputs


def _resolve_output(
    cas: ContentAddressableStore,
    output_hash: str | None,
    *,
    inline_cap: int,
) -> dict[str, Any]:
    if not output_hash:
        return {"text": "", "truncated": False, "output_hash": None}
    blob = cas.read(output_hash)
    if blob is None:
        return {
            "text": "",
            "truncated": False,
            "output_hash": output_hash,
            "missing": True,
        }
    if len(blob) <= inline_cap:
        return {
            "text": blob.decode("utf-8", errors="replace"),
            "truncated": False,
            "output_hash": output_hash,
        }
    head = blob[:inline_cap].decode("utf-8", errors="replace")
    return {
        "text": head,
        "truncated": True,
        "output_hash": output_hash,
        "full_size_bytes": len(blob),
        "note": "Full output stored in CAS; inline view truncated.",
    }


def assemble_bundle_payload(
    project: Project,
    graph: BuiltGraph,
    record: RunRecord,
    cas: ContentAddressableStore,
    *,
    inline_cap: int = DEFAULT_INLINE_CAP_BYTES,
) -> dict[str, Any]:
    """Pure function: run record + CAS → embeddable JSON (sorted keys via canonical_json)."""
    nodes_by_id: dict[str, dict[str, Any]] = {}
    bundle_nodes: list[dict[str, Any]] = []

    for raw in record.nodes:
        node_id = str(raw["node_id"])
        nodes_by_id[node_id] = raw

    for raw in sorted(record.nodes, key=lambda n: str(n["node_id"])):
        node_id = str(raw["node_id"])
        output_hash = raw.get("output_hash")
        output = _resolve_output(cas, output_hash, inline_cap=inline_cap)
        params = raw.get("params")
        if isinstance(params, str):
            params = json.loads(params)
        bundle_nodes.append(
            {
                "node_id": node_id,
                "step": raw["step"],
                "item_id": raw.get("item_id"),
                "kind": raw["kind"],
                "action_key": raw["action_key"],
                "output_hash": output_hash,
                "status": raw["status"],
                "model": raw["model"],
                "params": params,
                "input_tokens": raw["input_tokens"],
                "output_tokens": raw["output_tokens"],
                "cost": raw.get("cost"),
                "duration_ms": raw.get("duration_ms"),
                "started_at": raw["started_at"],
                "ended_at": raw["ended_at"],
                "rendered_prompt": raw.get("rendered_prompt", ""),
                "system_prompt": raw.get("system_prompt", ""),
                "inputs": _node_inputs(project, graph, node_id, nodes_by_id),
                "output": output,
            }
        )

    return {
        "cairn_bundle_version": 1,
        "project": {
            "name": project.name,
            "root_label": project.name,
        },
        "run": record.run,
        "nodes": bundle_nodes,
    }


def load_record_for_render(
    project_root: Path,
    run_id: str | None,
) -> RunRecord:
    runs_dir = project_root / "runs"
    if run_id is None:
        json_files = sorted(runs_dir.glob("*.json"), reverse=True) if runs_dir.is_dir() else []
        if not json_files:
            msg = "no runs found; run `cairn build` first"
            raise FileNotFoundError(msg)
        return load_run_record(json_files[0])
    path = runs_dir / f"{run_id}.json"
    if not path.is_file():
        msg = f"run not found: {run_id}"
        raise FileNotFoundError(msg)
    return load_run_record(path)


def bundle_payload_from_project(
    project_root: Path,
    run_id: str | None = None,
    *,
    inline_cap: int = DEFAULT_INLINE_CAP_BYTES,
) -> dict[str, Any]:
    project = load_project(project_root)
    graph = build_graph(project)
    record = load_record_for_render(project_root, run_id)
    cas = ContentAddressableStore(project_root / ".cairn")
    return assemble_bundle_payload(project, graph, record, cas, inline_cap=inline_cap)


def bundle_json(
    project_root: Path,
    run_id: str | None = None,
    *,
    inline_cap: int = DEFAULT_INLINE_CAP_BYTES,
) -> str:
    payload = bundle_payload_from_project(project_root, run_id, inline_cap=inline_cap)
    return canonical_json(payload)
