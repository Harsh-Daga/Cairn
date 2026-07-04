"""PreToolUse / Stop guard hooks — fail-open, local-first."""

from __future__ import annotations

import contextlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from cairn.config import get_guard_setting
from cairn.diagnose.should_stop import should_stop_verdict
from cairn.ingest.project_paths import resolve_git_root
from cairn.ingest.watch import resolve_cairn_executable
from cairn.ledger.ledger import Ledger

CAIRN_PRETOOLUSE_CMD = f"{resolve_cairn_executable()} hook pretooluse"
CAIRN_STOP_CMD = f"{resolve_cairn_executable()} hook stop"

_GUARD_HOOKS_BLOCK: dict[str, Any] = {
    "PreToolUse": [
        {
            "matcher": "*",
            "hooks": [{"type": "command", "command": CAIRN_PRETOOLUSE_CMD}],
        }
    ],
    "Stop": [
        {
            "matcher": "*",
            "hooks": [{"type": "command", "command": CAIRN_STOP_CMD}],
        }
    ],
}


def resolve_guard_run(
    conn: Any,
    session_id: str | None,
    cwd: str | None,
) -> str | None:
    """Prefer ledger run by session_id; else most recent run matching cwd."""
    if session_id:
        row = conn.execute(
            "SELECT run_id FROM runs WHERE external_id = ? ORDER BY started_at DESC LIMIT 1",
            (session_id,),
        ).fetchone()
        if row is not None:
            return str(row["run_id"])

    if not cwd:
        return None

    try:
        cwd_path = Path(cwd).resolve()
    except OSError:
        return None

    git_root = resolve_git_root(cwd_path)
    rows = conn.execute(
        "SELECT run_id, cwd FROM runs ORDER BY started_at DESC",
    ).fetchall()
    for row in rows:
        run_cwd = row["cwd"]
        if not run_cwd:
            continue
        try:
            run_path = Path(str(run_cwd)).resolve()
        except OSError:
            continue
        if run_path == cwd_path:
            return str(row["run_id"])
        if git_root is not None and (run_path == git_root or git_root in run_path.parents):
            return str(row["run_id"])
    return None


def load_tail_events(conn: Any, run_id: str, tail: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM events WHERE run_id = ? ORDER BY seq DESC LIMIT ?",
        (run_id, tail),
    ).fetchall()
    return [dict(r) for r in reversed(rows)]


def _guard_message(reason: str | None, suggestion: str | None, *, block: bool) -> str:
    base_reason = reason or "loop detected"
    alt = suggestion or "Try a different tool or target."
    if block:
        return f"cairn guard: {base_reason}. Denied to break the loop. Next step: {alt}"
    return f"cairn guard: {base_reason}. {alt}"


def handle_pretooluse(stdin_data: str, *, mode: str = "advisory") -> dict[str, Any] | None:
    """Analyze session tail; return hook JSON or None (healthy / fail-open)."""
    try:
        stripped = stdin_data.strip()
        if not stripped:
            return None
        data = json.loads(stripped)
        if not isinstance(data, dict):
            return None
    except (json.JSONDecodeError, TypeError):
        return None

    session_id = data.get("session_id") or data.get("sessionId")
    cwd = data.get("cwd")
    tool_name = data.get("tool_name")
    if isinstance(tool_name, str) and tool_name == "apply_patch":
        # Codex reports file edits as apply_patch — already normalized in ledger events.
        pass

    if not cwd and not session_id:
        return None

    root: Path | None = None
    if cwd:
        try:
            root = resolve_git_root(Path(str(cwd))) or Path(str(cwd)).resolve()
        except OSError:
            return None
    if root is None:
        return None

    db_path = root / ".cairn" / "ledger.db"
    if not db_path.is_file():
        return None

    tail = int(get_guard_setting("tail_events", 30))
    allow_block = bool(get_guard_setting("allow_block", False))

    ledger = Ledger(db_path)
    try:
        run_id = resolve_guard_run(
            ledger.connection,
            str(session_id) if session_id else None,
            str(cwd) if cwd else None,
        )
        if run_id is None:
            return None
        events = load_tail_events(ledger.connection, run_id, tail)
        verdict = should_stop_verdict(events, tail=tail)
        if not verdict.get("should_stop"):
            return None

        reason = verdict.get("reason")
        suggestion = verdict.get("suggestion")
        if mode == "block" and allow_block:
            msg = _guard_message(reason, suggestion, block=True)
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": msg,
                }
            }

        msg = _guard_message(reason, suggestion, block=False)
        if mode == "block" and not allow_block:
            msg += " (block requested but guard.allow_block=false)"
        return {"continue": True, "systemMessage": msg}
    except Exception:
        return None
    finally:
        ledger.close()


def run_pretooluse_hook(*, mode: str = "advisory") -> int:
    """CLI entry: read stdin, emit JSON decision or nothing (fail-open)."""
    try:
        stdin_data = sys.stdin.read()
    except OSError:
        return 0
    try:
        result = handle_pretooluse(stdin_data, mode=mode)
        if result is not None:
            print(json.dumps(result), flush=True)
    except Exception:
        pass
    return 0


def run_stop_hook() -> int:
    """Enqueue post-session work; never block; always silent."""
    try:
        stripped = sys.stdin.read().strip()
        raw = json.loads(stripped) if stripped else {}
        data: dict[str, Any] = raw if isinstance(raw, dict) else {}
    except (OSError, json.JSONDecodeError):
        data = {}

    session_id = str(data.get("session_id") or data.get("sessionId") or "")
    cwd = str(data.get("cwd") or "")

    with contextlib.suppress(Exception):
        _enqueue_post_session(session_id, cwd)
    return 0


def _enqueue_post_session(session_id: str, cwd: str) -> None:
    cmd = [
        sys.executable,
        "-m",
        "cairn",
        "advanced",
        "post-session",
        "--session",
        session_id,
        "--cwd",
        cwd,
    ]
    subprocess.Popen(
        cmd,
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _merge_hooks(existing: dict[str, Any], block: dict[str, Any]) -> dict[str, Any]:
    """Non-destructive idempotent merge of Cairn hook entries."""
    merged = dict(existing)
    for event_name, entries in block.items():
        current = merged.get(event_name)
        if not isinstance(current, list):
            current = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            hooks = entry.get("hooks")
            if not isinstance(hooks, list):
                continue
            command = None
            for h in hooks:
                if isinstance(h, dict) and h.get("type") == "command":
                    command = h.get("command")
                    break
            if not command:
                continue
            duplicate = False
            for existing_entry in current:
                if not isinstance(existing_entry, dict):
                    continue
                eh = existing_entry.get("hooks")
                if not isinstance(eh, list):
                    continue
                for hook in eh:
                    if isinstance(hook, dict) and hook.get("command") == command:
                        duplicate = True
                        break
                if duplicate:
                    break
            if not duplicate:
                current.append(entry)
        merged[event_name] = current
    return merged


def install_claude_hooks(target: Path) -> None:
    data: dict[str, Any] = {}
    if target.is_file():
        data = json.loads(target.read_text(encoding="utf-8"))
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        hooks = {}
    data["hooks"] = _merge_hooks(hooks, _GUARD_HOOKS_BLOCK)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def install_codex_hooks(target: Path) -> None:
    data: dict[str, Any] = {}
    if target.is_file():
        data = json.loads(target.read_text(encoding="utf-8"))
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        hooks = {}
    data["hooks"] = _merge_hooks(hooks, _GUARD_HOOKS_BLOCK)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def guard_install(
    project_root: Path,
    *,
    agent: str = "claude",
    write: bool = False,
) -> int:
    root = project_root.resolve()
    if agent == "claude":
        target = root / ".claude" / "settings.json"
        if write:
            install_claude_hooks(target)
            print(f"Installed guard hooks → {target}")
        else:
            print(f"Merge this into {target}:")
            print(json.dumps({"hooks": _GUARD_HOOKS_BLOCK}, indent=2))
        return 0

    if agent == "codex":
        target = root / ".codex" / "hooks.json"
        if write:
            install_codex_hooks(target)
            print(f"Installed guard hooks → {target}")
        else:
            print(f"Merge this into {target}:")
            print(json.dumps({"hooks": _GUARD_HOOKS_BLOCK}, indent=2))
        return 0

    if agent == "both":
        rc = guard_install(root, agent="claude", write=write)
        rc |= guard_install(root, agent="codex", write=write)
        return rc

    print(f"Unknown agent: {agent!r} (use claude, codex, or both)")
    return 1


def run_post_session(*, session_id: str, cwd: str) -> int:
    """Re-ingest one session and compute diagnostics (hidden advanced subcommand)."""
    from cairn.diagnose.engine import backfill_diagnostics
    from cairn.ingest.backfill import backfill_run
    from cairn.ingest.ingest import run_ingest
    from cairn.ingest.writer import CaptureWriter
    from cairn.render.narrative import session_narrative

    if not cwd:
        return 0
    try:
        root = resolve_git_root(Path(cwd)) or Path(cwd).resolve()
    except OSError:
        return 0

    transcript = _transcript_from_session(session_id, cwd)
    if transcript is not None and transcript.is_file():
        _ingest_transcript_file(root, transcript)
    else:
        run_ingest(root, source="all")

    db_path = root / ".cairn" / "ledger.db"
    if not db_path.is_file():
        return 0

    ledger = Ledger(db_path)
    try:
        run_id = resolve_guard_run(ledger.connection, session_id or None, cwd or None)
    finally:
        ledger.close()

    if run_id is None:
        return 0

    writer = CaptureWriter(root)
    try:
        backfill_run(writer, run_id)
        backfill_diagnostics(writer, run_id)
        diag_row = writer.connection.execute(
            "SELECT * FROM diagnostics WHERE run_id = ?", (run_id,)
        ).fetchone()
        run_row = writer.connection.execute(
            "SELECT * FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        if diag_row is not None and run_row is not None:
            from cairn.metrics.normalized import cost_vs_expected

            normalized = cost_vs_expected(writer.connection, dict(run_row))
            narrative = session_narrative(dict(diag_row), normalized)
            _maybe_sentry_session_verdict(root, run_id, narrative)
    finally:
        writer.close()
    return 0


def _transcript_from_session(session_id: str, cwd: str) -> Path | None:
    """Best-effort transcript path for Claude/Codex session ids."""
    if not session_id:
        return None
    slug = Path(cwd).resolve().as_posix().replace("/", "-")
    claude_dir = Path.home() / ".claude" / "projects" / slug
    if claude_dir.is_dir():
        for path in sorted(claude_dir.glob("*.jsonl"), reverse=True):
            if session_id in path.name or path.stem == session_id:
                return path
    codex_root = Path.home() / ".codex" / "sessions"
    if codex_root.is_dir():
        for path in sorted(codex_root.rglob("*.jsonl"), reverse=True):
            if session_id in path.name:
                return path
    return None


def _ingest_transcript_file(root: Path, path: Path) -> None:
    from cairn.ingest.parsers.claude_code import parse_jsonl_file
    from cairn.ingest.parsers.codex import _is_codex_rollout, parse_rollout_file
    from cairn.ingest.writer import CaptureWriter

    writer = CaptureWriter(root)
    try:
        if _is_codex_rollout(path):
            codex_parsed = parse_rollout_file(path, repo_root=root)
            if codex_parsed is not None:
                writer.ingest_codex_session(codex_parsed)
        else:
            claude_parsed = parse_jsonl_file(path, repo_root=root)
            if claude_parsed is not None:
                writer.ingest_claude_session(claude_parsed)
    finally:
        writer.close()


def _maybe_sentry_session_verdict(root: Path, run_id: str, message: str | None) -> None:
    import importlib

    try:
        sentry = importlib.import_module("cairn.live.sentry")
    except ImportError:
        return
    if not getattr(sentry, "is_enabled", lambda: False)():
        return
    push = getattr(sentry, "push_session_verdict", None)
    if push is None:
        return
    with contextlib.suppress(Exception):
        push(root, run_id=run_id, kind="session_verdict", message=message or "")
