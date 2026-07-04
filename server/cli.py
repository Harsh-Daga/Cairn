"""Typer CLI — subcommands auto-generated from action registry."""

from __future__ import annotations

import json
import webbrowser
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any

import typer
import uvicorn

from server.api.actions import build_manifest, get_action
from server.api.bootstrap import bootstrap_runtime
from server.api.context import ActionCtx
from server.api.show import render_waterfall
from server.app import create_app
from server.config import Settings

app = typer.Typer(
    name="cairn",
    help="Local-first observability and self-improvement for AI coding agents.",
    no_args_is_help=True,
)

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


@app.command()
def ui(
    host: Annotated[str, typer.Option("--host", help="Bind address")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", "-p", help="HTTP port")] = 8787,
    open_browser: Annotated[bool, typer.Option("--open/--no-open", help="Open browser")] = True,
    token: Annotated[str | None, typer.Option("--token", help="Auth token")] = None,
    workspace: Annotated[Path | None, typer.Option("--workspace", help="Workspace root")] = None,
) -> None:
    """Start the Cairn web UI server."""
    settings = Settings(host=host, port=port, token=token, workspace_root=workspace)
    settings.validate_bind()
    application = create_app(settings)

    if open_browser:
        webbrowser.open(f"http://{host}:{port}")

    uvicorn.run(application, host=host, port=port, log_level="info")


@app.command()
def stop() -> None:
    """Stop a running Cairn background server."""
    typer.echo("No running server found.")


@app.command()
def sync(
    source: Annotated[str | None, typer.Option("--source", help="Adapter source filter")] = None,
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
) -> None:
    """Sync agent logs into the local store."""
    result = _run_action("sync", {"source": source}, workspace)
    typer.echo(json.dumps(result, indent=2))


@app.command()
def check(
    min_quality: Annotated[float | None, typer.Option("--min-quality")] = None,
    max_waste_pct: Annotated[float | None, typer.Option("--max-waste-pct")] = None,
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
) -> None:
    """CI quality gate — exits non-zero on failure."""
    result = _run_action(
        "check",
        {"min_quality": min_quality, "max_waste_pct": max_waste_pct},
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


@app.command()
def optimize(
    llm: Annotated[bool, typer.Option("--llm")] = False,
    apply: Annotated[bool, typer.Option("--apply")] = False,
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
) -> None:
    """Generate optimization proposals."""
    result = _run_action("optimize_propose", {"llm": llm, "apply": apply}, workspace)
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
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
) -> None:
    """Export a scrubbed trace bundle."""
    result = _run_action("export_bundle", {"trace_id": trace_id, "scrub": True}, workspace)
    typer.echo(json.dumps(result, indent=2))


mcp_app = typer.Typer(help="MCP integration helpers.")
app.add_typer(mcp_app, name="mcp")


@mcp_app.command("install")
def mcp_install(workspace: Annotated[Path | None, typer.Option("--workspace")] = None) -> None:
    result = _run_action("mcp_install", {}, workspace)
    typer.echo(json.dumps(result, indent=2))


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
