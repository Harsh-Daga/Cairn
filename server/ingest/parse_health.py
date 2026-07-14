"""Adapter parse-health measurement and upstream shape canaries."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

PARSE_HEALTH_THRESHOLD = 0.90
UNKNOWN_FIELD_SPIKE = 3
_SAMPLE_BYTES = 64 * 1024

_EXPECTED_FIELDS: dict[str, frozenset[str]] = {
    "claude_code": frozenset(
        {
            "type",
            "sessionId",
            "uuid",
            "parentUuid",
            "timestamp",
            "cwd",
            "gitBranch",
            "message",
            "toolUseResult",
            "isSidechain",
            "requestId",
        }
    ),
    "codex": frozenset({"timestamp", "type", "payload"}),
    "cursor": frozenset({"role", "message", "timestamp", "model", "usage", "cwd"}),
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
        {"session_id", "messages", "model", "session_start", "last_updated", "usage"}
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
    "opencode": "agent_jsonl",
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
    shape = _SHAPE_ALIASES.get(adapter_id, adapter_id)
    expected = _EXPECTED_FIELDS.get(shape)
    if expected is None:
        return {}
    records = _sample_records(path)
    unknown: Counter[str] = Counter()
    for record in records:
        unknown.update(str(key) for key in record if key not in expected)
    return dict(sorted(unknown.items()))


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
            or sum(int(value) for value in recent.values()) >= UNKNOWN_FIELD_SPIKE
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
        text = path.read_bytes()[:_SAMPLE_BYTES].decode("utf-8", errors="replace")
    except OSError:
        return []
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        records: list[dict[str, Any]] = []
        for line in text.splitlines()[:100]:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                records.append(item)
        return records
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [item for item in value[:100] if isinstance(item, dict)]
    return []
