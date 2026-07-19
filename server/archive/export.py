"""Build versioned cairn.archive.v1 ZIP exports."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from server import __version__ as producer_version
from server.archive.schema import (
    ARCHIVE_SCHEMA_VERSION,
    DOMAIN_FILES,
    OTLP_LOSS_FIELDS,
    SUPPORTED_READ_SCHEMAS,
)
from server.configuration import load_config
from server.export.scrub import scrub_export_value
from server.ingest.storage import storage_status
from server.util.private_files import ensure_private_dir

ConflictMode = Literal["skip", "replace", "fail"]
ArchiveMode = Literal["full", "scrubbed", "metadata_only"]


def _canon(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _rows(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def preview_archive(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    workspace_root: Path,
    mode: ArchiveMode = "full",
    limit: int = 500,
) -> dict[str, Any]:
    """Exact preview of included field classes and approximate sizes (no write)."""
    domains = _collect_domains(
        conn,
        workspace_id=workspace_id,
        workspace_root=workspace_root,
        mode=mode,
        limit=limit,
    )
    sizes = {name: len(_canon(payload)) for name, payload in domains.items()}
    return {
        "ok": True,
        "dry_run": True,
        "schema": ARCHIVE_SCHEMA_VERSION,
        "mode": mode,
        "field_classes": _field_classes(mode),
        "member_bytes": sizes,
        "total_bytes_estimate": sum(sizes.values()),
        "trace_count": len(domains.get("traces.json", {}).get("rows", [])),
        "otlp_loss": list(OTLP_LOSS_FIELDS),
        "limitation": "Preview only — no archive written.",
    }


def export_archive(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    workspace_root: Path,
    output: Path | None = None,
    mode: ArchiveMode = "full",
    limit: int = 500,
) -> dict[str, Any]:
    """Write a path-safe ZIP under `.cairn/exports/` (or *output*)."""
    domains = _collect_domains(
        conn,
        workspace_id=workspace_id,
        workspace_root=workspace_root,
        mode=mode,
        limit=limit,
    )
    out_dir = workspace_root / ".cairn" / "exports"
    ensure_private_dir(out_dir)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    dest = (output or (out_dir / f"cairn-archive-{stamp}.zip")).expanduser().resolve()
    if dest.exists() and dest.is_symlink():
        return {"ok": False, "error": "output_is_symlink", "path": str(dest)}
    ensure_private_dir(dest.parent)

    encoded = {name: _canon(payload) for name, payload in domains.items()}
    checksums = {name: _sha256(data) for name, data in encoded.items() if name != "manifest.json"}
    manifest = domains["manifest.json"]
    manifest["checksums"] = checksums
    manifest["member_bytes"] = {name: len(data) for name, data in encoded.items()}
    encoded["manifest.json"] = _canon(manifest)

    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name in DOMAIN_FILES:
            if name in encoded:
                zf.writestr(name, encoded[name])

    return {
        "ok": True,
        "schema": ARCHIVE_SCHEMA_VERSION,
        "path": str(dest),
        "mode": mode,
        "checksums": checksums,
        "trace_count": len(domains["traces.json"]["rows"]),
        "field_classes": _field_classes(mode),
        "otlp_loss": list(OTLP_LOSS_FIELDS),
        "limitation": (
            "ZIP is a transport container, not a trust boundary. "
            "OTLP alone cannot carry all Cairn evidence — see otlp_loss."
        ),
    }


def _field_classes(mode: ArchiveMode) -> dict[str, list[str]]:
    included = [
        "workspace metadata",
        "normalized traces/spans/links",
        "outcomes",
        "data quality",
        "diagnostics",
        "verification receipts",
        "session corrections",
        "policy snapshot",
        "privacy inventory",
        "checksums/manifest",
    ]
    redacted: list[str] = []
    if mode == "scrubbed":
        redacted = [
            "titles and raw text_inline",
            "paths and repository identifiers",
            "URLs and credential-like strings",
        ]
    elif mode == "metadata_only":
        redacted = ["text_inline", "receipt_json bodies", "corrections_json bodies"]
        included = [c for c in included if c != "verification receipts"]
        included.append("receipt/correction hashes only")
    return {"included": included, "redacted": redacted}


def _collect_domains(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    workspace_root: Path,
    mode: ArchiveMode,
    limit: int,
) -> dict[str, Any]:
    cap = max(1, min(int(limit), 5_000))
    traces = _rows(
        conn,
        """
        SELECT * FROM traces
        WHERE workspace_id = ?
        ORDER BY started_at DESC
        LIMIT ?
        """,
        (workspace_id, cap),
    )
    trace_ids = [str(t["trace_id"]) for t in traces]
    spans: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []
    outcomes: list[dict[str, Any]] = []
    quality: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    receipts: list[dict[str, Any]] = []
    corrections: list[dict[str, Any]] = []

    if trace_ids:
        placeholders = ",".join("?" * len(trace_ids))
        spans = _rows(
            conn,
            f"SELECT * FROM spans WHERE trace_id IN ({placeholders}) ORDER BY trace_id, seq",
            tuple(trace_ids),
        )
        links = _rows(
            conn,
            f"""
            SELECT from_span_id, to_span_id, link_type FROM span_links
            WHERE from_span_id IN (SELECT span_id FROM spans WHERE trace_id IN ({placeholders}))
               OR to_span_id IN (SELECT span_id FROM spans WHERE trace_id IN ({placeholders}))
            """,
            tuple(trace_ids) + tuple(trace_ids),
        )
        for table, bucket in (
            ("outcomes", outcomes),
            ("data_quality", quality),
            ("diagnostics", diagnostics),
            ("verification_receipts", receipts),
            ("session_corrections", corrections),
        ):
            exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
                (table,),
            ).fetchone()
            if not exists:
                continue
            bucket.extend(
                _rows(
                    conn,
                    f"SELECT * FROM {table} WHERE trace_id IN ({placeholders})",
                    tuple(trace_ids),
                )
            )

    if mode == "metadata_only":
        for span in spans:
            span["text_inline"] = None
        for row in receipts:
            row["receipt_json"] = None
        for row in corrections:
            row["corrections_json"] = None
    elif mode == "scrubbed":
        traces = scrub_export_value(traces, workspace_root)
        spans = scrub_export_value(spans, workspace_root)
        outcomes = scrub_export_value(outcomes, workspace_root)
        quality = scrub_export_value(quality, workspace_root)
        diagnostics = scrub_export_value(diagnostics, workspace_root)
        receipts = scrub_export_value(receipts, workspace_root)
        corrections = scrub_export_value(corrections, workspace_root)

    config = load_config(workspace_root)
    storage = storage_status(workspace_root)
    now = datetime.now(UTC).isoformat()
    privacy = {
        "schema": "cairn.privacy.v1",
        "scrubbed": mode != "full",
        "mode": mode,
        "retention_mode": storage.get("mode"),
        "field_classes": _field_classes(mode),
        "otlp_loss": list(OTLP_LOSS_FIELDS),
    }
    workspace = {
        "workspace_id": workspace_id,
        "root_path_redacted": mode != "full",
        "exported_at": now,
        "producer_version": producer_version,
        "timezone_semantics": "UTC ISO-8601 timestamps",
        "storage": storage,
        "lifecycle": {
            "destructive_enabled": config.lifecycle.destructive_enabled,
            "default_retain_days": config.lifecycle.default_retain_days,
        },
    }
    if mode == "full":
        workspace["root_path"] = str(workspace_root.resolve())
    policy = config.policy.model_dump()
    manifest = {
        "schema": ARCHIVE_SCHEMA_VERSION,
        "producer_version": producer_version,
        "exported_at": now,
        "timezone": "UTC",
        "mode": mode,
        "workspace_id": workspace_id,
        "members": list(DOMAIN_FILES),
        "supported_read_schemas": sorted(SUPPORTED_READ_SCHEMAS),
        "checksums": {},
        "limitation": (
            "Lossless only for mode=full within the selected trace limit. "
            "Unknown newer fields are preserved as JSON; incompatible majors are rejected."
        ),
    }
    return {
        "manifest.json": manifest,
        "privacy.json": privacy,
        "workspace.json": workspace,
        "traces.json": {"rows": traces},
        "spans.json": {"rows": spans},
        "span_links.json": {"rows": links},
        "outcomes.json": {"rows": outcomes},
        "data_quality.json": {"rows": quality},
        "diagnostics.json": {"rows": diagnostics},
        "verification_receipts.json": {"rows": receipts},
        "session_corrections.json": {"rows": corrections},
        "policy.json": policy,
    }
