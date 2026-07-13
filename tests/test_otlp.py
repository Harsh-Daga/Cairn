"""OTLP/JSON receiver tests."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.api.sse import EventBus
from server.app import create_app
from server.ingest.otlp import OtlpReceiver, parse_otlp_json
from server.ingest.otlp_pb import decode_export_trace_service_request
from server.models.workspace import Workspace
from server.store.db import Database
from server.store.repos.spans import SpanRepo
from server.store.repos.traces import TraceRepo
from server.store.repos.workspaces import WorkspaceRepo
from server.util.ids import new_ulid


@asynccontextmanager
async def _noop_lifespan(_application: FastAPI) -> AsyncIterator[None]:
    yield


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "otlp"
SAMPLE_OTLP = json.loads((FIXTURE_DIR / "sample_trace.json").read_text(encoding="utf-8"))
SAMPLE_OTLP_PB = (FIXTURE_DIR / "sample_trace.pb").read_bytes()


@pytest.fixture
def otlp_setup(tmp_path: Path) -> tuple[Database, str, EventBus]:
    db = Database(tmp_path / "cairn.db")
    ws_id = new_ulid()
    WorkspaceRepo.create(
        db.reader,
        Workspace(
            workspace_id=ws_id,
            root_path=str(tmp_path),
            name="otlp",
            created_at="2026-01-01T00:00:00Z",
        ),
    )
    db.reader.commit()
    return db, ws_id, EventBus()


def test_parse_otlp_json_maps_spans() -> None:
    traces = parse_otlp_json(SAMPLE_OTLP)
    assert len(traces) == 1
    trace, spans, quality = traces[0]
    assert trace.source == "otlp:demo_agent"
    assert trace.input_tokens == 120
    assert trace.output_tokens == 45
    assert len(spans) == 2
    assert spans[0].kind == "llm_call"
    assert spans[1].kind == "tool_call"
    assert quality.parser_version == "otlp@1"


def test_otlp_receiver_round_trip(otlp_setup: tuple[Database, str, EventBus]) -> None:
    db, ws_id, bus = otlp_setup
    receiver = OtlpReceiver(db, ws_id, bus)
    results = receiver.ingest_payload(SAMPLE_OTLP)
    assert len(results) == 1
    assert results[0].inserted
    assert results[0].span_count == 2

    trace = TraceRepo.get(db.reader, results[0].trace_id)
    assert trace is not None
    assert trace.model == "gpt-4o"
    spans = SpanRepo.list_by_trace(db.reader, results[0].trace_id)
    assert len(spans) == 2


def test_decode_otlp_protobuf_maps_to_json_shape() -> None:
    decoded = decode_export_trace_service_request(SAMPLE_OTLP_PB)
    traces = parse_otlp_json(decoded)
    assert len(traces) == 1
    trace, spans, _quality = traces[0]
    assert trace.source == "otlp:demo_agent"
    assert trace.model == "gpt-4o"
    assert trace.input_tokens == 120
    assert trace.output_tokens == 45
    assert len(spans) == 2
    assert spans[1].kind == "tool_call"


def test_decode_otlp_protobuf_rejects_malformed_payload() -> None:
    with pytest.raises(ValueError, match="invalid OTLP protobuf payload"):
        decode_export_trace_service_request(b"\xff")


def test_otlp_http_endpoint(tmp_path: Path) -> None:
    from server.api.bootstrap import bootstrap_runtime
    from server.config import Settings

    settings = Settings(workspace_root=tmp_path)
    runtime = bootstrap_runtime(settings)
    app = create_app(settings)
    app.router.lifespan_context = _noop_lifespan
    app.state.runtime = runtime
    app.state.database = runtime.database
    app.state.workspace_id = runtime.workspace_id
    app.state.event_bus = runtime.event_bus

    client = TestClient(app)
    response = client.post("/v1/traces", content=json.dumps(SAMPLE_OTLP))
    assert response.status_code == 200
    body = response.json()
    assert body["results"][0]["inserted"] is True
    assert body["results"][0]["span_count"] == 2


@pytest.mark.parametrize("content_type", ["application/x-protobuf", "application/protobuf"])
def test_otlp_http_endpoint_protobuf(tmp_path: Path, content_type: str) -> None:
    from server.api.bootstrap import bootstrap_runtime
    from server.config import Settings

    settings = Settings(workspace_root=tmp_path)
    runtime = bootstrap_runtime(settings)
    app = create_app(settings)
    app.router.lifespan_context = _noop_lifespan
    app.state.runtime = runtime
    app.state.database = runtime.database
    app.state.workspace_id = runtime.workspace_id
    app.state.event_bus = runtime.event_bus

    client = TestClient(app)
    response = client.post(
        "/v1/traces",
        content=SAMPLE_OTLP_PB,
        headers={"content-type": content_type},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["results"][0]["inserted"] is True
    assert body["results"][0]["span_count"] == 2
