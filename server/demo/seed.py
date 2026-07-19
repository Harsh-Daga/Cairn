"""Compatibility facade for deterministic demo scenarios and fixtures."""

from server.demo.fixtures import seed_demo_workspace as seed_demo_workspace
from server.demo.scenarios import (
    DEMO_ACTORS as DEMO_ACTORS,
)
from server.demo.scenarios import (
    DEMO_DAYS as DEMO_DAYS,
)
from server.demo.scenarios import (
    DEMO_FAILURE_TRACE_INDEX as DEMO_FAILURE_TRACE_INDEX,
)
from server.demo.scenarios import (
    DEMO_MULTI_AGENT_TRACE_INDEX as DEMO_MULTI_AGENT_TRACE_INDEX,
)
from server.demo.scenarios import (
    DEMO_ROOT as DEMO_ROOT,
)
from server.demo.scenarios import (
    DEMO_SOURCES as DEMO_SOURCES,
)
from server.demo.scenarios import (
    DEMO_TAIL_TRACE_INDEX as DEMO_TAIL_TRACE_INDEX,
)
from server.demo.scenarios import (
    DEMO_TRACE_COUNT as DEMO_TRACE_COUNT,
)
from server.demo.scenarios import (
    DEMO_WORKSPACE_ID as DEMO_WORKSPACE_ID,
)
from server.demo.scenarios import (
    DemoSeedResult as DemoSeedResult,
)

__all__ = [
    "DEMO_ACTORS",
    "DEMO_DAYS",
    "DEMO_FAILURE_TRACE_INDEX",
    "DEMO_MULTI_AGENT_TRACE_INDEX",
    "DEMO_ROOT",
    "DEMO_SOURCES",
    "DEMO_TAIL_TRACE_INDEX",
    "DEMO_TRACE_COUNT",
    "DEMO_WORKSPACE_ID",
    "DemoSeedResult",
    "seed_demo_workspace",
]
