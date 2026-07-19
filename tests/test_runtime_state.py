"""Tests for persisted UI runtime state."""

from __future__ import annotations

import os
import signal
from pathlib import Path

import pytest

from server.util.runtime_state import (
    read_server_record,
    register_server,
    stop_server,
    unregister_server,
    write_server_record,
)


def test_stop_trusts_pid_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    record_path = write_server_record(
        pid=12345,
        host="127.0.0.1",
        port=59993,
        workspace=tmp_path,
    )
    if os.name != "nt":
        assert record_path.parent.stat().st_mode & 0o777 == 0o700
        assert record_path.stat().st_mode & 0o777 == 0o600

    killed: list[tuple[int, int]] = []
    alive = {12345: True}

    def fake_kill(pid: int, sig: int) -> None:
        killed.append((pid, sig))
        if sig in (signal.SIGTERM, signal.SIGKILL):
            alive[pid] = False

    def fake_is_alive(pid: int) -> bool:
        return alive.get(pid, False)

    monkeypatch.setattr(os, "kill", fake_kill)
    monkeypatch.setattr("server.util.runtime_state.is_process_alive", fake_is_alive)

    ok, message = stop_server(59993)
    assert ok is True
    assert "Stopped Cairn on port 59993" in message
    assert (12345, signal.SIGTERM) in killed
    assert read_server_record(59993) is None


def test_unregister_only_current_process(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    register_server(host="127.0.0.1", port=59992, workspace=None)
    unregister_server(59992)
    assert read_server_record(59992) is None

    register_server(host="127.0.0.1", port=59992, workspace=None)
    record = read_server_record(59992)
    assert record is not None
    assert record.pid == os.getpid()
