"""Coalesced session_cost_tick publisher coverage."""

from __future__ import annotations

from server.api.cost_ticks import (
    SESSION_COST_TICK_EVENT,
    SessionCostTickPublisher,
    estimate_kind_for_cost_source,
    session_cost_tick_payload,
)
from server.api.sse import EventBus
from server.models.trace import Trace


def _trace(
    *,
    trace_id: str = "tr_cost",
    cost: float = 1.25,
    cost_source: str = "observed",
    input_tokens: int = 100,
    output_tokens: int = 50,
    span_count: int = 3,
) -> Trace:
    return Trace(
        trace_id=trace_id,
        workspace_id="ws",
        source="cursor",
        cost=cost,
        cost_source=cost_source,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        span_count=span_count,
    )


def test_estimate_kind_maps_cost_source() -> None:
    assert estimate_kind_for_cost_source("observed") == "measured"
    assert estimate_kind_for_cost_source("priced") == "estimated"
    assert estimate_kind_for_cost_source("absent") == "unavailable"


def test_payload_uses_absolute_totals() -> None:
    payload = session_cost_tick_payload(
        _trace(cost=2.5, cost_source="priced", input_tokens=10, output_tokens=5, span_count=2)
    )
    assert payload["trace_id"] == "tr_cost"
    assert payload["cost"] == 2.5
    assert payload["estimate_kind"] == "estimated"
    assert payload["total_tokens"] == 15
    assert payload["span_count"] == 2


def test_first_observe_publishes_immediately() -> None:
    bus = EventBus()
    client_id, _ = bus.subscribe()
    clock = {"t": 0.0}
    publisher = SessionCostTickPublisher(bus, interval_s=2.0, clock=lambda: clock["t"])

    result = publisher.observe(_trace(cost=1.0))
    assert result.published is True
    event = bus.wait_for_event(client_id, timeout=0.1)
    assert event is not None
    assert event.event == SESSION_COST_TICK_EVENT
    assert event.data["cost"] == 1.0
    assert event.data["estimate_kind"] == "measured"
    publisher.close()
    bus.unsubscribe(client_id)


def test_burst_coalesces_to_latest_and_flush_due_publishes_once() -> None:
    bus = EventBus()
    client_id, _ = bus.subscribe()
    clock = {"t": 0.0}
    publisher = SessionCostTickPublisher(bus, interval_s=2.0, clock=lambda: clock["t"])

    assert publisher.observe(_trace(cost=1.0)).published is True
    assert bus.wait_for_event(client_id, timeout=0.1) is not None

    clock["t"] = 0.2
    assert publisher.observe(_trace(cost=1.5, span_count=4)).coalesced is True
    clock["t"] = 0.5
    assert publisher.observe(_trace(cost=2.0, span_count=5)).coalesced is True
    assert bus.wait_for_event(client_id, timeout=0.05) is None

    clock["t"] = 2.1
    assert publisher.flush_due() == 1
    event = bus.wait_for_event(client_id, timeout=0.1)
    assert event is not None
    assert event.data["cost"] == 2.0
    assert event.data["span_count"] == 5
    assert bus.wait_for_event(client_id, timeout=0.05) is None
    publisher.close()
    bus.unsubscribe(client_id)


def test_duplicate_totals_are_suppressed() -> None:
    bus = EventBus()
    client_id, _ = bus.subscribe()
    clock = {"t": 0.0}
    publisher = SessionCostTickPublisher(bus, interval_s=2.0, clock=lambda: clock["t"])

    assert publisher.observe(_trace(cost=1.0, span_count=2)).published is True
    assert bus.wait_for_event(client_id, timeout=0.1) is not None

    clock["t"] = 3.0
    result = publisher.observe(_trace(cost=1.0, span_count=2))
    assert result.suppressed is True
    assert bus.wait_for_event(client_id, timeout=0.05) is None
    publisher.close()
    bus.unsubscribe(client_id)


def test_interval_allows_new_publish_after_two_seconds() -> None:
    bus = EventBus()
    client_id, _ = bus.subscribe()
    clock = {"t": 0.0}
    publisher = SessionCostTickPublisher(bus, interval_s=2.0, clock=lambda: clock["t"])

    publisher.observe(_trace(cost=1.0))
    assert bus.wait_for_event(client_id, timeout=0.1) is not None

    clock["t"] = 2.0
    assert publisher.observe(_trace(cost=1.4)).published is True
    event = bus.wait_for_event(client_id, timeout=0.1)
    assert event is not None
    assert event.data["cost"] == 1.4
    publisher.close()
    bus.unsubscribe(client_id)


def test_event_bus_exposes_shared_cost_ticks_publisher() -> None:
    bus = EventBus()
    assert bus.cost_ticks is bus.cost_ticks
    bus.cost_ticks.close()
