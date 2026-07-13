"""Persisted runtime state for the Cairn UI server."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class ServerRecord:
    pid: int
    host: str
    port: int
    started_at: str
    workspace: str | None = None


def state_dir() -> Path:
    """Return the per-user Cairn state directory."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    path = base / "cairn"
    path.mkdir(parents=True, exist_ok=True)
    return path


def pid_file(port: int) -> Path:
    return state_dir() / f"ui-{port}.json"


def read_server_record(port: int) -> ServerRecord | None:
    path = pid_file(port)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return ServerRecord(
            pid=int(payload["pid"]),
            host=str(payload["host"]),
            port=int(payload["port"]),
            started_at=str(payload["started_at"]),
            workspace=str(payload["workspace"]) if payload.get("workspace") else None,
        )
    except (OSError, TypeError, ValueError, KeyError):
        return None


def write_server_record(
    *,
    pid: int,
    host: str,
    port: int,
    workspace: Path | None = None,
) -> Path:
    record = ServerRecord(
        pid=pid,
        host=host,
        port=port,
        started_at=datetime.now(UTC).isoformat(),
        workspace=str(workspace.resolve()) if workspace else None,
    )
    path = pid_file(port)
    path.write_text(json.dumps(record.__dict__, indent=2), encoding="utf-8")
    return path


def clear_server_record(port: int) -> None:
    path = pid_file(port)
    try:
        path.unlink(missing_ok=True)
    except OSError:
        return


def register_server(*, host: str, port: int, workspace: Path | None = None) -> Path:
    """Record the current process as the UI server for ``port``."""
    return write_server_record(pid=os.getpid(), host=host, port=port, workspace=workspace)


def unregister_server(port: int) -> None:
    """Remove the UI server record when owned by this process."""
    record = read_server_record(port)
    if record is None or record.pid != os.getpid():
        return
    clear_server_record(port)


def is_process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    if sys.platform != "win32":
        # `kill(pid, 0)` reports zombies as alive until their parent reaps
        # them. Treat them as stopped so SIGKILL success is not reported as a
        # false failure during the short reap window.
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "stat="],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return False
        if result.stdout.lstrip().startswith("Z"):
            return False
    return True


def _process_command(pid: int) -> str | None:
    if sys.platform == "win32":
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None
        return result.stdout.strip()
    result = subprocess.run(
        ["ps", "-p", str(pid), "-o", "command="],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    command = result.stdout.strip()
    return command or None


def is_cairn_ui_process(pid: int) -> bool:
    """Return True when ``pid`` is running ``cairn ui``."""
    command = _process_command(pid)
    if not command:
        return False
    if "pytest" in command:
        return False
    normalized = command.replace("\\", "/")
    return "/cairn ui" in normalized or normalized.endswith(" cairn ui")


def stop_server(port: int, *, timeout: float = 5.0) -> tuple[bool, str]:
    """Stop the Cairn UI server bound to ``port``."""
    targets: list[int] = []

    record = read_server_record(port)
    if record is not None:
        if is_process_alive(record.pid):
            targets.append(record.pid)
        else:
            clear_server_record(port)

    if not targets:
        from server.util.server_ctl import listeners_on_port

        for pid in listeners_on_port(port):
            if is_cairn_ui_process(pid):
                targets.append(pid)

    targets = sorted(set(targets))
    if not targets:
        return False, "No running server found."

    for pid in targets:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            continue

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not any(is_process_alive(pid) for pid in targets):
            clear_server_record(port)
            return True, f"Stopped Cairn on port {port}."
        time.sleep(0.1)

    for pid in targets:
        if not is_process_alive(pid):
            continue
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            continue

    kill_deadline = time.monotonic() + 1.0
    while time.monotonic() < kill_deadline and any(is_process_alive(pid) for pid in targets):
        time.sleep(0.05)

    survivors = [pid for pid in targets if is_process_alive(pid)]
    if survivors:
        pids = ", ".join(map(str, survivors))
        return False, f"Failed to stop Cairn on port {port} (pids: {pids})."
    clear_server_record(port)
    return True, f"Stopped Cairn on port {port}."
