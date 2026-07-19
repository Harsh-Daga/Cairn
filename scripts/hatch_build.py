"""Hatch build hook — bundle UI into wheel when static assets are missing."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

ROOT = Path(__file__).resolve().parent.parent
STATIC_INDEX = ROOT / "server" / "static" / "index.html"
STATIC_FILE_INDEX = ROOT / "server" / "static_file" / "index.html"
BUILD_SCRIPT = ROOT / "scripts" / "build_ui.py"


class CustomBuildHook(BuildHookInterface[Any]):
    """Run scripts/build_ui.py when the wheel lacks bundled static assets."""

    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict[str, object]) -> None:
        del version, build_data
        if STATIC_INDEX.is_file() and STATIC_FILE_INDEX.is_file():
            return
        if shutil.which("node") is None:
            raise RuntimeError(
                "server/static or server/static_file index missing and node not found — "
                "refusing to build an incomplete wheel; run scripts/build_ui.py first"
            )
        self.app.display_info("Building UI assets for wheel packaging...")
        subprocess.run(
            [sys.executable, str(BUILD_SCRIPT), "assets"],
            cwd=ROOT,
            check=True,
        )
