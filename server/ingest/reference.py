"""Reference/zero-copy content mode: source-authoritative logs + drift detection."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from server.ingest.contract import IngestCursor, cursor_for_file
from server.util.private_files import ensure_private_dir, write_private_text

DriftKind = Literal["missing", "rewritten_shorter", "mtime_regression"]

_LIMITATION = (
    "Reference mode treats agent source logs as authoritative for raw text. "
    "Cairn still stores cursors, hashes, metrics, and outcomes — not a pure zero-copy "
    "of every field. Replay/search of raw text is unavailable when the source is "
    "missing or rewritten; drift is recorded instead of presenting stale text as current."
)


@dataclass(frozen=True, slots=True)
class SourceDriftEvent:
    timestamp: str
    kind: DriftKind
    adapter_id: str
    source_path: str
    previous_size: int | None
    current_size: int | None
    previous_mtime_ns: int | None
    current_mtime_ns: int | None
    limitation: str = _LIMITATION


def drift_path(workspace_root: Path) -> Path:
    return (workspace_root / ".cairn" / "source_drift.jsonl").resolve()


def detect_source_drift(
    path: Path,
    previous: IngestCursor | None,
    *,
    adapter_id: str = "",
) -> SourceDriftEvent | None:
    """Return a drift event when the source log disappeared or was rewritten."""
    if previous is None:
        return None
    now = datetime.now(UTC).isoformat()
    if not path.is_file():
        return SourceDriftEvent(
            timestamp=now,
            kind="missing",
            adapter_id=adapter_id,
            source_path=str(path),
            previous_size=previous.size,
            current_size=None,
            previous_mtime_ns=previous.mtime_ns,
            current_mtime_ns=None,
        )
    try:
        current = cursor_for_file(path)
    except OSError:
        return SourceDriftEvent(
            timestamp=now,
            kind="missing",
            adapter_id=adapter_id,
            source_path=str(path),
            previous_size=previous.size,
            current_size=None,
            previous_mtime_ns=previous.mtime_ns,
            current_mtime_ns=None,
        )
    if previous.size is not None and current.size is not None and current.size < previous.size:
        return SourceDriftEvent(
            timestamp=now,
            kind="rewritten_shorter",
            adapter_id=adapter_id,
            source_path=str(path),
            previous_size=previous.size,
            current_size=current.size,
            previous_mtime_ns=previous.mtime_ns,
            current_mtime_ns=current.mtime_ns,
        )
    if (
        previous.mtime_ns is not None
        and current.mtime_ns is not None
        and current.mtime_ns < previous.mtime_ns
    ):
        return SourceDriftEvent(
            timestamp=now,
            kind="mtime_regression",
            adapter_id=adapter_id,
            source_path=str(path),
            previous_size=previous.size,
            current_size=current.size,
            previous_mtime_ns=previous.mtime_ns,
            current_mtime_ns=current.mtime_ns,
        )
    return None


def record_drift(workspace_root: Path, event: SourceDriftEvent) -> None:
    path = drift_path(workspace_root)
    ensure_private_dir(path.parent)
    line = json.dumps(asdict(event), sort_keys=True, ensure_ascii=False) + "\n"
    if path.is_file():
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line)
    else:
        write_private_text(path, line)


def list_drift(workspace_root: Path, *, limit: int = 100) -> list[dict[str, Any]]:
    path = drift_path(workspace_root)
    if not path.is_file():
        return []
    cap = max(1, min(int(limit), 500))
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines()[-cap:]:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def reference_status(workspace_root: Path) -> dict[str, Any]:
    rows = list_drift(workspace_root, limit=500)
    return {
        "mode_name": "reference",
        "source_authoritative": True,
        "stores_raw_text_inline": False,
        "stores": [
            "ingest cursors",
            "content hashes",
            "normalized metrics",
            "outcomes / evidence references",
        ],
        "does_not_claim_zero_copy_for": [
            "hashes",
            "token/cost aggregates",
            "normalized span rows",
            "outcomes",
        ],
        "drift_events": len(rows),
        "recent_drift": rows[-10:],
        "limitation": _LIMITATION,
    }
