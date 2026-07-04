"""Verify ledger matches on-disk transcripts (Phase 0)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from cairn.ingest.parsers.aider import parse_aider_jsonl
from cairn.ingest.parsers.claude_code import parse_jsonl_file
from cairn.ingest.parsers.codex import parse_rollout_file
from cairn.ingest.parsers.cursor import parse_transcript_file
from cairn.ingest.parsers.goose import parse_goose_jsonl
from cairn.ingest.parsers.hermes import parse_session_file
from cairn.ingest.parsers.opencode import parse_opencode_jsonl
from cairn.ingest.project_paths import (
    discover_aider_sessions,
    discover_claude_jsonl,
    discover_codex_rollouts,
    discover_cursor_transcripts,
    discover_goose_sessions,
    discover_hermes_sessions,
    discover_opencode_sessions,
    resolve_git_root,
)
from cairn.ingest.writer import CaptureWriter


@dataclass
class VerifyDrift:
    external_id: str
    source: str
    status: str  # ok | drift | missing | orphan
    details: list[str] = field(default_factory=list)


def _parse_file(source: str, path: Path, root: Path) -> Any:
    if source == "claude-code":
        return parse_jsonl_file(path, repo_root=root)
    if source == "codex":
        return parse_rollout_file(path, repo_root=root)
    if source == "cursor":
        return parse_transcript_file(path, repo_root=root)
    if source == "hermes":
        return parse_session_file(path, repo_root=root)
    if source == "aider":
        return parse_aider_jsonl(path, repo_root=root)
    if source == "opencode":
        return parse_opencode_jsonl(path, repo_root=root)
    if source == "goose":
        return parse_goose_jsonl(path, repo_root=root)
    return None


def _discover(source: str, root: Path) -> list[Path]:
    if source == "claude-code":
        return discover_claude_jsonl(root)
    if source == "codex":
        return discover_codex_rollouts(root)
    if source == "cursor":
        return [p for p, _ in discover_cursor_transcripts(root)]
    if source == "hermes":
        return discover_hermes_sessions(root)
    if source == "aider":
        return discover_aider_sessions(root)
    if source == "opencode":
        return discover_opencode_sessions(root)
    if source == "goose":
        return discover_goose_sessions(root)
    return []


def verify_ledger(
    project_root: Path,
    *,
    source: str = "all",
    since: datetime | None = None,
) -> list[VerifyDrift]:
    """Re-parse disk transcripts and compare against the ledger."""
    root = resolve_git_root(project_root) or project_root.resolve()
    writer = CaptureWriter(root)
    reports: list[VerifyDrift] = []
    sources = (
        ["claude-code", "codex", "cursor", "hermes", "aider", "opencode", "goose"]
        if source == "all"
        else [source]
    )
    seen_keys: set[tuple[str, str]] = set()

    try:
        for src in sources:
            for path in _discover(src, root):
                if since is not None:
                    mtime = datetime.fromtimestamp(path.stat().st_mtime)
                    if mtime < since:
                        continue
                parsed = _parse_file(src, path, root)
                if parsed is None:
                    continue
                ext_id = str(getattr(parsed, "external_id", ""))
                if not ext_id:
                    continue
                seen_keys.add((src, ext_id))
                disk_events = len(getattr(parsed, "events", []))
                if hasattr(parsed, "usage"):
                    disk_in = parsed.usage.usage.input_tokens
                    disk_out = parsed.usage.usage.output_tokens
                else:
                    disk_in = 0
                    disk_out = 0

                row = writer.connection.execute(
                    "SELECT run_id, event_count, total_input_tokens, total_output_tokens "
                    "FROM runs WHERE source = ? AND external_id = ?",
                    (src, ext_id),
                ).fetchone()
                if row is None:
                    reports.append(
                        VerifyDrift(
                            external_id=ext_id,
                            source=src,
                            status="missing",
                            details=[f"on disk ({path.name}) but not in ledger"],
                        )
                    )
                    continue

                details: list[str] = []
                if int(row["event_count"]) != disk_events:
                    details.append(f"event_count ledger={row['event_count']} disk={disk_events}")
                if int(row["total_input_tokens"]) != disk_in:
                    details.append(
                        f"input_tokens ledger={row['total_input_tokens']} disk={disk_in}"
                    )
                if int(row["total_output_tokens"]) != disk_out:
                    details.append(
                        f"output_tokens ledger={row['total_output_tokens']} disk={disk_out}"
                    )
                reports.append(
                    VerifyDrift(
                        external_id=ext_id,
                        source=src,
                        status="ok" if not details else "drift",
                        details=details,
                    )
                )

        if source in ("all",):
            orphan_rows = writer.connection.execute(
                "SELECT source, external_id FROM runs WHERE external_id IS NOT NULL"
            ).fetchall()
            for row in orphan_rows:
                key = (str(row["source"]), str(row["external_id"]))
                if key not in seen_keys and row["source"] != "cursor":
                    reports.append(
                        VerifyDrift(
                            external_id=str(row["external_id"]),
                            source=str(row["source"]),
                            status="orphan",
                            details=["in ledger but source file not found on disk"],
                        )
                    )
    finally:
        writer.close()
    return reports
