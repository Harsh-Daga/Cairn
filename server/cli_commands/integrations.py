"""Export, MCP, configuration, rebuild, demo, and adapter CLI commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

import server.cli as cli
from server.demo.seed import DEMO_ROOT
from server.export.static import export_static_snapshot

export_app = typer.Typer(
    help="Export scrubbed bundles, session HTML, or static snapshots.",
    invoke_without_command=True,
)
cli.app.add_typer(export_app, name="export")


@export_app.callback()
def export_root(
    ctx: typer.Context,
    trace_id: Annotated[str | None, typer.Option("--trace-id")] = None,
    static: Annotated[
        Path | None,
        typer.Option("--static", help="Export static read-only snapshot to directory"),
    ] = None,
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
) -> None:
    """Export a scrubbed trace bundle (default) or static snapshot."""
    if ctx.invoked_subcommand is not None:
        return
    if static is not None:
        if trace_id is not None:
            typer.echo("Cannot combine --trace-id with --static.", err=True)
            raise typer.Exit(code=2)
        out_dir = static.expanduser().resolve()
        root = workspace.resolve() if workspace is not None else None
        result = export_static_snapshot(root, out_dir)
        typer.echo(json.dumps(result, indent=2))
        return
    result = cli._run_action("export_bundle", {"trace_id": trace_id, "scrub": True}, workspace)
    typer.echo(json.dumps(result, indent=2))


@export_app.command("session")
def export_session(
    trace_id: Annotated[str, typer.Argument(help="Trace/session id")],
    html: Annotated[
        bool,
        typer.Option("--html", help="Write a self-contained scrubbed HTML report"),
    ] = False,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Destination HTML path"),
    ] = None,
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
) -> None:
    """Export one session as scrubbed self-contained HTML."""
    if not html:
        typer.echo("Pass --html to write the scrubbed session HTML report.", err=True)
        raise typer.Exit(code=2)
    result = cli._run_action(
        "export_session_html",
        {
            "trace_id": trace_id,
            "output": str(output) if output is not None else None,
        },
        workspace,
    )
    if not result.get("ok", True) and result.get("error") == "trace_not_found":
        typer.echo(f"Trace not found: {trace_id}", err=True)
        raise typer.Exit(code=1)
    for warning in result.get("warnings") or []:
        typer.echo(str(warning), err=True)
    typer.echo(json.dumps(result, indent=2, sort_keys=True))


@cli.app.command()
def demo(
    reset: Annotated[
        bool,
        typer.Option("--reset", help="Reset and reseed ~/.cairn-demo"),
    ] = False,
) -> None:
    """Seed a deterministic local demo workspace."""
    result = cli._run_action("demo_seed", {"reset": reset}, None)
    typer.echo(json.dumps(result, indent=2))
    typer.echo(f'Run "cairn ui --workspace {DEMO_ROOT}" to open the demo workspace.')


mcp_app = typer.Typer(help="MCP integration helpers.")
cli.app.add_typer(mcp_app, name="mcp")


@mcp_app.command("install")
def mcp_install_cmd(
    client: Annotated[
        str | None,
        typer.Option("--client", help="Agent client: claude-code, cursor, codex, other"),
    ] = None,
    print_only: Annotated[
        bool,
        typer.Option("--print", help="Print JSON only; do not write"),
    ] = False,
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
) -> None:
    """Install Cairn MCP config for Claude Code, Cursor, or Codex."""
    result = cli._run_action(
        "mcp_install",
        {"client": client, "print_only": print_only},
        workspace,
    )
    typer.echo(json.dumps(result, indent=2))


@cli.app.command("setup-prompt")
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
cli.app.add_typer(config_app, name="config")


@config_app.command("set")
def config_set(
    key: str,
    value: str,
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
    scope: Annotated[str, typer.Option("--scope", help="user or workspace")] = "user",
) -> None:
    """Validate and atomically set one typed configuration value."""
    result = cli._run_action(
        "config_set",
        {"operation": "set", "key": key, "value": value, "scope": scope},
        workspace,
    )
    typer.echo(json.dumps(result, indent=2))


@config_app.command("get")
def config_get(
    key: str,
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
    reveal_secrets: Annotated[bool, typer.Option("--show-secrets")] = False,
) -> None:
    """Print one resolved value, its source, and redaction status."""
    result = cli._run_action(
        "config_set",
        {"operation": "get", "key": key, "reveal_secrets": reveal_secrets},
        workspace,
    )
    typer.echo(json.dumps(result, indent=2))


@config_app.command("unset")
def config_unset(
    key: str,
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
    scope: Annotated[str, typer.Option("--scope", help="user or workspace")] = "user",
) -> None:
    """Remove one file-backed value so lower-precedence sources apply."""
    result = cli._run_action(
        "config_set",
        {"operation": "unset", "key": key, "scope": scope},
        workspace,
    )
    typer.echo(json.dumps(result, indent=2))


@config_app.command("list")
def config_list(
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
    reveal_secrets: Annotated[bool, typer.Option("--show-secrets")] = False,
) -> None:
    """List resolved typed values with source metadata and secret redaction."""
    result = cli._run_action(
        "config_set",
        {"operation": "list", "reveal_secrets": reveal_secrets},
        workspace,
    )
    typer.echo(json.dumps(result, indent=2))


@cli.app.command()
def rebuild(
    view: Annotated[str, typer.Option("--view", help="View name to rebuild")],
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
) -> None:
    """Rebuild an incremental analyzer view."""
    result = cli._run_action("rebuild_view", {"view": view}, workspace)
    typer.echo(json.dumps(result, indent=2))


adapter_app = typer.Typer(help="Ingest adapter scaffolding.")
cli.app.add_typer(adapter_app, name="adapter")


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


@adapter_app.command("doctor")
def adapter_doctor(
    adapter_id: str,
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
    sample: Annotated[
        Path | None, typer.Option("--sample", help="Specific live log sample")
    ] = None,
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Compare a live log sample with an adapter's expected shape."""
    from server.ingest.adapter_doctor import format_adapter_doctor, run_adapter_doctor

    result = run_adapter_doctor(adapter_id, workspace or Path.cwd(), sample_path=sample)
    typer.echo(json.dumps(result, indent=2) if json_out else format_adapter_doctor(result))
    if not result["ok"]:
        raise typer.Exit(code=1)
