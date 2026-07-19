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
    named = await anext(stream)
    assert "event: heartbeat" in named
    assert '"ok":true' in named
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


def test_event_bus_drop_oldest_backpressure() -> None:
    bus = EventBus()
    client_id, _ = bus.subscribe()
    for index in range(sse.SSE_QUEUE_SIZE + 5):
        bus.publish("trace-updated", {"trace_id": f"t-{index}"})
    assert bus.client_dropped(client_id) == 5
    first = bus.wait_for_event(client_id, timeout=0.1)
    assert first is not None
    assert first.data["trace_id"] == "t-5"
    bus.unsubscribe(client_id)


def test_format_sse_includes_dropped_count() -> None:
    frame = sse.format_sse(
        sse.SseEvent(event="trace-updated", data={"trace_id": "t1"}),
        include_dropped=3,
    )
    assert "event: trace-updated" in frame
    assert '"dropped_events":3' in frame


def test_live_events_route_is_registered_once(tmp_path) -> None:
    application = create_app(Settings(workspace_root=tmp_path))
    paths = application.openapi()["paths"]
    assert [path for path in paths if path == "/api/live/events"] == ["/api/live/events"]
    assert paths["/api/live/events"]["get"]["operationId"].startswith("live_events")
