"""Empty/truncated completions must not enter AC or CAS (Phase 2.1)."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from cairn.cache.store import CacheStore
from cairn.executor.runner import BuildOptions, _completion_request, execute_build
from cairn.graph.builder import build_graph
from cairn.loader.toml import load_project
from cairn.model.errors import EmptyCompletionError
from cairn.model.messages import CompletionRequest, CompletionResult, TokenUsage
from cairn.plan.planner import plan_build
from cairn.providers.completion import ensure_usable_completion
from cairn.providers.recorded import RecordedProvider, _request_key
from cairn.util.tokens import estimate_tokens_from_request


@dataclass
class _EmptyLengthProvider:
    name: str = "empty"
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def estimate_tokens(self, request: CompletionRequest) -> int:
        return estimate_tokens_from_request(request)

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        result = CompletionResult(
            text="",
            usage=TokenUsage(input_tokens=10, output_tokens=0),
            raw={"choices": [{"finish_reason": "length"}]},
            finish_reason="length",
        )
        return ensure_usable_completion(result)


def test_ensure_usable_completion_raises_on_empty_length() -> None:
    result = CompletionResult(
        text="",
        usage=TokenUsage(input_tokens=1, output_tokens=0),
        raw={},
        finish_reason="length",
    )
    with pytest.raises(EmptyCompletionError):
        ensure_usable_completion(result)


def test_ensure_usable_completion_allows_normal_text() -> None:
    result = CompletionResult(
        text="hello",
        usage=TokenUsage(input_tokens=1, output_tokens=1),
        raw={},
        finish_reason="stop",
    )
    assert ensure_usable_completion(result).text == "hello"


@pytest.mark.asyncio
async def test_empty_completion_does_not_cache(project_dir: Path) -> None:
    project = load_project(project_dir)
    graph = build_graph(project)
    cache = CacheStore(project.root)
    provider = _EmptyLengthProvider()
    ac_keys_before = cache.ledger.connection.execute(
        "SELECT COUNT(*) FROM action_cache"
    ).fetchone()[0]
    try:
        with pytest.raises(EmptyCompletionError):
            await execute_build(
                project,
                graph,
                cache,
                provider,
                BuildOptions(yes=True, concurrency=1),
            )
    finally:
        cache.close()
    cache2 = CacheStore(project.root)
    try:
        ac_keys_after = cache2.ledger.connection.execute(
            "SELECT COUNT(*) FROM action_cache"
        ).fetchone()[0]
    finally:
        cache2.close()
    assert ac_keys_after == ac_keys_before


@pytest.mark.asyncio
async def test_recorded_fixture_empty_length_raises(
    project_dir: Path,
    tmp_path: Path,
) -> None:
    project = load_project(project_dir)
    graph = build_graph(project)

    class EmptyCache:
        def get_output_hash(self, key: str) -> str | None:
            return None

        def has_blob(self, digest: str) -> bool:
            return False

    planned = plan_build(project, graph, EmptyCache()).nodes[0]
    req = _completion_request(planned)
    key = _request_key(req)
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    (fixtures / f"{key}.json").write_text(
        json.dumps(
            {
                "text": "",
                "input_tokens": 1,
                "output_tokens": 0,
                "finish_reason": "length",
                "raw": {},
            }
        ),
        encoding="utf-8",
    )
    provider = RecordedProvider(fixtures)
    with pytest.raises(EmptyCompletionError):
        await provider.complete(req)


def test_doctor_warns_low_max_tokens_on_reasoning_model(
    project_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cairn.doctor.checks import run_doctor
    from cairn.loader.toml import load_project

    monkeypatch.setenv("OLLAMA_CLOUD_API_KEY", "test-key")
    toml = project_dir / "cairn.toml"
    toml.write_text(
        toml.read_text(encoding="utf-8").replace("max_tokens = 500", "max_tokens = 200"),
        encoding="utf-8",
    )
    project = load_project(project_dir)
    report = run_doctor(project)
    assert any("reasoning" in i.message.lower() for i in report.issues)
