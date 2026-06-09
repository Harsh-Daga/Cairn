"""MCP server preflight helpers for cairn doctor."""

from __future__ import annotations

import shutil
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.error import URLError
from urllib.request import Request, urlopen

Transport = Literal["stdio", "http"]


@dataclass(frozen=True)
class McpServerConfig:
    name: str
    transport: Transport
    command: str | None
    args: tuple[str, ...]
    url: str | None


def load_mcp_servers(project_root: Path) -> tuple[McpServerConfig, ...]:
    toml_path = project_root / "cairn.toml"
    if not toml_path.is_file():
        return ()
    data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    mcp = data.get("mcp")
    if not isinstance(mcp, dict):
        return ()
    servers = mcp.get("servers")
    if not isinstance(servers, dict):
        return ()
    configs: list[McpServerConfig] = []
    for name, raw in servers.items():
        if not isinstance(raw, dict):
            continue
        transport = str(raw.get("transport", "stdio"))
        if transport not in ("stdio", "http"):
            continue
        command = raw.get("command")
        args_raw = raw.get("args", [])
        args = tuple(str(a) for a in args_raw) if isinstance(args_raw, list) else ()
        url = raw.get("url")
        configs.append(
            McpServerConfig(
                name=str(name),
                transport=transport,  # type: ignore[arg-type]
                command=str(command) if command is not None else None,
                args=args,
                url=str(url) if url is not None else None,
            )
        )
    return tuple(configs)


def load_agent_profiles(project_root: Path) -> tuple[str, ...]:
    toml_path = project_root / "cairn.toml"
    if not toml_path.is_file():
        return ()
    data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    agents = data.get("agents")
    if not isinstance(agents, dict):
        return ()
    profiles = agents.get("profiles")
    if not isinstance(profiles, list):
        return ()
    return tuple(str(p) for p in profiles)


def check_mcp_server(server: McpServerConfig) -> tuple[bool, str]:
    if server.transport == "stdio":
        if not server.command:
            return False, f"mcp server {server.name!r}: stdio transport requires command"
        if not shutil.which(server.command):
            return False, f"mcp server {server.name!r}: command not on PATH: {server.command!r}"
        return True, f"mcp server {server.name!r}: command {server.command!r} found"
    if not server.url:
        return False, f"mcp server {server.name!r}: http transport requires url"
    try:
        req = Request(server.url, method="HEAD")
        with urlopen(req, timeout=3) as resp:  # noqa: S310
            if resp.status >= 400:
                return False, f"mcp server {server.name!r}: HTTP {resp.status} from {server.url}"
    except URLError as exc:
        return False, f"mcp server {server.name!r}: unreachable at {server.url} ({exc.reason})"
    return True, f"mcp server {server.name!r}: reachable at {server.url}"
