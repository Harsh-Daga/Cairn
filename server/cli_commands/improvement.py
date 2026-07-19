"""Optimize and experiment CLI commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

import server.cli as cli

optimize_app = typer.Typer(
    help="Generate proposals and manage optimized instruction changes.",
    invoke_without_command=True,
)
cli.app.add_typer(optimize_app, name="optimize")


@optimize_app.callback()
def optimize(
    ctx: typer.Context,
    llm: Annotated[
        bool,
        typer.Option(
            "--llm",
            help="Rejected: use `cairn action reflector_preview` / reflector_run instead.",
        ),
    ] = False,
    apply: Annotated[
        bool,
        typer.Option(
            "--apply",
            help="Rejected: use experiment apply from the Optimize UI or experiment_apply.",
        ),
    ] = False,
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
) -> None:
    """Generate local optimization proposals when no subcommand is given."""
    if ctx.invoked_subcommand is not None:
        return
    if llm or apply:
        typer.echo(
            "optimize_propose is local-only. "
            "Omit --llm/--apply. For LLM reflection use reflector_preview/reflector_run; "
            "to apply a proposal use experiment_apply with an experiment_id.",
            err=True,
        )
        raise typer.Exit(code=2)
    result = cli._run_action("optimize_propose", {"llm": False, "apply": False}, workspace)
    typer.echo(json.dumps(result, indent=2))


@optimize_app.command("revert")
def optimize_revert(
    experiment_id: str,
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
) -> None:
    """Revert one applied optimization from its exact backup."""
    result = cli._run_action("experiment_revert", {"experiment_id": experiment_id}, workspace)
    typer.echo(json.dumps(result, indent=2))


@optimize_app.command("evaluate")
def optimize_evaluate(
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
    force: Annotated[
        bool,
        typer.Option("--force", help="Re-evaluate even when the interval has not elapsed"),
    ] = False,
    limit: Annotated[int, typer.Option("--limit", min=1, max=100)] = 20,
    json_out: Annotated[bool, typer.Option("--json", help="Emit JSON payload")] = False,
) -> None:
    """Opportunistically re-evaluate due portfolio experiments (no daemon)."""
    result = cli._run_action(
        "optimize_evaluate",
        {"force": force, "limit": limit},
        workspace,
    )
    if json_out:
        typer.echo(json.dumps(result, indent=2, sort_keys=True))
        return
    typer.echo(
        f"Evaluated {result.get('evaluated_count', 0)} due rule(s); "
        f"decay refreshed {result.get('decay_refreshed', 0)}."
    )
    typer.echo(str(result.get("limitation") or ""))
    for item in result.get("evaluated") or []:
        typer.echo(
            f"  {item.get('experiment_id', '')[:12]}  {item.get('action')}  "
            f"verdict={item.get('verdict')}  outside_interval="
            f"{item.get('regression_outside_interval')}"
        )


@optimize_app.command("export-effects")
def optimize_export_effects(
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Write a scrubbed local JSON of measured rule effects."""
    from server.export.rule_effects import export_rule_effects

    ctx = cli._make_ctx(workspace)
    destination = export_rule_effects(ctx.db.reader, ctx.workspace_root, output)
    typer.echo(str(destination))


@optimize_app.command("llm-preview")
def optimize_llm_preview(
    backend: Annotated[str | None, typer.Option("--backend")] = None,
    days: Annotated[int, typer.Option("--days", min=1, max=365)] = 14,
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
) -> None:
    """Show exactly what an optional LLM backend would receive; make no request."""
    result = cli._run_action(
        "reflector_preview",
        {"backend": backend, "days": days},
        workspace,
    )
    typer.echo(json.dumps(result, indent=2))


@optimize_app.command("llm-run")
def optimize_llm_run(
    consent_token: Annotated[
        str,
        typer.Option(
            "--consent-token",
            help="Exact token returned by llm-preview for unchanged content",
        ),
    ],
    backend: Annotated[str | None, typer.Option("--backend")] = None,
    days: Annotated[int, typer.Option("--days", min=1, max=365)] = 14,
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
) -> None:
    """Run the optional reflector only after an exact preview has been accepted."""
    result = cli._run_action(
        "reflector_run",
        {
            "backend": backend,
            "days": days,
            "consent_token": consent_token,
        },
        workspace,
    )
    typer.echo(json.dumps(result, indent=2))


experiments_app = typer.Typer(help="Manage improvement experiments.")
cli.app.add_typer(experiments_app, name="experiments")


@experiments_app.command("ls")
def experiments_ls(workspace: Annotated[Path | None, typer.Option("--workspace")] = None) -> None:
    from server.api.payloads import build_experiments

    ctx = cli._make_ctx(workspace)
    for row in build_experiments(ctx.db.reader).experiments:
        typer.echo(f"{row.experiment_id}  {row.status}  {row.target_file}")


@experiments_app.command("revert")
def experiments_revert(
    experiment_id: str,
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
) -> None:
    result = cli._run_action("experiment_revert", {"experiment_id": experiment_id}, workspace)
    typer.echo(json.dumps(result, indent=2))
