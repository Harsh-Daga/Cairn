"""Waterfall flattenTree performance — 10k spans should flatten in < 500ms."""

from __future__ import annotations

import time
from typing import Any

PERF_BUDGET_MS = 500
SPAN_COUNT = 10_000


def _make_span(span_id: str) -> dict[str, Any]:
    return {
        "span_id": span_id,
        "trace_id": "trace-1",
        "parent_span_id": None,
        "seq": 0,
        "kind": "tool_call",
        "name": f"span-{span_id}",
        "agent_id": None,
        "agent_lane": None,
        "started_at": None,
        "ended_at": None,
        "duration_ms": 1.0,
        "status": "ok",
        "model": None,
        "input_tokens": 10,
        "output_tokens": 5,
        "input_estimated": 0,
        "output_estimated": 0,
        "cache_read_tokens": None,
        "cache_creation_tokens": None,
        "context_tokens_after": None,
        "text_inline": None,
        "path_rel": None,
        "waste_category": None,
        "waste_tokens": 0,
    }


def flatten_tree(nodes: list[dict[str, Any]], depth: int = 0) -> list[tuple[dict[str, Any], int]]:
    """Python port of ui/src/components/waterfall/Waterfall.tsx flattenTree."""
    rows: list[tuple[dict[str, Any], int]] = []
    for node in nodes:
        rows.append((node["span"], depth))
        children = node.get("children") or []
        if children:
            rows.extend(flatten_tree(children, depth + 1))
    return rows


def _synthetic_tree(span_count: int) -> list[dict[str, Any]]:
    """Balanced tree: one root with span_count - 1 direct children."""
    root = {"span": _make_span("root"), "children": []}
    for i in range(span_count - 1):
        root["children"].append({"span": _make_span(f"child-{i}"), "children": []})
    return [root]


def test_flatten_tree_10k_spans_under_budget() -> None:
    tree = _synthetic_tree(SPAN_COUNT)
    start = time.perf_counter()
    rows = flatten_tree(tree)
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert len(rows) == SPAN_COUNT
    msg = f"flatten_tree took {elapsed_ms:.1f}ms (budget {PERF_BUDGET_MS}ms)"
    assert elapsed_ms < PERF_BUDGET_MS, msg
