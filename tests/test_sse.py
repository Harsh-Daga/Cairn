"""SSE stream lifecycle and keepalive coverage."""

from __future__ import annotations

import asyncio

import pytest

from server.api import sse
from server.api.sse import EventBus, sse_stream
from server.app import create_app
from server.config import Settings


@pytest.mark.asyncio
async def test_sse_stream_emits_heartbeat_and_unsubscribes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sse, "SSE_HEARTBEAT_SECONDS", 0.001)
    bus = EventBus()
    stream = sse_stream(bus)

    assert await anext(stream) == ": heartbeat\n\n"
    assert len(bus._clients) == 1

    await stream.aclose()
    assert not bus._clients


@pytest.mark.asyncio
async def test_sse_stream_delivers_events_without_waiting_for_heartbeat() -> None:
    bus = EventBus()
    stream = sse_stream(bus)
    pending = asyncio.create_task(anext(stream))
    await asyncio.sleep(0)
    bus.publish("trace-updated", {"trace_id": "trace-1"})

    frame = await pending
    assert "event: trace-updated" in frame
    assert '"trace_id":"trace-1"' in frame
    await stream.aclose()


def test_live_events_route_is_registered_once(tmp_path) -> None:
    application = create_app(Settings(workspace_root=tmp_path))
    paths = application.openapi()["paths"]
    assert [path for path in paths if path == "/api/live/events"] == ["/api/live/events"]
    assert paths["/api/live/events"]["get"]["operationId"].startswith("live_events")
