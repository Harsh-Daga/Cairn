"""Cursor state.vscdb discovery and read-only decoding stage."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from server.ingest.adapters.claude_code import FileArtifactDraft, ToolCallDraft
from server.ingest.adapters.cursor_models import ParsedCursorSession
from server.ingest.adapters.cursor_transcript import (
    parse_transcript_tools as _parse_transcript_tools,
)
from server.ingest.adapters.cursor_transcript import (
    strip_user_query as _strip_user_query,
)
from server.ingest.normalizer import text_payload
from server.ingest.usage import UsageAccumulator


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
