"""Build unified reports from capture sessions and provider runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cairn.artifacts.registry import ArtifactRegistry
from cairn.graph.engine import build_dependency_graph
from cairn.ingest.project_paths import resolve_git_root
from cairn.loader.toml import load_project
from cairn.render.bundle import bundle_payload_from_project
from cairn.render.capture_bundle import capture_bundle_from_project
from cairn.report.schema import REPORT_VERSION


def build_report(
    project_root: Path,
    *,
    session_id: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Resolve capture session or provider run and return a unified report."""
    if session_id and run_id:
        msg = "specify session_id or run_id, not both"
        raise ValueError(msg)
    if session_id:
        return report_from_capture(project_root, session_id)
    return report_from_provider(project_root, run_id)


def report_from_capture(project_root: Path, session_id: str) -> dict[str, Any]:
    root = resolve_git_root(project_root) or project_root.resolve()
    bundle = capture_bundle_from_project(root, session_id)
    session = bundle["session"]
    turns = bundle.get("turns", [])
    events = bundle.get("events", [])
    files = bundle.get("files", [])
    graphs = dict(bundle.get("graphs", {}))
    graphs.setdefault("dependency", {"nodes": [], "edges": [], "graph_kind": "dependency"})

    registry = ArtifactRegistry(root)
    try:
        ledger_artifacts = registry.list_for_run(str(session.get("run_id", "")))
    finally:
        registry.close()

    tool_usage = _tool_usage_from_events(events)
    artifacts = _artifact_inventory(files, ledger_artifacts)

    summary = {
        "title": _capture_title(turns),
        "status": session.get("status", "unknown"),
        "source": session.get("source"),
        "model": session.get("model"),
        "event_count": session.get("event_count", len(events)),
        "turn_count": len(turns),
        "cost": session.get("usage", {}).get("cost"),
        "input_tokens": session.get("usage", {}).get("input_tokens"),
        "output_tokens": session.get("usage", {}).get("output_tokens"),
    }

    return {
        "cairn_report_version": REPORT_VERSION,
        "kind": "capture",
        "summary": summary,
        "narrative": turns,
        "tool_usage": tool_usage,
        "artifacts": artifacts,
        "graphs": graphs,
        "reproducibility": {
            "session_id": session.get("external_id"),
            "run_id": session.get("run_id"),
            "git_commit": session.get("git", {}).get("commit"),
            "git_branch": session.get("git", {}).get("branch"),
            "model": session.get("model"),
            "cwd": session.get("cwd"),
            "started_at": session.get("started_at"),
            "ended_at": session.get("ended_at"),
        },
        "bundle": bundle,
    }


def report_from_provider(
    project_root: Path,
    run_id: str | None = None,
) -> dict[str, Any]:
    root = resolve_git_root(project_root) or project_root.resolve()
    project = load_project(root)
    bundle = bundle_payload_from_project(root, run_id)
    run = bundle.get("run", {})
    nodes = bundle.get("nodes", [])

    dependency = build_dependency_graph(project)
    execution = _provider_execution_graph(nodes)
    artifact = _provider_artifact_graph(nodes)

    summary = {
        "title": project.name,
        "status": run.get("status", "unknown"),
        "source": "provider",
        "model": _dominant_model(nodes),
        "node_count": len(nodes),
        "cost": sum(float(n.get("cost") or 0) for n in nodes),
        "input_tokens": sum(int(n.get("input_tokens") or 0) for n in nodes),
        "output_tokens": sum(int(n.get("output_tokens") or 0) for n in nodes),
    }

    return {
        "cairn_report_version": REPORT_VERSION,
        "kind": "provider",
        "summary": summary,
        "narrative": _provider_narrative(nodes),
        "tool_usage": _provider_tool_usage(nodes),
        "artifacts": _provider_artifacts(nodes),
        "graphs": {
            "execution": execution,
            "artifact": artifact,
            "dependency": dependency,
        },
        "reproducibility": {
            "run_id": run.get("run_id"),
            "project": project.name,
            "git_commit": run.get("git_commit"),
            "workflow_ref": run.get("workflow_ref"),
            "context_digest": run.get("context_digest"),
            "started_at": run.get("started_at"),
            "ended_at": run.get("ended_at"),
        },
        "bundle": bundle,
    }


def _capture_title(turns: list[dict[str, Any]]) -> str:
    if not turns:
        return "Capture session"
    first = turns[0].get("user_text") or turns[0].get("title") or ""
    if isinstance(first, str) and first.strip():
        line = first.strip().splitlines()[0]
        return line[:120] + ("…" if len(line) > 120 else "")
    return "Capture session"


def _tool_usage_from_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results_by_id: dict[str, dict[str, Any]] = {}
    for event in events:
        if event.get("type") == "tool_result":
            tool_use_id = event.get("tool_use_id")
            if isinstance(tool_use_id, str):
                results_by_id[tool_use_id] = event

    usage: list[dict[str, Any]] = []
    for event in events:
        if event.get("type") != "tool_call":
            continue
        tool_use_id = event.get("tool_use_id")
        result = results_by_id.get(str(tool_use_id)) if tool_use_id else None
        usage.append(
            {
                "seq": event.get("seq"),
                "tool_use_id": tool_use_id,
                "name": event.get("name"),
                "is_error": bool(result.get("is_error")) if result else None,
                "result_hash": result.get("result_hash") if result else None,
            }
        )
    return usage


def _artifact_inventory(
    files: list[dict[str, Any]],
    ledger_artifacts: list[Any],
) -> list[dict[str, Any]]:
    inventory: list[dict[str, Any]] = []
    seen: set[str] = set()

    for art in ledger_artifacts:
        inventory.append(art.to_dict())
        seen.add(art.content_hash)

    for row in files:
        path_rel = row.get("path_rel")
        content_hash = row.get("after_hash") or row.get("before_hash")
        if not isinstance(path_rel, str):
            continue
        key = str(content_hash or path_rel)
        if key in seen:
            continue
        seen.add(key)
        inventory.append(
            {
                "content_hash": content_hash,
                "kind": "file",
                "path_rel": path_rel,
                "snapshot_quality": row.get("snapshot_quality"),
            }
        )
    return inventory


def _provider_narrative(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for node in sorted(nodes, key=lambda n: str(n.get("node_id", ""))):
        cards.append(
            {
                "node_id": node.get("node_id"),
                "step": node.get("step"),
                "kind": node.get("kind"),
                "status": node.get("status"),
                "model": node.get("model"),
                "summary": _node_summary(node),
            }
        )
    return cards


def _node_summary(node: dict[str, Any]) -> str:
    output = node.get("output") or {}
    text = output.get("text") if isinstance(output, dict) else None
    if isinstance(text, str) and text.strip():
        line = text.strip().splitlines()[0]
        return line[:160] + ("…" if len(line) > 160 else "")
    return f"{node.get('step', 'step')} ({node.get('status', 'unknown')})"


def _provider_tool_usage(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "node_id": node.get("node_id"),
            "step": node.get("step"),
            "kind": node.get("kind"),
            "status": node.get("status"),
            "model": node.get("model"),
            "duration_ms": node.get("duration_ms"),
        }
        for node in nodes
    ]


def _provider_artifacts(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for node in nodes:
        output_hash = node.get("output_hash")
        if not output_hash:
            continue
        artifacts.append(
            {
                "content_hash": output_hash,
                "kind": "output",
                "path_rel": None,
                "node_id": node.get("node_id"),
                "step": node.get("step"),
            }
        )
    return artifacts


def _provider_execution_graph(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    graph_nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for node in nodes:
        node_id = str(node.get("node_id", ""))
        graph_nodes.append(
            {
                "id": node_id,
                "type": node.get("kind", "step"),
                "label": str(node.get("step", node_id)),
            }
        )
        for inp in node.get("inputs") or []:
            if inp.get("kind") == "upstream" and inp.get("node_id"):
                edges.append(
                    {
                        "from": str(inp["node_id"]),
                        "to": node_id,
                        "kind": "depends_on",
                    }
                )
    return {"nodes": graph_nodes, "edges": edges, "graph_kind": "execution"}


def _provider_artifact_graph(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    graph_nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for node in nodes:
        output_hash = node.get("output_hash")
        if not output_hash:
            continue
        node_id = str(node.get("node_id", ""))
        graph_nodes.append(
            {
                "id": output_hash,
                "type": "output",
                "label": str(node.get("step", node_id)),
            }
        )
        for inp in node.get("inputs") or []:
            if inp.get("kind") == "upstream" and inp.get("output_hash"):
                edges.append(
                    {
                        "from": str(inp["output_hash"]),
                        "to": output_hash,
                        "kind": "derived_from",
                    }
                )
    return {"nodes": graph_nodes, "edges": edges, "graph_kind": "artifact"}


def _dominant_model(nodes: list[dict[str, Any]]) -> str | None:
    models = [str(n["model"]) for n in nodes if n.get("model")]
    if not models:
        return None
    return max(set(models), key=models.count)
