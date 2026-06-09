"""Unified report schema with mandatory observability sections."""

from __future__ import annotations

from typing import Any

REPORT_VERSION = 1

REQUIRED_SECTIONS = (
    "summary",
    "narrative",
    "tool_usage",
    "artifacts",
    "graphs",
    "reproducibility",
)


def validate_report(payload: dict[str, Any]) -> list[str]:
    """Return validation errors; empty list means the report is well-formed."""
    errors: list[str] = []
    version = payload.get("cairn_report_version")
    if version != REPORT_VERSION:
        errors.append(f"cairn_report_version must be {REPORT_VERSION}, got {version!r}")

    kind = payload.get("kind")
    if kind not in ("capture", "provider"):
        errors.append(f"kind must be 'capture' or 'provider', got {kind!r}")

    for section in REQUIRED_SECTIONS:
        if section not in payload:
            errors.append(f"missing required section: {section}")
        elif not isinstance(payload[section], (dict, list)):
            errors.append(f"section {section} must be dict or list")

    graphs = payload.get("graphs")
    if isinstance(graphs, dict):
        for graph_kind in ("execution", "artifact", "dependency"):
            if graph_kind not in graphs:
                errors.append(f"graphs missing {graph_kind}")

    return errors
