"""`cairn hook` — live capture hook handler (R19.8)."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cairn.ingest.normalizer import args_payload, result_payload, text_payload
from cairn.ingest.parsers.codex import extract_apply_patch_paths, normalize_codex_tool_name
from cairn.ingest.project_paths import resolve_git_root
from cairn.ingest.writer import CaptureWriter

HOOK_ERROR_LOG = Path.home() / ".cairn" / "hook-errors.log"

_CLAUDE_EDIT = frozenset({"Edit", "Write", "MultiEdit"})
_CODEX_EDIT = frozenset({"apply_patch", "Edit", "Write"})


def log_hook_error(message: str) -> None:
    HOOK_ERROR_LOG.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).isoformat()
    with HOOK_ERROR_LOG.open("a", encoding="utf-8") as handle:
        handle.write(f"{stamp} {message}\n")


def run_hook(*, event: str, source: str) -> int:
    """Handle one hook invocation. Always returns 0 (R19.8)."""
    try:
        payload = _read_stdin_payload(event=event, source=source)
        if payload is None:
            return 0
        _dispatch(event, source, payload)
    except Exception as exc:  # noqa: BLE001 — hooks must never block the agent
        log_hook_error(f"{event}/{source}: {exc!s}")
    return 0


def _read_stdin_payload(*, event: str, source: str) -> dict[str, Any] | None:
    raw = sys.stdin.read()
    if not raw.strip():
        log_hook_error(f"empty stdin for {event}/{source}")
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        log_hook_error("malformed stdin JSON")
        return None
    return data if isinstance(data, dict) else None


def _dispatch(event: str, source: str, payload: dict[str, Any]) -> None:
    cwd = _payload_str(payload, "cwd") or _payload_str(payload, "working_directory")
    project_root = resolve_git_root(Path(cwd)) if cwd else None
    if project_root is None and cwd:
        project_root = Path(cwd).resolve()
    if project_root is None:
        log_hook_error("missing cwd in hook payload")
        return

    external_id = _session_id(payload, source)
    if external_id is None:
        log_hook_error("missing session id in hook payload")
        return

    writer = CaptureWriter(project_root)
    try:
        if event == "SessionStart":
            writer.begin_session(source=source, external_id=external_id, cwd=cwd)
            return
        run_id = writer.begin_session(source=source, external_id=external_id, cwd=cwd)
        if event == "UserPromptSubmit":
            _handle_user_prompt(writer, run_id, payload)
        elif event == "PreToolUse":
            _handle_pre_tool(writer, run_id, payload, source=source, cwd=cwd)
        elif event == "PostToolUse":
            _handle_post_tool(writer, run_id, payload, source=source, cwd=cwd)
        elif event == "Stop":
            writer.finish_session(run_id)
    finally:
        writer.close()


def _session_id(payload: dict[str, Any], source: str) -> str | None:
    for key in ("session_id", "sessionId", "conversation_id"):
        val = payload.get(key)
        if isinstance(val, str) and val:
            return val
    if source == "codex":
        val = payload.get("id")
        if isinstance(val, str) and val:
            return val
    return None


def _payload_str(payload: dict[str, Any], key: str) -> str | None:
    val = payload.get(key)
    return val if isinstance(val, str) else None


def _handle_user_prompt(
    writer: CaptureWriter,
    run_id: str,
    payload: dict[str, Any],
) -> None:
    for key in ("prompt", "user_message", "message"):
        text = payload.get(key)
        if isinstance(text, str) and text.strip():
            writer.append_event(run_id, {"type": "user_prompt", **text_payload(text)})
            return


def _handle_pre_tool(
    writer: CaptureWriter,
    run_id: str,
    payload: dict[str, Any],
    *,
    source: str,
    cwd: str | None,
) -> None:
    tool_name = _payload_str(payload, "tool_name") or _payload_str(payload, "name") or ""
    tool_input = _tool_input(payload)
    tool_use_id = (
        _payload_str(payload, "tool_use_id")
        or _payload_str(payload, "call_id")
        or _payload_str(payload, "tool_id")
        or "unknown"
    )
    norm_name = normalize_codex_tool_name(tool_name) if source == "codex" else tool_name
    arg_data = args_payload(tool_input)
    writer.append_event(
        run_id,
        {
            "type": "tool_call",
            "tool_use_id": tool_use_id,
            "name": norm_name,
            **arg_data,
        },
    )
    if not _is_edit_tool(tool_name, source):
        return
    for path_rel, before_hash in _file_paths_and_before(
        tool_name, tool_input, writer, cwd=cwd
    ):
        if before_hash:
            seq = writer.append_event(
                run_id,
                {
                    "type": "file_snapshot",
                    "path_rel": path_rel,
                    "op": "edit",
                    "before_hash": before_hash,
                },
            )
            writer.record_file_before(run_id, path_rel, before_hash, seq)


def _handle_post_tool(
    writer: CaptureWriter,
    run_id: str,
    payload: dict[str, Any],
    *,
    source: str,
    cwd: str | None,
) -> None:
    tool_name = _payload_str(payload, "tool_name") or _payload_str(payload, "name") or ""
    tool_input = _tool_input(payload)
    tool_use_id = (
        _payload_str(payload, "tool_use_id")
        or _payload_str(payload, "call_id")
        or _payload_str(payload, "tool_id")
        or "unknown"
    )
    if not writer.has_tool_call(run_id, tool_use_id):
        norm_name = normalize_codex_tool_name(tool_name) if source == "codex" else tool_name
        arg_data = args_payload(tool_input)
        writer.append_event(
            run_id,
            {
                "type": "tool_call",
                "tool_use_id": tool_use_id,
                "name": norm_name,
                **arg_data,
            },
        )
    result_text = _tool_result_text(payload)
    writer.append_event(
        run_id,
        {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            **result_payload(result_text),
            "is_error": bool(payload.get("is_error")),
        },
    )
    if not _is_edit_tool(tool_name, source):
        return
    for path_rel in _file_paths(tool_name, tool_input, writer, cwd=cwd):
        after_hash = writer.snapshot_file_hash(
            str((writer.project_root / path_rel).resolve()),
            None,
        )
        if after_hash is None:
            continue
        seq = writer.append_event(
            run_id,
            {
                "type": "file_snapshot",
                "path_rel": path_rel,
                "op": "edit",
                "after_hash": after_hash,
            },
        )
        writer.record_file_after(run_id, path_rel, after_hash, seq)


def _tool_input(payload: dict[str, Any]) -> dict[str, Any]:
    raw = payload.get("tool_input") or payload.get("arguments") or payload.get("input")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return {"raw": raw}
    return {}


def _tool_result_text(payload: dict[str, Any]) -> str:
    resp = payload.get("tool_response")
    if isinstance(resp, dict):
        stdout = resp.get("stdout")
        stderr = resp.get("stderr")
        parts: list[str] = []
        if isinstance(stdout, str) and stdout:
            parts.append(stdout)
        if isinstance(stderr, str) and stderr:
            parts.append(stderr)
        if parts:
            return "\n".join(parts)
        return json.dumps(resp, sort_keys=True)
    for key in ("tool_output", "result", "output", "content"):
        val = payload.get(key)
        if isinstance(val, str):
            return val
    return json.dumps({k: payload[k] for k in payload if k not in ("cwd",)}, sort_keys=True)


def _is_edit_tool(tool_name: str, source: str) -> bool:
    if source == "codex":
        return tool_name in _CODEX_EDIT
    return tool_name in _CLAUDE_EDIT


def _file_paths(
    tool_name: str,
    tool_input: dict[str, Any],
    writer: CaptureWriter,
    *,
    cwd: str | None,
) -> list[str]:
    paths: list[str] = []
    if tool_name == "apply_patch":
        patch = tool_input.get("patch") or tool_input.get("input") or ""
        if isinstance(patch, str):
            for raw in extract_apply_patch_paths(patch):
                rel = writer.rel_path(raw, cwd)
                if rel:
                    paths.append(rel)
        return paths
    for key in ("file_path", "path"):
        val = tool_input.get(key)
        if isinstance(val, str):
            rel = writer.rel_path(val, cwd)
            if rel:
                paths.append(rel)
            break
    return paths


def _file_paths_and_before(
    tool_name: str,
    tool_input: dict[str, Any],
    writer: CaptureWriter,
    *,
    cwd: str | None,
) -> list[tuple[str, str | None]]:
    out: list[tuple[str, str | None]] = []
    for path_rel in _file_paths(tool_name, tool_input, writer, cwd=cwd):
        before = writer.snapshot_file_hash(
            str((writer.project_root / path_rel).resolve()),
            None,
        )
        out.append((path_rel, before))
    return out

