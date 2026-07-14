"""Focused live-sample diagnostics for one ingest adapter."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from server.ingest.parse_health import inspect_stream_shape
from server.ingest.registry import build_adapters

_ACCURACY_DATA = Path(__file__).with_name("accuracy_data.json")


def run_adapter_doctor(
    adapter_id: str,
    workspace_root: Path,
    *,
    sample_path: Path | None = None,
) -> dict[str, Any]:
    root = workspace_root.resolve()
    adapters = {adapter.adapter_id: adapter for adapter in build_adapters(root, "adapter-doctor")}
    adapter = adapters.get(adapter_id)
    if adapter is None:
        return {
            "ok": False,
            "adapter_id": adapter_id,
            "error": f"unknown adapter; available: {', '.join(sorted(adapters))}",
        }
    path = (
        sample_path.resolve()
        if sample_path is not None
        else _newest_path(adapter.detect())
    )
    if path is None or not path.is_file():
        return {
            "ok": False,
            "adapter_id": adapter_id,
            "error": "no live log sample detected; pass --sample PATH",
        }
    shape = inspect_stream_shape(adapter_id, path)
    parse_error: str | None = None
    try:
        parsed = adapter.parse_path(path)
    except Exception as exc:
        parsed = None
        parse_error = f"{type(exc).__name__}: {exc}"
    unknown = shape["unknown_fields"]
    dropped = int(parsed.dropped_events) if parsed is not None else 0
    return {
        "ok": parsed is not None and not unknown and dropped == 0,
        "adapter_id": adapter_id,
        "sample_path": str(path),
        **shape,
        "parsed": parsed is not None,
        "normalized_events": len(parsed.events) if parsed is not None else 0,
        "dropped_events": dropped,
        "parse_error": parse_error,
        "token_accuracy": _token_accuracy(adapter_id),
    }


def format_adapter_doctor(result: dict[str, Any]) -> str:
    if "error" in result:
        return f"Adapter doctor: {result['adapter_id']}\n\n✗ {result['error']}"
    recognized = ", ".join(result["recognized_fields"]) or "none"
    unknown = result["unknown_fields"]
    unknown_text = ", ".join(f"{key}×{value}" for key, value in unknown.items()) or "none"
    accuracy = result["token_accuracy"]
    if accuracy is None:
        accuracy_text = "not measured (no expected-token fixture in ACCURACY.md)"
    else:
        accuracy_text = (
            f"{accuracy['method']}, MAPE {float(accuracy['mape_pct']):.2f}% — {accuracy['note']}"
        )
    mark = "✓" if result["ok"] else "✗"
    lines = [
        f"Adapter doctor: {result['adapter_id']}",
        "",
        f"  sample              {result['sample_path']}",
        f"  records sampled     {result['records_sampled']}",
        f"  parsed              {'yes' if result['parsed'] else 'no'}",
        f"  normalized events   {result['normalized_events']}",
        f"  dropped events      {result['dropped_events']}",
        f"  recognized fields   {recognized}",
        f"  unknown fields      {unknown_text}",
        f"  token accuracy      {accuracy_text}",
        "",
        f"{mark} {'sample fully parsed' if result['ok'] else 'sample degraded or skipped'}",
    ]
    if result.get("parse_error"):
        lines.insert(-1, f"  parse error         {result['parse_error']}")
    return "\n".join(lines)


def _newest_path(refs: list[Any]) -> Path | None:
    paths = [ref.path for ref in refs if ref.path.is_file()]
    return max(paths, key=lambda path: path.stat().st_mtime_ns) if paths else None


def _token_accuracy(adapter_id: str) -> dict[str, Any] | None:
    rows = json.loads(_ACCURACY_DATA.read_text(encoding="utf-8"))
    value = rows.get(adapter_id)
    if value is None and adapter_id == "gemini_cli":
        value = rows.get("gemini")
    return dict(value) if isinstance(value, dict) else None
