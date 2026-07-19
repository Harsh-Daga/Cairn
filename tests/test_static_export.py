"""Static export snapshot tests."""

from __future__ import annotations

import http.server
import json
import os
import sqlite3
import subprocess
import sys
import threading
from pathlib import Path
from urllib.request import urlopen

import pytest

from server.demo.seed import seed_demo_workspace
from server.export.static import export_static_snapshot


def _make_fake_static_dir(path: Path) -> None:
    (path / "assets").mkdir(parents=True, exist_ok=True)
    (path / "assets" / "main.js").write_text("console.log('demo');\n", encoding="utf-8")
    (path / "theme-bootstrap.js").write_text("document.documentElement.dataset.theme='dark';\n")
    (path / "index.html").write_text(
        (
            "<!doctype html><html><head><script src='/theme-bootstrap.js'></script>"
            "<script src='/assets/main.js'></script></head>"
            "<body><div id='root'></div></body></html>\n"
        ),
        encoding="utf-8",
    )


def test_export_static_snapshot_writes_payloads(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    seed_demo_workspace(workspace, reset=True)
    static_dir = tmp_path / "static-build"
    _make_fake_static_dir(static_dir)
    monkeypatch.setenv("CAIRN_STATIC_DIR", str(static_dir))

    out_dir = tmp_path / "snapshot"
    with sqlite3.connect(workspace / ".cairn" / "cairn.db") as conn:
        conn.execute(
            """UPDATE spans
               SET kind = 'user_msg', text_inline = ?, attrs_json = ?
               WHERE span_id = (SELECT span_id FROM spans LIMIT 1)""",
            (
                "Bearer private-token-123456 at /Users/alice/private/repo.py",
                json.dumps({"api_key": "sk-super-secret-value", "note": str(workspace)}),
            ),
        )
    result = export_static_snapshot(workspace, out_dir)
    assert result["trace_count"] == 120
    assert result["total_trace_count"] == 120
    assert result["payload_count"] > 20

    index_html = (out_dir / "index.html").read_text(encoding="utf-8")
    assert 'http-equiv="Content-Security-Policy"' in index_html
    assert "script-src 'self'" in index_html
    assert "unsafe-inline" not in index_html.split("script-src", 1)[1].split(";", 1)[0]
    assert '<script src="./cairn-static.js"></script>' in index_html
    assert (out_dir / "cairn-static.js").read_text(encoding="utf-8") == (
        "window.__CAIRN_STATIC__=true;\n"
    )
    assert "./assets/main.js" in index_html
    assert "./theme-bootstrap.js" in index_html
    assert 'src="/assets/' not in index_html
    assert (out_dir / "theme-bootstrap.js").is_file()
    assert (out_dir / "assets" / "main.js").is_file()
    assert (out_dir / "api" / "overview__days=30.json").is_file()
    assert (out_dir / "api" / "analytics" / "budget.json").is_file()
    assert (out_dir / "api" / "traces__days=30__limit=50__offset=0.json").is_file()
    assert (out_dir / "api" / "search__limit=20__q=demo.json").is_file()
    assert (out_dir / "api" / "recap.json").is_file()
    assert (out_dir / "api" / "static-manifest.json").is_file()
    assert (out_dir / "api" / "workspace.json").is_file()

    budget = json.loads((out_dir / "api" / "analytics" / "budget.json").read_text(encoding="utf-8"))
    assert budget["budget_state"] in {"unconfigured", "healthy", "attention", "over"}
    assert "month_spend_usd" in budget

    overview = json.loads((out_dir / "api" / "overview__days=30.json").read_text(encoding="utf-8"))
    assert overview["kpis"]["traces"] > 0
    assert len(overview["narrative"]) > 0
    assert {category["category"] for category in overview["attention"]} == {
        "failed_outcomes",
        "verification_debt",
        "unsupported_claims",
        "drift",
        "retry_storms",
        "parse_health",
        "budget",
        "decayed_rules",
    }
    trace_page = json.loads(
        (out_dir / "api" / "traces__days=30__limit=50__offset=0.json").read_text(encoding="utf-8")
    )
    assert all(row["first_user_request"] in {None, "<redacted>"} for row in trace_page["traces"])
    serialized = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted((out_dir / "api").rglob("*.json"))
    )
    for private_value in (
        str(workspace),
        "/Users/alice/private/repo.py",
        "private-token-123456",
        "sk-super-secret-value",
    ):
        assert private_value not in serialized
    workspace_payload = json.loads((out_dir / "api" / "workspace.json").read_text(encoding="utf-8"))
    assert workspace_payload["root_path"] == "<redacted>"
    manifest = json.loads((out_dir / "api" / "static-manifest.json").read_text(encoding="utf-8"))
    assert manifest["mutations"] is False
    assert manifest["live_updates"] is False
    assert manifest["data_bounds"]["start"]
    assert manifest["data_bounds"]["end"]
    assert manifest["supported_queries"]["time_ranges"]["days"] == [1, 7, 30, 90]
    assert manifest["capture_limits"] == {
        "trace_details": 1000,
        "total_traces": 120,
        "session_diff_pairs": 10,
    }
    assert manifest["custom_range_behavior"] == "rejected"
    assert "custom_time_ranges" in manifest["unsupported"]
    assert manifest["supported_queries"]["session_diff"] == "captured adjacent recent pairs only"
    assert "session_diff" not in manifest["unsupported"]
    diff_payloads = sorted((out_dir / "api" / "traces").glob("diff__a=*__b=*.json"))
    assert len(diff_payloads) == 10
    diff_payload = json.loads(diff_payloads[0].read_text(encoding="utf-8"))
    assert diff_payload["analysis"]["comparability"]["limitation"]
    assert diff_payload["analysis"]["what_changed"]
    embedded = (out_dir / "cairn-data.js").read_text(encoding="utf-8")
    assert "window.__CAIRN_STATIC_DATA__=" in embedded
    assert "./api/static-manifest.json" in embedded
    assert "cairn-data.js" in (out_dir / "index.html").read_text(encoding="utf-8")
    assert (out_dir / ".nojekyll").is_file()
    assert (out_dir / "404.html").read_text(encoding="utf-8") == index_html
    if os.name != "nt":
        assert out_dir.stat().st_mode & 0o777 == 0o700
        assert (out_dir / "api" / "workspace.json").stat().st_mode & 0o777 == 0o600


def test_static_export_serves_under_project_site_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Project sites host the demo below /Cairn/; relative assets must resolve."""
    workspace = tmp_path / "workspace"
    seed_demo_workspace(workspace, reset=True)
    static_dir = tmp_path / "static-build"
    _make_fake_static_dir(static_dir)
    monkeypatch.setenv("CAIRN_STATIC_DIR", str(static_dir))

    site_root = tmp_path / "site-root"
    project = site_root / "Cairn"
    export_static_snapshot(workspace, project)
    assert (project / ".nojekyll").is_file()
    assert (project / "404.html").is_file()

    class _Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, directory=str(site_root), **kwargs)  # type: ignore[arg-type]

        def log_message(self, format: str, *args: object) -> None:  # noqa: A003
            return

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}/Cairn"
        with urlopen(f"{base}/", timeout=5) as resp:
            body = resp.read().decode("utf-8")
            assert resp.status == 200
        assert "./assets/main.js" in body
        assert "./theme-bootstrap.js" in body
        assert 'src="/assets/' not in body
        with urlopen(f"{base}/assets/main.js", timeout=5) as resp:
            assert resp.status == 200
            assert b"console.log" in resp.read()
        with urlopen(f"{base}/404.html", timeout=5) as resp:
            assert resp.status == 200
            assert b"cairn-static.js" in resp.read()
    finally:
        server.shutdown()
        server.server_close()


def test_static_export_declares_and_enforces_trace_detail_capture_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    seed_demo_workspace(workspace, reset=True)
    static_dir = tmp_path / "static-build"
    _make_fake_static_dir(static_dir)
    monkeypatch.setenv("CAIRN_STATIC_DIR", str(static_dir))
    monkeypatch.setattr("server.export.static.MAX_STATIC_TRACE_DETAILS", 2)

    out_dir = tmp_path / "snapshot"
    result = export_static_snapshot(workspace, out_dir)
    manifest = json.loads((out_dir / "api" / "static-manifest.json").read_text(encoding="utf-8"))

    assert result["trace_count"] == 2
    assert result["total_trace_count"] == 120
    assert result["diff_pair_count"] == 1
    assert manifest["capture_limits"] == {
        "trace_details": 2,
        "total_traces": 120,
        "session_diff_pairs": 10,
    }


def test_static_export_refuses_symlink_and_workspace_root(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    seed_demo_workspace(workspace, reset=True)
    static_dir = tmp_path / "static-build"
    _make_fake_static_dir(static_dir)
    monkeypatch.setenv("CAIRN_STATIC_DIR", str(static_dir))

    with pytest.raises(ValueError, match="protected directory"):
        export_static_snapshot(workspace, workspace)

    real_out = tmp_path / "real-out"
    real_out.mkdir()
    linked_out = tmp_path / "linked-out"
    try:
        linked_out.symlink_to(real_out, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks unavailable")
    with pytest.raises(ValueError, match="must not be a symlink"):
        export_static_snapshot(workspace, linked_out)


def test_cli_export_static(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    seed_demo_workspace(workspace, reset=True)
    static_dir = tmp_path / "ui-build"
    _make_fake_static_dir(static_dir)
    out_dir = tmp_path / "site"

    env = os.environ.copy()
    env["CAIRN_STATIC_DIR"] = str(static_dir)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "server.cli",
            "export",
            "--static",
            str(out_dir),
            "--workspace",
            str(workspace),
        ],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["trace_count"] == 120
    assert payload["payload_count"] > 20
    assert (out_dir / "api" / "actions.json").is_file()
