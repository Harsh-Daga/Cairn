"""MCP stdio server — JSON-RPC over stdin/stdout."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from server.mcp.tools import ToolsContext, call_tool, list_tools, open_context

_PROTOCOL_VERSION = "2024-11-05"
_SERVER_INFO = {"name": "cairn", "version": "0.1.0"}


def serve(start_cwd: Path | None = None, *, stdin: Any = None, stdout: Any = None) -> int:
    """Run the stdio MCP server until stdin closes."""
    cwd = start_cwd or Path.cwd()
    in_stream = stdin or sys.stdin
    out_stream = stdout or sys.stdout

    ctx = open_context(cwd)
    try:
        for line in in_stream:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                _write(out_stream, _error(None, -32700, "parse error"))
                continue
            response = _handle(ctx, msg)
            if response is not None:
                _write(out_stream, response)
    finally:
        ctx.close()
    return 0


def _handle(ctx: ToolsContext, msg: dict[str, Any]) -> dict[str, Any] | None:
    method = msg.get("method")
    msg_id = msg.get("id")
    params = msg.get("params") or {}
    is_notification = "id" not in msg

    if method == "initialize":
        if is_notification:
            return None
        return _result(
            msg_id,
            {
                "protocolVersion": _PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": _SERVER_INFO,
            },
        )
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        if is_notification:
            return None
        tools = list_tools()
        return _result(
            msg_id,
            {
                "tools": [
                    {"name": t["name"], "description": t["description"], "inputSchema": t["schema"]}
                    for t in tools
                ]
            },
        )
    if method == "tools/call":
        if is_notification:
            return None
        name = params.get("name")
        args = params.get("arguments") or {}
        if not name:
            return _error(msg_id, -32602, "missing tool name")
        result = call_tool(ctx, str(name), args)
        return _result(
            msg_id,
            {
                "content": [{"type": "text", "text": json.dumps(result, default=str)}],
                "isError": bool(result.get("error")),
            },
        )
    if is_notification:
        return None
    return _error(msg_id, -32601, f"method not found: {method}")


def _result(msg_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _error(msg_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def _write(out: Any, obj: dict[str, Any]) -> None:
    out.write(json.dumps(obj) + "\n")
    out.flush()
