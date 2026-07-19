"""Deterministic demo scenario definitions, independent of SQLite writes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

DEMO_TRACE_COUNT = 120
DEMO_DAYS = 30
DEMO_SOURCES = ("claude_code", "cursor", "codex", "cline")
DEMO_ACTORS = (
    ("human", "Harsh"),
    ("agent", "Cairn Bot"),
    ("service", "CI Runner"),
)
DEMO_ROOT = Path("~/.cairn-demo").expanduser()
DEMO_WORKSPACE_ID = str(uuid5(NAMESPACE_URL, "cairn-demo/workspace"))
DEMO_FAILURE_TRACE_INDEX = 73
DEMO_MULTI_AGENT_TRACE_INDEX = 42
DEMO_TAIL_TRACE_INDEX = 117


@dataclass(frozen=True)
class DemoSeedResult:
    root: Path
    workspace_id: str
    trace_count: int
    actor_count: int
    source_count: int
    reset: bool


@dataclass(frozen=True)
class TraceScenario:
    index: int
    started_at: datetime
    ended_at: datetime
    source: str
    actor_index: int
    model: str
    project: str
    trace_id: str
    status: str
    input_tokens: int
    output_tokens: int
    waste_tokens: int
    cost: float
    title: str


def deterministic_uuid(label: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"cairn-demo/{label}"))


def trace_scenarios(now: datetime | None = None) -> tuple[TraceScenario, ...]:
    """Return the complete deterministic 30-day trace scenario."""
    anchor = now or datetime.now(UTC)
    start_day = (anchor - timedelta(days=DEMO_DAYS - 1)).replace(
        hour=9, minute=0, second=0, microsecond=0
    )
    scenarios: list[TraceScenario] = []
    for index in range(DEMO_TRACE_COUNT):
        started_at = start_day + timedelta(days=index // 4, hours=(index % 4) * 2)
        ended_at = started_at + timedelta(minutes=8 + (index % 9) * 4)
        source = DEMO_SOURCES[index % len(DEMO_SOURCES)]
        input_tokens = 1200 + (index % 11) * 130
        output_tokens = 700 + (index % 7) * 90
        waste_tokens = 120 + (index % 6) * 45
        cost = round((input_tokens + output_tokens) * 0.000003, 4)
        if index == DEMO_TAIL_TRACE_INDEX:
            cost = 14.75
            waste_tokens = 3100
        scenarios.append(
            TraceScenario(
                index=index,
                started_at=started_at,
                ended_at=ended_at,
                source=source,
                actor_index=index % len(DEMO_ACTORS),
                model="claude-4.6-sonnet" if index < 80 else "gpt-5.5-medium",
                project="demo-app" if index % 2 == 0 else "ops-tooling",
                trace_id=str(uuid5(NAMESPACE_URL, f"cairn-demo/trace/{index:03d}")),
                status="error" if index == DEMO_FAILURE_TRACE_INDEX else "completed",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                waste_tokens=waste_tokens,
                cost=cost,
                title=(
                    "Failure cascade after bad migration"
                    if index == DEMO_FAILURE_TRACE_INDEX
                    else f"Demo trace {index + 1:03d} — {source}"
                ),
            )
        )
    return tuple(scenarios)
