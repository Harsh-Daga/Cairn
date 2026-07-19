"""CLI for versioned portable Cairn archives (ADR-10)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal

import typer

import server.cli as cli
from server.archive.export import export_archive, preview_archive
from server.archive.import_archive import import_archive
from server.archive.inspect_archive import inspect_archive
from server.archive.schema import ARCHIVE_SCHEMA_VERSION

archive_app = typer.Typer(
    name="archive",
    help="Export, inspect, and import versioned cairn.archive.v1 ZIP files.",
    no_args_is_help=True,
)
cli.app.add_typer(archive_app, name="archive")


def _cli_json(payload: dict[str, Any]) -> str:
    body = {
        "schema": ARCHIVE_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        **payload,
    }
    return json.dumps(body, indent=2, sort_keys=True)


@archive_app.command("export")
def archive_export_cmd(
    mode: Annotated[
        Literal["full", "scrubbed", "metadata_only"],
        typer.Option("--mode"),
    ] = "scrubbed",
    limit: Annotated[int, typer.Option("--limit")] = 500,
    output: Annotated[Path | None, typer.Option("--output")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Write a portable workspace archive (or preview with --dry-run)."""
    ctx = cli._make_ctx(workspace)
    if dry_run:
        result = preview_archive(
            ctx.db.reader,
            workspace_id=ctx.workspace_id,
            workspace_root=ctx.workspace_root,
            mode=mode,
            limit=limit,
        )
    else:
        result = export_archive(
            ctx.db.reader,
            workspace_id=ctx.workspace_id,
            workspace_root=ctx.workspace_root,
            output=output,
            mode=mode,
            limit=limit,
        )
    if json_out:
        typer.echo(_cli_json(result))
        return
    if not result.get("ok", True) and result.get("ok") is False:
        raise typer.Exit(code=1)
    if dry_run:
        typer.echo(
            f"Preview  {result.get('trace_count')} traces · "
            f"~{result.get('total_bytes_estimate')} B · mode={mode}"
        )
    else:
        typer.echo(f"Wrote  {result.get('path')}")
    typer.echo(result.get("limitation", ""))


@archive_app.command("inspect")
def archive_inspect_cmd(
    archive: Annotated[Path, typer.Argument(help="Path to cairn.archive.v1 zip")],
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Inspect archive envelope, checksums, and OTLP-loss notes."""
    result = inspect_archive(archive)
    if json_out:
        typer.echo(_cli_json(result))
        return
    if not result.get("ok"):
        typer.echo(result.get("detail") or result.get("error"))
        raise typer.Exit(code=1)
    typer.echo(f"Schema  {result.get('schema')} (supported={result.get('supported')})")
    typer.echo(f"Mode  {result.get('mode')} · traces {result.get('trace_count')}")
    typer.echo(f"Producer  {result.get('producer_version')}")
    if result.get("checksum_mismatches"):
        typer.echo(f"Checksum mismatches  {result['checksum_mismatches']}")
    typer.echo(result.get("limitation", ""))


@archive_app.command("import")
def archive_import_cmd(
    archive: Annotated[Path, typer.Argument(help="Path to cairn.archive.v1 zip")],
    dry_run: Annotated[bool, typer.Option("--dry-run/--apply")] = True,
    conflict: Annotated[
        Literal["skip", "replace", "fail"],
        typer.Option("--conflict"),
    ] = "fail",
    workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Import archive into the workspace DB (dry-run by default)."""
    ctx = cli._make_ctx(workspace)

    def _run(conn: object) -> dict[str, Any]:
        import sqlite3

        assert isinstance(conn, sqlite3.Connection)
        return import_archive(
            conn,
            workspace_id=ctx.workspace_id,
            workspace_root=ctx.workspace_root,
            archive=archive,
            dry_run=dry_run,
            conflict=conflict,
        )

    result = _run(ctx.db.reader) if dry_run else ctx.db.write(_run)
    if json_out:
        typer.echo(_cli_json(result))
        return
    if not result.get("ok"):
        typer.echo(result.get("message") or result.get("error") or result.get("detail"))
        raise typer.Exit(code=1)
    typer.echo(
        f"{'Dry-run' if dry_run else 'Applied'}  "
        f"insert={result.get('would_insert', result.get('inserted'))} "
        f"replace={result.get('would_replace', result.get('replaced'))} "
        f"skip={result.get('would_skip', result.get('skipped'))}"
    )
    typer.echo(result.get("limitation", ""))
