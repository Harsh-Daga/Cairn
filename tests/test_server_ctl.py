"""Server control helpers."""

from __future__ import annotations

from server.util.server_ctl import pids_on_port, stop_server_on_port


def test_pids_on_port_free() -> None:
    # Use a high ephemeral port unlikely to be in use in CI.
    assert pids_on_port(59999) == []


def test_stop_server_on_port_noop() -> None:
    assert stop_server_on_port(59998) is False
