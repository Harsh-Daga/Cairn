"""cairn diff — compare capture sessions."""

from __future__ import annotations

import argparse
import json

from cairn.ingest.project_paths import resolve_git_root
from cairn.snapshot.engine import diff_sessions


def run(args: argparse.Namespace) -> int:
    project = args.project.resolve()
    root = resolve_git_root(project) or project
    try:
        diff = diff_sessions(root, args.session_a, args.session_b)
    except FileNotFoundError as exc:
        print(str(exc))
        return 1

    if args.json:
        print(json.dumps(diff, indent=2, sort_keys=True))
        return 0

    print(f"Session A: {diff['session_a']} ({diff['event_count_a']} events, {diff['status_a']})")
    print(f"Session B: {diff['session_b']} ({diff['event_count_b']} events, {diff['status_b']})")
    if diff["tools_only_in_a"]:
        print(f"  tools only in A: {', '.join(diff['tools_only_in_a'])}")
    if diff["tools_only_in_b"]:
        print(f"  tools only in B: {', '.join(diff['tools_only_in_b'])}")
    print(f"  shared tools: {', '.join(diff['shared_tools']) or '-'}")
    return 0
