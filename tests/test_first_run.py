"""Clean-workspace first-run contract tests."""

from pathlib import Path

from fastapi.testclient import TestClient

from server.app import create_app
from server.config import Settings


def test_clean_workspace_reports_real_empty_state_without_user_caches(tmp_path: Path) -> None:
    root = (tmp_path / "clean-workspace").resolve()
    root.mkdir()
    settings = Settings(workspace_root=root, static_dir=Settings().static_dir)

    with TestClient(create_app(settings)) as client:
        workspace = client.get("/api/workspace")
        overview = client.get("/api/overview?days=30")

    assert workspace.status_code == 200
    workspace_body = workspace.json()
    assert workspace_body["root_path"] == str(root)
    assert workspace_body["health"]["trace_count"] == 0
    assert workspace_body["adapters"] == []
    assert overview.status_code == 200
    assert overview.json()["kpis"]["traces"] == 0
    assert (root / ".cairn" / "cairn.db").is_file()
