"""Auto-detect agent sources by probing known log locations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cairn.ingest.parsers.cline_family import cline_global_storage_roots, discover_cline_sessions
from cairn.ingest.parsers.gemini_cli import discover_gemini_sessions, gemini_roots
from cairn.ingest.parsers.openclaw import discover_openclaw_sessions, openclaw_root
from cairn.ingest.project_paths import (
    aider_sessions_root,
    claude_projects_root,
    codex_sessions_root,
    cursor_projects_root,
    discover_aider_sessions,
    discover_claude_jsonl,
    discover_codex_rollouts,
    discover_cursor_transcripts,
    discover_goose_sessions,
    discover_hermes_sessions,
    discover_opencode_sessions,
    goose_sessions_root,
    opencode_sessions_root,
    resolve_git_root,
)


@dataclass(frozen=True)
class DetectedSource:
    source: str
    path: Path | None
    sessions_seen: int


def detect_sources(repo_root: Path) -> list[DetectedSource]:
    root = resolve_git_root(repo_root) or repo_root.resolve()
    results: list[DetectedSource] = []

    base = claude_projects_root()
    if base.is_dir():
        count = len(discover_claude_jsonl(root))
        results.append(DetectedSource(source="claude-code", path=base, sessions_seen=count))

    base = codex_sessions_root()
    if base.is_dir():
        count = len(discover_codex_rollouts(root))
        results.append(DetectedSource(source="codex", path=base, sessions_seen=count))

    base = cursor_projects_root()
    if base.is_dir():
        count = len(discover_cursor_transcripts(root))
        results.append(DetectedSource(source="cursor", path=base, sessions_seen=count))

    count = len(discover_hermes_sessions(root))
    results.append(DetectedSource(source="hermes", path=None, sessions_seen=count))

    base = aider_sessions_root()
    if base.is_dir():
        count = len(discover_aider_sessions(root))
        results.append(DetectedSource(source="aider", path=base, sessions_seen=count))

    base = opencode_sessions_root()
    if base.is_dir():
        count = len(discover_opencode_sessions(root))
        results.append(DetectedSource(source="opencode", path=base, sessions_seen=count))

    base = goose_sessions_root()
    if base.is_dir():
        count = len(discover_goose_sessions(root))
        results.append(DetectedSource(source="goose", path=base, sessions_seen=count))

    gemini_count = len(discover_gemini_sessions(root))
    if gemini_count or any(p.is_dir() for p in gemini_roots()):
        results.append(
            DetectedSource(
                source="gemini",
                path=gemini_roots()[0] if gemini_roots() else None,
                sessions_seen=gemini_count,
            )
        )

    cline_count = len(discover_cline_sessions(root))
    if cline_count or any(p.is_dir() for p in cline_global_storage_roots()):
        results.append(DetectedSource(source="cline", path=None, sessions_seen=cline_count))

    oc_root = openclaw_root()
    oc_count = len(discover_openclaw_sessions(root))
    if oc_count or oc_root.is_dir():
        results.append(
            DetectedSource(
                source="openclaw",
                path=oc_root if oc_root.is_dir() else None,
                sessions_seen=oc_count,
            )
        )

    return results
