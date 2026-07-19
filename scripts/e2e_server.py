#!/usr/bin/env python3
"""Run an isolated, deterministically seeded Cairn server for Playwright."""

from __future__ import annotations

import tempfile
from pathlib import Path

import uvicorn

from server.app import create_app
from server.config import Settings
from server.demo.seed import seed_demo_workspace


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="cairn-e2e-") as tmp:
        workspace = Path(tmp) / "workspace"
        seed_demo_workspace(workspace, reset=True)
        settings = Settings(host="127.0.0.1", port=8787, workspace_root=workspace)
        uvicorn.run(
            create_app(settings), host=settings.host, port=settings.port, log_level="warning"
        )


if __name__ == "__main__":
    main()
