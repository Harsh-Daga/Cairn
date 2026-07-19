"""CLI for local regression artifacts (no command execution)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import typer

import server.cli as cli
from server.regression.create import create_regression_from_trace
from server.regression.io import export_regression_zip, import_regression_zip
from server.regression.schema import REGRESSION_SCHEMA_VERSION
from server.regression.store import delete_regression, list_regressions, load_regression
from server.regression.validate import validate_artifact

REGRESSION_JSON_SCHEMA = REGRESSION_SCHEMA_VERSION

regression_app = typer.Typer(
    name="regression",
    help="Create, list, validate, record, compare, and port local regressions (no execution).",
    no_args_is_help=True,
)
cli.app.add_typer(regression_app, name="regression")


def _cli_json(payload: dict[str, Any]) -> str:
    body = {
        "schema": REGRESSION_JSON_SCHEMA,
        "generated_at": datetime.now(UTC).isoformat(),
        **payload,
    }
    return json.dumps(body, indent=2, sort_keys=True)


@regression_app.command("create")
def regression_create(
    trace_id: Annotated[str, typer.Argument(help="Source session/trace id")],
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Create a scrubbed local regression artifact from a recorded session."""
    action_ctx = cli._make_ctx(workspace)
    result = create_regression_from_trace(
        action_ctx.db.reader,
        workspace_root=action_ctx.workspace_root,
        workspace_id=action_ctx.workspace_id,
        trace_id=trace_id,
    )
    if not result.get("ok"):
        typer.echo(result.get("error", "create_failed"), err=True)
        raise typer.Exit(code=1)
    if json_out:
        typer.echo(_cli_json(result))
        return
    typer.echo(f"Created regression {result['regression_id']}")
    typer.echo(f"Path     {result['path']}")
    typer.echo(f"Hash     {result['content_hash']}")
    typer.echo("Note     Setup/verification commands are not executed.")


@regression_app.command("ls")
def regression_ls(
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """List local regression artifacts under ``.cairn/regressions``."""
    action_ctx = cli._make_ctx(workspace)
    items = list_regressions(action_ctx.workspace_root)
    if json_out:
        typer.echo(
            _cli_json(
                {
                    "count": len(items),
                    "items": [item.model_dump(mode="json") for item in items],
                }
            )
        )
        return
    if not items:
        typer.echo("No local regressions.")
        return
    for item in items:
        title = (item.title or "")[:60]
        typer.echo(f"{item.regression_id}  {item.created_at}  {title}")


@regression_app.command("show")
def regression_show(
    regression_id: Annotated[str, typer.Argument()],
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Show a local regression artifact."""
    action_ctx = cli._make_ctx(workspace)
    artifact = load_regression(action_ctx.workspace_root, regression_id)
    if artifact is None:
        typer.echo("regression_not_found", err=True)
        raise typer.Exit(code=1)
    if json_out:
        typer.echo(_cli_json(artifact.model_dump(mode="json")))
        return
    typer.echo(f"Regression  {artifact.regression_id}")
    typer.echo(f"Task        {artifact.scrubbed_task or '(missing)'}")
    typer.echo(
        f"Commit      {artifact.repo_start_ref.commit or '(missing)'} "
        f"[{artifact.repo_start_ref.commit_source}]"
    )
    typer.echo(f"Verify cmds {len(artifact.verification_commands)} (inferred; not executed)")
    typer.echo(f"Setup cmds  {len(artifact.setup_commands)} (empty by default)")
    typer.echo(f"Runs        {len(artifact.runs)} recorded (not executed)")
    typer.echo(f"Source      {artifact.provenance.source_trace_id}")
    typer.echo(f"Hash        {artifact.content_hash}")
    for note in artifact.limitations[:4]:
        typer.echo(f"Limitation  {note}")


@regression_app.command("run")
def regression_run(
    regression_id: Annotated[str, typer.Argument()],
    trace_id: Annotated[str, typer.Option("--trace", help="Ingested session to record")],
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Record an observed run from an ingested trace (never executes commands)."""
    from server.regression.run import record_run_from_trace

    action_ctx = cli._make_ctx(workspace)
    result = record_run_from_trace(
        action_ctx.db.reader,
        workspace_root=action_ctx.workspace_root,
        workspace_id=action_ctx.workspace_id,
        regression_id=regression_id,
        trace_id=trace_id,
    )
    if not result.get("ok"):
        typer.echo(result.get("error", "run_failed"), err=True)
        raise typer.Exit(code=1)
    if json_out:
        typer.echo(_cli_json(result))
        return
    typer.echo(f"Recorded run {result['run_id']}")
    typer.echo(f"Trace     {result['source_trace_id']}")
    typer.echo(f"Runs      {result['runs']}")
    typer.echo("Note      Commands were not executed.")


@regression_app.command("compare")
def regression_compare(
    regression_id: Annotated[str, typer.Argument()],
    run_id: Annotated[str | None, typer.Option("--run", help="Run id (default: latest)")] = None,
    against: Annotated[
        str,
        typer.Option("--against", help="expected or another run_id"),
    ] = "expected",
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Compare expected outcome (or another run) to a recorded run."""
    from server.regression.compare import compare_regression

    action_ctx = cli._make_ctx(workspace)
    result = compare_regression(
        action_ctx.workspace_root,
        regression_id=regression_id,
        run_id=run_id,
        against=against,
    )
    if not result.get("ok"):
        typer.echo(result.get("error", "compare_failed"), err=True)
        raise typer.Exit(code=1)
    if json_out:
        typer.echo(_cli_json(result))
        return
    typer.echo(f"Verdict   {result['verdict']}")
    typer.echo(f"Run       {result['run_id']} vs {result['against']}")
    for diff in result.get("diffs") or []:
        typer.echo(
            f"  {diff['field']}: expected={diff['expected']!r} "
            f"observed={diff['observed']!r} ({diff['status']})"
        )
    typer.echo(result["limitation"])


@regression_app.command("validate")
def regression_validate(
    regression_id: Annotated[str, typer.Argument()],
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Validate schema and honesty constraints; does not run commands."""
    action_ctx = cli._make_ctx(workspace)
    artifact = load_regression(action_ctx.workspace_root, regression_id)
    if artifact is None:
        typer.echo("regression_not_found", err=True)
        raise typer.Exit(code=1)
    report = validate_artifact(artifact)
    if json_out:
        typer.echo(_cli_json(report))
    else:
        status = "ok" if report["ok"] else "failed"
        typer.echo(f"Validate   {status}")
        for err in report["errors"]:
            typer.echo(f"Error      {err}")
        for warn in report["warnings"]:
            typer.echo(f"Warning    {warn}")
        typer.echo(f"Limitation {report['limitation']}")
    if not report["ok"]:
        raise typer.Exit(code=2)


@regression_app.command("export")
def regression_export(
    regression_id: Annotated[str, typer.Argument()],
    output: Annotated[Path, typer.Option("--output", "-o")],
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Export a regression directory as a portable zip (metadata only)."""
    action_ctx = cli._make_ctx(workspace)
    result = export_regression_zip(
        action_ctx.workspace_root,
        regression_id,
        output=output,
    )
    if not result.get("ok"):
        typer.echo(result.get("error", "export_failed"), err=True)
        raise typer.Exit(code=1)
    if json_out:
        typer.echo(_cli_json(result))
        return
    typer.echo(f"Exported {result['regression_id']} → {result['path']}")


@regression_app.command("import")
def regression_import(
    archive: Annotated[Path, typer.Argument(help="Path to regression zip")],
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
    replace: Annotated[bool, typer.Option("--replace")] = False,
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Import a portable regression zip after hostile-path checks."""
    action_ctx = cli._make_ctx(workspace)
    result = import_regression_zip(
        action_ctx.workspace_root,
        archive,
        replace=replace,
    )
    if not result.get("ok"):
        typer.echo(result.get("error", "import_failed"), err=True)
        raise typer.Exit(code=1)
    if json_out:
        typer.echo(_cli_json(result))
        return
    typer.echo(f"Imported {result['regression_id']}")
    typer.echo(f"Path     {result['path']}")
    typer.echo(result["limitation"])


@regression_app.command("delete")
def regression_delete(
    regression_id: Annotated[str, typer.Argument()],
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
    yes: Annotated[bool, typer.Option("--yes", "-y")] = False,
) -> None:
    """Delete a local regression artifact directory."""
    if not yes:
        typer.echo("Pass --yes to delete.", err=True)
        raise typer.Exit(code=1)
    action_ctx = cli._make_ctx(workspace)
    if not delete_regression(action_ctx.workspace_root, regression_id):
        typer.echo("regression_not_found", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"Deleted {regression_id}")
