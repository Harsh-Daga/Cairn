"""Static export snapshot tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from server.demo.seed import seed_demo_workspace
from server.export.static import export_static_snapshot


def _make_fake_static_dir(path: Path) -> None:
    (path / "assets").mkdir(parents=True, exist_ok=True)
    (path / "assets" / "main.js").write_text("console.log('demo');\n", encoding="utf-8")
    (path / "index.html").write_text(
        (
            "<!doctype html><html><head><meta charset='utf-8'></head>"
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
    result = export_static_snapshot(workspace, out_dir)
    assert result["trace_count"] == 120
    assert result["payload_count"] > 20

    index_html = (out_dir / "index.html").read_text(encoding="utf-8")
    assert "window.__CAIRN_STATIC__=true;" in index_html
    assert (out_dir / "assets" / "main.js").is_file()
    assert (out_dir / "api" / "overview__days=30.json").is_file()
    assert (out_dir / "api" / "traces__days=30__limit=100__offset=0.json").is_file()
    assert (out_dir / "api" / "workspace.json").is_file()

    overview = json.loads((out_dir / "api" / "overview__days=30.json").read_text(encoding="utf-8"))
    assert overview["kpis"]["traces"] > 0
    assert len(overview["narrative"]) > 0


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
