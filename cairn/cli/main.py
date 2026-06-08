"""Cairn CLI entry point (§10)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from cairn import __version__
from cairn.cli import (
    build_cmd,
    context_cmd,
    doctor_cmd,
    graph_cmd,
    hook_cmd,
    ingest_cmd,
    init_cmd,
    plan_cmd,
    render_cmd,
    runs_cmd,
    sessions_cmd,
    show_cmd,
    status_cmd,
    validate_cmd,
    watch_cmd,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cairn", description="Build system for LLM work")
    parser.add_argument("--version", action="version", version=f"cairn {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    init_p = sub.add_parser("init", help="Scaffold a new project")
    init_p.add_argument("dir", nargs="?", default=".", type=Path)
    init_p.set_defaults(func=init_cmd.run)

    validate_p = sub.add_parser("validate", help="Parse and validate project (no tokens)")
    validate_p.add_argument("project", nargs="?", default=".", type=Path)
    validate_p.set_defaults(func=validate_cmd.run)

    doctor_p = sub.add_parser("doctor", help="Preflight environment checks (no tokens)")
    doctor_p.add_argument("project", nargs="?", default=".", type=Path)
    doctor_p.set_defaults(func=doctor_cmd.run)

    status_p = sub.add_parser("status", help="Show per-node cache state and cost estimate")
    status_p.add_argument("project", nargs="?", default=".", type=Path)
    status_p.set_defaults(func=status_cmd.run)

    plan_p = sub.add_parser("plan", help="Show execution plan with rendered prompts")
    plan_p.add_argument("project", nargs="?", default=".", type=Path)
    plan_p.set_defaults(func=plan_cmd.run)

    build_p = sub.add_parser("build", help="Execute the work list")
    build_p.add_argument("project", nargs="?", default=".", type=Path)
    build_p.add_argument("--dry-run", action="store_true")
    build_p.add_argument("--refresh", action="append", default=[], metavar="SELECTOR")
    build_p.add_argument("--concurrency", type=int, default=4)
    build_p.add_argument("--max-cost", type=float, default=None)
    build_p.add_argument("--yes", "-y", action="store_true")
    build_p.add_argument(
        "--provider-mode",
        choices=["recorded", "live"],
        default="recorded",
        help="recorded=replay fixtures (default for CI); live=real APIs",
    )
    build_p.set_defaults(func=build_cmd.run)

    render_p = sub.add_parser("render", help="Render provenance bundle (no tokens)")
    render_p.add_argument("project", nargs="?", default=".", type=Path)
    render_p.add_argument("--run", metavar="RUN_ID", default=None)
    render_p.add_argument("--session", metavar="SESSION_ID", default=None)
    render_p.add_argument("-o", "--output", type=Path, default=None)
    render_p.add_argument("--zip", action="store_true")
    render_p.add_argument(
        "--split",
        action="store_true",
        help="write data/cairn-data.json externally (requires HTTP server; not file://)",
    )
    render_p.set_defaults(func=render_cmd.run)

    runs_p = sub.add_parser("runs", help="List recent runs (no tokens)")
    runs_p.add_argument("project", nargs="?", default=".", type=Path)
    runs_p.add_argument("--limit", type=int, default=20)
    runs_p.set_defaults(func=runs_cmd.run)

    ingest_p = sub.add_parser("ingest", help="Batch-import agent transcripts")
    ingest_p.add_argument("project", nargs="?", default=".", type=Path)
    ingest_p.add_argument("--since", default=None, metavar="DURATION", help="e.g. 7d, 24h")
    ingest_p.add_argument(
        "--source",
        default="claude-code",
        choices=["claude-code", "codex", "cursor", "hermes", "all"],
    )
    ingest_p.add_argument("--claude-project-dir", type=Path, default=None)
    ingest_p.add_argument("--cursor-workspace", type=Path, default=None)
    ingest_p.add_argument("--json", action="store_true")
    ingest_p.set_defaults(func=ingest_cmd.run)

    graph_p = sub.add_parser("graph", help="Export capture session graph")
    graph_p.add_argument("session_id")
    graph_p.add_argument("project", nargs="?", default=".", type=Path)
    graph_p.add_argument("--format", choices=["json", "dot"], default="json")
    graph_p.set_defaults(func=graph_cmd.run)

    sessions_p = sub.add_parser("sessions", help="List captured sessions")
    sessions_p.add_argument("project", nargs="?", default=".", type=Path)
    sessions_p.add_argument("--limit", type=int, default=20)
    sessions_p.add_argument("--source", default=None)
    sessions_p.add_argument("--json", action="store_true")
    sessions_p.set_defaults(func=sessions_cmd.run)

    show_p = sub.add_parser("show", help="Show session summary or trajectory")
    show_p.add_argument("session_id")
    show_p.add_argument("project", nargs="?", default=".", type=Path)
    show_p.add_argument("--json", action="store_true")
    show_p.set_defaults(func=show_cmd.run)

    hook_p = sub.add_parser("hook", help="Capture hook handler (internal)")
    hook_p.add_argument("--event", required=True)
    hook_p.add_argument(
        "--source",
        required=True,
        choices=["claude-code", "codex"],
    )
    hook_p.set_defaults(func=hook_cmd.run)

    watch_p = sub.add_parser("watch", help="Install capture hooks")
    watch_sub = watch_p.add_subparsers(dest="watch_command", required=True)
    watch_install = watch_sub.add_parser("install", help="Install hooks")
    watch_install.add_argument("project", nargs="?", default=".", type=Path)
    watch_install.add_argument("--source", default="all")
    watch_install.set_defaults(func=watch_cmd.run)
    watch_uninstall = watch_sub.add_parser("uninstall", help="Uninstall hooks")
    watch_uninstall.add_argument("project", nargs="?", default=".", type=Path)
    watch_uninstall.set_defaults(func=watch_cmd.run)
    watch_status_p = watch_sub.add_parser("status", help="Show hook install status")
    watch_status_p.add_argument("project", nargs="?", default=".", type=Path)
    watch_status_p.set_defaults(func=watch_cmd.run)

    context_p = sub.add_parser("context", help="Project context assets")
    context_sub = context_p.add_subparsers(dest="context_command", required=True)
    context_scan = context_sub.add_parser("scan", help="Scan and index context files")
    context_scan.add_argument("project", nargs="?", default=".", type=Path)
    context_scan.add_argument("--json", action="store_true")
    context_scan.set_defaults(func=context_cmd.run)
    context_list = context_sub.add_parser("list", help="List indexed context assets")
    context_list.add_argument("project", nargs="?", default=".", type=Path)
    context_list.add_argument("--json", action="store_true")
    context_list.set_defaults(func=context_cmd.run)
    context_show = context_sub.add_parser("show", help="Show one context asset")
    context_show.add_argument("selector")
    context_show.add_argument("project", nargs="?", default=".", type=Path)
    context_show.add_argument("--json", action="store_true")
    context_show.set_defaults(func=context_cmd.run)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
