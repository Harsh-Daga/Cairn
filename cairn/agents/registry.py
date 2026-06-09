"""Registry of agent parsers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from cairn.ingest.parsers.aider import parse_aider_jsonl
from cairn.ingest.parsers.claude_code import parse_jsonl_file
from cairn.ingest.parsers.codex import parse_rollout_file
from cairn.ingest.parsers.cursor import parse_transcript_file
from cairn.ingest.parsers.goose import parse_goose_jsonl
from cairn.ingest.parsers.hermes import parse_session_file
from cairn.ingest.parsers.openhands import parse_openhands_jsonl
from cairn.ingest.types import AgentSourceId, ParsedAgentSession

ParseFn = Callable[..., ParsedAgentSession | None]


@dataclass(frozen=True)
class AgentSource:
    source_id: AgentSourceId
    label: str
    parse: ParseFn


def _wrap_claude(path: Path, *, repo_root: Path | None = None) -> ParsedAgentSession | None:
    parsed = parse_jsonl_file(path, repo_root=repo_root)
    return _from_claude(parsed) if parsed else None


def _wrap_codex(path: Path, *, repo_root: Path | None = None) -> ParsedAgentSession | None:
    parsed = parse_rollout_file(path, repo_root=repo_root)
    return _from_codex(parsed) if parsed else None


def _wrap_cursor(path: Path, *, repo_root: Path | None = None) -> ParsedAgentSession | None:
    parsed = parse_transcript_file(path, repo_root=repo_root)
    return _from_cursor(parsed) if parsed else None


def _wrap_hermes(path: Path, *, repo_root: Path | None = None) -> ParsedAgentSession | None:
    parsed = parse_session_file(path, repo_root=repo_root)
    return _from_hermes(parsed) if parsed else None


def _from_claude(parsed: object) -> ParsedAgentSession:
    return ParsedAgentSession(
        source="claude-code",
        external_id=parsed.external_id,  # type: ignore[attr-defined]
        cwd=parsed.cwd,  # type: ignore[attr-defined]
        git_branch=parsed.git_branch,  # type: ignore[attr-defined]
        started_at=parsed.started_at,  # type: ignore[attr-defined]
        ended_at=parsed.ended_at,  # type: ignore[attr-defined]
        model=parsed.model,  # type: ignore[attr-defined]
        events=parsed.events,  # type: ignore[attr-defined]
        tool_calls=parsed.tool_calls,  # type: ignore[attr-defined]
        file_artifacts=parsed.file_artifacts,  # type: ignore[attr-defined]
        usage=parsed.usage,  # type: ignore[attr-defined]
    )


def _from_codex(parsed: object) -> ParsedAgentSession:
    return ParsedAgentSession(
        source="codex",
        external_id=parsed.external_id,  # type: ignore[attr-defined]
        cwd=parsed.cwd,  # type: ignore[attr-defined]
        git_branch=None,
        started_at=parsed.started_at,  # type: ignore[attr-defined]
        ended_at=parsed.ended_at,  # type: ignore[attr-defined]
        model=parsed.model,  # type: ignore[attr-defined]
        events=parsed.events,  # type: ignore[attr-defined]
        tool_calls=parsed.tool_calls,  # type: ignore[attr-defined]
        file_artifacts=parsed.file_artifacts,  # type: ignore[attr-defined]
        usage=parsed.usage,  # type: ignore[attr-defined]
    )


def _from_cursor(parsed: object) -> ParsedAgentSession:
    events = list(parsed.events)  # type: ignore[attr-defined]
    for link in parsed.sub_agent_links:  # type: ignore[attr-defined]
        events.append(
            {
                "type": "sub_agent",
                "parent_tool_use_id": link["parent_tool_use_id"],
                "child_session_id": link["child_session_id"],
                "child_source": link["child_source"],
            }
        )
    return ParsedAgentSession(
        source="cursor",
        external_id=parsed.external_id,  # type: ignore[attr-defined]
        cwd=parsed.cwd,  # type: ignore[attr-defined]
        git_branch=parsed.git_branch,  # type: ignore[attr-defined]
        started_at=parsed.started_at,  # type: ignore[attr-defined]
        ended_at=parsed.ended_at,  # type: ignore[attr-defined]
        model=parsed.model,  # type: ignore[attr-defined]
        events=events,
        tool_calls=parsed.tool_calls,  # type: ignore[attr-defined]
        file_artifacts=parsed.file_artifacts,  # type: ignore[attr-defined]
        usage=parsed.usage,  # type: ignore[attr-defined]
    )


def _from_hermes(parsed: object) -> ParsedAgentSession:
    return ParsedAgentSession(
        source="hermes",
        external_id=parsed.external_id,  # type: ignore[attr-defined]
        cwd=parsed.cwd,  # type: ignore[attr-defined]
        git_branch=None,
        started_at=parsed.started_at,  # type: ignore[attr-defined]
        ended_at=parsed.ended_at,  # type: ignore[attr-defined]
        model=parsed.model,  # type: ignore[attr-defined]
        events=parsed.events,  # type: ignore[attr-defined]
        tool_calls=parsed.tool_calls,  # type: ignore[attr-defined]
        file_artifacts=parsed.file_artifacts,  # type: ignore[attr-defined]
        usage=parsed.usage,  # type: ignore[attr-defined]
    )


AGENT_SOURCES: dict[AgentSourceId, AgentSource] = {
    "claude-code": AgentSource("claude-code", "Claude Code", _wrap_claude),
    "codex": AgentSource("codex", "Codex", _wrap_codex),
    "cursor": AgentSource("cursor", "Cursor", _wrap_cursor),
    "hermes": AgentSource("hermes", "Hermes", _wrap_hermes),
    "aider": AgentSource("aider", "Aider", parse_aider_jsonl),
    "openhands": AgentSource("openhands", "OpenHands", parse_openhands_jsonl),
    "goose": AgentSource("goose", "Goose", parse_goose_jsonl),
}


def get_parser(source_id: AgentSourceId) -> AgentSource:
    return AGENT_SOURCES[source_id]


def list_agent_sources() -> list[AgentSourceId]:
    return list(AGENT_SOURCES.keys())
