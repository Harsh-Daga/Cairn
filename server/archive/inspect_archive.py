"""Inspect a cairn.archive.v1 ZIP without applying it."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from server.archive.safe_zip import ArchiveZipError, safe_read_members
from server.archive.schema import ARCHIVE_SCHEMA_VERSION, OTLP_LOSS_FIELDS, SUPPORTED_READ_SCHEMAS


def inspect_archive(archive: Path) -> dict[str, Any]:
    try:
        members = safe_read_members(archive)
    except ArchiveZipError as exc:
        return {"ok": False, "error": "inspect_rejected", "detail": str(exc)}

    manifest = json.loads(members["manifest.json"].decode("utf-8"))
    privacy = json.loads(members["privacy.json"].decode("utf-8"))
    schema = str(manifest.get("schema") or "")
    compatible = schema in SUPPORTED_READ_SCHEMAS
    checksums = manifest.get("checksums") or {}
    mismatches: list[str] = []
    for name, expected in checksums.items():
        if name == "manifest.json":
            continue
        raw = members.get(name)
        if raw is None:
            mismatches.append(name)
            continue
        if hashlib.sha256(raw).hexdigest() != expected:
            mismatches.append(name)

    unknown_members = sorted(set(members) - set(checksums) - {"manifest.json"})
    traces = json.loads(members.get("traces.json", b'{"rows":[]}').decode("utf-8"))
    return {
        "ok": True,
        "schema": schema,
        "supported": compatible,
        "producer_version": manifest.get("producer_version"),
        "exported_at": manifest.get("exported_at"),
        "mode": manifest.get("mode") or privacy.get("mode"),
        "workspace_id": manifest.get("workspace_id"),
        "members": sorted(members),
        "member_bytes": {name: len(data) for name, data in members.items()},
        "trace_count": len(traces.get("rows") or []),
        "checksum_mismatches": mismatches,
        "unknown_preserved_members": unknown_members,
        "privacy": privacy,
        "otlp_loss": list(OTLP_LOSS_FIELDS),
        "current_schema": ARCHIVE_SCHEMA_VERSION,
        "limitation": (
            "Inspect is offline and does not modify the workspace. "
            "Incompatible schema majors are rejected on import."
            if compatible
            else f"Unsupported archive schema {schema!r}; import will refuse."
        ),
    }
