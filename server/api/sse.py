"""SSE event bus — bounded per-client queues with drop-oldest."""

from __future__ import annotations

import json
import queue
import threading
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

SSE_QUEUE_SIZE = 64


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
            with contextlib_suppress_queue_full(client):
                client.queue.put_nowait(None)

    def client_dropped(self, client_id: str) -> int:
        """Return dropped-event count for a client."""
        with self._lock:
            client = self._clients.get(client_id)
            return client.dropped if client is not None else 0

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


def contextlib_suppress_queue_full(client: _ClientQueue) -> _SuppressQueueFull:
    return _SuppressQueueFull(client)


class _SuppressQueueFull:
    def __init__(self, client: _ClientQueue) -> None:
        self._client = client

    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return exc_type is queue.Full


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


def sse_stream(bus: EventBus) -> Iterator[str]:
    """Blocking generator for FastAPI StreamingResponse."""
    client_id, iterator = bus.subscribe()
    try:
        for event in iterator:
            dropped = bus.client_dropped(client_id)
            yield format_sse(event, include_dropped=dropped)
    finally:
        bus.unsubscribe(client_id)
