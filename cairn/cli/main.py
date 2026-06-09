"""Cairn CLI entry point (§10)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from cairn import __version__
from cairn.cli import (
    artifact_cmd,
    build_cmd,
    collab_cmd,
    context_cmd,
    diff_cmd,
    doctor_cmd,
    graph_cmd,
    hook_cmd,
    ingest_cmd,
    init_cmd,
    live_cmd,
    plan_cmd,
    prompt_cmd,
    report_cmd,
    render_cmd,
    runs_cmd,
    sessions_cmd,
    show_cmd,
    snapshot_cmd,
    status_cmd,
    validate_cmd,
    watch_cmd,
    workflow_cmd,
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

    report_p = sub.add_parser("report", help="Unified observability report (JSON)")
    report_p.add_argument("project", nargs="?", default=".", type=Path)
    report_p.add_argument("--session", metavar="SESSION_ID", default=None)
    report_p.add_argument("--run", metavar="RUN_ID", default=None)
    report_p.add_argument("--json", action="store_true")
    report_p.set_defaults(func=report_cmd.run)

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
        choices=[
            "claude-code",
            "codex",
            "cursor",
            "hermes",
            "aider",
            "openhands",
            "goose",
            "all",
        ],
    )
    ingest_p.add_argument("--claude-project-dir", type=Path, default=None)
    ingest_p.add_argument("--cursor-workspace", type=Path, default=None)
    ingest_p.add_argument("--json", action="store_true")
    ingest_p.set_defaults(func=ingest_cmd.run)

    graph_p = sub.add_parser("graph", help="Export capture session graph")
    graph_p.add_argument("session_id")
    graph_p.add_argument("project", nargs="?", default=".", type=Path)
    graph_p.add_argument("--format", choices=["json", "dot"], default="json")
    graph_p.add_argument(
        "--kind",
        choices=["execution", "artifact", "dependency"],
        default="execution",
        help="execution=session events; artifact=file outputs; dependency=pipeline steps",
    )
    graph_p.set_defaults(func=graph_cmd.run)

    sessions_p = sub.add_parser("sessions", help="Captured sessions")
    sessions_sub = sessions_p.add_subparsers(dest="sessions_command")
    sessions_list = sessions_sub.add_parser("list", help="List captured sessions")
    sessions_list.add_argument("project", nargs="?", default=".", type=Path)
    sessions_list.add_argument("--limit", type=int, default=20)
    sessions_list.add_argument("--source", default=None)
    sessions_list.add_argument("--json", action="store_true")
    sessions_list.set_defaults(func=sessions_cmd.run)
    sessions_replay = sessions_sub.add_parser("replay", help="Replay session to bundle")
    sessions_replay.add_argument("session_id")
    sessions_replay.add_argument("project", nargs="?", default=".", type=Path)
    sessions_replay.add_argument("-o", "--output", type=Path, default=None)
    sessions_replay.set_defaults(func=sessions_cmd.run)
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

    prompt_p = sub.add_parser("prompt", help="Prompt library and versions")
    prompt_sub = prompt_p.add_subparsers(dest="prompt_command", required=True)
    prompt_sync = prompt_sub.add_parser("sync", help="Register prompt versions from prompts/")
    prompt_sync.add_argument("project", nargs="?", default=".", type=Path)
    prompt_sync.add_argument("--json", action="store_true")
    prompt_sync.set_defaults(func=prompt_cmd.run)
    prompt_list = prompt_sub.add_parser("list", help="List registered prompts")
    prompt_list.add_argument("project", nargs="?", default=".", type=Path)
    prompt_list.add_argument("--json", action="store_true")
    prompt_list.set_defaults(func=prompt_cmd.run)
    prompt_show = prompt_sub.add_parser("show", help="Show a prompt version")
    prompt_show.add_argument("ref")
    prompt_show.add_argument("project", nargs="?", default=".", type=Path)
    prompt_show.add_argument("--json", action="store_true")
    prompt_show.set_defaults(func=prompt_cmd.run)
    prompt_diff = prompt_sub.add_parser("diff", help="Diff two prompt versions")
    prompt_diff.add_argument("left")
    prompt_diff.add_argument("right")
    prompt_diff.add_argument("project", nargs="?", default=".", type=Path)
    prompt_diff.set_defaults(func=prompt_cmd.run)

    diff_p = sub.add_parser("diff", help="Compare two capture sessions")
    diff_p.add_argument("session_a")
    diff_p.add_argument("session_b")
    diff_p.add_argument("project", nargs="?", default=".", type=Path)
    diff_p.add_argument("--json", action="store_true")
    diff_p.set_defaults(func=diff_cmd.run)

    snapshot_p = sub.add_parser("snapshot", help="Point-in-time project snapshots")
    snapshot_sub = snapshot_p.add_subparsers(dest="snapshot_command", required=True)
    snapshot_create = snapshot_sub.add_parser("create", help="Create a snapshot")
    snapshot_create.add_argument("project", nargs="?", default=".", type=Path)
    snapshot_create.add_argument("--label", default=None)
    snapshot_create.add_argument("--json", action="store_true")
    snapshot_create.set_defaults(func=snapshot_cmd.run)
    snapshot_list = snapshot_sub.add_parser("list", help="List snapshots")
    snapshot_list.add_argument("project", nargs="?", default=".", type=Path)
    snapshot_list.add_argument("--json", action="store_true")
    snapshot_list.set_defaults(func=snapshot_cmd.run)
    snapshot_diff = snapshot_sub.add_parser("diff", help="Diff two snapshots")
    snapshot_diff.add_argument("left")
    snapshot_diff.add_argument("right")
    snapshot_diff.add_argument("project", nargs="?", default=".", type=Path)
    snapshot_diff.add_argument("--json", action="store_true")
    snapshot_diff.set_defaults(func=snapshot_cmd.run)
    snapshot_restore = snapshot_sub.add_parser("restore", help="Restore a snapshot")
    snapshot_restore.add_argument("snapshot_id")
    snapshot_restore.add_argument("project", nargs="?", default=".", type=Path)
    snapshot_restore.add_argument("--json", action="store_true")
    snapshot_restore.set_defaults(func=snapshot_cmd.run)

    collab_p = sub.add_parser("collab", help="File-based collaboration sync")
    collab_sub = collab_p.add_subparsers(dest="collab_command", required=True)
    collab_export = collab_sub.add_parser("export", help="Export ledger snapshot for sync")
    collab_export.add_argument("dest", type=Path)
    collab_export.add_argument("project", nargs="?", default=".", type=Path)
    collab_export.add_argument("--label", default=None)
    collab_export.add_argument("--json", action="store_true")
    collab_export.set_defaults(func=collab_cmd.run)
    collab_import = collab_sub.add_parser("import", help="Import a remote sync bundle")
    collab_import.add_argument("source", type=Path)
    collab_import.add_argument("project", nargs="?", default=".", type=Path)
    collab_import.add_argument("--json", action="store_true")
    collab_import.set_defaults(func=collab_cmd.run)
    collab_status = collab_sub.add_parser("status", help="Show local sync cursor")
    collab_status.add_argument("project", nargs="?", default=".", type=Path)
    collab_status.add_argument("--json", action="store_true")
    collab_status.set_defaults(func=collab_cmd.run)

    live_p = sub.add_parser("live", help="Live capture workspace")
    live_sub = live_p.add_subparsers(dest="live_command", required=True)
    live_serve = live_sub.add_parser("serve", help="Serve live session UI over HTTP + SSE")
    live_serve.add_argument("project", nargs="?", default=".", type=Path)
    live_serve.add_argument("--host", default="127.0.0.1")
    live_serve.add_argument("--port", type=int, default=8787)
    live_serve.add_argument("--session", metavar="SESSION_ID", default=None)
    live_serve.set_defaults(func=live_cmd.run)

    workflow_p = sub.add_parser("workflow", help="Workflow definitions and execution")
    workflow_sub = workflow_p.add_subparsers(dest="workflow_command", required=True)
    workflow_list = workflow_sub.add_parser("list", help="List workflows")
    workflow_list.add_argument("project", nargs="?", default=".", type=Path)
    workflow_list.add_argument("--json", action="store_true")
    workflow_list.set_defaults(func=workflow_cmd.run)
    workflow_validate = workflow_sub.add_parser("validate", help="Validate a workflow")
    workflow_validate.add_argument("ref", nargs="?", default=None)
    workflow_validate.add_argument("project", nargs="?", default=".", type=Path)
    workflow_validate.add_argument("--json", action="store_true")
    workflow_validate.set_defaults(func=workflow_cmd.run)
    workflow_run = workflow_sub.add_parser("run", help="Execute a workflow")
    workflow_run.add_argument("ref", nargs="?", default=None)
    workflow_run.add_argument("project", nargs="?", default=".", type=Path)
    workflow_run.add_argument("--dry-run", action="store_true")
    workflow_run.add_argument("--yes", "-y", action="store_true")
    workflow_run.add_argument("--max-cost", type=float, default=None)
    workflow_run.add_argument(
        "--provider-mode",
        choices=["recorded", "live"],
        default="recorded",
    )
    workflow_run.add_argument("--json", action="store_true")
    workflow_run.set_defaults(func=workflow_cmd.run)
    workflow_history_p = workflow_sub.add_parser("history", help="List workflow runs")
    workflow_history_p.add_argument("project", nargs="?", default=".", type=Path)
    workflow_history_p.add_argument("--limit", type=int, default=20)
    workflow_history_p.add_argument("--json", action="store_true")
    workflow_history_p.set_defaults(func=workflow_cmd.run)

    artifact_p = sub.add_parser("artifact", help="Artifact registry and lineage")
    artifact_sub = artifact_p.add_subparsers(dest="artifact_command", required=True)
    artifact_list = artifact_sub.add_parser("list", help="List artifacts for a session")
    artifact_list.add_argument("session_id")
    artifact_list.add_argument("project", nargs="?", default=".", type=Path)
    artifact_list.add_argument("--json", action="store_true")
    artifact_list.set_defaults(func=artifact_cmd.run)
    artifact_show = artifact_sub.add_parser("show", help="Show one artifact")
    artifact_show.add_argument("hash")
    artifact_show.add_argument("project", nargs="?", default=".", type=Path)
    artifact_show.add_argument("--json", action="store_true")
    artifact_show.set_defaults(func=artifact_cmd.run)
    artifact_lineage = artifact_sub.add_parser("lineage", help="Artifact lineage graph")
    artifact_lineage.add_argument("hash")
    artifact_lineage.add_argument("project", nargs="?", default=".", type=Path)
    artifact_lineage.add_argument("--json", action="store_true")
    artifact_lineage.set_defaults(func=artifact_cmd.run)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
