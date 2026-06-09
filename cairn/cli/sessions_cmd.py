"""cairn sessions — list and replay captured sessions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cairn.agents.replay import replay_session
from cairn.ingest.project_paths import resolve_git_root
from cairn.ingest.writer import CaptureWriter, SessionSummary


def run(args: argparse.Namespace) -> int:
    command = getattr(args, "sessions_command", None) or "list"
    if command == "replay":
        return run_replay(args)
    return run_list(args)


def run_list(args: argparse.Namespace) -> int:
    project = args.project.resolve()
    root = resolve_git_root(project) or project
    db_path = root / ".cairn" / "ledger.db"
    if not db_path.is_file():
        print("No captured sessions yet.")
        return 0

    writer = CaptureWriter(root)
    try:
        sessions = writer.list_sessions(limit=args.limit, source=args.source)
    finally:
        writer.close()

    if not sessions:
        print("No captured sessions yet.")
        return 0

    if args.json:
        print(json.dumps([_session_dict(s) for s in sessions], indent=2))
        return 0

    print(f"{'SESSION ID':<38} {'SOURCE':<12} {'EVENTS':>6}  STARTED")
    print("-" * 80)
    for s in sessions:
        print(
            f"{s.external_id:<38} {s.source:<12} {s.event_count:>6}  {s.started_at}"
        )
    return 0


def run_replay(args: argparse.Namespace) -> int:
    project = args.project.resolve()
    root = resolve_git_root(project) or project
    output = getattr(args, "output", None)
    out_path = Path(output) if output is not None else None
    try:
        index = replay_session(root, args.session_id, output=out_path)
    except KeyError as exc:
        print(str(exc))
        return 1
    print(f"Replay bundle: {index}")
    return 0


def _session_dict(session: SessionSummary) -> dict[str, object]:
    return {
        "session_id": session.external_id,
        "run_id": session.run_id,
        "source": session.source,
        "cwd": session.cwd,
        "git_branch": session.git_branch,
        "git_commit": session.git_commit,
        "started_at": session.started_at,
        "ended_at": session.ended_at,
        "status": session.status,
        "event_count": session.event_count,
        "total_input_tokens": session.total_input_tokens,
        "total_output_tokens": session.total_output_tokens,
        "total_cost": session.total_cost,
    }
