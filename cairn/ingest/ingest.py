"""Batch ingest orchestration (§11.1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from cairn.ingest.parsers.aider import parse_aider_jsonl
from cairn.ingest.parsers.claude_code import parse_jsonl_file
from cairn.ingest.parsers.codex import parse_rollout_file
from cairn.ingest.parsers.cursor import ParsedCursorSession, parse_transcript_file
from cairn.ingest.parsers.goose import parse_goose_jsonl
from cairn.ingest.parsers.hermes import parse_session_file
from cairn.ingest.parsers.openhands import parse_openhands_jsonl
from cairn.ingest.project_paths import (
    cursor_subagent_external_id,
    discover_aider_sessions,
    discover_claude_jsonl,
    discover_codex_rollouts,
    discover_cursor_transcripts,
    discover_goose_sessions,
    discover_hermes_sessions,
    discover_openhands_sessions,
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
    cursor_workspace: Path | None = None,
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
        if source in ("cursor", "all"):
            reports.append(
                _ingest_cursor(
                    writer,
                    root,
                    since=since,
                    cursor_workspace=cursor_workspace,
                )
            )
        if source in ("hermes", "all"):
            reports.append(_ingest_hermes(writer, root, since=since))
        if source in ("aider", "all"):
            reports.append(_ingest_aider(writer, root, since=since))
        if source in ("openhands", "all"):
            reports.append(_ingest_openhands(writer, root, since=since))
        if source in ("goose", "all"):
            reports.append(_ingest_goose(writer, root, since=since))
        if source not in (
            "claude-code",
            "codex",
            "cursor",
            "hermes",
            "aider",
            "openhands",
            "goose",
            "all",
        ):
            msg = f"unsupported ingest source: {source!r}"
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


def _ingest_cursor(
    writer: CaptureWriter,
    repo_root: Path,
    *,
    since: datetime | None,
    cursor_workspace: Path | None,
) -> IngestReport:
    report = IngestReport(source="cursor")
    for path, parent_session_id in discover_cursor_transcripts(
        repo_root,
        cursor_workspace=cursor_workspace,
        since=since,
    ):
        report.scanned += 1
        parsed = parse_transcript_file(
            path,
            repo_root=repo_root,
            parent_session_id=parent_session_id,
        )
        if parsed is None:
            report.skipped += 1
            continue
        if parent_session_id is None and isinstance(parsed, ParsedCursorSession):
            sub_dir = path.parent / "subagents"
            if sub_dir.is_dir():
                linked = {link["child_session_id"] for link in parsed.sub_agent_links}
                for sub_path in sorted(sub_dir.glob("*.jsonl")):
                    child_id = cursor_subagent_external_id(sub_path, parsed.external_id)
                    if child_id in linked:
                        continue
                    parsed.sub_agent_links.append(
                        {
                            "parent_tool_use_id": f"subagent:{sub_path.stem}",
                            "child_session_id": child_id,
                            "child_source": "cursor",
                        }
                    )
                    linked.add(child_id)
        result = writer.ingest_cursor_session(parsed)
        if result.inserted:
            report.inserted += 1
        else:
            report.skipped += 1
        report.results.append(result)
    return report


def _ingest_hermes(
    writer: CaptureWriter,
    repo_root: Path,
    *,
    since: datetime | None,
) -> IngestReport:
    report = IngestReport(source="hermes")
    for path in discover_hermes_sessions(repo_root, since=since):
        report.scanned += 1
        parsed = parse_session_file(path, repo_root=repo_root)
        if parsed is None:
            report.skipped += 1
            continue
        result = writer.ingest_hermes_session(parsed)
        if result.inserted:
            report.inserted += 1
        else:
            report.skipped += 1
        report.results.append(result)
    return report


def _ingest_agent_jsonl(
    writer: CaptureWriter,
    repo_root: Path,
    *,
    source: str,
    paths: list[Path],
    parse: object,
) -> IngestReport:
    report = IngestReport(source=source)
    for path in paths:
        report.scanned += 1
        parsed = parse(path, repo_root=repo_root)  # type: ignore[operator]
        if parsed is None:
            report.skipped += 1
            continue
        result = writer.ingest_agent_session(parsed)
        if result.inserted:
            report.inserted += 1
        else:
            report.skipped += 1
        report.results.append(result)
    return report


def _ingest_aider(
    writer: CaptureWriter,
    repo_root: Path,
    *,
    since: datetime | None,
) -> IngestReport:
    return _ingest_agent_jsonl(
        writer,
        repo_root,
        source="aider",
        paths=discover_aider_sessions(repo_root, since=since),
        parse=parse_aider_jsonl,
    )


def _ingest_openhands(
    writer: CaptureWriter,
    repo_root: Path,
    *,
    since: datetime | None,
) -> IngestReport:
    return _ingest_agent_jsonl(
        writer,
        repo_root,
        source="openhands",
        paths=discover_openhands_sessions(repo_root, since=since),
        parse=parse_openhands_jsonl,
    )


def _ingest_goose(
    writer: CaptureWriter,
    repo_root: Path,
    *,
    since: datetime | None,
) -> IngestReport:
    return _ingest_agent_jsonl(
        writer,
        repo_root,
        source="goose",
        paths=discover_goose_sessions(repo_root, since=since),
        parse=parse_goose_jsonl,
    )
