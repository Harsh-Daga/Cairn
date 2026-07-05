"""Tests for cairn doctor."""

from __future__ import annotations

from server.doctor import run_doctor


def test_doctor_runs_all_checks() -> None:
    results = run_doctor()
    names = {r.name for r in results}
    assert "Python >=3.11" in names
    assert "Static UI assets" in names
    assert "Adapters detected" in names


def test_doctor_python_passes() -> None:
    results = run_doctor()
    python = next(r for r in results if r.name == "Python >=3.11")
    assert python.ok
