"""OpenCode SQLite session store (``opencode.db``) discovery and parsing."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from server.ingest.adapters.claude_code import FileArtifactDraft, ToolCallDraft
from server.ingest.normalizer import args_payload, result_payload, text_payload
from server.ingest.project_paths import path_rel_to_repo
from server.ingest.usage import ObservedUsage, UsageAccumulator

_LOGGER = logging.getLogger(__name__)

_EDIT_TOOLS = frozenset({"edit", "write", "multiedit", "apply_patch", "patch"})
_READ_TOOLS = frozenset({"read", "list", "glob", "grep", "search"})
_SAFE_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_MAX_DISCOVERED_SESSIONS = 200
_MAX_MESSAGES_PER_SESSION = 20_000
_MAX_PARTS_PER_SESSION = 80_000
_MAX_PROJECT_UNDER_SESSION_DEPTH = 3


@dataclass
class ParsedOpenCodeSession:
    external_id: str
    cwd: str | None
    started_at: str | None
    ended_at: str | None
    model: str | None
    events: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[ToolCallDraft] = field(default_factory=list)
    file_artifacts: list[FileArtifactDraft] = field(default_factory=list)
    usage: UsageAccumulator = field(default_factory=UsageAccumulator)
    has_cost: bool = False


def opencode_data_root() -> Path:
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / "opencode"
    return Path.home() / ".local" / "share" / "opencode"


def opencode_db_path() -> Path:
    return opencode_data_root() / "opencode.db"


def opencode_stream_stub_root() -> Path:
    return Path.home() / ".cairn" / "opencode-streams"


def discover_opencode_db_sessions(
    repo_root: Path,
    *,
    since: datetime | None = None,
) -> list[Path]:
    """Return unique stub paths (one per matching session) for pipeline ingest."""
    db = opencode_db_path()
    if not db.is_file():
        return []
    project = repo_root.resolve()
    project_s = str(project)
    since_ms = int(since.timestamp() * 1000) if since is not None else None
    stubs: list[Path] = []
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        _LOGGER.warning("opencode db open failed: %s", exc)
        return []
    try:
        # Exact match, session under project, or project under session cwd.
        rows = conn.execute(
            """
            SELECT id, directory, title, time_created, time_updated
            FROM session
            WHERE directory IS NOT NULL
              AND (
                directory = ?
                OR directory LIKE ? || '/%'
                OR ? LIKE directory || '/%'
              )
            ORDER BY time_updated DESC
            LIMIT ?
            """,
            (project_s, project_s, project_s, _MAX_DISCOVERED_SESSIONS),
        ).fetchall()
    except sqlite3.Error as exc:
        _LOGGER.warning("opencode session discover failed: %s", exc)
        conn.close()
        return []
    for session_id, directory, title, time_created, time_updated in rows:
        if not isinstance(session_id, str) or not session_id:
            continue
        if not isinstance(directory, str) or not directory:
            continue
        try:
            session_dir = Path(directory).resolve()
        except OSError:
            continue
        if not _directory_matches_project(session_dir, project):
            continue
        updated = int(time_updated or time_created or 0)
        if since_ms is not None and updated < since_ms:
            continue
        stub = _ensure_session_stub(
            session_id=session_id,
            db=db,
            directory=directory,
            title=title if isinstance(title, str) else None,
            mtime_ms=updated,
        )
        if stub is not None:
            stubs.append(stub)
    conn.close()
    return stubs


def parse_opencode_session_stub(
    path: Path,
    *,
    repo_root: Path | None = None,
) -> ParsedOpenCodeSession | None:
    """Parse a Cairn ``.opencode-session`` stub pointing at ``opencode.db``."""
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(meta, dict):
        return None
    session_id = meta.get("session_id")
    db_raw = meta.get("db")
    if not isinstance(session_id, str) or not isinstance(db_raw, str):
        return None
    db_path = Path(db_raw)
    if not _is_trusted_opencode_db(db_path):
        _LOGGER.warning("rejecting opencode stub with untrusted db path: %s", db_path)
        return None
    return parse_opencode_db_session(db_path, session_id, repo_root=repo_root)


def parse_opencode_db_session(
    db_path: Path,
    session_id: str,
    *,
    repo_root: Path | None = None,
) -> ParsedOpenCodeSession | None:
    if not db_path.is_file():
        return None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        _LOGGER.warning("opencode db open failed: %s", exc)
        return None
    try:
        row = conn.execute(
            """
            SELECT id, directory, title, model, time_created, time_updated,
                   cost, tokens_input, tokens_output, tokens_reasoning,
                   tokens_cache_read, tokens_cache_write, agent
            FROM session WHERE id = ?
            """,
            (session_id,),
        ).fetchone()
        if row is None:
            return None
        (
            sid,
            directory,
            _title,
            model_raw,
            time_created,
            time_updated,
            cost,
            tokens_input,
            tokens_output,
            tokens_reasoning,
            tokens_cache_read,
            tokens_cache_write,
            _agent,
        ) = row
        messages = conn.execute(
            """
            SELECT id, time_created, data
            FROM message
            WHERE session_id = ?
            ORDER BY time_created ASC, id ASC
            LIMIT ?
            """,
            (session_id, _MAX_MESSAGES_PER_SESSION),
        ).fetchall()
        parts_by_message: dict[str, list[dict[str, Any]]] = {}
        part_count = 0
        for message_id, _tc, part_data in conn.execute(
            """
            SELECT message_id, time_created, data
            FROM part
            WHERE session_id = ?
            ORDER BY time_created ASC, id ASC
            LIMIT ?
            """,
            (session_id, _MAX_PARTS_PER_SESSION),
        ):
            if not isinstance(message_id, str):
                continue
            part_count += 1
            try:
                payload = json.loads(part_data) if part_data else {}
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                parts_by_message.setdefault(message_id, []).append(payload)
        if part_count >= _MAX_PARTS_PER_SESSION:
            _LOGGER.warning(
                "opencode session %s truncated at %s parts",
                session_id,
                _MAX_PARTS_PER_SESSION,
            )
    except sqlite3.Error as exc:
        _LOGGER.warning("opencode session parse failed: %s", exc)
        conn.close()
        return None
    conn.close()

    state = _ParserState(
        external_id=str(sid),
        cwd=directory if isinstance(directory, str) else None,
        repo_root=repo_root,
        model=_coerce_model(model_raw),
        started_at=_ms_to_iso(time_created),
        ended_at=_ms_to_iso(time_updated or time_created),
    )
    session_usage = ObservedUsage(
        input_tokens=int(tokens_input or 0),
        output_tokens=int(tokens_output or 0),
        reasoning_tokens=int(tokens_reasoning or 0),
        cache_read_tokens=int(tokens_cache_read or 0),
        cache_creation_tokens=int(tokens_cache_write or 0),
        cost=float(cost) if isinstance(cost, (int, float)) else None,
    )
    if any(
        (
            session_usage.input_tokens,
            session_usage.output_tokens,
            session_usage.cache_read_tokens,
            session_usage.cache_creation_tokens,
        )
    ):
        state._usage.usage.add(session_usage)
        state._has_cost = session_usage.cost is not None and session_usage.cost > 0

    for message_id, _tc, data in messages:
        try:
            message = json.loads(data) if data else {}
        except json.JSONDecodeError:
            continue
        if not isinstance(message, dict):
            continue
        parts = parts_by_message.get(str(message_id), [])
        state.consume_message(message, parts)

    return state.finish()


def _ensure_session_stub(
    *,
    session_id: str,
    db: Path,
    directory: str,
    title: str | None,
    mtime_ms: int,
) -> Path | None:
    path = _stub_path_for_session(session_id)
    if path is None:
        return None
    payload = {
        "db": str(db.resolve()),
        "session_id": session_id,
        "directory": directory,
        "title": title or "",
    }
    encoded = json.dumps(payload, sort_keys=True) + "\n"
    try:
        if not path.is_file() or path.read_text(encoding="utf-8") != encoded:
            path.write_text(encoded, encoding="utf-8")
        if mtime_ms > 0:
            ts = mtime_ms / 1000.0
            os.utime(path, (ts, ts))
    except OSError as exc:
        _LOGGER.warning("opencode stub write failed for %s: %s", session_id, exc)
        return None
    return path


def _stub_path_for_session(session_id: str) -> Path | None:
    root = opencode_stream_stub_root().resolve()
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    if _SAFE_SESSION_ID_RE.fullmatch(session_id):
        name = f"{session_id}.opencode-session"
    else:
        digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:32]
        name = f"sess_{digest}.opencode-session"
    path = (root / name).resolve()
    if not path.is_relative_to(root):
        _LOGGER.warning("rejecting opencode stub path escape for session %r", session_id)
        return None
    return path


def _is_trusted_opencode_db(db_path: Path) -> bool:
    try:
        return db_path.resolve() == opencode_db_path().resolve()
    except OSError:
        return False


class _ParserState:
    def __init__(
        self,
        *,
        external_id: str,
        cwd: str | None,
        repo_root: Path | None,
        model: str | None,
        started_at: str | None,
        ended_at: str | None,
    ) -> None:
        self._external_id = external_id
        self._cwd = cwd
        self._repo_root = repo_root
        self._model = model
        self._started_at = started_at
        self._ended_at = ended_at
        self._events: list[dict[str, Any]] = []
        self._tool_calls: list[ToolCallDraft] = []
        self._file_artifacts: list[FileArtifactDraft] = []
        self._usage = UsageAccumulator()
        self._has_cost = False
        self._seq_hint = 0

    def consume_message(self, message: dict[str, Any], parts: list[dict[str, Any]]) -> None:
        role = message.get("role")
        model = _coerce_model(message.get("model")) or _coerce_model(
            {
                "providerID": message.get("providerID"),
                "modelID": message.get("modelID"),
            }
        )
        if model:
            self._model = model
        tokens = message.get("tokens")
        if isinstance(tokens, dict):
            cache = tokens.get("cache")
            if isinstance(cache, dict):
                cache_read = int(cache.get("read") or 0)
                cache_write = int(cache.get("write") or 0)
            else:
                cache_read = int(cache or tokens.get("cache_read") or 0)
                cache_write = int(tokens.get("cache_write") or 0)
            observed = ObservedUsage(
                input_tokens=int(tokens.get("input") or tokens.get("input_tokens") or 0),
                output_tokens=int(tokens.get("output") or tokens.get("output_tokens") or 0),
                reasoning_tokens=int(tokens.get("reasoning") or 0),
                cache_read_tokens=cache_read,
                cache_creation_tokens=cache_write,
            )
            if (
                (observed.input_tokens or observed.output_tokens or observed.cache_read_tokens)
                and self._usage.usage.input_tokens == 0
                and self._usage.usage.output_tokens == 0
            ):
                self._usage.usage.add(observed)
        cost = message.get("cost")
        if isinstance(cost, (int, float)) and cost > 0:
            self._has_cost = True
            if self._usage.usage.cost is None:
                self._usage.usage.cost = float(cost)

        if role == "user":
            text = _parts_text(parts, include_reasoning=False)
            if text:
                self._seq_hint += 1
                self._events.append({"type": "user_prompt", **text_payload(text)})
            return

        if role != "assistant":
            return

        text = _parts_text(parts, include_reasoning=False)
        if text:
            self._seq_hint += 1
            self._events.append(
                {
                    "type": "assistant_message",
                    "model": self._model or "opencode",
                    **text_payload(text),
                }
            )
        for part in parts:
            if part.get("type") != "tool":
                continue
            self._emit_tool(part)

    def _emit_tool(self, part: dict[str, Any]) -> None:
        name = part.get("tool") or part.get("name")
        call_id = part.get("callID") or part.get("callId") or part.get("id")
        if not isinstance(name, str) or not name:
            return
        if not isinstance(call_id, str) or not call_id:
            call_id = f"opencode:{self._seq_hint + 1}:{name}"
        state_obj = part.get("state")
        state: dict[str, Any] = state_obj if isinstance(state_obj, dict) else {}
        input_obj = state.get("input")
        tool_input: dict[str, Any] = input_obj if isinstance(input_obj, dict) else {}
        output = state.get("output")
        status = state.get("status")
        seq = self._seq_hint + 1
        self._seq_hint = seq
        payload = args_payload(tool_input if isinstance(tool_input, dict) else {})
        self._events.append(
            {
                "type": "tool_call",
                "tool_use_id": call_id,
                "name": name,
                **payload,
            }
        )
        path_rel = None
        lowered = name.lower()
        if lowered in _EDIT_TOOLS or lowered in _READ_TOOLS:
            for key in ("filePath", "path", "file_path"):
                raw = tool_input.get(key) if isinstance(tool_input, dict) else None
                if isinstance(raw, str) and raw:
                    path_rel = (
                        path_rel_to_repo(self._repo_root, raw)
                        if self._repo_root is not None
                        else raw
                    )
                    op = "edit" if lowered in _EDIT_TOOLS else "read"
                    if path_rel:
                        self._file_artifacts.append(
                            FileArtifactDraft(
                                path_rel=path_rel,
                                first_seq_hint=seq,
                                last_seq_hint=seq,
                                op=op,
                            )
                        )
                    break
        self._tool_calls.append(
            ToolCallDraft(
                tool_use_id=call_id,
                name=name,
                args_hash=str(payload["args_hash"]),
                seq_hint=seq,
                path_rel=path_rel,
            )
        )
        if output is not None or status:
            text = output if isinstance(output, str) else json.dumps(output)
            self._seq_hint += 1
            self._events.append(
                {
                    "type": "tool_result",
                    "tool_use_id": call_id,
                    **result_payload(text if isinstance(text, str) else str(text)),
                    "is_error": isinstance(status, str) and status.lower() in {"error", "failed"},
                }
            )

    def finish(self) -> ParsedOpenCodeSession:
        return ParsedOpenCodeSession(
            external_id=self._external_id,
            cwd=self._cwd,
            started_at=self._started_at,
            ended_at=self._ended_at,
            model=self._model,
            events=self._events,
            tool_calls=self._tool_calls,
            file_artifacts=self._file_artifacts,
            usage=self._usage,
            has_cost=self._has_cost,
        )


def _parts_text(parts: list[dict[str, Any]], *, include_reasoning: bool) -> str:
    chunks: list[str] = []
    for part in parts:
        ptype = part.get("type")
        if ptype == "text" or (include_reasoning and ptype == "reasoning"):
            text = part.get("text")
            if isinstance(text, str) and text.strip():
                chunks.append(text.strip())
    return "\n".join(chunks).strip()


def _coerce_model(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, dict):
        model_id = value.get("modelID") or value.get("id") or value.get("model")
        provider = value.get("providerID") or value.get("provider")
        if isinstance(model_id, str) and model_id:
            if isinstance(provider, str) and provider:
                return f"{provider}/{model_id}"
            return model_id
    return None


def _ms_to_iso(value: Any) -> str | None:
    if not isinstance(value, (int, float)) or value <= 0:
        return None
    return datetime.fromtimestamp(float(value) / 1000.0, tz=UTC).isoformat()


def _directory_matches_project(session_dir: Path, project: Path) -> bool:
    if session_dir == project:
        return True
    try:
        session_dir.relative_to(project)
        return True
    except ValueError:
        pass
    try:
        rel = project.relative_to(session_dir)
        return len(rel.parts) <= _MAX_PROJECT_UNDER_SESSION_DEPTH
    except ValueError:
        return False
