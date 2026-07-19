"""Honest local resource / disk inventory and descriptive growth forecast."""

from __future__ import annotations

import os
import sqlite3
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, TypedDict, cast

from server.configuration import load_config

BudgetStatus = Literal["ok", "warn", "over", "unknown"]
ShieldState = Literal[
    "healthy",
    "degraded",
    "paused",
    "quarantined",
    "attention",
    "unknown",
    "unavailable",
]


class ResourceShieldFields(TypedDict):
    state: ShieldState
    summary: str
    facts: list[str]
    limitation: str


try:
    import resource as _stdlib_resource
except ImportError:  # pragma: no cover - non-Unix
    _stdlib_resource = None  # type: ignore[assignment]


@dataclass(frozen=True, slots=True)
class DirSize:
    path: str
    bytes: int
    file_count: int
    present: bool


def _dir_size(path: Path) -> DirSize:
    if not path.is_dir():
        return DirSize(path=str(path), bytes=0, file_count=0, present=False)
    total = 0
    count = 0
    for child in path.rglob("*"):
        try:
            if child.is_symlink() or not child.is_file():
                continue
            total += child.stat().st_size
            count += 1
        except OSError:
            continue
    return DirSize(path=str(path), bytes=total, file_count=count, present=True)


def _file_size(path: Path) -> int | None:
    try:
        return path.stat().st_size if path.is_file() and not path.is_symlink() else None
    except OSError:
        return None


def inventory_disk(workspace_root: Path) -> dict[str, Any]:
    """Break out Cairn on-disk footprint by category (no process claims)."""
    root = (workspace_root / ".cairn").resolve()
    db = root / "cairn.db"
    wal = root / "cairn.db-wal"
    shm = root / "cairn.db-shm"
    exports = _dir_size(root / "exports")
    backups = _dir_size(root / "backups")
    regressions = _dir_size(root / "regressions")
    receipts = _dir_size(root / "receipts")
    static = _dir_size(root / "static")
    known_dirs = {"exports", "backups", "regressions", "receipts", "static"}
    other = 0
    other_files = 0
    if root.is_dir():
        for child in root.iterdir():
            name = child.name
            if name.startswith("cairn.db") or name in known_dirs:
                continue
            if child.is_file() and not child.is_symlink():
                try:
                    other += child.stat().st_size
                    other_files += 1
                except OSError:
                    continue
            elif child.is_dir() and not child.is_symlink():
                sized = _dir_size(child)
                other += sized.bytes
                other_files += sized.file_count
    db_bytes = _file_size(db) or 0
    wal_bytes = _file_size(wal) or 0
    shm_bytes = _file_size(shm) or 0
    total = (
        db_bytes
        + wal_bytes
        + shm_bytes
        + exports.bytes
        + backups.bytes
        + regressions.bytes
        + receipts.bytes
        + static.bytes
        + other
    )
    return {
        "cairn_dir": str(root),
        "categories": {
            "database_bytes": _file_size(db),
            "wal_bytes": _file_size(wal),
            "shm_bytes": _file_size(shm),
            "exports": asdict(exports),
            "backups": asdict(backups),
            "regressions": asdict(regressions),
            "receipts_cache": asdict(receipts),
            "static_exports": asdict(static),
            "other_bytes": other,
            "other_file_count": other_files,
        },
        "total_bytes": total,
        "permissions": {
            "cairn_dir_mode": oct(root.stat().st_mode & 0o777) if root.is_dir() else None,
            "expected_mode": "0o700",
        },
    }


def forecast_growth(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    current_total_bytes: int,
    days: int = 7,
) -> dict[str, Any]:
    """Descriptive growth forecast from recent ingest volume — not a CI."""
    since = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    row = conn.execute(
        """
        SELECT COUNT(*) AS traces,
               COALESCE(SUM(span_count), 0) AS spans,
               COALESCE(SUM(input_tokens + output_tokens), 0) AS tokens
        FROM traces
        WHERE workspace_id = ? AND started_at >= ?
        """,
        (workspace_id, since),
    ).fetchone()
    traces = int(row["traces"] or 0) if row else 0
    spans = int(row["spans"] or 0) if row else 0
    tokens = int(row["tokens"] or 0) if row else 0
    estimated_bytes_added = spans * 200
    per_day = estimated_bytes_added / max(days, 1)
    return {
        "window_days": days,
        "traces_ingested": traces,
        "spans_ingested": spans,
        "tokens_recorded": tokens,
        "estimated_bytes_added": estimated_bytes_added,
        "estimated_bytes_per_day": round(per_day),
        "projected_total_in_30d": (current_total_bytes + int(per_day * 30) if traces > 0 else None),
        "kind": "descriptive",
        "limitation": (
            "Growth forecast is a descriptive extrapolation from recent span counts, "
            "not a confidence-bounded prediction. Raw text retention is not modeled yet."
        ),
    }


def budget_status(total_bytes: int, soft_budget_bytes: int | None) -> dict[str, Any]:
    if soft_budget_bytes is None or soft_budget_bytes <= 0:
        return {
            "status": "unknown",
            "soft_budget_bytes": None,
            "ratio": None,
            "message": "No soft disk budget configured ([resources].soft_budget_bytes).",
        }
    ratio = total_bytes / soft_budget_bytes
    if ratio >= 1.0:
        status: BudgetStatus = "over"
        message = "Soft disk budget exceeded; compaction/cleanup requires confirmation."
    elif ratio >= 0.8:
        status = "warn"
        message = "Approaching soft disk budget (≥80%)."
    else:
        status = "ok"
        message = "Under soft disk budget."
    return {
        "status": status,
        "soft_budget_bytes": soft_budget_bytes,
        "ratio": round(ratio, 4),
        "message": message,
    }


def process_snapshot() -> dict[str, Any]:
    """Best-effort current-process RSS; never invents idle-soak claims."""
    pid = os.getpid()
    rss = None
    if _stdlib_resource is not None:
        try:
            usage = _stdlib_resource.getrusage(_stdlib_resource.RUSAGE_SELF)
            rss = int(usage.ru_maxrss)
            if sys.platform.startswith("linux"):
                rss *= 1024
        except Exception:
            rss = None
    return {
        "pid": pid,
        "rss_bytes": rss,
        "limitation": (
            "RSS is a point sample for this process only. "
            "Idle CPU soak and multi-hour stability are not claimed here."
        ),
    }


def format_bytes(value: int | None) -> str:
    if value is None:
        return "n/a"
    if value < 1024:
        return f"{value} B"
    units = ("KiB", "MiB", "GiB", "TiB")
    amount = float(value)
    for unit in units:
        amount /= 1024.0
        if amount < 1024.0:
            return f"{amount:.1f} {unit}"
    return f"{amount:.1f} PiB"


def build_resource_report(
    conn: sqlite3.Connection,
    *,
    workspace_root: Path,
    workspace_id: str,
) -> dict[str, Any]:
    """Versioned resource report used by CLI and API."""
    config = load_config(workspace_root)
    soft_budget = config.resources.soft_budget_bytes
    disk = inventory_disk(workspace_root)
    total = int(disk["total_bytes"])
    forecast = forecast_growth(conn, workspace_id=workspace_id, current_total_bytes=total)
    budget = budget_status(total, soft_budget)
    return {
        "schema": "cairn.resource.v1",
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "workspace_root": str(workspace_root),
        "disk": disk,
        "budget": budget,
        "forecast": forecast,
        "process": process_snapshot(),
        "collection": {
            "mode": config.collection.mode,
            "help": "Backend auto-sync mode; independent of browser SSE.",
        },
        "limitation": (
            "Inventory is local filesystem accounting. "
            "CPU soak, queue depth, and watcher health expand in later T06 tasks."
        ),
    }


def _dir_bytes_or_none(entry: Any) -> int | None:
    if not isinstance(entry, dict) or not entry.get("present"):
        return None
    return int(entry.get("bytes") or 0)


def resource_status_payload(report: dict[str, Any]) -> dict[str, Any]:
    """Compact API shape for WorkspaceResponse.resources."""
    categories = report["disk"]["categories"]
    return {
        "disk": {
            "cairn_dir": report["disk"]["cairn_dir"],
            "total_bytes": int(report["disk"]["total_bytes"]),
            "database_bytes": categories.get("database_bytes"),
            "wal_bytes": categories.get("wal_bytes"),
            "exports_bytes": _dir_bytes_or_none(categories.get("exports")),
            "backups_bytes": _dir_bytes_or_none(categories.get("backups")),
            "regressions_bytes": _dir_bytes_or_none(categories.get("regressions")),
        },
        "budget": report["budget"],
        "forecast": {
            "window_days": report["forecast"]["window_days"],
            "traces_ingested": report["forecast"]["traces_ingested"],
            "estimated_bytes_per_day": report["forecast"]["estimated_bytes_per_day"],
            "projected_total_in_30d": report["forecast"]["projected_total_in_30d"],
            "kind": "descriptive",
            "limitation": report["forecast"]["limitation"],
        },
        "process_rss_bytes": report["process"].get("rss_bytes"),
        "collection_mode": report["collection"].get("mode"),
        "limitation": report["limitation"],
    }


def resource_shield_fields(report: dict[str, Any]) -> ResourceShieldFields:
    """Overview/session shield fields derived from a measured inventory."""
    budget = report["budget"]
    status = str(budget["status"])
    state: ShieldState
    if status in {"over", "warn"}:
        state = "attention"
    elif status == "ok":
        state = "healthy"
    else:
        state = "unknown"
    total = int(report["disk"]["total_bytes"])
    facts = [
        f"On-disk total: {format_bytes(total)}.",
        f"Database: {format_bytes(report['disk']['categories'].get('database_bytes'))}.",
        f"WAL: {format_bytes(report['disk']['categories'].get('wal_bytes'))}.",
        budget["message"],
    ]
    rss = report["process"].get("rss_bytes")
    if rss is not None:
        facts.append(f"Process RSS sample: {format_bytes(int(rss))}.")
    if report["forecast"]["traces_ingested"] > 0:
        facts.append(
            "Descriptive growth ~"
            f"{format_bytes(report['forecast']['estimated_bytes_per_day'])}/day "
            f"(last {report['forecast']['window_days']}d ingest)."
        )
    # Circuit-breaker overlay (paused/quarantined/degraded take precedence).
    root = Path(str(report.get("workspace_root") or ""))
    if root.is_dir():
        from server.ingest.circuit_breakers import shield_overlay

        overlay = shield_overlay(root)
        facts.extend(overlay.get("facts") or [])
        overlay_state = overlay.get("state")
        if overlay_state in {"paused", "quarantined", "degraded"}:
            state = cast(ShieldState, overlay_state)
    return {
        "state": state,
        "summary": (
            f"Local Cairn data uses {format_bytes(total)} "
            f"(collection mode: {report['collection']['mode']})."
        ),
        "facts": facts,
        "limitation": (
            f"{report['limitation']} {report['process'].get('limitation', '')} "
            f"{report['forecast'].get('limitation', '')}"
        ).strip(),
    }
