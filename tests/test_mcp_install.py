"""Tests for MCP install helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path

from server.mcp.install import BOOTSTRAP_PROMPT, install_mcp_config


def test_bootstrap_prompt_shape() -> None:
    assert "AGENT_SETUP.md" in BOOTSTRAP_PROMPT
    assert len(BOOTSTRAP_PROMPT.splitlines()) <= 3


def test_print_only_cursor(tmp_path: Path) -> None:
    result = install_mcp_config(
        workspace_root=tmp_path,
        client="cursor",
        write=False,
    )
    assert result["written"] is False
    assert "mcpServers" in result["snippet"]


def test_write_cursor_json(tmp_path: Path, monkeypatch) -> None:
    cfg = tmp_path / "mcp.json"
    monkeypatch.setattr(
        "server.mcp.install.CLIENT_TARGETS",
        {
            "cursor": type(
                "T",
                (),
                {
                    "client": "cursor",
                    "config_path": cfg,
                    "merge_key": "mcpServers",
                },
            )()
        },
    )
    result = install_mcp_config(workspace_root=tmp_path, client="cursor", write=True)
    assert result["written"] is True
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert "cairn" in data["mcpServers"]
    if os.name != "nt":
        assert cfg.parent.stat().st_mode & 0o777 == 0o700
        assert cfg.stat().st_mode & 0o777 == 0o600
