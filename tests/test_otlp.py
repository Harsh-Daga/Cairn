"""OTLP/JSON receiver tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server.api.sse import EventBus
from server.app import create_app
from server.ingest.otlp import OtlpReceiver, parse_otlp_json
from server.models.workspace import Workspace
from server.store.db import Database
from server.store.repos.spans import SpanRepo
from server.store.repos.traces import TraceRepo
from server.store.repos.workspaces import WorkspaceRepo
from server.util.ids import new_ulid

SAMPLE_OTLP = {
    "resourceSpans": [
        {
            "resource": {
                "attributes": [{"key": "service.name", "value": {"stringValue": "demo-agent"}}]
            },
            "scopeSpans": [
                {
                    "spans": [
                        {
                            "traceId": "abc123",
                            "spanId": "span001",
                            "name": "chat turn",
                            "kind": 4,
                            "startTimeUnixNano": "1700000000000000000",
                            "endTimeUnixNano": "1700000001000000000",
                            "attributes": [
                                {
                                    "key": "gen_ai.request.model",
                                    "value": {"stringValue": "gpt-4o"},
                                },
                                {
                                    "key": "gen_ai.usage.input_tokens",
                                    "value": {"intValue": "120"},
                                },
                                {
                                    "key": "gen_ai.usage.output_tokens",
                                    "value": {"intValue": "45"},
                                },
                            ],
                            "status": {"code": 1},
                        },
                        {
                            "traceId": "abc123",
                            "spanId": "span002",
                            "parentSpanId": "span001",
                            "name": "tool.read_file",
                            "kind": 2,
                            "startTimeUnixNano": "1700000002000000000",
                            "endTimeUnixNano": "1700000003000000000",
                            "attributes": [
                                {
                                    "key": "gen_ai.tool.name",
                                    "value": {"stringValue": "read_file"},
                                }
                            ],
                            "status": {"code": 1},
                        },
                    ]
                }
            ],
        }
    ]
}


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


def test_otlp_http_endpoint(tmp_path: Path) -> None:
    from server.config import Settings

    settings = Settings(workspace_root=tmp_path)
    app = create_app(settings)

    with TestClient(app) as client:
        response = client.post("/v1/traces", content=json.dumps(SAMPLE_OTLP))
        assert response.status_code == 200
        body = response.json()
        assert body["results"][0]["inserted"] is True
        assert body["results"][0]["span_count"] == 2
