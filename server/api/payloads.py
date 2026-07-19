"""Compatibility facade for API payload builders.

Implementations live in :mod:`server.api.payload_domains`; these re-exports keep
the public ``server.api.payloads`` import surface stable for routers and extensions.
"""

from server.api.payload_domains.analytics import (
    build_agents as build_agents,
)
from server.api.payload_domains.analytics import (
    build_behavior as build_behavior,
)
from server.api.payload_domains.analytics import (
    build_quality as build_quality,
)
from server.api.payload_domains.analytics import (
    build_regions_analytics as build_regions_analytics,
)
from server.api.payload_domains.analytics import (
    build_tail_analytics as build_tail_analytics,
)
from server.api.payload_domains.analytics import (
    build_usage_analytics as build_usage_analytics,
)
from server.api.payload_domains.analytics import (
    build_waste_analytics as build_waste_analytics,
)
from server.api.payload_domains.budget import (
    build_budget_analytics as build_budget_analytics,
)
from server.api.payload_domains.compare import (
    build_compare_analytics as build_compare_analytics,
)
from server.api.payload_domains.files import (
    build_files_analytics as build_files_analytics,
)
from server.api.payload_domains.guard import (
    build_guard_analytics as build_guard_analytics,
)
from server.api.payload_domains.improvement import (
    build_evidence_chain as build_evidence_chain,
)
from server.api.payload_domains.improvement import (
    build_experiment_detail as build_experiment_detail,
)
from server.api.payload_domains.improvement import (
    build_experiments as build_experiments,
)
from server.api.payload_domains.improvement import (
    build_insights as build_insights,
)
from server.api.payload_domains.overview import (
    build_overview as build_overview,
)
from server.api.payload_domains.overview import (
    build_recap as build_recap,
)
from server.api.payload_domains.system import (
    build_search as build_search,
)
from server.api.payload_domains.system import (
    build_workspace as build_workspace,
)
from server.api.payload_domains.tools import (
    build_tools_analytics as build_tools_analytics,
)
from server.api.payload_domains.traces import (
    build_replay as build_replay,
)
from server.api.payload_domains.traces import (
    build_replay_checkpoints as build_replay_checkpoints,
)
from server.api.payload_domains.traces import (
    build_trace_corrections as build_trace_corrections,
)
from server.api.payload_domains.traces import (
    build_trace_detail as build_trace_detail,
)
from server.api.payload_domains.traces import (
    build_trace_diff as build_trace_diff,
)
from server.api.payload_domains.traces import (
    build_trace_handoff as build_trace_handoff,
)
from server.api.payload_domains.traces import (
    build_trace_receipt as build_trace_receipt,
)
from server.api.payload_domains.traces import (
    build_traces_list as build_traces_list,
)

__all__ = [
    "build_agents",
    "build_behavior",
    "build_budget_analytics",
    "build_compare_analytics",
    "build_guard_analytics",
    "build_evidence_chain",
    "build_experiment_detail",
    "build_experiments",
    "build_files_analytics",
    "build_insights",
    "build_overview",
    "build_quality",
    "build_recap",
    "build_regions_analytics",
    "build_replay",
    "build_replay_checkpoints",
    "build_search",
    "build_tail_analytics",
    "build_tools_analytics",
    "build_trace_corrections",
    "build_trace_detail",
    "build_trace_diff",
    "build_trace_handoff",
    "build_trace_receipt",
    "build_traces_list",
    "build_usage_analytics",
    "build_waste_analytics",
    "build_workspace",
]
