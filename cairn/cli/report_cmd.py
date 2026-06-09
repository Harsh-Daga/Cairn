"""cairn report — unified observability report for sessions and runs."""

from __future__ import annotations

import argparse
import json

from cairn.ingest.project_paths import resolve_git_root
from cairn.report.engine import build_report
from cairn.report.schema import validate_report


def run(args: argparse.Namespace) -> int:
    project = args.project.resolve()
    root = resolve_git_root(project) or project

    if args.session and args.run:
        print("error: use either --session or --run, not both")
        return 1

    try:
        report = build_report(
            root,
            session_id=args.session,
            run_id=args.run,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc))
        return 1

    errors = validate_report(report)
    if errors:
        print("report validation failed:")
        for err in errors:
            print(f"  - {err}")
        return 1

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    summary = report["summary"]
    print(f"Report ({report['kind']})")
    print(f"  title:   {summary.get('title', '-')}")
    print(f"  status:  {summary.get('status', '-')}")
    print(f"  model:   {summary.get('model') or '-'}")
    if report["kind"] == "capture":
        print(f"  turns:   {summary.get('turn_count', 0)}")
        print(f"  events:  {summary.get('event_count', 0)}")
    else:
        print(f"  nodes:   {summary.get('node_count', 0)}")
    print(f"  tools:   {len(report['tool_usage'])}")
    print(f"  artifacts: {len(report['artifacts'])}")
    repro = report["reproducibility"]
    print(f"  run_id:  {repro.get('run_id') or '-'}")
    if repro.get("git_commit"):
        print(f"  commit:  {repro['git_commit'][:12]}")
    return 0
