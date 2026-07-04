#!/usr/bin/env python3
"""Build UI static assets into server/static/ for packaging."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UI_DIR = ROOT / "ui"
STATIC_DIR = ROOT / "server" / "static"
TYPES_OUT = UI_DIR / "src" / "lib" / "types.ts"
OPENAPI_PLACEHOLDER = (
    "/** Placeholder types - generated from OpenAPI in scripts/build_ui.py (Phase 7). */\n\n"
    "export interface TraceRow {\n"
    "  trace_id: string;\n"
    "  title: string | null;\n"
    "  source: string;\n"
    "  started_at: string | null;\n"
    "  cost: number;\n"
    "  input_tokens: number;\n"
    "  output_tokens: number;\n"
    "}\n\n"
    "export interface InsightRow {\n"
    "  insight_id: string;\n"
    "  title: string;\n"
    "  severity: string;\n"
    "  state: string;\n"
    "}\n\n"
    'export type TimeRange = "24h" | "7d" | "30d" | "90d";\n'
)


def run(cmd: list[str], cwd: Path) -> None:
    """Run a subprocess command, exiting on failure."""
    print(f"$ {' '.join(cmd)}")
    subprocess.run(cmd, cwd=cwd, check=True)


def ensure_npm_deps() -> None:
    """Install npm dependencies if node_modules is missing."""
    if not (UI_DIR / "node_modules").is_dir():
        run(["npm", "install"], UI_DIR)


def generate_types() -> None:
    """Generate TypeScript types from OpenAPI (placeholder until Phase 7)."""
    TYPES_OUT.write_text(OPENAPI_PLACEHOLDER, encoding="utf-8")
    print(f"Wrote placeholder types to {TYPES_OUT.relative_to(ROOT)}")


def build_ui() -> None:
    """Run vite build."""
    ensure_npm_deps()
    run(["npm", "run", "build"], UI_DIR)
    if not (STATIC_DIR / "index.html").is_file():
        print("ERROR: build did not produce index.html", file=sys.stderr)
        sys.exit(1)
    print(f"UI built to {STATIC_DIR.relative_to(ROOT)}")


def clean() -> None:
    """Remove built static assets."""
    if STATIC_DIR.is_dir():
        for child in STATIC_DIR.iterdir():
            if child.name == ".gitkeep":
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    print("Cleaned server/static/")


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "clean":
        clean()
        return
    build_ui()


if __name__ == "__main__":
    main()
