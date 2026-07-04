"""Pillar 5 — MCP server package."""

from __future__ import annotations

from cairn.mcp.server import serve
from cairn.mcp.tools import list_tools, open_context

__all__ = ["serve", "list_tools", "open_context"]
