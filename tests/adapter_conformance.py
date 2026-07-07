"""Parametrized conformance harness for all ingest adapters."""

from __future__ import annotations

from pathlib import Path
from typing import get_args

import pytest

from server.ingest.adapters.base import FileAdapterBase
from server.ingest.adapters.claude_code_adapter import ClaudeCodeAdapter
from server.ingest.adapters.cline_adapter import ClineAdapter, KiloAdapter, RooAdapter
from server.ingest.adapters.codex_adapter import CodexAdapter
from server.ingest.adapters.cursor_adapter import CursorAdapter
from server.ingest.adapters.gemini_adapter import GeminiAdapter
from server.ingest.adapters.generic_jsonl_adapter import AiderAdapter, GooseAdapter, OpenCodeAdapter
from server.ingest.adapters.hermes_adapter import HermesAdapter
from server.ingest.adapters.openclaw_adapter import OpenClawAdapter
from server.models.span import SpanKind
from server.util.ids import new_ulid

FIXTURES = Path(__file__).parent / "fixtures" / "ingest"
CLINE_TASK = FIXTURES / "cline_mini" / "tasks" / "task-redacted-001" / "ui_messages.json"
VALID_KINDS = set(get_args(SpanKind))

ADAPTER_FIXTURES: list[tuple[type[FileAdapterBase], Path]] = [
    (ClaudeCodeAdapter, FIXTURES / "claude_code_mini.jsonl"),
    (CodexAdapter, FIXTURES / "codex_mini.jsonl"),
    (CursorAdapter, FIXTURES / "cursor_mini.jsonl"),
    (ClineAdapter, CLINE_TASK),
    (RooAdapter, CLINE_TASK),
    (KiloAdapter, CLINE_TASK),
    (GooseAdapter, FIXTURES / "agent_jsonl_mini.jsonl"),
    (AiderAdapter, FIXTURES / "agent_jsonl_mini.jsonl"),
    (OpenCodeAdapter, FIXTURES / "agent_jsonl_mini.jsonl"),
    (GeminiAdapter, FIXTURES / "gemini_mini.jsonl"),
    (HermesAdapter, FIXTURES / "hermes_mini.json"),
    (OpenClawAdapter, FIXTURES / "openclaw_mini.jsonl"),
]


@pytest.fixture
def workspace_root(tmp_path: Path) -> Path:
    return tmp_path


@pytest.mark.parametrize(
    ("adapter_cls", "fixture_path"),
    ADAPTER_FIXTURES,
    ids=[cls.__name__ for cls, _ in ADAPTER_FIXTURES],
)
def test_adapter_conformance(
    adapter_cls: type[FileAdapterBase],
    fixture_path: Path,
    workspace_root: Path,
) -> None:
    ws_id = new_ulid()
    adapter = adapter_cls(workspace_root, ws_id)
    assert fixture_path.is_file(), f"missing fixture: {fixture_path}"

    first = adapter.parse_path(fixture_path)
    second = adapter.parse_path(fixture_path)
    assert first is not None, f"{adapter_cls.__name__} failed to parse {fixture_path.name}"
    assert second is not None

    trace_a, spans_a, quality_a = adapter.to_spans(
        first, workspace_id=ws_id, repo_root=workspace_root
    )
    trace_b, spans_b, quality_b = adapter.to_spans(
        second, workspace_id=ws_id, repo_root=workspace_root
    )

    ids_a = [span.span_id for span in spans_a]
    ids_b = [span.span_id for span in spans_b]
    assert ids_a == ids_b, "determinism: span_ids differ between parses"
    assert trace_a.trace_id == trace_b.trace_id

    assert spans_a, "expected at least one span"
    seqs = [span.seq for span in spans_a]
    assert seqs == sorted(seqs), "seq must be monotonic"
    assert len(seqs) == len(set(seqs)), "seq values must be unique"

    span_ids = {span.span_id for span in spans_a}
    for span in spans_a:
        assert span.kind in VALID_KINDS, f"invalid kind: {span.kind}"
        if span.parent_span_id is not None:
            assert span.parent_span_id in span_ids, f"orphan parent: {span.parent_span_id}"

    for quality in (quality_a, quality_b):
        assert quality.trace_id == trace_a.trace_id
        assert quality.cost_source in ("absent", "observed", "priced")
