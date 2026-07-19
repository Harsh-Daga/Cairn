"""SSE event bus — bounded per-client queues with drop-oldest."""

from __future__ import annotations

import asyncio
import json
import queue
import threading
import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from server.api.cost_ticks import SessionCostTickPublisher

SSE_QUEUE_SIZE = 64
SSE_HEARTBEAT_SECONDS = 15.0


@dataclass(frozen=True)
class SseEvent:
    """One server-sent event."""

    event: str
    data: dict[str, Any]
    id: str = field(default_factory=lambda: uuid.uuid4().hex)


@dataclass
class _ClientQueue:
    queue: queue.Queue[SseEvent | None]
    dropped: int = 0


class EventBus:
    """Thread-safe pub/sub bus for live UI updates."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._clients: dict[str, _ClientQueue] = {}
        self._cost_ticks: SessionCostTickPublisher | None = None

    @property
    def cost_ticks(self) -> SessionCostTickPublisher:
        """Lazily create the shared per-session cost-tick coalescer.

        Lazy import avoids a module cycle with ``server.api.cost_ticks``.
        """
        if self._cost_ticks is None:
            from server.api.cost_ticks import SessionCostTickPublisher

            self._cost_ticks = SessionCostTickPublisher(self)
        return self._cost_ticks

    def publish(self, event: str, data: dict[str, Any] | None = None) -> SseEvent:
        """Broadcast an event to all connected SSE clients."""
        payload = data or {}
        message = SseEvent(
            event=event,
            data={
                **payload,
                "ts": datetime.now(UTC).isoformat(),
            },
        )
        with self._lock:
            for client in self._clients.values():
                self._enqueue(client, message)
        return message

    def subscribe(self) -> tuple[str, Iterator[SseEvent]]:
        """Register a client and return (client_id, blocking iterator)."""
        client_id = uuid.uuid4().hex
        client = _ClientQueue(queue=queue.Queue(maxsize=SSE_QUEUE_SIZE))
        with self._lock:
            self._clients[client_id] = client
        return client_id, self._iter_client(client_id, client)

    def unsubscribe(self, client_id: str) -> None:
        """Remove a client and unblock its iterator."""
        with self._lock:
            client = self._clients.pop(client_id, None)
        if client is not None:
            with suppress(queue.Full):
                client.queue.put_nowait(None)

    def client_dropped(self, client_id: str) -> int:
        """Return dropped-event count for a client."""
        with self._lock:
            client = self._clients.get(client_id)
            return client.dropped if client is not None else 0

    def wait_for_event(self, client_id: str, timeout: float) -> SseEvent | None:
        """Wait briefly for one client event, returning ``None`` on timeout/close."""
        with self._lock:
            client = self._clients.get(client_id)
        if client is None:
            return None
        try:
            return client.queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def is_subscribed(self, client_id: str) -> bool:
        with self._lock:
            return client_id in self._clients

    def _enqueue(self, client: _ClientQueue, message: SseEvent) -> None:
        try:
            client.queue.put_nowait(message)
        except queue.Full:
            try:
                client.queue.get_nowait()
                client.dropped += 1
            except queue.Empty:
                pass
            try:
                client.queue.put_nowait(message)
            except queue.Full:
                client.dropped += 1

    def _iter_client(self, client_id: str, client: _ClientQueue) -> Iterator[SseEvent]:
        while True:
            item = client.queue.get()
            if item is None:
                break
            yield item
        with self._lock:
            self._clients.pop(client_id, None)


def format_sse(event: SseEvent, *, include_dropped: int = 0) -> str:
    """Serialize one SSE frame."""
    payload = dict(event.data)
    if include_dropped:
        payload["dropped_events"] = include_dropped
    lines = [
        f"event: {event.event}",
        f"id: {event.id}",
        f"data: {json.dumps(payload, separators=(',', ':'))}",
        "",
        "",
    ]
    return "\n".join(lines)


async def sse_stream(bus: EventBus) -> AsyncIterator[str]:
    """Yield SSE events without pinning a request worker indefinitely.

    The timed wait gives the ASGI server a cancellation point when a client
    disconnects or the application is shutting down.  Comment heartbeats keep
    otherwise-idle connections alive through common reverse proxies.
    """
    client_id, _ = bus.subscribe()
    try:
        while True:
            try:
                event = await asyncio.to_thread(
                    bus.wait_for_event, client_id, SSE_HEARTBEAT_SECONDS
                )
            except asyncio.CancelledError:
                raise
            if event is None:
                if not bus.is_subscribed(client_id):
                    break
                # Comment keeps proxies warm; named event lets clients observe liveness.
                yield ": heartbeat\n\n"
                yield format_sse(SseEvent(event="heartbeat", data={"ok": True}))
                continue
            dropped = bus.client_dropped(client_id)
            yield format_sse(event, include_dropped=dropped)
    finally:
        bus.unsubscribe(client_id)
