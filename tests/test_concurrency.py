"""Executor level-parallel scheduling tests (R12)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from cairn.cache.store import CacheStore
from cairn.executor.runner import BuildOptions, execute_build
from cairn.graph.builder import build_graph
from cairn.graph.levels import compute_node_levels
from cairn.loader.toml import load_project
from cairn.model.messages import CompletionRequest, CompletionResult, TokenUsage
from cairn.util.tokens import estimate_tokens_from_request


@dataclass
class SlowProvider:
    max_in_flight: int = 0
    _in_flight: int = 0
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    name: str = "slow"

    def estimate_tokens(self, request: CompletionRequest) -> int:
        return estimate_tokens_from_request(request)

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        async with self._lock:
            self._in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self._in_flight)
        await asyncio.sleep(0.08)
        async with self._lock:
            self._in_flight -= 1
        return CompletionResult(
            text=f"ok:{request.model}",
            usage=TokenUsage(input_tokens=1, output_tokens=1),
            raw={},
        )


@pytest.mark.asyncio
async def test_map_nodes_run_concurrently(project_dir: Path) -> None:
    project = load_project(project_dir)
    graph = build_graph(project)
    levels = compute_node_levels(project, graph)
    assert levels[0] == ("summaries:alpha", "summaries:beta", "summaries:gamma")

    cache = CacheStore(project.root)
    provider = SlowProvider()
    try:
        await execute_build(
            project,
            graph,
            cache,
            provider,
            BuildOptions(yes=True, concurrency=3),
        )
    finally:
        cache.close()
    assert provider.max_in_flight >= 2


def test_plan_nodes_called_once_per_level(
    project_dir: Path,
    fixtures_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []
    import cairn.executor.runner as runner

    original = runner.plan_nodes

    def tracked(*args: object, **kwargs: object) -> tuple[object, ...]:
        node_ids = kwargs["node_ids"] if "node_ids" in kwargs else args[3]
        calls.append(len(node_ids))  # type: ignore[arg-type]
        return original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(runner, "plan_nodes", tracked)

    from tests.test_invariants import _build

    _build(project_dir, fixtures_dir)
    assert calls == [3, 1, 1]
