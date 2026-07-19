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
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
UI_DIR = ROOT / "ui"
STATIC_DIR = ROOT / "server" / "static"
STATIC_FILE_DIR = ROOT / "server" / "static_file"
TYPES_OUT = UI_DIR / "src" / "lib" / "generated" / "api-types.ts"
FILTER_TYPES_OUT = UI_DIR / "src" / "lib" / "generated" / "filter-grammar.ts"
COMPAT_OUT = ROOT / "docs" / "api" / "openapi-compat.json"
FILTER_SPEC_OUT = ROOT / "docs" / "api" / "filter-grammar.json"
API_DOC_OUT = ROOT / "docs" / "api" / "generated.md"
REQUEST_SCHEMAS = frozenset({"HTTPValidationError", "HumanLabelRequest", "ValidationError"})


def run(cmd: list[str], cwd: Path, *, env: dict[str, str] | None = None) -> None:
    """Run a subprocess command, exiting on failure."""
    executable = cmd[0]
    if executable == "npm" and sys.platform == "win32":
        npm = shutil.which("npm") or shutil.which("npm.cmd")
        if npm:
            cmd = [npm, *cmd[1:]]
    print(f"$ {' '.join(cmd)}")
    subprocess.run(cmd, cwd=cwd, env=env, check=True)


def ensure_npm_deps() -> None:
    """Install npm dependencies if node_modules is missing."""
    if not (UI_DIR / "node_modules").is_dir():
        run(["npm", "ci"], UI_DIR)


def _ts_type(schema: dict[str, Any] | bool, schemas: dict[str, Any]) -> str:
    if isinstance(schema, bool):
        return "unknown" if schema else "never"

    if "$ref" in schema:
        ref_name = str(schema["$ref"]).rsplit("/", maxsplit=1)[-1]
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
    if "allOf" in schema:
        parts = [_ts_type(part, schemas) for part in schema["allOf"]]
        return " & ".join(dict.fromkeys(parts))

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
        item_type = _ts_type(items, schemas)
        if " | " in item_type or " & " in item_type:
            item_type = f"({item_type})"
        return f"{item_type}[]"
    if schema_type == "object" or "properties" in schema:
        properties = schema.get("properties", {})
        if properties:
            required = set(schema.get("required", []))
            fields = []
            for name, value in properties.items():
                optional = "" if name in required else "?"
                fields.append(f"{json.dumps(name)}{optional}: {_ts_type(value, schemas)}")
            return "{ " + "; ".join(fields) + " }"
        additional = schema.get("additionalProperties")
        if additional is not None:
            if additional is True:
                return "Record<string, unknown>"
            if additional is False:
                return "Record<string, never>"
            return f"Record<string, {_ts_type(additional, schemas)}>"
        return "Record<string, unknown>"
    if schema_type is None and "enum" in schema:
        return " | ".join(json.dumps(v) for v in schema["enum"])
    return "unknown"


def _render_interface(
    name: str,
    schema: dict[str, Any],
    schemas: dict[str, Any],
    *,
    force_required: bool = False,
) -> str:
    props = schema.get("properties", {})
    required = set(schema.get("required", []))
    lines = [f"export interface {name} {{"]
    for prop_name, prop_schema in props.items():
        optional = "" if force_required or prop_name in required else "?"
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
        "/** Regenerate via `uv run python scripts/build_ui.py types`. */\n\n"
    )

    definitions: list[str] = []
    for name in sorted(schemas):
        schema = schemas[name]
        if schema.get("type") == "string" and "enum" in schema:
            definitions.append(
                f"export type {name} = {' | '.join(json.dumps(v) for v in schema['enum'])};"
            )
        elif schema.get("type") == "object" or "properties" in schema:
            definitions.append(
                _render_interface(
                    name,
                    schema,
                    schemas,
                    force_required=name not in REQUEST_SCHEMAS,
                )
            )
        else:
            definitions.append(f"export type {name} = {_ts_type(schema, schemas)};")
    return header + "\n\n".join(definitions) + "\n"


def _fetch_openapi_schema() -> dict[str, Any]:
    from server.app import create_app

    app = create_app()
    return app.openapi()


def generated_types_content() -> str:
    """Return deterministic TypeScript transport types from the live OpenAPI schema."""
    return _openapi_to_typescript(_fetch_openapi_schema())


def _filter_grammar_artifacts() -> tuple[str, str]:
    from server.query_filters import FILTER_SPECS

    spec_json = json.dumps(FILTER_SPECS, indent=2, sort_keys=True) + "\n"
    typescript = (
        "/** Auto-generated from server.query_filters.FILTER_SPECS — do not edit. */\n"
        "/** Regenerate via `uv run python scripts/build_ui.py types`. */\n\n"
        f"export const FILTER_SPECS = {json.dumps(FILTER_SPECS, sort_keys=True)} as const;\n\n"
        "export type FilterField = keyof typeof FILTER_SPECS;\n"
    )
    return typescript, spec_json


def _compatibility_snapshot(openapi: dict[str, Any]) -> dict[str, Any]:
    paths: dict[str, Any] = {}
    for path, methods in sorted(openapi["paths"].items()):
        paths[path] = {
            method: {
                "operation_id": operation["operationId"],
                "responses": sorted(operation.get("responses", {})),
            }
            for method, operation in sorted(methods.items())
        }
    schemas: dict[str, Any] = {}
    for name, schema in sorted(openapi.get("components", {}).get("schemas", {}).items()):
        schemas[name] = {
            "required": sorted(schema.get("required", [])),
            "properties": sorted(schema.get("properties", {})),
            "enum": schema.get("enum"),
        }
    return {"paths": paths, "schemas": schemas}


def _generated_api_markdown(openapi: dict[str, Any]) -> str:
    lines = [
        "# Generated HTTP API index",
        "",
        "Generated from FastAPI OpenAPI. Do not edit by hand.",
        "",
        "| Method | Path | Operation ID | Success schema |",
        "|---|---|---|---|",
    ]
    for path, methods in sorted(openapi["paths"].items()):
        for method, operation in sorted(methods.items()):
            success = operation.get("responses", {}).get("200", {})
            schema = success.get("content", {}).get("application/json", {}).get("schema", {})
            response_name = schema.get("$ref", "").rsplit("/", 1)[-1] or "inline/stream"
            lines.append(
                f"| {method.upper()} | `{path}` | `{operation['operationId']}` | "
                f"`{response_name}` |"
            )
    return "\n".join(lines) + "\n"


def generate_types(*, check: bool = False) -> None:
    """Write committed transport types, or fail when the committed copy drifted."""
    openapi = _fetch_openapi_schema()
    types_content = _openapi_to_typescript(openapi)
    compat_content = json.dumps(_compatibility_snapshot(openapi), indent=2, sort_keys=True) + "\n"
    docs_content = _generated_api_markdown(openapi)
    filter_types_content, filter_spec_content = _filter_grammar_artifacts()
    if check:
        expected = {
            TYPES_OUT: types_content,
            FILTER_TYPES_OUT: filter_types_content,
            COMPAT_OUT: compat_content,
            FILTER_SPEC_OUT: filter_spec_content,
            API_DOC_OUT: docs_content,
        }
        stale = [
            path.relative_to(ROOT)
            for path, content in expected.items()
            if not path.is_file() or path.read_text(encoding="utf-8") != content
        ]
        if stale:
            msg = (
                f"Generated API artifacts are stale: {', '.join(map(str, stale))}; "
                "run: uv run python scripts/build_ui.py types"
            )
            raise SystemExit(msg)
        print("Generated API artifacts are current")
        return
    for path, content in (
        (TYPES_OUT, types_content),
        (FILTER_TYPES_OUT, filter_types_content),
        (COMPAT_OUT, compat_content),
        (FILTER_SPEC_OUT, filter_spec_content),
        (API_DOC_OUT, docs_content),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        print(f"Wrote {path.relative_to(ROOT)}")


def build_ui() -> None:
    """Run vite build."""
    ensure_npm_deps()
    run(["npm", "run", "build"], UI_DIR)
    static_env = os.environ.copy()
    static_env["CAIRN_STATIC_IIFE"] = "1"
    run(["npm", "run", "build"], UI_DIR, env=static_env)
    # Vite clears its output directory before emitting assets. Keep the tracked
    # placeholder so a local build does not leave the repository dirty.
    (STATIC_DIR / ".gitkeep").write_text(
        "# Vite build output is copied here by scripts/build_ui.py.\n",
        encoding="utf-8",
    )
    (STATIC_FILE_DIR / ".gitkeep").write_text(
        "# File-compatible IIFE build output is copied here by scripts/build_ui.py.\n",
        encoding="utf-8",
    )
    if not (STATIC_DIR / "index.html").is_file():
        print("ERROR: build did not produce index.html", file=sys.stderr)
        sys.exit(1)
    if not (STATIC_FILE_DIR / "index.html").is_file():
        print("ERROR: file-compatible build did not produce index.html", file=sys.stderr)
        sys.exit(1)
    print(f"UI built to {STATIC_DIR.relative_to(ROOT)} and {STATIC_FILE_DIR.relative_to(ROOT)}")


def clean() -> None:
    """Remove built static assets."""
    for directory in (STATIC_DIR, STATIC_FILE_DIR):
        if directory.is_dir():
            for child in directory.iterdir():
                if child.name == ".gitkeep":
                    continue
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
    print("Cleaned server/static/ and server/static_file/")


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else "build"
    if command == "clean":
        clean()
        return
    if command == "types":
        generate_types()
        return
    if command == "types-check":
        generate_types(check=True)
        return
    if command == "assets":
        build_ui()
        return
    if command != "build":
        raise SystemExit(f"Unknown build_ui command: {command}")
    generate_types()
    build_ui()


if __name__ == "__main__":
    main()
