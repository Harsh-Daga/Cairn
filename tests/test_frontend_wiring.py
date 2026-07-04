"""Regression guard: backend payload fields must have frontend consumers."""

from __future__ import annotations

from pathlib import Path

from cairn.render.dash_payload import overview_payload
from cairn.render.session_payload import session_payload
from tests.test_dash_payload import _conn, _seed_diagnostics_run, _seed_run

ASSETS = Path(__file__).parent.parent / "cairn" / "assets"

# (payload_builder, payload_kwargs, field, js_file, js_literal)
WIRING = [
    (overview_payload, {"days": 30}, "narrative", "dashboard.js", "narrative"),
    (overview_payload, {"days": 30}, "confidence", "dashboard.js", "estimation_method"),
    (overview_payload, {"days": 30}, "confidence", "dashboard.js", "estimation_error_pct"),
    (overview_payload, {"days": 30}, "diagnostics_summary", "dashboard.js", "diagnostics_summary"),
]

SESSION_WIRING = [
    ("diagnostics", "session.js", "diagnostics"),
    ("narrative", "session.js", "narrative"),
    ("ideal_path", "session.js", "ideal_path"),
    ("failure_origin_event_id", "session.js", "failure_origin_event_id"),
    ("cascade_root_event_id", "session.js", "cascade_root_event_id"),
    ("ideal_path", "session.js", "ideal_path_savings_tokens"),
    ("confidence", "session.js", "estimation_method"),
    ("confidence", "session.js", "estimation_error_pct"),
    ("event_count_for_diagnosis", "session.js", "event_count_for_diagnosis"),
    ("agents", "session.js", "Cost by agent"),
]


def _js(name: str) -> str:
    return (ASSETS / name).read_text(encoding="utf-8")


def test_overview_payload_fields_have_dashboard_consumers(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    _seed_run(conn)
    for builder, kwargs, field, js_file, literal in WIRING:
        payload = builder(conn, **kwargs)
        assert field in payload, f"overview_payload missing {field}"
        assert literal in _js(js_file), f"{js_file} missing consumer for {field} ({literal})"
    conn.close()


def test_session_payload_fields_have_session_consumers(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    _seed_diagnostics_run(conn)
    payload = session_payload(conn, run_id="diag-run")
    js = _js("session.js")
    for field, js_file, literal in SESSION_WIRING:
        assert field in payload, f"session_payload missing {field}"
        assert literal in js, f"{js_file} missing consumer for {field} ({literal})"
    conn.close()


def test_index_html_has_narrative_hero_mount() -> None:
    html = (ASSETS / "index.html").read_text(encoding="utf-8")
    assert "narrative-hero" in html
    assert "narrative-headline" in html
    assert "narrative-cta" in html


def test_session_html_has_autopsy_mount() -> None:
    html = (ASSETS / "session.html").read_text(encoding="utf-8")
    assert "autopsy-mount" in html
