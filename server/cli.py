"""Typer CLI — subcommands auto-generated from action registry."""

from __future__ import annotations

import json
import subprocess
import webbrowser
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlencode

import typer
import uvicorn

from server import __version__
from server.api.actions import build_manifest, get_action
from server.api.bootstrap import bootstrap_runtime
from server.api.context import ActionCtx
from server.api.show import render_waterfall
from server.app import create_app
from server.config import Settings
from server.demo.seed import DEMO_ROOT
from server.doctor import print_doctor
from server.export.static import export_static_snapshot
from server.update import render_command, upgrade_command

app = typer.Typer(
    name="cairn",
    help="Local-first observability and self-improvement for AI coding agents.",
    invoke_without_command=True,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def main_callback(
    ctx: typer.Context,
    version: Annotated[
        bool | None,
        typer.Option("--version", callback=_version_callback, is_eager=True),
    ] = None,
) -> None:
    """Cairn CLI — local-first agent observability."""
    if ctx.invoked_subcommand is not None or version:
        return
    _run_action("sync", {}, None)
    _print_money_slide()
    ui()


action_app = typer.Typer(help="Run any registered action by name.")
app.add_typer(action_app, name="action")


def _make_ctx(root: Path | None = None) -> ActionCtx:
    settings = Settings(workspace_root=root)
    runtime = bootstrap_runtime(settings)
    return ActionCtx(
        db=runtime.database,
        workspace_id=runtime.workspace_id,
        workspace_root=runtime.workspace_root,
        event_bus=runtime.event_bus,
        pipeline=runtime.pipeline,
        jobs=runtime.jobs,
    )


def _run_action(name: str, params: dict[str, Any], root: Path | None = None) -> dict[str, Any]:
    action_def = get_action(name)
    if action_def is None:
        typer.echo(f"Unknown action: {name}", err=True)
        raise typer.Exit(code=1)
    ctx = _make_ctx(root)
    validated = action_def.params_model.model_validate(params)
    return action_def.handler(validated, ctx)


def _render_money_slide(money: Any) -> str:
    estimate = " ± est." if money.waste_estimated else ""
    lines = [
        f"Cairn · last {money.period_days} days",
        f"Spend      ${money.total_spend_usd:,.2f}",
        (
            f"Waste      ${money.wasted_spend_usd:,.2f}{estimate} "
            f"({money.wasted_spend_pct:.1f}%)"
        ),
    ]
    if money.top_causes:
        lines.append("Top causes")
        for index, cause in enumerate(money.top_causes, 1):
            label = cause.category.replace("_", " ")
            lines.append(f"  {index}. ${cause.estimated_savings_usd:,.2f} · {label}")
            lines.append(f"     Fix: {cause.fix}")
    else:
        lines.append("Top causes  waiting for priced waste data")
    lines.append("Action      Review proposed fix → http://127.0.0.1:8787/optimize")
    return "\n".join(lines)


def _print_money_slide(workspace: Path | None = None) -> None:
    from server.api.payloads import build_overview

    action_ctx = _make_ctx(workspace)
    overview = build_overview(
        action_ctx.db.reader,
        workspace_id=action_ctx.workspace_id,
        days=30,
    )
    typer.echo(_render_money_slide(overview.money))


@app.command()
def ui(
    host: Annotated[str, typer.Option("--host", help="Bind address")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", "-p", help="HTTP port")] = 8787,
    open_browser: Annotated[bool, typer.Option("--open/--no-open", help="Open browser")] = True,
    token: Annotated[str | None, typer.Option("--token", help="Auth token")] = None,
    workspace: Annotated[Path | None, typer.Option("--workspace", help="Workspace root")] = None,
) -> None:
    """Start the Cairn web UI server."""
    from server.util.runtime_state import register_server, unregister_server

    settings = Settings(host=host, port=port, token=token, workspace_root=workspace)
    settings.validate_bind()
    application = create_app(settings)

    if open_browser:
        query = f"?{urlencode({'token': token})}" if token else ""
        webbrowser.open(f"http://{host}:{port}/{query}")

    register_server(host=host, port=port, workspace=workspace)
    try:
        uvicorn.run(application, host=host, port=port, log_level="info")
    finally:
        unregister_server(port)


@app.command()
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


@app.command()
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


@app.command()
def sync(
    source: Annotated[str | None, typer.Option("--source", help="Adapter source filter")] = None,
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
) -> None:
    """Sync agent logs into the local store."""
    result = _run_action("sync", {"source": source}, workspace)
    typer.echo(json.dumps(result, indent=2))


@app.command()
def doctor(
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
    port: Annotated[int, typer.Option("--port", "-p")] = 8787,
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Verify install, environment, and workspace readiness."""
    raise typer.Exit(print_doctor(workspace=workspace, port=port, as_json=json_out))


@app.command()
def check(
    min_quality: Annotated[float | None, typer.Option("--min-quality")] = None,
    max_waste_pct: Annotated[float | None, typer.Option("--max-waste-pct")] = None,
    max_tail_cost: Annotated[float | None, typer.Option("--max-tail-cost")] = None,
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
) -> None:
    """CI quality gate — exits non-zero on failure."""
    result = _run_action(
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


@app.command(name="show")
def show_trace(
    trace_id: str,
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
) -> None:
    """Print a text waterfall for a trace."""
    ctx = _make_ctx(workspace)
    text = render_waterfall(ctx.db.reader, trace_id)
    if text is None:
        typer.echo(f"Trace not found: {trace_id}", err=True)
        raise typer.Exit(code=1)
    typer.echo(text)


traces_app = typer.Typer(help="List and inspect traces.")
app.add_typer(traces_app, name="traces")


@traces_app.command("ls")
def traces_ls(
    days: Annotated[int, typer.Option("--days")] = 30,
    limit: Annotated[int, typer.Option("--limit")] = 20,
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
) -> None:
    """List recent traces as a plain table."""
    from server.api.payloads import build_traces_list

    ctx = _make_ctx(workspace)
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


@app.command()
def insights(
    state: Annotated[str | None, typer.Option("--state")] = None,
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
) -> None:
    """List insights."""
    from server.api.payloads import build_insights

    ctx = _make_ctx(workspace)
    payload = build_insights(ctx.db.reader, state=state)
    for row in payload.insights:
        typer.echo(f"[{row.severity}/{row.state}] {row.title}")


optimize_app = typer.Typer(
    help="Generate proposals and manage optimized instruction changes.",
    invoke_without_command=True,
)
app.add_typer(optimize_app, name="optimize")


@optimize_app.callback()
def optimize(
    ctx: typer.Context,
    llm: Annotated[bool, typer.Option("--llm")] = False,
    apply: Annotated[bool, typer.Option("--apply")] = False,
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
) -> None:
    """Generate optimization proposals when no subcommand is given."""
    if ctx.invoked_subcommand is not None:
        return
    result = _run_action("optimize_propose", {"llm": llm, "apply": apply}, workspace)
    typer.echo(json.dumps(result, indent=2))


@optimize_app.command("revert")
def optimize_revert(
    experiment_id: str,
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
) -> None:
    """Revert one applied optimization from its exact backup."""
    result = _run_action("experiment_revert", {"experiment_id": experiment_id}, workspace)
    typer.echo(json.dumps(result, indent=2))


experiments_app = typer.Typer(help="Manage improvement experiments.")
app.add_typer(experiments_app, name="experiments")


@experiments_app.command("ls")
def experiments_ls(workspace: Annotated[Path | None, typer.Option("--workspace")] = None) -> None:
    from server.api.payloads import build_experiments

    ctx = _make_ctx(workspace)
    for row in build_experiments(ctx.db.reader).experiments:
        typer.echo(f"{row.experiment_id}  {row.status}  {row.target_file}")


@experiments_app.command("revert")
def experiments_revert(
    experiment_id: str,
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
) -> None:
    result = _run_action("experiment_revert", {"experiment_id": experiment_id}, workspace)
    typer.echo(json.dumps(result, indent=2))


@app.command()
def export(
    trace_id: Annotated[str | None, typer.Option("--trace-id")] = None,
    static: Annotated[
        Path | None,
        typer.Option("--static", help="Export static read-only snapshot to directory"),
    ] = None,
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
) -> None:
    """Export a scrubbed trace bundle."""
    if static is not None:
        if trace_id is not None:
            typer.echo("Cannot combine --trace-id with --static.", err=True)
            raise typer.Exit(code=2)
        out_dir = static.expanduser().resolve()
        root = workspace.resolve() if workspace is not None else None
        result = export_static_snapshot(root, out_dir)
        typer.echo(json.dumps(result, indent=2))
        return
    result = _run_action("export_bundle", {"trace_id": trace_id, "scrub": True}, workspace)
    typer.echo(json.dumps(result, indent=2))


@app.command()
def demo(
    reset: Annotated[
        bool,
        typer.Option("--reset", help="Reset and reseed ~/.cairn-demo"),
    ] = False,
) -> None:
    """Seed a deterministic local demo workspace."""
    result = _run_action("demo_seed", {"reset": reset}, None)
    typer.echo(json.dumps(result, indent=2))
    typer.echo(f'Run "cairn ui --workspace {DEMO_ROOT}" to open the demo workspace.')


mcp_app = typer.Typer(help="MCP integration helpers.")
app.add_typer(mcp_app, name="mcp")


@mcp_app.command("install")
def mcp_install_cmd(
    client: Annotated[
        str,
        typer.Option("--client", help="Agent client: claude-code, cursor, codex, other"),
    ] = "cursor",
    print_only: Annotated[
        bool,
        typer.Option("--print", help="Print JSON only; do not write"),
    ] = False,
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
) -> None:
    """Install Cairn MCP config for Claude Code, Cursor, or Codex."""
    result = _run_action(
        "mcp_install",
        {"client": client, "print_only": print_only},
        workspace,
    )
    typer.echo(json.dumps(result, indent=2))


@app.command("setup-prompt")
def setup_prompt() -> None:
    """Print the short agent bootstrap prompt for README copy-paste."""
    from server.mcp.install import BOOTSTRAP_PROMPT

    typer.echo(BOOTSTRAP_PROMPT)


@mcp_app.callback(invoke_without_command=True)
def mcp_main(
    ctx: typer.Context,
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
) -> None:
    """Run the Cairn MCP stdio server."""
    if ctx.invoked_subcommand is not None:
        return
    from server.mcp.server import serve

    root = workspace or Path.cwd()
    raise typer.Exit(serve(root))


config_app = typer.Typer(help="Runtime configuration.")
app.add_typer(config_app, name="config")


@config_app.command("set")
def config_set(
    key: str,
    value: str,
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
) -> None:
    result = _run_action("config_set", {"key": key, "value": value}, workspace)
    typer.echo(json.dumps(result, indent=2))


@app.command()
def rebuild(
    view: Annotated[str, typer.Option("--view", help="View name to rebuild")],
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
) -> None:
    """Rebuild an incremental analyzer view."""
    result = _run_action("rebuild_view", {"view": view}, workspace)
    typer.echo(json.dumps(result, indent=2))


adapter_app = typer.Typer(help="Ingest adapter scaffolding.")
app.add_typer(adapter_app, name="adapter")


@adapter_app.command("new")
def adapter_new(
    name: str,
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
) -> None:
    """Scaffold a new ingest adapter module, fixture, and test."""
    from server.ingest.scaffold import scaffold_adapter

    root = (workspace or Path.cwd()).resolve()
    try:
        created = scaffold_adapter(root, name)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Scaffolded {name} adapter:")
    for path in created:
        typer.echo(f"  {path.relative_to(root)}")
    from server.ingest.scaffold import entry_point_snippet

    class_name = "".join(part.capitalize() for part in name.split("_")) + "Adapter"
    typer.echo(
        'Next: add to pyproject.toml [project.entry-points."cairn.adapters"] '
        f"or server/ingest/registry.py:\n  {entry_point_snippet(name, class_name)}"
    )


def _register_action_commands() -> None:
    for entry in build_manifest():
        action_name = entry.name
        title = entry.title

        def _make_cmd(resolved_name: str, doc: str) -> Callable[..., None]:
            def _cmd(
                params_json: Annotated[
                    str | None,
                    typer.Option("--params-json", help="JSON params object"),
                ] = None,
                workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
            ) -> None:
                params: dict[str, Any] = {}
                if params_json:
                    params = json.loads(params_json)
                result = _run_action(resolved_name, params, workspace)
                typer.echo(json.dumps(result, indent=2))

            _cmd.__doc__ = doc
            return _cmd

        action_app.command(name=action_name)(_make_cmd(action_name, title))


_register_action_commands()


def main() -> None:
    """Entry point for the cairn console script."""
    app()


if __name__ == "__main__":
    main()
