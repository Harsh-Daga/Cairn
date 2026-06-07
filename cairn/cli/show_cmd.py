"""cairn show — session summary or full trajectory."""

from __future__ import annotations

import argparse
import json

from cairn.ingest.project_paths import resolve_git_root
from cairn.ingest.writer import CaptureWriter, SessionSummary


def run(args: argparse.Namespace) -> int:
    project = args.project.resolve()
    root = resolve_git_root(project) or project
    db_path = root / ".cairn" / "ledger.db"
    if not db_path.is_file():
        print(f"session not found: {args.session_id}")
        return 1

    writer = CaptureWriter(root)
    try:
        summary = writer.load_session_by_external_id(args.session_id)
        if summary is None:
            print(f"session not found: {args.session_id}")
            return 1
        if args.json:
            trajectory = writer.load_trajectory(args.session_id)
            if trajectory is not None:
                print(json.dumps(trajectory, indent=2))
            else:
                events = writer.load_events(summary.run_id)
                print(
                    json.dumps(
                        {
                            "session": _summary_dict(summary),
                            "events": events,
                        },
                        indent=2,
                    )
                )
            return 0

        print(f"Session: {summary.external_id}")
        print(f"Source:  {summary.source}")
        print(f"Status:  {summary.status}")
        print(f"Events:  {summary.event_count}")
        print(f"Started: {summary.started_at}")
        if summary.ended_at:
            print(f"Ended:   {summary.ended_at}")
        if summary.cwd:
            print(f"CWD:     {summary.cwd}")
        if summary.git_branch:
            print(f"Branch:  {summary.git_branch}")
        if summary.git_commit:
            print(f"Commit:  {summary.git_commit[:12]}")
        print(
            f"Tokens:  {summary.total_input_tokens} in / "
            f"{summary.total_output_tokens} out"
        )
    finally:
        writer.close()
    return 0


def _summary_dict(summary: SessionSummary) -> dict[str, object]:
    return {
        "session_id": summary.external_id,
        "run_id": summary.run_id,
        "source": summary.source,
        "cwd": summary.cwd,
        "git_branch": summary.git_branch,
        "git_commit": summary.git_commit,
        "started_at": summary.started_at,
        "ended_at": summary.ended_at,
        "status": summary.status,
        "event_count": summary.event_count,
    }
