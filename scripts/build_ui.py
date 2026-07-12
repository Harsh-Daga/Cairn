#!/usr/bin/env python3
"""Build UI static assets into server/static/ for packaging."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
UI_DIR = ROOT / "ui"
STATIC_DIR = ROOT / "server" / "static"
TYPES_OUT = UI_DIR / "src" / "lib" / "types.ts"

KEY_SCHEMAS = (
    "OverviewResponse",
    "TraceRow",
    "TracesListResponse",
    "Span",
    "SpanNode",
    "Trace",
    "TraceDetailResponse",
    "ReplayResponse",
    "InsightRow",
    "InsightsResponse",
    "EvidenceChainResponse",
    "ActionManifestEntry",
    "ActionsManifestResponse",
    "AgentAggregate",
    "AgentsResponse",
    "BehaviorResponse",
    "QualityResponse",
    "RegionsAnalyticsResponse",
    "WasteAnalyticsResponse",
    "ExperimentRow",
    "ExperimentsResponse",
    "ExperimentDetailResponse",
    "SearchHit",
    "SearchResponse",
    "WorkspaceAdapter",
    "PlanWindowGauge",
    "WorkspaceResponse",
    "DataNote",
    "NarrativeSentence",
    "TailRisk",
    "SpanLink",
    "UsageAnalyticsResponse",
    "TailAnalyticsResponse",
)


def run(cmd: list[str], cwd: Path) -> None:
    """Run a subprocess command, exiting on failure."""
    executable = cmd[0]
    if executable == "npm" and sys.platform == "win32":
        npm = shutil.which("npm") or shutil.which("npm.cmd")
        if npm:
            cmd = [npm, *cmd[1:]]
    print(f"$ {' '.join(cmd)}")
    subprocess.run(cmd, cwd=cwd, check=True)


def ensure_npm_deps() -> None:
    """Install npm dependencies if node_modules is missing."""
    if not (UI_DIR / "node_modules").is_dir():
        run(["npm", "install"], UI_DIR)


def _ts_type(schema: dict[str, Any] | bool, schemas: dict[str, Any]) -> str:
    if isinstance(schema, bool):
        return "unknown" if schema else "never"

    if "$ref" in schema:
        ref_name = schema["$ref"].rsplit("/", maxsplit=1)[-1]
        return ref_name

    if "anyOf" in schema:
        parts = [_ts_type(part, schemas) for part in schema["anyOf"]]
        nullable = "null" in parts
        non_null = [p for p in parts if p != "null"]
        if nullable and len(non_null) == 1:
            return f"{non_null[0]} | null"
        return " | ".join(dict.fromkeys(parts))

    if "oneOf" in schema:
        parts = [_ts_type(part, schemas) for part in schema["oneOf"]]
        return " | ".join(dict.fromkeys(parts))

    schema_type = schema.get("type")
    if schema_type == "string":
        if "enum" in schema:
            return " | ".join(json.dumps(v) for v in schema["enum"])
        return "string"
    if schema_type == "integer":
        return "number"
    if schema_type == "number":
        return "number"
    if schema_type == "boolean":
        return "boolean"
    if schema_type == "null":
        return "null"
    if schema_type == "array":
        items = schema.get("items", {})
        return f"{_ts_type(items, schemas)}[]"
    if schema_type == "object" or "properties" in schema:
        additional = schema.get("additionalProperties")
        if additional is not None and not schema.get("properties"):
            if additional is True:
                return "Record<string, unknown>"
            if additional is False:
                return "Record<string, never>"
            return f"Record<string, {_ts_type(additional, schemas)}>"
        return "Record<string, unknown>"
    if schema_type is None and "enum" in schema:
        return " | ".join(json.dumps(v) for v in schema["enum"])
    return "unknown"


def _render_interface(name: str, schema: dict[str, Any], schemas: dict[str, Any]) -> str:
    props = schema.get("properties", {})
    required = set(schema.get("required", []))
    lines = [f"export interface {name} {{"]
    for prop_name, prop_schema in props.items():
        optional = "" if prop_name in required else "?"
        ts_type = _ts_type(prop_schema, schemas)
        lines.append(f"  {prop_name}{optional}: {ts_type};")
    lines.append("}")
    return "\n".join(lines)


def _openapi_to_typescript(openapi: dict[str, Any]) -> str:
    schemas: dict[str, Any] = openapi.get("components", {}).get("schemas", {})
    if not schemas:
        msg = "OpenAPI schema has no components.schemas"
        raise ValueError(msg)

    header = (
        "/** Auto-generated from FastAPI OpenAPI — do not edit by hand. */\n"
        "/** Regenerate via `python scripts/build_ui.py` (optional OPENAPI_GEN=1). */\n\n"
    )

    enum_types: list[str] = []
    interfaces: list[str] = []

    for name in KEY_SCHEMAS:
        schema = schemas.get(name)
        if schema is None:
            continue
        if schema.get("type") == "string" and "enum" in schema:
            enum_types.append(
                f"export type {name} = {' | '.join(json.dumps(v) for v in schema['enum'])};"
            )
        else:
            interfaces.append(_render_interface(name, schema, schemas))

    extra_enums = [
        ("InsightSeverity", schemas.get("InsightSeverity")),
        ("InsightLifecycle", schemas.get("InsightLifecycle")),
        ("SpanKind", schemas.get("SpanKind")),
    ]
    for enum_name, enum_schema in extra_enums:
        if enum_schema and "enum" in enum_schema:
            vals = " | ".join(json.dumps(v) for v in enum_schema["enum"])
            enum_types.append(f"export type {enum_name} = {vals};")

    time_range = 'export type TimeRange = "24h" | "7d" | "30d" | "90d";\n'
    body = "\n\n".join([*enum_types, *interfaces])
    return header + time_range + "\n" + body + "\n"


def _fetch_openapi_schema() -> dict[str, Any]:
    from server.app import create_app

    app = create_app()
    return app.openapi()


def generate_types() -> None:
    """Generate TypeScript types from OpenAPI; skip on failure unless OPENAPI_GEN=1."""
    strict = os.environ.get("OPENAPI_GEN") == "1"
    try:
        openapi = _fetch_openapi_schema()
        types_content = _openapi_to_typescript(openapi)
    except Exception as exc:
        if strict:
            print(f"ERROR: OpenAPI type generation failed: {exc}", file=sys.stderr)
            raise
        print(f"Skipping OpenAPI type generation: {exc}")
        return

    if not strict:
        print(
            f"OpenAPI type generation OK ({len(types_content)} chars); "
            "set OPENAPI_GEN=1 to overwrite ui/src/lib/types.ts",
        )
        return

    TYPES_OUT.write_text(types_content, encoding="utf-8")
    print(f"Wrote generated types to {TYPES_OUT.relative_to(ROOT)}")


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
    generate_types()
    build_ui()


if __name__ == "__main__":
    main()
