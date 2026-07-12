"""Server control helpers."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from server.util.runtime_state import (
    clear_server_record,
    pid_file,
    read_server_record,
    register_server,
    state_dir,
    stop_server,
    unregister_server,
    write_server_record,
)
from server.util.server_ctl import find_server_pids, listeners_on_port, stop_server_on_port


def test_listeners_on_port_free() -> None:
    assert listeners_on_port(59999) == []


def test_stop_server_on_port_noop() -> None:
    assert stop_server_on_port(59998) is False


def test_find_server_pids_free() -> None:
    assert find_server_pids(59997) == []


def test_register_stop_and_clear(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    register_server(host="127.0.0.1", port=59996, workspace=tmp_path)
    record = read_server_record(59996)
    assert record is not None
    assert record.pid == os.getpid()
    assert record.host == "127.0.0.1"
    assert record.workspace == str(tmp_path.resolve())

    unregister_server(59996)
    assert read_server_record(59996) is None


def test_stale_pid_file_is_removed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    write_server_record(pid=999999, host="127.0.0.1", port=59995, workspace=None)
    ok, message = stop_server(59995)
    assert ok is False
    assert "No running server found" in message
    assert read_server_record(59995) is None


def test_pid_file_location(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    register_server(host="127.0.0.1", port=59994, workspace=None)
    expected = state_dir() / "ui-59994.json"
    assert pid_file(59994) == expected
    assert expected.is_file()
    clear_server_record(59994)
