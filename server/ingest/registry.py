"""Adapter plugin registry."""

from __future__ import annotations

import importlib.metadata
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from server.ingest.contract import Adapter

ADAPTER_IDS: list[str] = [
    "claude_code",
    "codex",
    "cursor",
    "cline",
    "roo",
    "kilo",
    "goose",
    "aider",
    "gemini_cli",
    "opencode",
    "hermes",
    "openclaw",
    "agent_jsonl",
]


def _entry_point_adapters(workspace_root: Path, workspace_id: str) -> list[Adapter]:
    adapters: list[Adapter] = []
    for entry in importlib.metadata.entry_points(group="cairn.adapters"):
        cls = entry.load()
        adapters.append(cls(workspace_root, workspace_id))
    return adapters


def build_adapters(workspace_root: Path, workspace_id: str) -> list[Adapter]:
    """Instantiate all ingest adapters for a workspace."""
    from server.ingest.adapters.claude_code_adapter import ClaudeCodeAdapter
    from server.ingest.adapters.cline_adapter import ClineAdapter, KiloAdapter, RooAdapter
    from server.ingest.adapters.codex_adapter import CodexAdapter
    from server.ingest.adapters.cursor_adapter import CursorAdapter
    from server.ingest.adapters.gemini_adapter import GeminiAdapter
    from server.ingest.adapters.generic_jsonl_adapter import (
        AiderAdapter,
        GooseAdapter,
        OpenCodeAdapter,
    )
    from server.ingest.adapters.hermes_adapter import HermesAdapter
    from server.ingest.adapters.openclaw_adapter import OpenClawAdapter

    built: list[Adapter] = [
        ClaudeCodeAdapter(workspace_root, workspace_id),
        CodexAdapter(workspace_root, workspace_id),
        CursorAdapter(workspace_root, workspace_id),
        ClineAdapter(workspace_root, workspace_id),
        RooAdapter(workspace_root, workspace_id),
        KiloAdapter(workspace_root, workspace_id),
        GooseAdapter(workspace_root, workspace_id),
        AiderAdapter(workspace_root, workspace_id),
        GeminiAdapter(workspace_root, workspace_id),
        OpenCodeAdapter(workspace_root, workspace_id),
        HermesAdapter(workspace_root, workspace_id),
        OpenClawAdapter(workspace_root, workspace_id),
    ]
    built.extend(_entry_point_adapters(workspace_root, workspace_id))
    return built
