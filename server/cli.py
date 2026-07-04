"""Typer CLI — subcommands auto-generated from action registry in later phases."""

from __future__ import annotations

import webbrowser
from typing import Annotated

import typer
import uvicorn

from server.app import create_app
from server.config import Settings

app = typer.Typer(
    name="cairn",
    help="Local-first observability and self-improvement for AI coding agents.",
    no_args_is_help=True,
)


@app.command()
def ui(
    host: Annotated[str, typer.Option("--host", help="Bind address")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", "-p", help="HTTP port")] = 8787,
    open_browser: Annotated[bool, typer.Option("--open/--no-open", help="Open browser")] = True,
    token: Annotated[str | None, typer.Option("--token", help="Auth token")] = None,
) -> None:
    """Start the Cairn web UI server."""
    settings = Settings(host=host, port=port, token=token)
    settings.validate_bind()
    application = create_app(settings)

    if open_browser:
        webbrowser.open(f"http://{host}:{port}")

    uvicorn.run(application, host=host, port=port, log_level="info")


@app.command()
def stop() -> None:
    """Stop a running Cairn background server (Phase 7)."""
    typer.echo("No running server found.")


def main() -> None:
    """Entry point for the cairn console script."""
    app()


if __name__ == "__main__":
    main()
