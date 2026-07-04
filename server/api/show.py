"""Text waterfall renderer for `cairn show <id>`."""

from __future__ import annotations

import sqlite3

from server.models.span import Span
from server.store.repos.spans import SpanRepo
from server.store.repos.traces import TraceRepo


def _format_tokens(value: int | None) -> str:
    if value is None:
        return "-"
    if value >= 1000:
        return f"{value / 1000:.1f}K"
    return str(value)


def _span_label(span: Span) -> str:
    name = getattr(span, "name", None) or getattr(span, "kind", "span")
    kind = getattr(span, "kind", "")
    return f"{kind} · {name}"


def render_waterfall(conn: sqlite3.Connection, trace_id: str) -> str | None:
    """Render an indented text waterfall for a trace."""
    trace = TraceRepo.get(conn, trace_id)
    if trace is None:
        return None
    spans = SpanRepo.list_by_trace(conn, trace_id)
    if not spans:
        header = f"trace {trace_id} ({trace.source}) — 0 spans"
        return header

    by_parent: dict[str | None, list[Span]] = {}
    for span in spans:
        by_parent.setdefault(span.parent_span_id, []).append(span)

    lines: list[str] = []
    title = trace.title or trace_id
    lines.append(f"{title}  [{trace.source}]  cost=${trace.cost:.2f}")
    lines.append(f"{'span':<40} {'in':>8} {'out':>8} {'ms':>8}")
    lines.append("-" * 68)

    def _walk(parent_id: str | None, depth: int) -> None:
        for span in by_parent.get(parent_id, []):
            indent = "  " * depth
            in_tok = _format_tokens(span.input_tokens)
            out_tok = _format_tokens(span.output_tokens)
            dur = str(span.duration_ms) if span.duration_ms is not None else "-"
            label = _span_label(span)[:40]
            flag = " !" if span.status == "error" else ""
            lines.append(f"{indent}{label:<40} {in_tok:>8} {out_tok:>8} {dur:>8}{flag}")
            _walk(span.span_id, depth + 1)

    _walk(None, 0)
    return "\n".join(lines)
