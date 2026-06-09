"""Lightweight micro-benchmarks for hot paths."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from cairn.cache.cas import ContentAddressableStore
from cairn.render.graph_layout import layout_session_graph


def benchmark_cas_reads(root: Path, digest: str, *, iterations: int = 100) -> float:
    """Return average seconds per cached CAS read."""
    cas = ContentAddressableStore(root, read_cache_size=64)
    if cas.read(digest) is None:
        digest = cas.put(b"benchmark-payload")
    start = time.perf_counter()
    for _ in range(iterations):
        cas.read(digest)
    elapsed = time.perf_counter() - start
    return elapsed / iterations


def benchmark_graph_layout(graph: dict[str, Any], *, iterations: int = 50) -> float:
    """Return average seconds per layout_session_graph call (includes memoization)."""
    layout_session_graph(graph)
    start = time.perf_counter()
    for _ in range(iterations):
        layout_session_graph(graph)
    elapsed = time.perf_counter() - start
    return elapsed / iterations
