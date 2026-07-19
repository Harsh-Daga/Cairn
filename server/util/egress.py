"""Privacy-minimized ledger for Cairn-initiated network attempts (ADR-11)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from server.util.private_files import ensure_private_dir, write_private_text

EGRESS_SCHEMA = "cairn.egress.v1"
_MAX_ENTRIES_READ = 500
_LIMITATION = (
    "Ledger records only Cairn-initiated attempts. "
    "It cannot observe traffic from unrelated agent processes."
)


@dataclass(frozen=True, slots=True)
class EgressEntry:
    timestamp: str
    trigger: str
    destination_origin: str
    purpose: str
    provider: str
    field_classes: list[str]
    byte_estimate: int | None
    consent_source: str
    success: bool
    error_class: str | None
    schema: str = EGRESS_SCHEMA
    limitation: str = _LIMITATION


def egress_path(workspace_root: Path) -> Path:
    return (workspace_root / ".cairn" / "egress.jsonl").resolve()


def origin_from_url(url: str) -> str:
    """Return scheme://host only — never path/query/fragment or credentials."""
    parts = urlsplit(url.strip())
    if not parts.scheme or not parts.netloc:
        return "unknown"
    # Strip userinfo if present.
    host = parts.netloc.split("@")[-1]
    return f"{parts.scheme}://{host}"


def record_egress(
    workspace_root: Path,
    *,
    trigger: str,
    destination: str,
    purpose: str,
    provider: str,
    field_classes: list[str] | None = None,
    byte_estimate: int | None = None,
    consent_source: str = "explicit_consent",
    success: bool,
    error_class: str | None = None,
) -> EgressEntry:
    """Append one secret-free egress row. Never stores tokens, prompts, or payloads."""
    entry = EgressEntry(
        timestamp=datetime.now(UTC).isoformat(),
        trigger=trigger[:120],
        destination_origin=origin_from_url(destination),
        purpose=purpose[:200],
        provider=provider[:120],
        field_classes=list(field_classes or []),
        byte_estimate=byte_estimate,
        consent_source=consent_source[:80],
        success=success,
        error_class=(error_class[:80] if error_class else None),
    )
    path = egress_path(workspace_root)
    ensure_private_dir(path.parent)
    line = json.dumps(asdict(entry), sort_keys=True, ensure_ascii=False) + "\n"
    if path.is_file():
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line)
    else:
        write_private_text(path, line)
    return entry


def list_egress(
    workspace_root: Path,
    *,
    limit: int = 100,
) -> list[dict[str, Any]]:
    path = egress_path(workspace_root)
    if not path.is_file():
        return []
    cap = max(1, min(int(limit), _MAX_ENTRIES_READ))
    lines = path.read_text(encoding="utf-8").splitlines()
    out: list[dict[str, Any]] = []
    for line in lines[-cap:]:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def egress_status(workspace_root: Path) -> dict[str, Any]:
    rows = list_egress(workspace_root, limit=_MAX_ENTRIES_READ)
    successes = sum(1 for r in rows if r.get("success"))
    failures = sum(1 for r in rows if r.get("success") is False)
    last = rows[-1] if rows else None
    return {
        "schema": EGRESS_SCHEMA,
        "path": str(egress_path(workspace_root)),
        "entry_count": len(rows),
        "successes": successes,
        "failures": failures,
        "last": last,
        "default_flows_expect_empty": True,
        "auto_download": False,
        "limitation": _LIMITATION,
    }


def export_egress(
    workspace_root: Path,
    *,
    output: Path | None = None,
) -> dict[str, Any]:
    """Machine-readable export of the ledger (still secret-free)."""
    rows = list_egress(workspace_root, limit=_MAX_ENTRIES_READ)
    payload = {
        "schema": EGRESS_SCHEMA,
        "exported_at": datetime.now(UTC).isoformat(),
        "workspace_root_redacted": True,
        "entries": rows,
        "limitation": _LIMITATION,
    }
    out_dir = workspace_root / ".cairn" / "exports"
    ensure_private_dir(out_dir)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    dest = (output or (out_dir / f"egress-{stamp}.json")).expanduser().resolve()
    if dest.is_symlink():
        return {"ok": False, "error": "output_is_symlink", "path": str(dest)}
    ensure_private_dir(dest.parent)
    write_private_text(dest, json.dumps(payload, indent=2, sort_keys=True))
    return {
        "ok": True,
        "path": str(dest),
        "entry_count": len(rows),
        "limitation": _LIMITATION,
    }
