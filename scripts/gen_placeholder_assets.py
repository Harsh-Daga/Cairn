#!/usr/bin/env python3
"""Deprecated wrapper — use scripts/gen_readme_assets.py."""

from __future__ import annotations

import runpy
from pathlib import Path

if __name__ == "__main__":
    script = Path(__file__).resolve().parent / "gen_readme_assets.py"
    runpy.run_path(str(script), run_name="__main__")
