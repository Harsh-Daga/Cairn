"""Find and stop Cairn UI server processes."""

from __future__ import annotations

import os
import signal
import subprocess
import sys


def pids_on_port(port: int) -> list[int]:
    """Return PIDs listening on ``port`` (best-effort, Unix-first)."""
    if sys.platform == "win32":
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

    result = subprocess.run(
        ["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return []
    out: list[int] = []
    for token in result.stdout.strip().split():
        try:
            out.append(int(token))
        except ValueError:
            continue
    return sorted(set(out))


def stop_server_on_port(port: int) -> bool:
    """Send SIGTERM to listeners on ``port``. Returns True if any were stopped."""
    pids = pids_on_port(port)
    if not pids:
        return False
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            continue
        except PermissionError:
            continue
    return True
