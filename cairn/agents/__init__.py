"""Agent integration framework (charter §11, Phase 8)."""

from cairn.agents.protocol import AgentParser
from cairn.agents.registry import AGENT_SOURCES, get_parser, list_agent_sources
from cairn.ingest.types import AgentSourceId, ParsedAgentSession

__all__ = [
    "AGENT_SOURCES",
    "AgentParser",
    "AgentSourceId",
    "ParsedAgentSession",
    "get_parser",
    "list_agent_sources",
]
