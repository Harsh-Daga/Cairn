"""Hatch build hook — bundle UI into wheel when static assets are missing."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

ROOT = Path(__file__).resolve().parent.parent
STATIC_INDEX = ROOT / "server" / "static" / "index.html"
BUILD_SCRIPT = ROOT / "scripts" / "build_ui.py"


class CustomBuildHook(BuildHookInterface):
    """Run scripts/build_ui.py when the wheel lacks bundled static assets."""

    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict[str, object]) -> None:
        del version, build_data
        if STATIC_INDEX.is_file():
            return
        if shutil.which("node") is None:
            self.app.display_warning(
                "server/static/index.html missing and node not found — "
                "wheel will ship without UI; run scripts/build_ui.py before publishing"
            )
            return
        self.app.display_info("Building UI assets for wheel packaging...")
        subprocess.run(
            [sys.executable, str(BUILD_SCRIPT)],
            cwd=ROOT,
            check=True,
        )
