"""Port-based helpers for locating Cairn UI listeners."""

from __future__ import annotations

import subprocess
import sys


def _parse_pids(text: str) -> list[int]:
    out: list[int] = []
    for token in text.strip().split():
        try:
            out.append(int(token))
        except ValueError:
            continue
    return sorted(set(out))


def listeners_on_port(port: int) -> list[int]:
    """Return PIDs listening on ``port``."""
    if sys.platform == "win32":
        return _listeners_on_port_windows(port)
    commands = [
        ["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"],
        ["lsof", "-nP", "-iTCP", f":{port}", "-sTCP:LISTEN", "-t"],
    ]
    for cmd in commands:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return _parse_pids(result.stdout)
    return []


def _listeners_on_port_windows(port: int) -> list[int]:
    result = subprocess.run(
        ["netstat", "-ano"],
        capture_output=True,
        text=True,
        check=False,
    )
    pids: list[int] = []
    suffix = f":{port}"
    for line in result.stdout.splitlines():
        if "LISTENING" not in line or suffix not in line:
            continue
        parts = line.split()
        if parts:
            try:
                pids.append(int(parts[-1]))
            except ValueError:
                continue
    return sorted(set(pids))


def find_server_pids(port: int) -> list[int]:
    """Return listener PIDs on ``port`` (legacy helper for doctor/tests)."""
    return listeners_on_port(port)


def stop_server_on_port(port: int) -> bool:
    """Stop the Cairn UI server on ``port``."""
    from server.util.runtime_state import stop_server

    ok, _message = stop_server(port)
    return ok
