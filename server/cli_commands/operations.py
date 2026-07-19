"""Operational and observability CLI commands."""

from __future__ import annotations

import json
import signal
import sqlite3
import subprocess
import sys
import time
import webbrowser
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlencode

import typer
import uvicorn

import server.cli as cli
from server.analyze.git_privacy import assess_git_privacy, report_as_dict
from server.api.show import render_waterfall
from server.app import create_app
from server.config import Settings
from server.doctor import print_doctor
from server.ingest.pricing import pricing_status
from server.ingest.storage import storage_status
from server.store.lifecycle import lifecycle_status
from server.update import render_command, upgrade_command
from server.util.egress import egress_status
from server.util.resources import build_resource_report

STATS_JSON_SCHEMA = "cairn.stats.v1"
GUARD_JSON_SCHEMA = "cairn.guard.v1"
TOP_JSON_SCHEMA = "cairn.top.v1"
WHY_JSON_SCHEMA = "cairn.why.v1"


def _cli_json(schema: str, payload: dict[str, Any]) -> str:
    body = {"schema": schema, "generated_at": datetime.now(UTC).isoformat(), **payload}
    return json.dumps(body, indent=2, sort_keys=True)


@cli.app.command()
def stats(
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
    json_out: Annotated[bool, typer.Option("--json", help="Emit JSON payload")] = False,
) -> None:
    """Show current-month budget burn, projections, and spend shares."""
    from server.api.payloads import build_budget_analytics
    from server.configuration import load_config

    action_ctx = cli._make_ctx(workspace)
    budgets = load_config(action_ctx.workspace_root).budgets
    payload = build_budget_analytics(
        action_ctx.db.reader,
        workspace_id=action_ctx.workspace_id,
        monthly_limit_usd=budgets.monthly_usd,
        weekly_limit_usd=budgets.weekly_usd,
        daily_limit_usd=budgets.daily_usd,
        timezone="UTC",
    )
    if json_out:
        typer.echo(_cli_json(STATS_JSON_SCHEMA, payload.model_dump(mode="json")))
        return
    typer.echo(cli._render_budget_stats(payload))


@cli.app.command()
def guard(
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
    days: Annotated[int, typer.Option("--days", min=1, max=365)] = 30,
    json_out: Annotated[bool, typer.Option("--json", help="Emit JSON payload")] = False,
) -> None:
    """List instruction-file Guard events and non-causal associations."""
    from server.api.payloads import build_guard_analytics

    action_ctx = cli._make_ctx(workspace)
    payload = build_guard_analytics(
        action_ctx.db.reader,
        workspace_id=action_ctx.workspace_id,
        workspace_root=action_ctx.workspace_root,
        days=days,
    )
    if json_out:
        typer.echo(_cli_json(GUARD_JSON_SCHEMA, payload.model_dump(mode="json")))
        return
    typer.echo(payload.ledger.conclusion)
    typer.echo(payload.ledger.limitation)
    for event in payload.events[:20]:
        assoc = event.association
        assoc_bit = (
            f" · {assoc.language} {assoc.verdict} n={assoc.pre_n}/{assoc.post_n}"
            if assoc is not None
            else ""
        )
        typer.echo(f"{event.occurred_at}  {event.event_kind:14}  {event.path_rel}{assoc_bit}")
    if not payload.events:
        typer.echo("No Guard events in range.")


@cli.app.command()
def top(
    once: Annotated[
        bool,
        typer.Option("--once", help="Print one snapshot and exit (default on non-TTY)"),
    ] = False,
    interval: Annotated[
        float,
        typer.Option("--interval", min=0.5, max=60.0, help="Refresh seconds when looping"),
    ] = 2.0,
    limit: Annotated[int, typer.Option("--limit", min=1, max=100)] = 15,
    days: Annotated[int, typer.Option("--days", min=1, max=365)] = 30,
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
    json_out: Annotated[bool, typer.Option("--json", help="Emit JSON payload")] = False,
) -> None:
    """Show recent sessions by spend (refreshes on a TTY until Ctrl-C)."""
    action_ctx = cli._make_ctx(workspace)
    single = once or json_out or not sys.stdout.isatty()
    stop = False

    def _on_signal(_signum: int, _frame: object) -> None:
        nonlocal stop
        stop = True

    previous_handler = signal.signal(signal.SIGINT, _on_signal)
    try:
        while not stop:
            rows = _top_rows(
                action_ctx.db.reader,
                workspace_id=action_ctx.workspace_id,
                days=days,
                limit=limit,
            )
            if json_out:
                typer.echo(
                    _cli_json(
                        TOP_JSON_SCHEMA,
                        {"days": days, "limit": limit, "rows": rows},
                    )
                )
                return
            text = _render_top_table(rows)
            if single:
                typer.echo(text)
                return
            typer.echo("\033[2J\033[H", nl=False)
            typer.echo(text)
            typer.echo(f"\nRefreshing every {interval:g}s · Ctrl-C to quit")
            deadline = time.monotonic() + interval
            while not stop and time.monotonic() < deadline:
                time.sleep(min(0.2, max(0.0, deadline - time.monotonic())))
    finally:
        signal.signal(signal.SIGINT, previous_handler)


@cli.app.command()
def receipt(
    trace_id: Annotated[str, typer.Argument(help="Trace/session id")],
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
    json_out: Annotated[bool, typer.Option("--json", help="Emit JSON payload")] = False,
    markdown: Annotated[
        bool,
        typer.Option("--markdown", help="Emit Markdown (default when not using --json)"),
    ] = False,
) -> None:
    """Print a deterministic verification receipt for a session."""
    from server.api.payloads import build_trace_receipt

    action_ctx = cli._make_ctx(workspace)
    payload = build_trace_receipt(action_ctx.db.reader, trace_id)
    if payload is None:
        typer.echo(f"Trace not found: {trace_id}", err=True)
        raise typer.Exit(code=1)
    if json_out:
        typer.echo(
            _cli_json(
                "cairn.receipt.v1",
                payload.model_dump(mode="json"),
            )
        )
        return
    typer.echo(payload.markdown or "")
    if markdown:
        return


@cli.app.command()
def handoff(
    trace_id: Annotated[str, typer.Argument(help="Trace/session id")],
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
    json_out: Annotated[bool, typer.Option("--json", help="Emit JSON payload")] = False,
) -> None:
    """Print an offline handoff capsule (fact / inference / recommendation)."""
    from server.api.payloads import build_trace_handoff

    action_ctx = cli._make_ctx(workspace)
    payload = build_trace_handoff(
        action_ctx.db.reader,
        trace_id,
        workspace_root=action_ctx.workspace_root,
    )
    if payload is None:
        typer.echo(f"Trace not found: {trace_id}", err=True)
        raise typer.Exit(code=1)
    if json_out:
        typer.echo(_cli_json("cairn.handoff.v1", payload.model_dump(mode="json")))
        return
    typer.echo(payload.markdown or "")


@cli.app.command()
def review(
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
    limit: Annotated[int, typer.Option("--limit", min=1, max=100)] = 20,
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """List highest-priority sessions for human review (advisory, not ranking people)."""
    from server.analyze.policy import evaluate_session_policy
    from server.analyze.verification import build_receipt_for_trace
    from server.configuration import load_config
    from server.store.repos.outcomes import OutcomeRepo
    from server.store.repos.spans import SpanRepo

    action_ctx = cli._make_ctx(workspace)
    policy = load_config(action_ctx.workspace_root).policy
    rows = action_ctx.db.reader.execute(
        """
        SELECT trace_id, title, started_at, cost, status
        FROM traces WHERE workspace_id = ?
        ORDER BY started_at DESC LIMIT ?
        """,
        (action_ctx.workspace_id, max(limit * 3, 60)),
    ).fetchall()
    items: list[dict[str, Any]] = []
    for row in rows:
        trace_id = str(row["trace_id"])
        receipt = build_receipt_for_trace(action_ctx.db.reader, trace_id)
        spans = SpanRepo.list_by_trace(action_ctx.db.reader, trace_id)
        outcome = OutcomeRepo.get(action_ctx.db.reader, trace_id)
        risk = evaluate_session_policy(spans=spans, outcome=outcome, policy=policy)
        debt = float((receipt or {}).get("debt", {}).get("score") or 0.0)
        review_risk = str(risk.get("review_risk") or "none")
        priority = (
            3
            if review_risk == "high"
            else 2
            if debt >= 0.4 or review_risk == "medium"
            else 1
            if debt > 0
            else 0
        )
        if priority == 0:
            continue
        why = []
        if review_risk == "high":
            why.append("high review risk from advisory policy")
        if debt > 0:
            why.append(f"verification debt {debt:.2f}")
        items.append(
            {
                "trace_id": trace_id,
                "title": row["title"],
                "started_at": row["started_at"],
                "priority": priority,
                "review_risk": review_risk,
                "debt_score": debt,
                "why": why,
                "inspect_first": (why[0] if why else "Open session receipt"),
                "ranking_forbidden": True,
            }
        )
    items.sort(key=lambda item: (-int(item["priority"]), -float(item["debt_score"])))
    items = items[:limit]
    payload = {
        "count": len(items),
        "items": items,
        "limitation": (
            "Advisory review queue for the individual operator. "
            "Not for employee ranking or performance scoring."
        ),
    }
    if json_out:
        typer.echo(_cli_json("cairn.review.v1", payload))
        return
    if not items:
        typer.echo("No high-priority review items in the recent window.")
        return
    for item in items:
        typer.echo(f"{item['trace_id']}  risk={item['review_risk']}  debt={item['debt_score']:.2f}")
        typer.echo(f"  Why     {'; '.join(item['why'])}")
        typer.echo(f"  Inspect {item['inspect_first']}")


verify_app = typer.Typer(
    name="verify",
    help="Verification helpers (preview only; does not execute checks).",
    no_args_is_help=True,
)
cli.app.add_typer(verify_app, name="verify")


@verify_app.command("next")
def verify_next(
    trace_id: Annotated[str, typer.Argument(help="Trace/session id")],
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Preview the smallest repository-grounded next check without executing it."""
    from server.mcp.evidence import next_evidence

    action_ctx = cli._make_ctx(workspace)
    payload = next_evidence(
        action_ctx.db.reader,
        action_ctx.workspace_root,
        action_ctx.workspace_id,
        {"trace_id": trace_id},
    )
    if payload.get("error"):
        typer.echo(str(payload.get("error")), err=True)
        raise typer.Exit(code=1)
    if json_out:
        typer.echo(_cli_json("cairn.verify.next.v1", payload))
        return
    check = payload["next_check"]
    typer.echo(f"Next     {check['text']}")
    typer.echo(f"Approval {check['approval_class']}")
    typer.echo(f"Effects  {', '.join(check['side_effects'])}")
    if check.get("suggested_command"):
        typer.echo(f"Command  {check['suggested_command']} (not executed)")
    typer.echo("Note     Preview only — Cairn does not run this check.")


@cli.app.command()
def resource(
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Show local Cairn disk inventory, soft budget, and descriptive growth forecast."""
    action_ctx = cli._make_ctx(workspace)
    payload = build_resource_report(
        action_ctx.db.reader,
        workspace_root=action_ctx.workspace_root,
        workspace_id=action_ctx.workspace_id,
    )
    if json_out:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return
    disk = payload["disk"]
    categories = disk["categories"]
    budget = payload["budget"]
    forecast = payload["forecast"]
    process = payload["process"]
    typer.echo(f"Cairn dir     {disk['cairn_dir']}")
    typer.echo(f"Total         {int(disk['total_bytes']):,} B")
    typer.echo(f"Database      {_fmt_opt_bytes(categories.get('database_bytes'))}")
    typer.echo(f"WAL           {_fmt_opt_bytes(categories.get('wal_bytes'))}")
    typer.echo(f"Exports       {_fmt_dir_bytes(categories.get('exports'))}")
    typer.echo(f"Backups       {_fmt_dir_bytes(categories.get('backups'))}")
    typer.echo(f"Regressions   {_fmt_dir_bytes(categories.get('regressions'))}")
    typer.echo(f"Budget        {budget['status']} — {budget['message']}")
    if forecast.get("estimated_bytes_per_day") and forecast.get("traces_ingested"):
        typer.echo(
            f"Forecast      ~{int(forecast['estimated_bytes_per_day']):,} B/day "
            f"(descriptive; {forecast['traces_ingested']} recent sessions)"
        )
    else:
        typer.echo("Forecast      insufficient recent ingest for a growth rate")
    rss = process.get("rss_bytes")
    typer.echo(f"Process RSS   {_fmt_opt_bytes(rss)}")
    typer.echo(payload["limitation"])


def _fmt_opt_bytes(value: Any) -> str:
    return "n/a" if value is None else f"{int(value):,} B"


def _fmt_dir_bytes(value: Any) -> str:
    if not isinstance(value, dict):
        return "n/a"
    if not value.get("present"):
        return "absent"
    return f"{int(value.get('bytes') or 0):,} B"


@cli.app.command()
def privacy(
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Show privacy posture for local Cairn data (modes and paths)."""
    action_ctx = cli._make_ctx(workspace)
    root = action_ctx.workspace_root / ".cairn"
    storage = storage_status(action_ctx.workspace_root)
    git_privacy = report_as_dict(assess_git_privacy(action_ctx.workspace_root))
    lifecycle = lifecycle_status(action_ctx.workspace_root)
    pricing = pricing_status(action_ctx.workspace_root)
    egress = egress_status(action_ctx.workspace_root)
    payload = {
        "workspace_root": str(action_ctx.workspace_root),
        "data_dir": str(root),
        "defaults": {
            "local_first": True,
            "no_cloud_by_default": True,
            "directory_mode_expected": "0700",
            "egress": "opt-in only (reflector/MCP provider calls)",
        },
        "storage": storage,
        "git": git_privacy,
        "lifecycle": lifecycle,
        "pricing": pricing,
        "egress": egress,
        "artifacts": {
            "regressions": (root / "regressions").is_dir(),
            "exports": (root / "exports").is_dir(),
            "mcp_events": (root / "mcp-events.jsonl").is_file(),
        },
        "limitation": (
            "Storage mode controls raw text_inline retention; strip via "
            "`cairn action storage_strip` or `lifecycle_cleanup`. Git exclude is local "
            "(.git/info/exclude) and requires approve=true. Destructive delete/restore "
            "needs [lifecycle].destructive_enabled. This report does not claim forensic wiping."
        ),
    }
    if json_out:
        typer.echo(_cli_json("cairn.privacy.v1", payload))
        return
    typer.echo("Local-first  yes")
    typer.echo("Cloud default  off")
    typer.echo(f"Data dir  {payload['data_dir']}")
    typer.echo(f"Storage mode  {storage['mode']} (max inline {storage['text_inline_max']})")
    typer.echo(f"Git privacy  {git_privacy['kind']} — {git_privacy['message']}")
    retain = lifecycle["default_retain_days"]
    destr = "enabled" if lifecycle["destructive_enabled"] else "warn-only"
    typer.echo(f"Lifecycle  retain {retain}d · destructive {destr}")
    integrity = lifecycle.get("integrity") or {}
    typer.echo(f"Integrity  {'ok' if integrity.get('ok') else integrity.get('detail', 'n/a')}")
    stale = "stale" if pricing.get("stale") else "fresh"
    typer.echo(
        f"Pricing  v{pricing.get('version')} · {stale} · "
        f"overrides={pricing.get('override_count')} (offline)"
    )
    typer.echo(
        f"Egress  {egress.get('entry_count', 0)} entries · "
        f"last={'none' if not egress.get('last') else egress['last'].get('destination_origin')}"
    )
    if storage.get("warning"):
        typer.echo(f"Warning  {storage['warning']}")
    typer.echo(payload["limitation"])


@cli.app.command()
def why(
    trace_id: Annotated[str, typer.Argument(help="Trace/session id")],
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
    json_out: Annotated[bool, typer.Option("--json", help="Emit JSON payload")] = False,
) -> None:
    """Print a deterministic postmortem for a session (diagnose localization, not causality)."""
    from server.analyze.postmortem import build_postmortem
    from server.store.repos.diagnostics import DiagnosticRepo
    from server.store.repos.outcomes import OutcomeRepo
    from server.store.repos.spans import SpanRepo
    from server.store.repos.traces import TraceRepo

    action_ctx = cli._make_ctx(workspace)
    trace = TraceRepo.get(action_ctx.db.reader, trace_id)
    if trace is None:
        typer.echo(f"Trace not found: {trace_id}", err=True)
        raise typer.Exit(code=1)
    spans = SpanRepo.list_by_trace(action_ctx.db.reader, trace_id)
    diagnostic = DiagnosticRepo.get(action_ctx.db.reader, trace_id)
    outcome = OutcomeRepo.get(action_ctx.db.reader, trace_id)
    postmortem = build_postmortem(
        trace=trace,
        spans=spans,
        diagnostic=diagnostic,
        outcome=outcome,
    )
    if postmortem is None:
        message = (
            "No postmortem available: no diagnose row, failure outcome, or error spans "
            "were recorded for this session."
        )
        if json_out:
            typer.echo(
                _cli_json(
                    WHY_JSON_SCHEMA,
                    {
                        "trace_id": trace_id,
                        "available": False,
                        "message": message,
                        "postmortem": None,
                    },
                )
            )
        else:
            typer.echo(message, err=True)
        raise typer.Exit(code=2)
    if json_out:
        typer.echo(
            _cli_json(
                WHY_JSON_SCHEMA,
                {
                    "trace_id": trace_id,
                    "available": True,
                    "message": None,
                    "postmortem": postmortem,
                },
            )
        )
        return
    typer.echo(str(postmortem.get("markdown") or ""))


def _top_rows(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    days: int,
    limit: int,
) -> list[dict[str, Any]]:
    from server.api.payloads import build_traces_list

    payload = build_traces_list(
        conn,
        workspace_id=workspace_id,
        days=days,
        limit=limit,
    )
    rows = sorted(
        payload.traces,
        key=lambda row: (float(row.cost or 0.0), int(row.span_count or 0)),
        reverse=True,
    )
    return [
        {
            "trace_id": row.trace_id,
            "source": row.source,
            "status": row.status,
            "cost": float(row.cost or 0.0),
            "cost_source": row.cost_source,
            "input_tokens": int(row.input_tokens or 0),
            "output_tokens": int(row.output_tokens or 0),
            "span_count": int(row.span_count or 0),
            "started_at": row.started_at,
            "title": row.title,
        }
        for row in rows
    ]


def _render_top_table(rows: list[dict[str, Any]]) -> str:
    lines = [
        f"{'trace_id':<28} {'source':<12} {'status':<10} {'cost':>8} {'tokens':>10} title",
        "-" * 90,
    ]
    if not rows:
        lines.append("(no sessions in range)")
        return "\n".join(lines)
    for row in rows:
        tokens = int(row["input_tokens"]) + int(row["output_tokens"])
        title = str(row["title"] or "")[:36]
        lines.append(
            f"{row['trace_id']:<28} {row['source']:<12} {row['status']:<10} "
            f"{float(row['cost']):>8.2f} {tokens:>10} {title}"
        )
    return "\n".join(lines)


@cli.app.command()
def recap(
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
    share: Annotated[bool, typer.Option("--share", help="Write a private PNG recap card")] = False,
    show_repo: Annotated[
        bool,
        typer.Option("--show-repo", help="Include the workspace name on a shared card"),
    ] = False,
    output: Annotated[Path | None, typer.Option("--output", help="PNG output path")] = None,
) -> None:
    """Show a one-screen weekly spend, waste, quality, and experiment recap."""
    from server.api.payloads import build_recap

    action_ctx = cli._make_ctx(workspace)
    if share:
        from datetime import UTC, datetime

        from server.recap_share import build_share_card_data, render_share_card
        from server.store.repos.workspaces import WorkspaceRepo

        workspace_row = WorkspaceRepo.get(action_ctx.db.reader, action_ctx.workspace_id)
        repo_name = workspace_row.name if show_repo and workspace_row is not None else None
        card = build_share_card_data(
            action_ctx.db.reader,
            workspace_id=action_ctx.workspace_id,
            repo_name=repo_name,
        )
        target = output or (
            action_ctx.workspace_root
            / ".cairn"
            / "recaps"
            / f"agent-wrapped-{datetime.now(UTC).date().isoformat()}.png"
        )
        png_path, _svg_path = render_share_card(card, target)
        typer.echo(str(png_path.resolve()))
        return
    payload = build_recap(action_ctx.db.reader, workspace_id=action_ctx.workspace_id)
    typer.echo(cli._render_recap(payload))


@cli.app.command()
def ui(
    host: Annotated[str | None, typer.Option("--host", help="Bind address")] = None,
    port: Annotated[int | None, typer.Option("--port", "-p", help="HTTP port")] = None,
    open_browser: Annotated[bool, typer.Option("--open/--no-open", help="Open browser")] = True,
    token: Annotated[str | None, typer.Option("--token", help="Auth token")] = None,
    workspace: Annotated[Path | None, typer.Option("--workspace", help="Workspace root")] = None,
) -> None:
    """Start the Cairn web UI server."""
    from server.util.runtime_state import register_server, unregister_server

    overrides: dict[str, Any] = {"workspace_root": workspace}
    if host is not None:
        overrides["host"] = host
    if port is not None:
        overrides["port"] = port
    if token is not None:
        overrides["token"] = token
    settings = Settings(**overrides)
    settings.validate_bind()
    application = create_app(settings)

    if open_browser:
        query = f"?{urlencode({'token': settings.token})}" if settings.token else ""
        webbrowser.open(f"http://{settings.host}:{settings.port}/{query}")

    register_server(host=settings.host, port=settings.port, workspace=workspace)
    try:
        uvicorn.run(application, host=settings.host, port=settings.port, log_level="info")
    finally:
        unregister_server(settings.port)


@cli.app.command()
def stop(
    port: Annotated[int, typer.Option("--port", "-p", help="HTTP port")] = 8787,
) -> None:
    """Stop a running Cairn UI server (by port)."""
    from server.util.runtime_state import stop_server

    ok, message = stop_server(port)
    if ok:
        typer.echo(message)
    else:
        typer.echo(message, err=True)
        raise typer.Exit(code=1)


@cli.app.command()
def upgrade(
    check: Annotated[
        bool,
        typer.Option("--check", help="Print the update command without running it"),
    ] = False,
) -> None:
    """Upgrade Cairn to the latest published release."""
    method, command = upgrade_command()
    rendered = render_command(command)
    typer.echo(f"Updating Cairn via {method}: {rendered}")
    if check:
        return
    try:
        result = subprocess.run(command, check=False)
    except OSError as exc:
        typer.echo(f"Could not start updater: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if result.returncode:
        typer.echo(f"Update failed (exit {result.returncode}). Run: {rendered}", err=True)
        raise typer.Exit(code=result.returncode)
    typer.echo("Updated. Restart Cairn to use the new version.")


@cli.app.command()
def sync(
    source: Annotated[str | None, typer.Option("--source", help="Adapter source filter")] = None,
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
) -> None:
    """Sync agent logs into the local store."""
    result = cli._run_action("sync", {"source": source}, workspace)
    typer.echo(json.dumps(result, indent=2))
    typer.echo(cli._render_sync_next_step(result))


@cli.app.command()
def doctor(
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
    port: Annotated[int, typer.Option("--port", "-p")] = 8787,
    json_out: Annotated[bool, typer.Option("--json")] = False,
    repair_permissions: Annotated[
        bool,
        typer.Option(
            "--repair-permissions",
            help="Restrict existing Cairn data to the current user",
        ),
    ] = False,
) -> None:
    """Verify install, environment, and workspace readiness."""
    raise typer.Exit(
        print_doctor(
            workspace=workspace,
            port=port,
            as_json=json_out,
            repair_permissions=repair_permissions,
        )
    )


@cli.app.command()
def check(
    min_quality: Annotated[float | None, typer.Option("--min-quality")] = None,
    max_waste_pct: Annotated[float | None, typer.Option("--max-waste-pct")] = None,
    max_tail_cost: Annotated[float | None, typer.Option("--max-tail-cost")] = None,
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
) -> None:
    """CI quality gate — exits non-zero on failure."""
    result = cli._run_action(
        "check",
        {
            "min_quality": min_quality,
            "max_waste_pct": max_waste_pct,
            "max_tail_cost": max_tail_cost,
        },
        workspace,
    )
    typer.echo(json.dumps(result, indent=2))
    if not result.get("ok", True):
        raise typer.Exit(code=1)


@cli.app.command(name="show")
def show_trace(
    trace_id: str,
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
) -> None:
    """Print a text waterfall for a trace."""
    ctx = cli._make_ctx(workspace)
    text = render_waterfall(ctx.db.reader, trace_id)
    if text is None:
        typer.echo(f"Trace not found: {trace_id}", err=True)
        raise typer.Exit(code=1)
    typer.echo(text)


traces_app = typer.Typer(help="List and inspect traces.")
cli.app.add_typer(traces_app, name="traces")


@traces_app.command("ls")
def traces_ls(
    days: Annotated[int, typer.Option("--days")] = 30,
    limit: Annotated[int, typer.Option("--limit")] = 20,
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
) -> None:
    """List recent traces as a plain table."""
    from server.api.payloads import build_traces_list

    ctx = cli._make_ctx(workspace)
    payload = build_traces_list(
        ctx.db.reader,
        workspace_id=ctx.workspace_id,
        days=days,
        limit=limit,
    )
    typer.echo(f"{'trace_id':<28} {'source':<12} {'cost':>8} {'title'}")
    for row in payload.traces:
        title = (row.title or "")[:40]
        typer.echo(f"{row.trace_id:<28} {row.source:<12} {row.cost:>8.2f} {title}")


@traces_app.command("show")
def traces_show(
    trace_id: str,
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
) -> None:
    """Alias for `cairn show`."""
    show_trace(trace_id, workspace)


@cli.app.command()
def insights(
    state: Annotated[str | None, typer.Option("--state")] = None,
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
) -> None:
    """List insights."""
    from server.api.payloads import build_insights

    ctx = cli._make_ctx(workspace)
    payload = build_insights(ctx.db.reader, state=state)
    for row in payload.insights:
        typer.echo(f"[{row.severity}/{row.state}] {row.title}")
