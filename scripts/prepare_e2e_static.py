#!/usr/bin/env python3
"""Create a deterministic static snapshot for the file:// Playwright journey."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from server.demo.seed import seed_demo_workspace
from server.export.static import export_static_snapshot


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: prepare_e2e_static.py OUTPUT_DIR")
    output = Path(sys.argv[1]).resolve()
    with tempfile.TemporaryDirectory(prefix="cairn-static-e2e-") as tmp:
        workspace = Path(tmp) / "workspace"
        seed_demo_workspace(workspace, reset=True)
        export_static_snapshot(workspace, output)


if __name__ == "__main__":
    main()
