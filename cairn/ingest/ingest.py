"""Batch ingest orchestration (§11.1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from cairn.ingest.parsers.claude_code import parse_jsonl_file
from cairn.ingest.parsers.codex import parse_rollout_file
from cairn.ingest.project_paths import (
    discover_claude_jsonl,
    discover_codex_rollouts,
    resolve_git_root,
)
from cairn.ingest.writer import CaptureWriter, IngestResult


@dataclass
class IngestReport:
    source: str
    scanned: int = 0
    inserted: int = 0
    skipped: int = 0
    results: list[IngestResult] = field(default_factory=list)


def run_ingest(
    project_root: Path,
    *,
    source: str = "claude-code",
    since: datetime | None = None,
    claude_project_dir: Path | None = None,
) -> list[IngestReport]:
    root = resolve_git_root(project_root) or project_root.resolve()
    writer = CaptureWriter(root)
    reports: list[IngestReport] = []
    try:
        if source in ("claude-code", "all"):
            reports.append(
                _ingest_claude(
                    writer,
                    root,
                    since=since,
                    claude_project_dir=claude_project_dir,
                )
            )
        if source in ("codex", "all"):
            reports.append(_ingest_codex(writer, root, since=since))
        if source not in ("claude-code", "codex", "all"):
            msg = f"unsupported ingest source for Phase 4: {source!r}"
            raise ValueError(msg)
    finally:
        writer.close()
    return reports


def _ingest_claude(
    writer: CaptureWriter,
    repo_root: Path,
    *,
    since: datetime | None,
    claude_project_dir: Path | None,
) -> IngestReport:
    report = IngestReport(source="claude-code")
    paths = discover_claude_jsonl(
        repo_root,
        claude_project_dir=claude_project_dir,
        since=since,
    )
    for path in paths:
        report.scanned += 1
        parsed = parse_jsonl_file(path, repo_root=repo_root)
        if parsed is None:
            report.skipped += 1
            continue
        result = writer.ingest_claude_session(parsed)
        if result.inserted:
            report.inserted += 1
        else:
            report.skipped += 1
        report.results.append(result)
    return report


def _ingest_codex(
    writer: CaptureWriter,
    repo_root: Path,
    *,
    since: datetime | None,
) -> IngestReport:
    report = IngestReport(source="codex")
    for path in discover_codex_rollouts(repo_root, since=since):
        report.scanned += 1
        parsed = parse_rollout_file(path, repo_root=repo_root)
        if parsed is None:
            report.skipped += 1
            continue
        result = writer.ingest_codex_session(parsed)
        if result.inserted:
            report.inserted += 1
        else:
            report.skipped += 1
        report.results.append(result)
    return report
