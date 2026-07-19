"""Disk inventory, soft budget, and descriptive growth forecast."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from server.api.payload_domains.overview import build_overview
from server.api.payload_domains.system import build_workspace
from server.configuration import mutate_config
from server.doctor import run_doctor
from server.store.db import Database
from server.util.ids import new_ulid
from server.util.private_files import write_private_text
from server.util.resources import (
    budget_status,
    build_resource_report,
    inventory_disk,
    resource_status_payload,
)


def _seed_workspace(tmp_path: Path) -> tuple[Path, Database, str]:
    root = tmp_path / "ws"
    root.mkdir()
    cairn = root / ".cairn"
    cairn.mkdir()
    write_private_text(cairn / "config.toml", "")
    db = Database(cairn / "cairn.db")
    ws_id = new_ulid()
    db.write(
        lambda conn: conn.execute(
            "INSERT INTO workspaces (workspace_id, root_path, name, created_at) "
            "VALUES (?, ?, ?, ?)",
            (ws_id, str(root), "resources", "2026-07-01T00:00:00Z"),
        )
    )
    return root, db, ws_id


def test_inventory_breaks_out_categories(tmp_path: Path) -> None:
    root, db, _ws_id = _seed_workspace(tmp_path)
    exports = root / ".cairn" / "exports"
    exports.mkdir()
    (exports / "bundle.json").write_text("{}", encoding="utf-8")
    inventory = inventory_disk(root)
    assert inventory["total_bytes"] > 0
    assert inventory["categories"]["database_bytes"] is not None
    assert inventory["categories"]["exports"]["present"] is True
    assert inventory["categories"]["exports"]["bytes"] > 0
    assert inventory["categories"]["regressions"]["present"] is False
    db.close()


def test_soft_budget_warn_and_over() -> None:
    assert budget_status(50, 100)["status"] == "ok"
    assert budget_status(85, 100)["status"] == "warn"
    assert budget_status(120, 100)["status"] == "over"
    assert budget_status(10, None)["status"] == "unknown"


def test_resource_report_and_workspace_embed(tmp_path: Path) -> None:
    root, db, ws_id = _seed_workspace(tmp_path)
    mutate_config(
        "set",
        "resources.soft_budget_bytes",
        value="1048576",
        scope="workspace",
        workspace_root=root,
    )
    now = datetime.now(UTC)
    for index in range(3):
        started = (now - timedelta(days=index)).isoformat().replace("+00:00", "Z")
        db.write(
            lambda conn, i=index, started_at=started: conn.execute(
                """
                INSERT INTO traces (
                  trace_id, workspace_id, source, started_at, status, title,
                  input_tokens, output_tokens, cost, cost_source, span_count, waste_tokens
                ) VALUES (?, ?, 'cursor', ?, 'completed', ?, 10, 20, 0.01, 'priced', 5, 0)
                """,
                (new_ulid(), ws_id, started_at, f"t{i}"),
            )
        )
    report = build_resource_report(db.reader, workspace_root=root, workspace_id=ws_id)
    assert report["schema"] == "cairn.resource.v1"
    assert report["budget"]["status"] in {"ok", "warn", "over"}
    assert report["forecast"]["kind"] == "descriptive"
    assert report["forecast"]["traces_ingested"] == 3
    payload = resource_status_payload(report)
    assert payload["disk"]["total_bytes"] == report["disk"]["total_bytes"]
    workspace = build_workspace(db.reader, workspace_id=ws_id, root_path=str(root))
    assert workspace.resources is not None
    assert workspace.resources.disk.total_bytes >= 0
    assert workspace.resources.budget.status in {"ok", "warn", "over", "unknown"}
    overview = build_overview(
        db.reader,
        workspace_id=ws_id,
        workspace_root=root,
    )
    resource = next(shield for shield in overview.shields if shield.shield == "resource")
    assert resource.state != "unavailable"
    assert any("disk" in fact.lower() or "bytes" in fact.lower() for fact in resource.facts)
    db.close()


def test_doctor_disk_soft_budget_advisory(tmp_path: Path) -> None:
    root, db, _ws_id = _seed_workspace(tmp_path)
    mutate_config(
        "set",
        "resources.soft_budget_bytes",
        value="1",
        scope="workspace",
        workspace_root=root,
    )
    results = run_doctor(workspace=root)
    disk_check = next(item for item in results if item.name == "Disk soft budget")
    assert disk_check.ok is False
    assert disk_check.fix is not None
    db.close()
