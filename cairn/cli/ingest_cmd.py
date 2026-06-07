"""cairn ingest — batch-import agent transcripts (§10.1)."""

from __future__ import annotations

import argparse
import json

from cairn.ingest.ingest import run_ingest
from cairn.ingest.project_paths import parse_since, resolve_git_root


def run(args: argparse.Namespace) -> int:
    project = args.project.resolve()
    root = resolve_git_root(project) or project
    since = parse_since(args.since) if args.since else None
    claude_dir = args.claude_project_dir.resolve() if args.claude_project_dir else None
    cursor_dir = args.cursor_workspace.resolve() if args.cursor_workspace else None

    try:
        reports = run_ingest(
            root,
            source=args.source,
            since=since,
            claude_project_dir=claude_dir,
            cursor_workspace=cursor_dir,
        )
    except ValueError as exc:
        print(f"error: {exc}")
        return 1

    if args.json:
        payload = [
            {
                "source": r.source,
                "scanned": r.scanned,
                "inserted": r.inserted,
                "skipped": r.skipped,
            }
            for r in reports
        ]
        print(json.dumps(payload, indent=2))
        return 0

    for report in reports:
        print(
            f"{report.source}: scanned {report.scanned}, "
            f"inserted {report.inserted}, skipped {report.skipped}"
        )
    return 0
