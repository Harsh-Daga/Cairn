"""Coalesced per-session cost ticks for the live SSE stream."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from server.api.sse import EventBus
from server.models.trace import Trace

SESSION_COST_TICK_EVENT = "session_cost_tick"
SESSION_COST_TICK_INTERVAL_S = 2.0

Clock = Callable[[], float]


def estimate_kind_for_cost_source(cost_source: str) -> str:
    """Map stored cost provenance to the live tick marker."""
    if cost_source == "observed":
        return "measured"
    if cost_source == "priced":
        return "estimated"
    return "unavailable"


def session_cost_tick_payload(trace: Trace) -> dict[str, Any]:
    """Build a reconnect-safe absolute cost tick payload."""
    total_tokens = (
        int(trace.input_tokens)
        + int(trace.output_tokens)
        + int(trace.cache_read_tokens)
        + int(trace.cache_creation_tokens)
        + int(trace.reasoning_tokens)
    )
    return {
        "trace_id": trace.trace_id,
        "cost": round(float(trace.cost), 6),
        "cost_source": trace.cost_source,
        "estimate_kind": estimate_kind_for_cost_source(trace.cost_source),
        "input_tokens": int(trace.input_tokens),
        "output_tokens": int(trace.output_tokens),
        "total_tokens": total_tokens,
        "span_count": int(trace.span_count),
    }


@dataclass(slots=True)
class _PendingTick:
    payload: dict[str, Any]
    timer: threading.Timer | None = None


class SessionCostTickPublisher:
    """Publish at most one ``session_cost_tick`` per session every two seconds.

    Bursts coalesce to the latest absolute totals. Duplicate totals are suppressed.
    Pending ticks flush on a timer so the final coalesced value still ships when
    ingest goes quiet.
    """

    def __init__(
        self,
        bus: EventBus,
        *,
        interval_s: float = SESSION_COST_TICK_INTERVAL_S,
        clock: Clock | None = None,
    ) -> None:
        self._bus = bus
        self._interval = interval_s
        self._clock = clock or time.monotonic
        self._lock = threading.Lock()
        self._last_published_at: dict[str, float] = {}
        self._last_signature: dict[str, tuple[float, int, int]] = {}
        self._pending: dict[str, _PendingTick] = {}
        self._closed = False

    def observe(self, trace: Trace) -> SsePublishResult:
        """Observe a trace snapshot and publish or coalesce a cost tick."""
        payload = session_cost_tick_payload(trace)
        signature = (
            float(payload["cost"]),
            int(payload["total_tokens"]),
            int(payload["span_count"]),
        )
        trace_id = trace.trace_id
        with self._lock:
            if self._closed:
                return SsePublishResult(published=False, coalesced=False, suppressed=True)
            if self._last_signature.get(trace_id) == signature:
                return SsePublishResult(published=False, coalesced=False, suppressed=True)
            now = self._clock()
            last_at = self._last_published_at.get(trace_id)
            if last_at is None or now - last_at >= self._interval:
                self._publish_locked(trace_id, payload, signature, now)
                return SsePublishResult(published=True, coalesced=False, suppressed=False)
            self._store_pending_locked(trace_id, payload, last_at)
            return SsePublishResult(published=False, coalesced=True, suppressed=False)

    def flush_due(self) -> int:
        """Publish any pending ticks whose interval has elapsed. Returns count published."""
        published = 0
        with self._lock:
            if self._closed:
                return 0
            now = self._clock()
            due = [
                trace_id
                for trace_id, pending in self._pending.items()
                if now - self._last_published_at.get(trace_id, 0.0) >= self._interval
            ]
            for trace_id in due:
                pending = self._pending.pop(trace_id)
                self._cancel_timer(pending)
                signature = (
                    float(pending.payload["cost"]),
                    int(pending.payload["total_tokens"]),
                    int(pending.payload["span_count"]),
                )
                self._publish_locked(trace_id, pending.payload, signature, now)
                published += 1
        return published

    def close(self) -> None:
        """Cancel pending flush timers (does not force-publish)."""
        with self._lock:
            self._closed = True
            for pending in self._pending.values():
                self._cancel_timer(pending)
            self._pending.clear()

    def _store_pending_locked(
        self,
        trace_id: str,
        payload: dict[str, Any],
        last_at: float,
    ) -> None:
        existing = self._pending.get(trace_id)
        if existing is not None:
            self._cancel_timer(existing)
        delay = max(0.0, self._interval - (self._clock() - last_at))
        timer = threading.Timer(delay, self._flush_one, args=(trace_id,))
        timer.daemon = True
        self._pending[trace_id] = _PendingTick(payload=payload, timer=timer)
        timer.start()

    def _flush_one(self, trace_id: str) -> None:
        with self._lock:
            if self._closed:
                return
            pending = self._pending.pop(trace_id, None)
            if pending is None:
                return
            pending.timer = None
            signature = (
                float(pending.payload["cost"]),
                int(pending.payload["total_tokens"]),
                int(pending.payload["span_count"]),
            )
            if self._last_signature.get(trace_id) == signature:
                return
            self._publish_locked(trace_id, pending.payload, signature, self._clock())

    def _publish_locked(
        self,
        trace_id: str,
        payload: dict[str, Any],
        signature: tuple[float, int, int],
        now: float,
    ) -> None:
        existing = self._pending.pop(trace_id, None)
        if existing is not None:
            self._cancel_timer(existing)
        self._last_published_at[trace_id] = now
        self._last_signature[trace_id] = signature
        self._bus.publish(SESSION_COST_TICK_EVENT, payload)

    @staticmethod
    def _cancel_timer(pending: _PendingTick) -> None:
        if pending.timer is not None:
            pending.timer.cancel()
            pending.timer = None


@dataclass(frozen=True, slots=True)
class SsePublishResult:
    published: bool
    coalesced: bool
    suppressed: bool
