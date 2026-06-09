"""Precompute SVG positions for capture session graphs (R19.12)."""

from __future__ import annotations

from typing import Any

from cairn.util.canonical import hash_obj

_LAYOUT_CACHE: dict[str, dict[str, Any]] = {}
_MAX_LAYOUT_CACHE = 256

_COL_WIDTH = 220
_ROW_HEIGHT = 72
_MARGIN_X = 48
_MARGIN_Y = 48
_TURN_NODE_WIDTH = 300
_TURN_NODE_HEIGHT = 72
_TURN_ROW_HEIGHT = 96
_DISPLAY_EVENT_THRESHOLD = 48

_TYPE_COLUMN = {
    "user_prompt": 0,
    "assistant_message": 1,
    "tool_call": 2,
    "tool_result": 3,
    "file_snapshot": 3,
    "sub_agent": 1,
    "error": 1,
}


def layout_session_graph(graph: dict[str, Any]) -> dict[str, Any]:
    cache_key = hash_obj(
        {
            "nodes": graph.get("nodes") or [],
            "edges": graph.get("edges") or [],
        }
    )
    cached = _LAYOUT_CACHE.get(cache_key)
    if cached is not None:
        return cached

    result = _layout_session_graph(graph)
    if len(_LAYOUT_CACHE) >= _MAX_LAYOUT_CACHE:
        _LAYOUT_CACHE.clear()
    _LAYOUT_CACHE[cache_key] = result
    return result


def _layout_session_graph(graph: dict[str, Any]) -> dict[str, Any]:
    nodes = list(graph.get("nodes") or [])
    edges = list(graph.get("edges") or [])
    if not nodes:
        return {
            "nodes": [],
            "edges": edges,
            "layout": "layered-dag",
            "width": 0,
            "height": 0,
            "mode": "events",
            "event_count": 0,
        }

    by_seq: dict[int, list[dict[str, Any]]] = {}
    max_seq = 0
    for node in nodes:
        seq = int(node.get("seq", 0))
        max_seq = max(max_seq, seq)
        by_seq.setdefault(seq, []).append(node)

    positioned: list[dict[str, Any]] = []
    layer_rows: dict[int, int] = {}

    for seq in sorted(by_seq.keys()):
        row_nodes = sorted(
            by_seq[seq],
            key=lambda n: _TYPE_COLUMN.get(str(n.get("type", "")), 2),
        )
        for node in row_nodes:
            node_type = str(node.get("type", "unknown"))
            col = _TYPE_COLUMN.get(node_type, 2)
            stack = layer_rows.get(col, 0)
            layer_rows[col] = stack + 1
            x = _MARGIN_X + col * _COL_WIDTH
            y = _MARGIN_Y + (seq - 1) * _ROW_HEIGHT + stack * 18
            positioned.append(
                {
                    **node,
                    "x": x,
                    "y": y,
                    "layer": seq,
                    "column": col,
                }
            )

    width = _MARGIN_X * 2 + 3 * _COL_WIDTH + 120
    height = _MARGIN_Y * 2 + max(max_seq, 1) * _ROW_HEIGHT + 40

    return {
        "nodes": positioned,
        "edges": edges,
        "layout": "layered-dag",
        "width": width,
        "height": height,
        "mode": "events",
        "event_count": len(positioned),
    }


def build_display_graph(
    events: list[dict[str, Any]],
    turns: list[dict[str, Any]],
    event_graph: dict[str, Any],
) -> dict[str, Any]:
    """Use turn-level graph when event DAG is too tall for the SVG viewport."""
    if len(events) <= _DISPLAY_EVENT_THRESHOLD:
        return {**event_graph, "mode": "events", "event_count": len(events)}
    return layout_turn_graph(turns)


def layout_turn_graph(turns: list[dict[str, Any]]) -> dict[str, Any]:
    if not turns:
        return {
            "nodes": [],
            "edges": [],
            "layout": "turn-dag",
            "width": 0,
            "height": 0,
            "mode": "turns",
            "event_count": 0,
            "turn_count": 0,
        }

    nodes: list[dict[str, Any]] = []
    for idx, turn in enumerate(turns):
        turn_id = int(turn["turn_id"])
        nodes.append(
            {
                "id": f"t{turn_id}",
                "type": "turn",
                "title": f"Turn {turn_id}",
                "label": _turn_label(turn),
                "seq": int(turn.get("seq_start", turn_id)),
                "turn_id": turn_id,
                "tool_count": int(turn.get("tool_count", 0)),
                "x": _MARGIN_X,
                "y": _MARGIN_Y + idx * _TURN_ROW_HEIGHT,
                "layer": turn_id,
                "column": 0,
            }
        )

    edges: list[dict[str, Any]] = []
    for prev, nxt in zip(nodes, nodes[1:], strict=False):
        edges.append({"from": prev["id"], "to": nxt["id"], "kind": "temporal"})

    width = _MARGIN_X * 2 + _TURN_NODE_WIDTH
    height = _MARGIN_Y * 2 + len(turns) * _TURN_ROW_HEIGHT + 24

    return {
        "nodes": nodes,
        "edges": edges,
        "layout": "turn-dag",
        "width": width,
        "height": height,
        "mode": "turns",
        "event_count": sum(int(t.get("tool_count", 0)) for t in turns),
        "turn_count": len(turns),
    }


def _turn_label(turn: dict[str, Any]) -> str:
    text = turn.get("user_text")
    if isinstance(text, str) and text.strip():
        collapsed = " ".join(text.split())
        if len(collapsed) > 72:
            return collapsed[:69] + "…"
        return collapsed
    return f"Turn {turn.get('turn_id', '?')}"
