"""Cursor parser — ``state.vscdb`` is canonical (§2.2 + §2.7G)."""

from __future__ import annotations

import json
import os
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from server.ingest.adapters.claude_code import FileArtifactDraft, ToolCallDraft
from server.ingest.normalizer import args_payload, text_payload
from server.ingest.project_paths import (
    cursor_subagent_external_id,
    path_rel_to_repo,
)
from server.ingest.usage import UsageAccumulator

_CURSOR_EDIT = frozenset({"Write", "StrReplace", "EditNotebook"})
_CURSOR_READ = frozenset({"Read", "Glob", "Grep"})
_USER_QUERY_RE = re.compile(r"<user_query>\s*(.*?)\s*</user_query>", re.DOTALL)


@dataclass
class ParsedCursorSession:
    external_id: str
    cwd: str | None
    git_branch: str | None
    started_at: str | None
    ended_at: str | None
    model: str | None
    parent_session_id: str | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[ToolCallDraft] = field(default_factory=list)
    file_artifacts: list[FileArtifactDraft] = field(default_factory=list)
    sub_agent_links: list[dict[str, str]] = field(default_factory=list)
    usage: UsageAccumulator = field(default_factory=UsageAccumulator)
    has_cost: bool = False
    is_best_of_n_subcomposer: bool = False
    num_sub_composers: int | None = None
    data_notes: list[str] = field(default_factory=list)


def normalize_cursor_tool_name(tool_name: str) -> str:
    if tool_name in _CURSOR_READ:
        return "search" if tool_name == "Grep" else "read"
    if tool_name in _CURSOR_EDIT:
        return "edit"
    if tool_name == "Shell":
        return "bash"
    if tool_name == "Delete":
        return "delete"
    if tool_name == "Task":
        return "sub_agent"
    return tool_name.lower()


# ---------------------------------------------------------------------------
# state.vscdb (canonical)
# ---------------------------------------------------------------------------


def locate_cursor_vscdb() -> Path | None:
    """Return the global Cursor ``state.vscdb`` path for this platform."""
    home = Path.home()
    candidates = [
        home / "Library/Application Support/Cursor/User/globalStorage/state.vscdb",
        home / ".config/Cursor/User/globalStorage/state.vscdb",
        home / "AppData/Roaming/Cursor/User/globalStorage/state.vscdb",
    ]
    env = os.environ.get("CAIRN_CURSOR_VSCDB")
    if env:
        candidates.insert(0, Path(env))
    for path in candidates:
        if path.is_file():
            return path
    return None


def _open_vscdb_readonly(path: Path) -> sqlite3.Connection:
    uri = f"file:{path.as_posix()}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def _decode_value(raw: Any) -> Any:
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    if not isinstance(raw, str):
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def parse_cursor_vscdb(
    vscdb_path: Path,
    *,
    repo_root: Path | None = None,
    transcript_root: Path | None = None,
) -> list[ParsedCursorSession]:
    """Parse every composer in ``state.vscdb``.

    ``transcript_root`` (``~/.cursor/projects/<slug>/agent-transcripts``) is
    used to join tool-call structure by ``composerId``; missing transcripts are
    fine — bubbles still yield user/assistant events with real tokens.
    """
    sessions: list[ParsedCursorSession] = []
    try:
        conn = _open_vscdb_readonly(vscdb_path)
    except sqlite3.OperationalError:
        return sessions
    try:
        rows = conn.execute(
            "SELECT key, value FROM cursorDiskKV WHERE key LIKE 'composerData:%'"
        ).fetchall()
    except sqlite3.OperationalError:
        conn.close()
        return sessions

    for key, value in rows:
        composer_id = str(key).split(":", 1)[1]
        data = _decode_value(value)
        if not isinstance(data, dict):
            continue
        session = _build_session_from_composer(
            conn, composer_id, data, repo_root=repo_root, transcript_root=transcript_root
        )
        if session is not None:
            sessions.append(session)
    conn.close()
    return sessions


def _build_session_from_composer(
    conn: sqlite3.Connection,
    composer_id: str,
    data: dict[str, Any],
    *,
    repo_root: Path | None,
    transcript_root: Path | None,
) -> ParsedCursorSession | None:
    created = data.get("createdAt")
    updated = data.get("lastUpdatedAt")
    started_at = _iso_timestamp(created)
    ended_at = _iso_timestamp(updated) or started_at

    usage_data = data.get("usageData")
    cost_cents: int | float | None = None
    if isinstance(usage_data, dict):
        default = usage_data.get("default")
        if isinstance(default, dict):
            cents = default.get("costInCents")
            if isinstance(cents, (int, float)):
                cost_cents = cents
            elif default.get("amount") is not None:
                amt = default.get("amount")
                if isinstance(amt, (int, float)):
                    cost_cents = amt
    source_workspace = data.get("source")
    cwd = source_workspace if isinstance(source_workspace, str) else None

    headers = data.get("fullConversationHeadersOnly")
    bubble_ids: list[str] = []
    if isinstance(headers, list):
        for entry in headers:
            if isinstance(entry, str):
                bubble_ids.append(entry)
            elif isinstance(entry, dict):
                bid = entry.get("bubbleId") or entry.get("id")
                if isinstance(bid, str):
                    bubble_ids.append(bid)

    events: list[dict[str, Any]] = []
    tool_calls: list[ToolCallDraft] = []
    file_artifacts: list[FileArtifactDraft] = []
    usage = UsageAccumulator()
    has_any_tokens = False
    total_input = 0
    total_output = 0
    notes: list[str] = []

    for bid in bubble_ids:
        bubble = _fetch_value(conn, f"bubbleId:{composer_id}:{bid}")
        if not isinstance(bubble, dict):
            continue
        btype = bubble.get("type")
        text = bubble.get("text")
        text = text if isinstance(text, str) else ""
        token_count = bubble.get("tokenCount")
        in_tok = out_tok = 0
        if isinstance(token_count, dict):
            in_tok = _to_int(token_count.get("inputTokens"))
            out_tok = _to_int(token_count.get("outputTokens"))
            if in_tok or out_tok:
                has_any_tokens = True
            total_input += in_tok
            total_output += out_tok
        if btype == 1:
            text = _strip_user_query(text)
            if text:
                events.append({"type": "user_prompt", **text_payload(text)})
        elif btype == 2:
            event: dict[str, Any] = {
                "type": "assistant_message",
                "model": "cursor",
                **text_payload(text),
                "input_tokens": in_tok or None,
                "output_tokens": out_tok or None,
                "context_tokens_after": (total_input + total_output) or None,
            }
            events.append(event)

    # Best-effort join with the agent-transcript JSONL for tool-call structure.
    transcript_path = _find_transcript(transcript_root, composer_id)
    if transcript_path is not None:
        t_events, t_tools, t_artifacts, t_links = _parse_transcript_tools(
            transcript_path, repo_root=repo_root
        )
        events.extend(t_events)
        tool_calls.extend(t_tools)
        file_artifacts.extend(t_artifacts)
        # t_links consumed below

    has_cost = has_any_tokens or cost_cents is not None
    if cost_cents is not None:
        usage.usage.cost = float(cost_cents) / 100.0
    usage.usage.input_tokens = total_input
    usage.usage.output_tokens = total_output
    if not has_cost:
        notes.append(
            "cursor: no tokenCount/costInCents in state.vscdb (older Cursor or privacy mode)"
        )

    is_best_of_n = bool(data.get("isBestOfNSubcomposer"))
    num_sub = data.get("numSubComposers")
    num_sub = int(num_sub) if isinstance(num_sub, int) else None
    if is_best_of_n:
        notes.append(
            "cursor: best-of-N subagent — has_cost=0 so parent composer totals "
            "are not double-counted"
        )
        has_cost = False

    return ParsedCursorSession(
        external_id=composer_id,
        cwd=cwd,
        git_branch=None,
        started_at=started_at,
        ended_at=ended_at,
        model="cursor",
        events=events,
        tool_calls=tool_calls,
        file_artifacts=file_artifacts,
        sub_agent_links=[],
        usage=usage,
        has_cost=has_cost,
        is_best_of_n_subcomposer=is_best_of_n,
        num_sub_composers=num_sub,
        data_notes=notes,
    )


def _fetch_value(conn: sqlite3.Connection, key: str) -> Any:
    row = conn.execute("SELECT value FROM cursorDiskKV WHERE key = ?", (key,)).fetchone()
    if row is None:
        return None
    return _decode_value(row[0])


def _find_transcript(transcript_root: Path | None, composer_id: str) -> Path | None:
    if transcript_root is None:
        return None
    candidate = transcript_root / f"{composer_id}.jsonl"
    if candidate.is_file():
        return candidate
    for path in transcript_root.rglob(f"{composer_id}.jsonl"):
        return path
    return None


def _iso_timestamp(value: Any) -> str | None:
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value / 1000.0, tz=UTC).isoformat()
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str) and value:
        return value
    return None


def _to_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    return 0


# ---------------------------------------------------------------------------
# Legacy agent-transcript fallback (no timestamps / no usage)
# ---------------------------------------------------------------------------


def parse_transcript_file(
    path: Path,
    *,
    repo_root: Path | None = None,
    external_id: str | None = None,
    parent_session_id: str | None = None,
) -> ParsedCursorSession | None:
    """Parse one Cursor ``agent-transcripts/.../*.jsonl`` file (legacy fallback).

    Transcripts carry no timestamps and no usage. We never store ``line:N``;
    ``started_at`` comes from the file mtime (ISO-8601) so the run is not
    pinned to 1 Jan 1970, and ``has_cost`` stays 0 with a data-note.
    """
    session_id = external_id or _session_id_from_path(path, parent_session_id)
    if session_id is None:
        return None
    state = _TranscriptState(
        repo_root=repo_root,
        external_id=session_id,
        parent_session_id=parent_session_id,
    )
    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                obj = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict):
                continue
            state.consume(obj, line_no=line_no)
    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat()
    except OSError:
        mtime = None
    return state.finish(mtime)


def _session_id_from_path(path: Path, parent_session_id: str | None) -> str | None:
    stem = path.stem
    if not stem:
        return None
    if parent_session_id is not None:
        return cursor_subagent_external_id(path, parent_session_id)
    parent_dir = path.parent.name
    if parent_dir == "subagents" and path.parent.parent.name:
        return cursor_subagent_external_id(path, path.parent.parent.name)
    return stem


def _parse_transcript_tools(
    path: Path,
    *,
    repo_root: Path | None,
) -> tuple[
    list[dict[str, Any]], list[ToolCallDraft], list[FileArtifactDraft], list[dict[str, str]]
]:
    state = _TranscriptState(repo_root=repo_root, external_id=path.stem, parent_session_id=None)
    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                obj = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                state.consume(obj, line_no=line_no)
    return state._events, state._tool_calls, state._file_artifacts, state._sub_agent_links


class _TranscriptState:
    def __init__(
        self,
        *,
        repo_root: Path | None,
        external_id: str,
        parent_session_id: str | None,
    ) -> None:
        self._repo_root = repo_root
        self._external_id = external_id
        self._parent_session_id = parent_session_id
        self._cwd: str | None = str(repo_root) if repo_root else None
        self._events: list[dict[str, Any]] = []
        self._tool_calls: list[ToolCallDraft] = []
        self._file_artifacts: list[FileArtifactDraft] = []
        self._sub_agent_links: list[dict[str, str]] = []
        self._seq_hint = 0
        self._tool_counter = 0

    def consume(self, obj: dict[str, Any], *, line_no: int) -> None:
        role = obj.get("role")
        if role == "user":
            self._parse_user(obj, line_no=line_no)
        elif role == "assistant":
            self._parse_assistant(obj, line_no=line_no)

    def finish(self, mtime: str | None) -> ParsedCursorSession:
        return ParsedCursorSession(
            external_id=self._external_id,
            cwd=self._cwd,
            git_branch=None,
            started_at=mtime,
            ended_at=mtime,
            model="cursor",
            parent_session_id=self._parent_session_id,
            events=self._events,
            tool_calls=self._tool_calls,
            file_artifacts=self._file_artifacts,
            sub_agent_links=self._sub_agent_links,
            has_cost=False,
            data_notes=["cursor: agent-transcript fallback has no token/cost data"],
        )

    def _next_seq_hint(self) -> int:
        self._seq_hint += 1
        return self._seq_hint

    def _next_tool_use_id(self, line_no: int, block_idx: int) -> str:
        self._tool_counter += 1
        return f"cursor:{line_no}:{block_idx}"

    def _parse_user(self, obj: dict[str, Any], *, line_no: int) -> None:
        message = obj.get("message")
        if not isinstance(message, dict):
            return
        content = message.get("content")
        if not isinstance(content, list):
            return
        text = _content_text(content)
        if not text:
            return
        text = _strip_user_query(text)
        if not text:
            return
        self._next_seq_hint()
        self._events.append({"type": "user_prompt", **text_payload(text)})

    def _parse_assistant(self, obj: dict[str, Any], *, line_no: int) -> None:
        message = obj.get("message")
        if not isinstance(message, dict):
            return
        content = message.get("content")
        if not isinstance(content, list):
            return
        text_parts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        text = "\n".join(str(t) for t in text_parts if t).strip()
        if text:
            self._next_seq_hint()
            self._events.append(
                {"type": "assistant_message", "model": "cursor", **text_payload(text)}
            )
        block_idx = 0
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") != "tool_use":
                continue
            self._emit_tool_call(block, line_no=line_no, block_idx=block_idx)
            block_idx += 1

    def _emit_tool_call(self, block: dict[str, Any], *, line_no: int, block_idx: int) -> None:
        name = block.get("name")
        tool_input = block.get("input")
        if not isinstance(name, str):
            return
        if not isinstance(tool_input, dict):
            tool_input = {}
        tool_use_id = block.get("id")
        if not isinstance(tool_use_id, str) or not tool_use_id:
            tool_use_id = self._next_tool_use_id(line_no, block_idx)
        norm_name = normalize_cursor_tool_name(name)
        seq = self._next_seq_hint()
        payload = args_payload(tool_input)
        self._events.append(
            {"type": "tool_call", "tool_use_id": tool_use_id, "name": norm_name, **payload}
        )
        path_rel = _extract_path_rel(name, tool_input, self._repo_root)
        if path_rel and norm_name == "edit":
            self._file_artifacts.append(
                FileArtifactDraft(
                    path_rel=path_rel, first_seq_hint=seq, last_seq_hint=seq, op="edit"
                )
            )
        if norm_name == "sub_agent":
            child_id = _subagent_child_id(tool_input)
            if child_id:
                self._sub_agent_links.append(
                    {
                        "parent_tool_use_id": tool_use_id,
                        "child_session_id": child_id,
                        "child_source": "cursor",
                    }
                )
        self._tool_calls.append(
            ToolCallDraft(
                tool_use_id=tool_use_id,
                name=norm_name,
                args_hash=str(payload["args_hash"]),
                seq_hint=seq,
                path_rel=path_rel,
            )
        )


def _content_text(content: list[Any]) -> str:
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str) and text:
                parts.append(text)
    return "\n".join(parts).strip()


def _strip_user_query(text: str) -> str:
    match = _USER_QUERY_RE.search(text)
    if match:
        return match.group(1).strip()
    return text.strip()


def _extract_path_rel(
    tool_name: str,
    tool_input: dict[str, Any],
    repo_root: Path | None,
) -> str | None:
    if tool_name in _CURSOR_EDIT or tool_name == "Delete":
        for key in ("path", "file_path", "target_file"):
            val = tool_input.get(key)
            if isinstance(val, str) and val:
                if repo_root is None:
                    return val
                return path_rel_to_repo(repo_root, val)
    if tool_name == "Read":
        val = tool_input.get("path")
        if isinstance(val, str) and val:
            if repo_root is None:
                return val
            return path_rel_to_repo(repo_root, val)
    return None


def _subagent_child_id(tool_input: dict[str, Any]) -> str | None:
    for key in ("subagent_id", "agent_id", "session_id", "child_session_id"):
        val = tool_input.get(key)
        if isinstance(val, str) and val:
            return val
    return None
