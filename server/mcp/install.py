"""MCP client configuration helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

McpClient = Literal["claude-code", "cursor", "codex", "other"]

AGENT_SETUP_URL = "https://raw.githubusercontent.com/Harsh-Daga/Cairn/main/AGENT_SETUP.md"

BOOTSTRAP_PROMPT = (
    "Set up Cairn (open-source agent observability, https://github.com/Harsh-Daga/Cairn) "
    "in this repo. Fetch "
    "https://raw.githubusercontent.com/Harsh-Daga/Cairn/main/AGENT_SETUP.md "
    "and follow it exactly. Do not use sudo; stop and report if any VERIFY step fails."
)


@dataclass(frozen=True)
class ClientTarget:
    client: McpClient
    config_path: Path
    merge_key: str  # top-level key holding servers map


CLIENT_TARGETS: dict[McpClient, ClientTarget] = {
    "cursor": ClientTarget(
        client="cursor",
        config_path=Path.home() / ".cursor" / "mcp.json",
        merge_key="mcpServers",
    ),
    "claude-code": ClientTarget(
        client="claude-code",
        config_path=Path.home() / ".config" / "claude" / "claude_desktop_config.json",
        merge_key="mcpServers",
    ),
    "codex": ClientTarget(
        client="codex",
        config_path=Path.home() / ".codex" / "config.toml",
        merge_key="mcp_servers",
    ),
}


def mcp_server_snippet(workspace_root: Path) -> dict[str, object]:
    return {
        "command": "cairn",
        "args": ["mcp"],
        "cwd": str(workspace_root.resolve()),
    }


def generic_print_block(workspace_root: Path) -> dict[str, object]:
    return {"mcpServers": {"cairn": mcp_server_snippet(workspace_root)}}


def install_mcp_config(
    *,
    workspace_root: Path,
    client: McpClient = "cursor",
    write: bool = True,
) -> dict[str, object]:
    """Write or preview Cairn MCP config for a supported client."""
    if client == "other":
        return {
            "client": client,
            "written": False,
            "path": None,
            "snippet": generic_print_block(workspace_root),
            "instructions": "Paste the snippet into your agent's MCP config file.",
        }

    target = CLIENT_TARGETS[client]
    snippet = mcp_server_snippet(workspace_root)
    path = target.config_path

    if not write:
        return {
            "client": client,
            "written": False,
            "path": str(path),
            "snippet": {target.merge_key: {"cairn": snippet}},
        }

    path.parent.mkdir(parents=True, exist_ok=True)
    if client == "codex":
        _merge_codex_toml(path, snippet)
    else:
        _merge_json_servers(path, target.merge_key, snippet)

    return {"client": client, "written": True, "path": str(path), "snippet": snippet}


def _merge_json_servers(path: Path, merge_key: str, snippet: dict[str, object]) -> None:
    existing = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    servers = existing.setdefault(merge_key, {})
    if not isinstance(servers, dict):
        servers = {}
        existing[merge_key] = servers
    servers["cairn"] = snippet
    path.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")


def _merge_codex_toml(path: Path, snippet: dict[str, object]) -> None:
    block = (
        "\n[mcp_servers.cairn]\n"
        f'command = "{snippet["command"]}"\n'
        f'args = {json.dumps(snippet["args"])}\n'
        f'cwd = "{snippet["cwd"]}"\n'
    )
    if path.is_file():
        text = path.read_text(encoding="utf-8")
        if "[mcp_servers.cairn]" in text:
            return
        path.write_text(text.rstrip() + block, encoding="utf-8")
    else:
        path.write_text(block.lstrip(), encoding="utf-8")
