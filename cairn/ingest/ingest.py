"""Batch ingest orchestration (§11.1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from cairn.ingest.parsers.aider import parse_aider_jsonl
from cairn.ingest.parsers.claude_code import parse_jsonl_file
from cairn.ingest.parsers.cline_family import discover_cline_sessions, parse_cline_task
from cairn.ingest.parsers.codex import parse_rollout_file
from cairn.ingest.parsers.cursor import (
    ParsedCursorSession,
    locate_cursor_vscdb,
    parse_cursor_vscdb,
    parse_transcript_file,
)
from cairn.ingest.parsers.gemini_cli import discover_gemini_sessions, parse_gemini_file
from cairn.ingest.parsers.goose import parse_goose_jsonl
from cairn.ingest.parsers.hermes import parse_session_file
from cairn.ingest.parsers.openclaw import discover_openclaw_sessions, parse_openclaw_file
from cairn.ingest.parsers.opencode import parse_opencode_jsonl
from cairn.ingest.project_paths import (
    cursor_composer_matches_project,
    cursor_project_composer_ids,
    cursor_subagent_external_id,
    discover_aider_sessions,
    discover_claude_jsonl,
    discover_codex_rollouts,
    discover_cursor_transcripts,
    discover_goose_sessions,
    discover_hermes_sessions,
    discover_opencode_sessions,
    resolve_cursor_workspace,
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
        if source in ("opencode", "all"):
            reports.append(_ingest_opencode(writer, root, since=since))
        if source in ("goose", "all"):
            reports.append(_ingest_goose(writer, root, since=since))
        if source in ("gemini", "all"):
            reports.append(_ingest_gemini(writer, root, since=since))
        if source in ("cline", "roo", "kilo", "all"):
            reports.append(_ingest_cline(writer, root, since=since, source=source))
        if source in ("openclaw", "all"):
            reports.append(_ingest_openclaw(writer, root, since=since))
        if source not in (
            "claude-code",
            "codex",
            "cursor",
            "hermes",
            "aider",
            "opencode",
            "goose",
            "gemini",
            "cline",
            "roo",
            "kilo",
            "openclaw",
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
    refresh: bool = False,
) -> IngestReport:
    report = IngestReport(source="cursor")
    workspace = resolve_cursor_workspace(repo_root, cursor_workspace=cursor_workspace)
    transcript_root = (workspace / "agent-transcripts") if workspace is not None else None
    project_composer_ids = cursor_project_composer_ids(repo_root, cursor_workspace=cursor_workspace)
    ingested_external: set[str] = set()

    vscdb = locate_cursor_vscdb()
    if vscdb is not None:
        for parsed in parse_cursor_vscdb(
            vscdb, repo_root=repo_root, transcript_root=transcript_root
        ):
            report.scanned += 1
            if not cursor_composer_matches_project(
                repo_root,
                parsed.cwd,
                composer_id=parsed.external_id,
                project_composer_ids=project_composer_ids,
            ):
                report.skipped += 1
                continue
            if since is not None and parsed.started_at is not None:
                try:
                    started = datetime.fromisoformat(parsed.started_at.replace("Z", "+00:00"))
                except ValueError:
                    started = None
                if started is not None and started < since:
                    report.skipped += 1
                    continue
            result = writer.ingest_cursor_session(parsed, force_refresh=refresh)
            ingested_external.add(parsed.external_id)
            if result.inserted or result.refreshed:
                report.inserted += 1
            else:
                report.skipped += 1
            report.results.append(result)

    # Transcript fallback for project sessions missing from vscdb (or no tokens in vscdb).
    for path, parent_session_id in discover_cursor_transcripts(
        repo_root,
        cursor_workspace=cursor_workspace,
        since=since,
    ):
        report.scanned += 1
        transcript = parse_transcript_file(
            path,
            repo_root=repo_root,
            parent_session_id=parent_session_id,
        )
        if transcript is None:
            report.skipped += 1
            continue
        if transcript.external_id in ingested_external:
            report.skipped += 1
            continue
        if parent_session_id is None and isinstance(transcript, ParsedCursorSession):
            sub_dir = path.parent / "subagents"
            if sub_dir.is_dir():
                linked = {link["child_session_id"] for link in transcript.sub_agent_links}
                for sub_path in sorted(sub_dir.glob("*.jsonl")):
                    child_id = cursor_subagent_external_id(sub_path, transcript.external_id)
                    if child_id in linked:
                        continue
                    transcript.sub_agent_links.append(
                        {
                            "parent_tool_use_id": f"subagent:{sub_path.stem}",
                            "child_session_id": child_id,
                            "child_source": "cursor",
                        }
                    )
                    linked.add(child_id)
        result = writer.ingest_cursor_session(transcript, force_refresh=refresh)
        ingested_external.add(transcript.external_id)
        if result.inserted or result.refreshed:
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


def _ingest_opencode(
    writer: CaptureWriter,
    repo_root: Path,
    *,
    since: datetime | None,
) -> IngestReport:
    return _ingest_agent_jsonl(
        writer,
        repo_root,
        source="opencode",
        paths=discover_opencode_sessions(repo_root, since=since),
        parse=parse_opencode_jsonl,
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


def _ingest_gemini(
    writer: CaptureWriter,
    repo_root: Path,
    *,
    since: datetime | None,
) -> IngestReport:
    del since
    report = IngestReport(source="gemini")
    for path in discover_gemini_sessions(repo_root):
        report.scanned += 1
        parsed = parse_gemini_file(path, repo_root=repo_root)
        if parsed is None:
            report.skipped += 1
            continue
        result = writer.ingest_gemini_session(parsed)
        if result.inserted:
            report.inserted += 1
        else:
            report.skipped += 1
        report.results.append(result)
    return report


def _ingest_cline(
    writer: CaptureWriter,
    repo_root: Path,
    *,
    since: datetime | None,
    source: str,
) -> IngestReport:
    del since
    targets = discover_cline_sessions(repo_root)
    if source in ("cline", "roo", "kilo"):
        targets = [(p, s) for p, s in targets if s == source]
    by_source: dict[str, IngestReport] = {}
    for path, src in targets:
        report = by_source.setdefault(src, IngestReport(source=src))
        report.scanned += 1
        parsed = parse_cline_task(path, source=src, repo_root=repo_root)
        if parsed is None:
            report.skipped += 1
            continue
        result = writer.ingest_cline_session(parsed)
        if result.inserted:
            report.inserted += 1
        else:
            report.skipped += 1
        report.results.append(result)
    if source in ("cline", "roo", "kilo"):
        return by_source.get(source, IngestReport(source=source))
    merged = IngestReport(source="cline-family")
    for rep in by_source.values():
        merged.scanned += rep.scanned
        merged.inserted += rep.inserted
        merged.skipped += rep.skipped
        merged.results.extend(rep.results)
    return merged


def _ingest_openclaw(
    writer: CaptureWriter,
    repo_root: Path,
    *,
    since: datetime | None,
) -> IngestReport:
    del since
    report = IngestReport(source="openclaw")
    for path in discover_openclaw_sessions(repo_root):
        report.scanned += 1
        parsed = parse_openclaw_file(path, repo_root=repo_root)
        if parsed is None:
            report.skipped += 1
            continue
        result = writer.ingest_openclaw_session(parsed)
        if result.inserted:
            report.inserted += 1
        else:
            report.skipped += 1
        report.results.append(result)
    return report


def ingest_cursor_incremental(repo_root: Path) -> IngestReport:
    """Re-ingest Cursor composers from ``state.vscdb`` after a live file change."""
    writer = CaptureWriter(repo_root)
    try:
        return _ingest_cursor(writer, repo_root, since=None, cursor_workspace=None, refresh=True)
    finally:
        writer.close()
