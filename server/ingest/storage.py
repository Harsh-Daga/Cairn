"""Content storage modes: Metrics / Balanced / Forensic / Reference."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from server.configuration import StorageConfig, load_config
from server.export.scrub import scrub_text
from server.models.span import Span

StorageMode = Literal["metrics", "balanced", "forensic", "reference"]

# Higher rank = more invasive local raw-text retention.
_MODE_RANK: dict[StorageMode, int] = {
    "reference": 0,
    "metrics": 0,
    "balanced": 1,
    "forensic": 2,
}

_DEFAULT_BALANCED_MAX = 500
_DEFAULT_FORENSIC_MAX = 8_192


@dataclass(frozen=True, slots=True)
class StorageRuntime:
    mode: StorageMode
    text_inline_max: int
    scrub_at_ingest: bool
    balanced_retain_days: int
    limitation: str


def normalize_storage_mode(value: str | None) -> StorageMode:
    cleaned = (value or "balanced").strip().lower().replace("-", "_")
    if cleaned in {"metrics", "metrics_only", "metricsonly"}:
        return "metrics"
    if cleaned in {"forensic", "full"}:
        return "forensic"
    if cleaned in {"reference", "ref", "zero_copy", "zerocopy"}:
        return "reference"
    return "balanced"


def mode_rank(mode: StorageMode) -> int:
    return _MODE_RANK[mode]


def is_upgrade(current: StorageMode, new: StorageMode) -> bool:
    """True when new mode retains more invasive content than current."""
    return mode_rank(new) > mode_rank(current)


def resolve_storage_runtime(config: StorageConfig) -> StorageRuntime:
    mode = normalize_storage_mode(config.mode)
    if mode in {"metrics", "reference"}:
        text_max = 0
    elif mode == "forensic":
        text_max = int(config.text_inline_max or _DEFAULT_FORENSIC_MAX)
    else:
        text_max = int(config.text_inline_max or _DEFAULT_BALANCED_MAX)
    if mode == "reference":
        limitation = (
            "Reference mode keeps source logs authoritative for raw text. "
            "Cairn stores cursors, hashes, metrics, and outcomes (not pure zero-copy). "
            "Source drift is detected when logs move/rewrite. "
            "Mode upgrades require explicit confirmation."
        )
    else:
        limitation = (
            "Storage mode controls raw span text retention only. "
            "Hashes, tokens, costs, and outcomes remain. "
            "Mode upgrades require explicit confirmation."
        )
    return StorageRuntime(
        mode=mode,
        text_inline_max=max(0, text_max),
        scrub_at_ingest=bool(config.scrub_at_ingest),
        balanced_retain_days=max(1, int(config.balanced_retain_days)),
        limitation=limitation,
    )


def storage_status(workspace_root: Path) -> dict[str, Any]:
    runtime = resolve_storage_runtime(load_config(workspace_root).storage)
    retained = {
        "reference": [
            "ingest cursors",
            "tokens",
            "cost",
            "timing",
            "tool/file names",
            "content hashes",
            "outcomes",
        ],
        "metrics": [
            "tokens",
            "cost",
            "timing",
            "tool/file names",
            "content hashes",
            "outcomes",
        ],
        "balanced": [
            "recent truncated text_inline",
            "hashes",
            "metrics",
            "outcomes",
        ],
        "forensic": [
            "full available local text_inline (within truncate cap)",
            "hashes",
            "metrics",
            "outcomes",
        ],
    }[runtime.mode]
    omitted = {
        "reference": [
            "raw prompt/assistant/tool-result text (source logs authoritative)",
        ],
        "metrics": ["raw prompt/assistant/tool-result text"],
        "balanced": ["text older than balanced_retain_days (after strip)", "untruncated blobs"],
        "forensic": [],
    }[runtime.mode]
    payload: dict[str, Any] = {
        "mode": runtime.mode,
        "text_inline_max": runtime.text_inline_max,
        "scrub_at_ingest": runtime.scrub_at_ingest,
        "balanced_retain_days": runtime.balanced_retain_days,
        "retains": retained,
        "omits": omitted,
        "warning": (
            "Forensic retains the most local content; never default for team exports."
            if runtime.mode == "forensic"
            else (
                "Reference mode: replay of raw text requires intact source logs."
                if runtime.mode == "reference"
                else None
            )
        ),
        "limitation": runtime.limitation,
    }
    if runtime.mode == "reference":
        from server.ingest.reference import reference_status

        payload["reference"] = reference_status(workspace_root)
    return payload


def apply_content_policy(
    span: Span,
    *,
    workspace_root: Path,
    runtime: StorageRuntime | None = None,
) -> Span:
    """Apply workspace storage mode to one span before persist (hashes preserved)."""
    policy = runtime or resolve_storage_runtime(load_config(workspace_root).storage)
    text = span.text_inline
    if policy.mode in {"metrics", "reference"}:
        text = None
    elif text:
        if policy.scrub_at_ingest:
            text = scrub_text(text, workspace_root)
        if policy.text_inline_max <= 0:
            text = None
        elif len(text) > policy.text_inline_max:
            text = text[: policy.text_inline_max]
    if text == span.text_inline:
        return span
    return span.model_copy(update={"text_inline": text})


def apply_policy_to_spans(
    spans: list[Span],
    *,
    workspace_root: Path,
) -> list[Span]:
    runtime = resolve_storage_runtime(load_config(workspace_root).storage)
    return [
        apply_content_policy(span, workspace_root=workspace_root, runtime=runtime) for span in spans
    ]


def strip_inline_content(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    mode: StorageMode | None = None,
    retain_days: int | None = None,
    limit: int = 5_000,
) -> dict[str, Any]:
    """
    Null out text_inline without deleting metrics/hashes.

    - metrics/reference: strip all workspace span text
    - balanced: strip text older than retain_days (by trace.started_at)
    - forensic: no-op (returns stripped=0)
    """
    resolved = mode or "metrics"
    if resolved == "forensic":
        return {
            "mode": resolved,
            "stripped": 0,
            "remaining_with_text": _count_with_text(conn, workspace_id),
            "limitation": "Forensic mode does not strip retained text.",
        }
    params: list[Any] = [workspace_id]
    age_clause = ""
    if resolved == "balanced":
        days = max(1, int(retain_days or 14))
        cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
        age_clause = " AND t.started_at < ?"
        params.append(cutoff)
    params.append(max(1, min(int(limit), 50_000)))
    cur = conn.execute(
        f"""
        UPDATE spans
        SET text_inline = NULL
        WHERE span_id IN (
          SELECT s.span_id
          FROM spans s
          JOIN traces t ON t.trace_id = s.trace_id
          WHERE t.workspace_id = ?
            AND s.text_inline IS NOT NULL
            AND s.text_inline != ''
            {age_clause}
          ORDER BY t.started_at ASC
          LIMIT ?
        )
        """,
        params,
    )
    return {
        "mode": resolved,
        "stripped": int(cur.rowcount or 0),
        "remaining_with_text": _count_with_text(conn, workspace_id),
        "limitation": (
            "Strip nulls text_inline only; hashes/tokens/costs/outcomes remain. "
            "Resumable — re-run until remaining_with_text reaches the mode target."
        ),
    }


def _count_with_text(conn: sqlite3.Connection, workspace_id: str) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM spans s
        JOIN traces t ON t.trace_id = s.trace_id
        WHERE t.workspace_id = ?
          AND s.text_inline IS NOT NULL
          AND s.text_inline != ''
        """,
        (workspace_id,),
    ).fetchone()
    return int(row["n"] or 0) if row is not None else 0
