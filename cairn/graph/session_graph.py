"""Capture micro DAG linker (R19.10)."""

from __future__ import annotations

from typing import Any

_WRITE_TOOL_NAMES = frozenset({"edit", "write", "apply_patch", "multiedit"})


def build_session_graph(events: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Infer temporal, causal, data, and delegation edges from ordered events."""
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    node_for_seq: dict[int, str] = {}

    for event in sorted(events, key=lambda e: int(e.get("seq", 0))):
        seq = int(event["seq"])
        event_type = str(event.get("type", "unknown"))
        node_id = f"e{seq}"
        node_for_seq[seq] = node_id
        nodes.append(
            {
                "id": node_id,
                "type": event_type,
                "label": _event_label(event),
                "seq": seq,
            }
        )

    seqs = sorted(node_for_seq.keys())
    for idx in range(len(seqs) - 1):
        edges.append(
            {
                "from": node_for_seq[seqs[idx]],
                "to": node_for_seq[seqs[idx + 1]],
                "kind": "temporal",
            }
        )

    tool_call_seq: dict[str, int] = {}
    for event in events:
        if event.get("type") != "tool_call":
            continue
        tool_use_id = event.get("tool_use_id")
        if isinstance(tool_use_id, str):
            tool_call_seq[tool_use_id] = int(event["seq"])

    for event in events:
        if event.get("type") != "tool_result":
            continue
        tool_use_id = event.get("tool_use_id")
        if not isinstance(tool_use_id, str):
            continue
        call_seq = tool_call_seq.get(tool_use_id)
        if call_seq is None:
            continue
        edges.append(
            {
                "from": f"e{call_seq}",
                "to": f"e{int(event['seq'])}",
                "kind": "causal",
            }
        )

    read_by_path: dict[str, int] = {}
    write_by_path: dict[str, int] = {}
    for event in events:
        seq = int(event["seq"])
        if event.get("type") == "file_snapshot":
            path_rel = event.get("path_rel")
            if not isinstance(path_rel, str):
                continue
            op = str(event.get("op", "read"))
            if op == "read":
                read_by_path[path_rel] = seq
            elif op == "edit":
                write_by_path[path_rel] = seq
        elif event.get("type") == "tool_call":
            path_rel = _tool_path(event)
            if path_rel and str(event.get("name", "")).lower() in _WRITE_TOOL_NAMES:
                write_by_path[path_rel] = seq

    for path_rel, write_seq in write_by_path.items():
        read_seq = read_by_path.get(path_rel)
        if read_seq is not None and read_seq < write_seq:
            edges.append(
                {
                    "from": f"e{read_seq}",
                    "to": f"e{write_seq}",
                    "kind": "data",
                    "path_rel": path_rel,
                }
            )

    for event in events:
        if event.get("type") != "sub_agent":
            continue
        parent_seq = int(event["seq"])
        child_id = event.get("child_session_id")
        label = str(child_id) if isinstance(child_id, str) else "sub_agent"
        child_node = f"sub:{label}"
        nodes.append(
            {
                "id": child_node,
                "type": "sub_agent",
                "label": label,
                "seq": parent_seq,
            }
        )
        edges.append(
            {
                "from": f"e{parent_seq}",
                "to": child_node,
                "kind": "delegation",
            }
        )

    return {"nodes": nodes, "edges": edges}


def _event_label(event: dict[str, Any]) -> str:
    event_type = str(event.get("type", "event"))
    if event_type == "tool_call":
        name = event.get("name")
        return f"{name}" if isinstance(name, str) else "tool_call"
    if event_type == "user_prompt":
        text = event.get("text_inline")
        if isinstance(text, str) and text:
            return text[:80]
        return "user_prompt"
    if event_type == "file_snapshot":
        path_rel = event.get("path_rel")
        return str(path_rel) if isinstance(path_rel, str) else "file_snapshot"
    return event_type


def _tool_path(event: dict[str, Any]) -> str | None:
    args = event.get("args_inline")
    if not isinstance(args, dict):
        return None
    for key in ("path", "file_path", "target_file"):
        val = args.get(key)
        if isinstance(val, str) and val:
            return val
    return None
