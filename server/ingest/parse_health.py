"""Adapter parse-health measurement and upstream shape canaries."""

from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

# Pretty-printed JSON typically uses 2-space indent for top-level object keys.
# Nested keys sit at 4+ spaces and must not be treated as top-level.
_TOP_LEVEL_KEY_RE = re.compile(r'^  "([^\\"]+)"\s*:\s*', re.MULTILINE)

PARSE_HEALTH_THRESHOLD = 0.90
UNKNOWN_FIELD_SPIKE = 3
_SAMPLE_BYTES = 64 * 1024

_EXPECTED_FIELDS: dict[str, frozenset[str]] = {
    "claude_code": frozenset(
        {
            "type",
            "sessionId",
            "session_id",
            "uuid",
            "parentUuid",
            "timestamp",
            "cwd",
            "gitBranch",
            "message",
            "toolUseResult",
            "isSidechain",
            "requestId",
            # Common Claude Code metadata / bookkeeping keys (not trajectory payload).
            "userType",
            "version",
            "entrypoint",
            "attachment",
            "promptId",
            "permissionMode",
            "snapshot",
            "isSnapshotUpdate",
            "messageId",
            "mode",
            "leafUuid",
            "isMeta",
            "origin",
            "promptSource",
            "aiTitle",
            "lastPrompt",
            "content",
            "subtype",
            "level",
            "error",
            "apiErrorStatus",
            "isApiErrorMessage",
            "stopReason",
            "durationMs",
            "operation",
            "queuePriority",
            "sourceToolAssistantUUID",
            "sourceToolUseID",
            "toolUseID",
            "hookAdditionalContext",
            "hookCount",
            "hookErrors",
            "hookInfos",
            "imagePasteIds",
            "attributionMcpServer",
            "attributionMcpTool",
            "attributionPlugin",
            "attributionSkill",
            "hasOutput",
            "messageCount",
            "pendingBackgroundAgentCount",
            "preventedContinuation",
            "prNumber",
            "prRepository",
            "prUrl",
            "agent_id",
            "agentId",
            "attributionAgent",
        }
    ),
    "codex": frozenset({"timestamp", "type", "payload"}),
    "cursor": frozenset(
        {
            "role",
            "message",
            "timestamp",
            "model",
            "usage",
            "cwd",
            # Agent-transcript turn markers (ignored for trajectory, expected shape).
            "type",
            "status",
            "error",
        }
    ),
    "cline": frozenset(
        {
            "type",
            "say",
            "ask",
            "text",
            "ts",
            "partial",
            "lastCheckpointHash",
            "conversationHistoryIndex",
            "conversationHistoryDeletedRange",
            "tool",
            "toolInput",
            "toolUseId",
        }
    ),
    "agent_jsonl": frozenset(
        {
            "session_id",
            "timestamp",
            "cwd",
            "git_branch",
            "type",
            "content",
            "model",
            "usage",
            "tool_name",
            "tool_use_id",
            "tool_id",
            "name",
            "input",
            "result",
            "is_error",
        }
    ),
    "gemini": frozenset(
        {
            "role",
            "timestamp",
            "cwd",
            "content",
            "model",
            "usage",
            "type",
            "tool_call",
            "tool_result",
            "tool_name",
            "tool_use_id",
            "input",
        }
    ),
    "hermes": frozenset(
        {
            "session_id",
            "messages",
            "model",
            "session_start",
            "last_updated",
            "usage",
            "base_url",
            "platform",
            "system_prompt",
            "tools",
            "message_count",
        }
    ),
    "opencode": frozenset(
        {
            # Cairn stream stubs for SQLite-backed OpenCode sessions.
            "db",
            "session_id",
            "directory",
            "title",
            # Legacy JSONL fallback (agent_jsonl shape).
            "timestamp",
            "cwd",
            "git_branch",
            "type",
            "content",
            "model",
            "usage",
            "tool_name",
            "tool_use_id",
            "tool_id",
            "name",
            "input",
            "result",
            "is_error",
        }
    ),
    "openclaw": frozenset(
        {
            "event",
            "timestamp",
            "cwd",
            "content",
            "model",
            "usage",
            "tool",
            "tool_name",
            "tool_use_id",
            "tool_input",
            "name",
            "input",
            "result",
            "is_error",
        }
    ),
}

_SHAPE_ALIASES = {
    "aider": "agent_jsonl",
    "goose": "agent_jsonl",
    "roo": "cline",
    "kilo": "cline",
    "gemini_cli": "gemini",
}


def adapter_issue_url(adapter_id: str) -> str:
    title = quote(f"Adapter format change: {adapter_id}")
    return (
        "https://github.com/Harsh-Daga/Cairn/issues/new"
        f"?template=bug_report.yml&title={title}&labels=adapter"
    )


def inspect_unknown_fields(adapter_id: str, path: Path) -> dict[str, int]:
    """Count unknown top-level fields in a bounded live-log sample."""
    unknown = inspect_stream_shape(adapter_id, path)["unknown_fields"]
    return {str(key): int(value) for key, value in unknown.items()}


def unknown_field_spike(unknown_fields: dict[str, int] | None) -> bool:
    """True when one unknown field repeats or many distinct unknowns appear."""
    if not unknown_fields:
        return False
    counts = [int(value) for value in unknown_fields.values()]
    return max(counts) >= UNKNOWN_FIELD_SPIKE or len(counts) >= UNKNOWN_FIELD_SPIKE


def inspect_stream_shape(adapter_id: str, path: Path) -> dict[str, Any]:
    """Describe recognized and unknown fields in a bounded sample."""
    shape = _SHAPE_ALIASES.get(adapter_id, adapter_id)
    expected = _EXPECTED_FIELDS.get(shape)
    if expected is None:
        return {
            "records_sampled": 0,
            "recognized_fields": [],
            "unknown_fields": {},
            "expected_shape_available": False,
        }
    records = _sample_records(path)
    unknown: Counter[str] = Counter()
    recognized: set[str] = set()
    for record in records:
        unknown.update(str(key) for key in record if key not in expected)
        recognized.update(str(key) for key in record if key in expected)
    return {
        "records_sampled": len(records),
        "recognized_fields": sorted(recognized),
        "unknown_fields": dict(sorted(unknown.items())),
        "expected_shape_available": True,
    }


def reset_parse_health(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    adapter_id: str | None = None,
) -> int:
    """Clear accumulated parse-health counters (used by force rescan)."""
    if adapter_id is None:
        cur = conn.execute(
            "DELETE FROM adapter_parse_health WHERE workspace_id = ?",
            (workspace_id,),
        )
    else:
        cur = conn.execute(
            "DELETE FROM adapter_parse_health WHERE workspace_id = ? AND adapter_id = ?",
            (workspace_id, adapter_id),
        )
    return int(cur.rowcount or 0)


def record_parse_attempt(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    adapter_id: str,
    outcome: str,
    unknown_fields: dict[str, int] | None = None,
) -> None:
    """Persist one fully-parsed, degraded, or skipped parse attempt."""
    if outcome not in {"fully_parsed", "degraded", "skipped"}:
        raise ValueError(f"unknown parse outcome: {outcome}")
    now = datetime.now(UTC).isoformat()
    row = conn.execute(
        """SELECT attempts, fully_parsed, degraded, skipped, unknown_fields_json
           FROM adapter_parse_health WHERE workspace_id = ? AND adapter_id = ?""",
        (workspace_id, adapter_id),
    ).fetchone()
    totals: Counter[str] = Counter()
    if row is not None:
        totals.update(json.loads(str(row["unknown_fields_json"])))
    totals.update(unknown_fields or {})
    previous = dict(row) if row is not None else {}
    fully_parsed = int(previous.get("fully_parsed", 0)) + (outcome == "fully_parsed")
    degraded = int(previous.get("degraded", 0)) + (outcome == "degraded")
    skipped = int(previous.get("skipped", 0)) + (outcome == "skipped")
    conn.execute(
        """INSERT INTO adapter_parse_health (
             workspace_id, adapter_id, attempts, fully_parsed, degraded, skipped,
             unknown_fields_json, recent_unknown_fields_json, last_success_at, updated_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(workspace_id, adapter_id) DO UPDATE SET
             attempts=excluded.attempts,
             fully_parsed=excluded.fully_parsed,
             degraded=excluded.degraded,
             skipped=excluded.skipped,
             unknown_fields_json=excluded.unknown_fields_json,
             recent_unknown_fields_json=excluded.recent_unknown_fields_json,
             last_success_at=COALESCE(
               excluded.last_success_at, adapter_parse_health.last_success_at
             ),
             updated_at=excluded.updated_at""",
        (
            workspace_id,
            adapter_id,
            int(previous.get("attempts", 0)) + 1,
            fully_parsed,
            degraded,
            skipped,
            json.dumps(dict(sorted(totals.items()))),
            json.dumps(unknown_fields or {}, sort_keys=True),
            now if outcome != "skipped" else None,
            now,
        ),
    )


def health_payload(row: sqlite3.Row) -> dict[str, Any]:
    attempts = int(row["attempts"] or 0)
    fully = int(row["fully_parsed"] or 0)
    recent = json.loads(str(row["recent_unknown_fields_json"] or "{}"))
    coverage = fully / attempts if attempts else None
    warning = bool(
        attempts
        and (
            coverage is not None
            and coverage < PARSE_HEALTH_THRESHOLD
            or unknown_field_spike(recent)
        )
    )
    return {
        "attempts": attempts,
        "fully_parsed": fully,
        "degraded": int(row["degraded"] or 0),
        "skipped": int(row["skipped"] or 0),
        "parse_coverage": coverage,
        "unknown_fields": json.loads(str(row["unknown_fields_json"] or "{}")),
        "recent_unknown_fields": recent,
        "last_success_at": row["last_success_at"],
        "warning": warning,
    }


def _sample_records(path: Path) -> list[dict[str, Any]]:
    try:
        raw = path.read_bytes()
    except OSError:
        return []
    # Prefer a full parse when the file fits; otherwise sample the head and
    # recover top-level object keys from truncated pretty-printed JSON.
    if len(raw) <= _SAMPLE_BYTES:
        try:
            value = json.loads(raw.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            value = None
        else:
            if isinstance(value, dict):
                return [value]
            if isinstance(value, list):
                return [item for item in value[:100] if isinstance(item, dict)]
    text = raw[:_SAMPLE_BYTES].decode("utf-8", errors="replace")
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        records: list[dict[str, Any]] = []
        for line in text.splitlines()[:100]:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                item = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                records.append(item)
        if records:
            return records
        recovered = _recover_top_level_object(text)
        return [recovered] if recovered is not None else []
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [item for item in value[:100] if isinstance(item, dict)]
    return []


def _recover_top_level_object(text: str) -> dict[str, Any] | None:
    """Best-effort top-level keys from a truncated pretty-printed JSON object."""
    start = text.find("{")
    if start < 0:
        return None
    decoder = json.JSONDecoder()
    try:
        value, _ = decoder.raw_decode(text[start:])
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass
    # Truncated object: collect "key": value pairs near the top level.
    recovered: dict[str, Any] = {}
    for match in _TOP_LEVEL_KEY_RE.finditer(text[start:]):
        key = match.group(1)
        rest = text[start + match.end() :]
        try:
            value, _ = decoder.raw_decode(rest)
        except json.JSONDecodeError:
            recovered[key] = True
            continue
        recovered[key] = value
        if len(recovered) >= 40:
            break
    return recovered or None
