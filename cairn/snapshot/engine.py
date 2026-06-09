"""Create, list, diff, and restore project snapshots."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cairn.ingest.project_paths import resolve_git_root
from cairn.ingest.writer import CaptureWriter
from cairn.ledger.schema import migrate
from cairn.snapshot.protocol import SNAPSHOT_VERSION, SnapshotManifest


def snapshots_dir(project_root: Path) -> Path:
    path = project_root / ".cairn" / "snapshots"
    path.mkdir(parents=True, exist_ok=True)
    return path


def create_snapshot(project_root: Path, *, label: str | None = None) -> SnapshotManifest:
    root = resolve_git_root(project_root) or project_root.resolve()
    ledger = root / ".cairn" / "ledger.db"
    if not ledger.is_file():
        msg = "no ledger found; nothing to snapshot"
        raise FileNotFoundError(msg)

    snapshot_id = f"snap-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
    dest = snapshots_dir(root) / snapshot_id
    dest.mkdir(parents=True, exist_ok=True)

    shutil.copy2(ledger, dest / "ledger.db")
    ledger_sha256 = _sha256_file(dest / "ledger.db")
    cas_hashes = _collect_cas_hashes(ledger)
    _copy_cas_objects(root, dest, cas_hashes)

    sessions_dest = dest / "sessions"
    sessions_dest.mkdir(parents=True, exist_ok=True)
    session_ids: list[str] = []
    sessions_src = root / ".cairn" / "sessions"
    if sessions_src.is_dir():
        for mirror in sorted(sessions_src.glob("*.json")):
            shutil.copy2(mirror, sessions_dest / mirror.name)
            session_ids.append(mirror.stem)

    git_commit = _current_git_commit(ledger)
    created_at = datetime.now(UTC).isoformat()
    manifest = SnapshotManifest(
        cairn_snapshot_version=SNAPSHOT_VERSION,
        snapshot_id=snapshot_id,
        created_at=created_at,
        label=label,
        git_commit=git_commit,
        ledger_sha256=ledger_sha256,
        sessions=tuple(session_ids),
        cas_hashes=tuple(cas_hashes),
    )
    (dest / "manifest.json").write_text(
        json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def list_snapshots(project_root: Path) -> list[SnapshotManifest]:
    root = resolve_git_root(project_root) or project_root.resolve()
    base = snapshots_dir(root)
    manifests: list[SnapshotManifest] = []
    for child in sorted(base.iterdir()):
        if not child.is_dir():
            continue
        manifest_path = child / "manifest.json"
        if manifest_path.is_file():
            manifests.append(_load_manifest(manifest_path))
    return manifests


def restore_snapshot(project_root: Path, snapshot_id: str) -> SnapshotManifest:
    root = resolve_git_root(project_root) or project_root.resolve()
    snap_dir = snapshots_dir(root) / snapshot_id
    manifest = _load_manifest(snap_dir / "manifest.json")
    if manifest.cairn_snapshot_version != SNAPSHOT_VERSION:
        msg = f"unsupported snapshot version: {manifest.cairn_snapshot_version}"
        raise ValueError(msg)

    ledger_src = snap_dir / "ledger.db"
    if not ledger_src.is_file():
        msg = f"snapshot missing ledger: {snapshot_id}"
        raise FileNotFoundError(msg)

    cairn_dir = root / ".cairn"
    cairn_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ledger_src, cairn_dir / "ledger.db")
    _restore_cas_objects(snap_dir, root, manifest.cas_hashes)

    sessions_dest = cairn_dir / "sessions"
    sessions_dest.mkdir(parents=True, exist_ok=True)
    sessions_src = snap_dir / "sessions"
    if sessions_src.is_dir():
        for mirror in sessions_src.glob("*.json"):
            shutil.copy2(mirror, sessions_dest / mirror.name)

    return manifest


def diff_snapshots(project_root: Path, left_id: str, right_id: str) -> dict[str, Any]:
    root = resolve_git_root(project_root) or project_root.resolve()
    left = _load_manifest(snapshots_dir(root) / left_id / "manifest.json")
    right = _load_manifest(snapshots_dir(root) / right_id / "manifest.json")
    left_sessions = set(left.sessions)
    right_sessions = set(right.sessions)
    left_cas = set(left.cas_hashes)
    right_cas = set(right.cas_hashes)
    return {
        "left": left.snapshot_id,
        "right": right.snapshot_id,
        "sessions_added": sorted(right_sessions - left_sessions),
        "sessions_removed": sorted(left_sessions - right_sessions),
        "sessions_unchanged": sorted(left_sessions & right_sessions),
        "cas_added": sorted(right_cas - left_cas),
        "cas_removed": sorted(left_cas - right_cas),
        "git_commit_changed": left.git_commit != right.git_commit,
        "left_git_commit": left.git_commit,
        "right_git_commit": right.git_commit,
    }


def diff_sessions(project_root: Path, session_a: str, session_b: str) -> dict[str, Any]:
    root = resolve_git_root(project_root) or project_root.resolve()
    writer = CaptureWriter(root)
    try:
        summary_a = writer.load_session_by_external_id(session_a)
        summary_b = writer.load_session_by_external_id(session_b)
        if summary_a is None:
            msg = f"session not found: {session_a}"
            raise FileNotFoundError(msg)
        if summary_b is None:
            msg = f"session not found: {session_b}"
            raise FileNotFoundError(msg)
        events_a = writer.load_events(summary_a.run_id)
        events_b = writer.load_events(summary_b.run_id)
    finally:
        writer.close()

    types_a = _event_type_counts(events_a)
    types_b = _event_type_counts(events_b)
    tools_a = _tool_names(events_a)
    tools_b = _tool_names(events_b)
    return {
        "session_a": session_a,
        "session_b": session_b,
        "event_count_a": len(events_a),
        "event_count_b": len(events_b),
        "event_types_a": types_a,
        "event_types_b": types_b,
        "tools_only_in_a": sorted(tools_a - tools_b),
        "tools_only_in_b": sorted(tools_b - tools_a),
        "shared_tools": sorted(tools_a & tools_b),
        "status_a": summary_a.status,
        "status_b": summary_b.status,
    }


def _load_manifest(path: Path) -> SnapshotManifest:
    data = json.loads(path.read_text(encoding="utf-8"))
    return SnapshotManifest(
        cairn_snapshot_version=int(data["cairn_snapshot_version"]),
        snapshot_id=str(data["snapshot_id"]),
        created_at=str(data["created_at"]),
        label=data.get("label"),
        git_commit=data.get("git_commit"),
        ledger_sha256=str(data.get("ledger_sha256", "")),
        sessions=tuple(str(s) for s in data.get("sessions", [])),
        cas_hashes=tuple(str(h) for h in data.get("cas_hashes", [])),
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _collect_cas_hashes(ledger_path: Path) -> list[str]:
    conn = sqlite3.connect(ledger_path)
    migrate(conn)
    hashes: set[str] = set()
    try:
        for row in conn.execute(
            "SELECT trajectory_hash FROM runs WHERE trajectory_hash IS NOT NULL"
        ):
            if row[0]:
                hashes.add(str(row[0]))
        for row in conn.execute("SELECT output_hash FROM nodes WHERE output_hash IS NOT NULL"):
            if row[0]:
                hashes.add(str(row[0]))
        for row in conn.execute("SELECT output_hash FROM cas_refs"):
            if row[0]:
                hashes.add(str(row[0]))
    finally:
        conn.close()
    return sorted(hashes)


def _copy_cas_objects(project_root: Path, snap_dir: Path, hashes: list[str]) -> None:
    cas_src = project_root / ".cairn" / "cache" / "cas"
    cas_dest = snap_dir / "cas"
    for digest in hashes:
        src = cas_src / digest[:2] / digest
        if not src.is_file():
            continue
        target = cas_dest / digest[:2] / digest
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)


def _restore_cas_objects(snap_dir: Path, project_root: Path, hashes: tuple[str, ...]) -> None:
    cas_src = snap_dir / "cas"
    cas_dest = project_root / ".cairn" / "cache" / "cas"
    for digest in hashes:
        src = cas_src / digest[:2] / digest
        if not src.is_file():
            continue
        target = cas_dest / digest[:2] / digest
        if target.is_file():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)


def _current_git_commit(ledger_path: Path) -> str | None:
    conn = sqlite3.connect(ledger_path)
    try:
        row = conn.execute(
            """
            SELECT git_commit FROM runs
            WHERE git_commit IS NOT NULL
            ORDER BY started_at DESC
            LIMIT 1
            """
        ).fetchone()
        return str(row[0]) if row else None
    finally:
        conn.close()


def _event_type_counts(events: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in events:
        event_type = str(event.get("type", "unknown"))
        counts[event_type] = counts.get(event_type, 0) + 1
    return counts


def _tool_names(events: list[dict[str, Any]]) -> set[str]:
    names: set[str] = set()
    for event in events:
        if event.get("type") == "tool_call" and event.get("name"):
            names.add(str(event["name"]))
    return names
