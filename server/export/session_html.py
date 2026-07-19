"""Self-contained scrubbed session HTML export (no scripts, no remote loads)."""

from __future__ import annotations

import html
import re
import sqlite3
from pathlib import Path
from typing import Any

from server.analyze.git_privacy import export_path_warnings
from server.analyze.postmortem import build_postmortem
from server.api.payload_domains.traces import build_trace_detail
from server.api.show import render_waterfall
from server.export.scrub import scrub_text
from server.util.private_files import ensure_private_dir, write_private_text

SESSION_HTML_SCHEMA = "cairn.session_html.v1"
SIZE_WARNING_SPANS = 400
SIZE_WARNING_CHARS = 750_000

_CSP = (
    "default-src 'none'; script-src 'none'; style-src 'unsafe-inline'; "
    "img-src data:; font-src 'none'; connect-src 'none'; object-src 'none'; "
    "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)

_CSS = "\n".join(
    [
        ":root { color-scheme: light dark; --fg:#1a1a1a; --muted:#5a5a5a;",
        "--bg:#f7f5f0; --card:#fff; --line:#d8d2c4; --warn:#8a4b12; }",
        "@media (prefers-color-scheme: dark) {",
        ":root { --fg:#ece8df; --muted:#a39e93; --bg:#161411;",
        "--card:#221f1a; --line:#3a342c; --warn:#e0a060; }",
        "}",
        "body { margin:0; font:14px/1.45 ui-sans-serif,system-ui,sans-serif;",
        "color:var(--fg); background:var(--bg); }",
        "main { max-width:920px; margin:0 auto; padding:1.5rem; }",
        "h1,h2 { font-weight:650; letter-spacing:-0.02em; }",
        "h1 { font-size:1.4rem; margin:0 0 0.35rem; }",
        "h2 { font-size:1.05rem; margin:1.5rem 0 0.5rem;",
        "border-bottom:1px solid var(--line); padding-bottom:0.35rem; }",
        ".meta,.warn,.note { color:var(--muted); font-size:0.85rem; }",
        ".warn { color:var(--warn); }",
        "section { background:var(--card); border:1px solid var(--line);",
        "border-radius:6px; padding:0.9rem 1rem; margin:0.75rem 0; }",
        "pre { white-space:pre-wrap; word-break:break-word; margin:0;",
        "font:12px/1.4 ui-monospace,monospace; }",
        "ul { margin:0.25rem 0 0; padding-left:1.2rem; }",
        "li { margin:0.2rem 0; }",
    ]
)


def export_session_html(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    workspace_root: Path,
    trace_id: str,
    output: Path | None = None,
) -> dict[str, Any]:
    """Write a scrubbed self-contained HTML report for one session."""
    detail = build_trace_detail(conn, trace_id)
    if detail is None or detail.trace.workspace_id != workspace_id:
        return {"ok": False, "error": "trace_not_found", "trace_id": trace_id}

    document = render_session_html(
        conn,
        workspace_root=workspace_root,
        detail=detail,
    )
    out_dir = (workspace_root / ".cairn" / "exports").resolve()
    ensure_private_dir(out_dir)
    out_path = (
        output.expanduser().resolve()
        if output is not None
        else out_dir / f"session-{trace_id}.html"
    )
    write_private_text(out_path, document)

    warnings: list[str] = []
    span_count = len(detail.spans)
    if span_count >= SIZE_WARNING_SPANS or len(document) >= SIZE_WARNING_CHARS:
        warnings.append(
            f"Large session export ({span_count} spans, {len(document)} chars); "
            "review before sharing."
        )
    warnings.extend(export_path_warnings(workspace_root, out_path))
    return {
        "ok": True,
        "schema": SESSION_HTML_SCHEMA,
        "path": str(out_path),
        "trace_id": trace_id,
        "scrubbed": True,
        "bytes": len(document.encode("utf-8")),
        "span_count": span_count,
        "warnings": warnings,
    }


def render_session_html(
    conn: sqlite3.Connection,
    *,
    workspace_root: Path,
    detail: Any,
) -> str:
    """Render deterministic CSP HTML from a TraceDetailResponse."""
    trace = detail.trace
    trace_id = trace.trace_id
    waterfall = render_waterfall(conn, trace_id) or "(waterfall unavailable)"
    waterfall = scrub_text(waterfall, workspace_root)

    transcript_lines: list[str] = []
    for span in sorted(detail.spans, key=lambda item: (item.seq, item.span_id)):
        label = f"{span.seq:04d} {span.kind}"
        if span.name:
            label += f"/{span.name}"
        if span.status:
            label += f" [{span.status}]"
        text = scrub_text(str(span.text_inline or ""), workspace_root) if span.text_inline else ""
        if text:
            transcript_lines.append(f"{label}: {text}")
        else:
            transcript_lines.append(label)

    postmortem = detail.postmortem
    if postmortem is None:
        # Rebuild from models already on detail when response omitted markdown-only path.
        postmortem_raw = build_postmortem(
            trace=trace,
            spans=list(detail.spans),
            diagnostic=detail.diagnostics,
            outcome=detail.outcome,
        )
        postmortem_md = (
            scrub_text(str(postmortem_raw.get("markdown") or ""), workspace_root)
            if postmortem_raw
            else "No postmortem available for this session."
        )
    else:
        postmortem_md = scrub_text(str(postmortem.markdown or ""), workspace_root)

    evidence = _evidence_lines(detail, workspace_root)
    size_note = ""
    if len(detail.spans) >= SIZE_WARNING_SPANS:
        size_note = (
            f'<p class="warn">Size warning: {len(detail.spans)} spans exported. '
            "Share only if intended.</p>"
        )

    title = scrub_text(str(trace.title or trace_id), workspace_root)
    evidence_html = "<ul>" + "".join(f"<li>{_esc(line)}</li>" for line in evidence) + "</ul>"
    transcript_text = chr(10).join(transcript_lines) if transcript_lines else "(no span text)"
    sections = [
        ("Evidence summary", evidence_html),
        ("Waterfall", f"<pre>{_esc(waterfall)}</pre>"),
        ("Transcript", f"<pre>{_esc(transcript_text)}</pre>"),
        ("Postmortem", f"<pre>{_esc(postmortem_md)}</pre>"),
    ]

    body_parts = [
        "<main>",
        f"<h1>Cairn session · {_esc(trace_id)}</h1>",
        f'<p class="meta">Source {_esc(trace.source)} · status {_esc(trace.status)} · '
        f"title {_esc(title)}</p>",
        '<p class="note">Self-contained local export. Scrubbed paths/secrets. '
        "No scripts. No remote requests. Not a causal report.</p>",
        size_note,
    ]
    for heading, content in sections:
        body_parts.append(f"<section><h2>{_esc(heading)}</h2>{content}</section>")
    body_parts.append("</main>")

    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        f'<meta http-equiv="Content-Security-Policy" content="{_CSP}">\n'
        f"<title>Cairn session {_esc(trace_id)}</title>\n"
        f"<style>{_CSS}</style>\n"
        "</head>\n"
        f"<body>\n{''.join(body_parts)}\n</body>\n"
        "</html>\n"
    )


def _evidence_lines(detail: Any, workspace_root: Path) -> list[str]:
    lines: list[str] = []
    trace = detail.trace
    lines.append(
        f"Tokens in/out: {int(trace.input_tokens or 0)}/{int(trace.output_tokens or 0)}; "
        f"cost={float(trace.cost or 0.0):.4f} ({trace.cost_source})"
    )
    lines.append(f"Spans: {len(detail.spans)}; waste_tokens={int(trace.waste_tokens or 0)}")
    if detail.outcome is not None:
        outcome = detail.outcome
        lines.append(
            scrub_text(
                f"Outcome label={outcome.outcome_label}; quality={outcome.quality_score}; "
                f"human={outcome.human_label}",
                workspace_root,
            )
        )
    else:
        lines.append("Outcome: none recorded")
    if detail.diagnostics is not None:
        diag = detail.diagnostics
        lines.append(
            scrub_text(
                f"Diagnose primary={diag.primary_category}; "
                f"signature={diag.failure_signature}; "
                f"cascade_blast_tokens={diag.cascade_blast_tokens}",
                workspace_root,
            )
        )
    else:
        lines.append("Diagnose: none recorded")
    if detail.quality is not None:
        quality = detail.quality
        lines.append(
            scrub_text(
                f"Data quality cost_source={quality.cost_source}",
                workspace_root,
            )
        )
    for shield in list(detail.shields or [])[:6]:
        lines.append(
            scrub_text(
                f"Shield {shield.shield} ({shield.state}): {shield.summary}",
                workspace_root,
            )
        )
    return lines


def _esc(value: str) -> str:
    return html.escape(value, quote=True)


def assert_hostile_safe(document: str) -> None:
    """Raise AssertionError when known hostile patterns remain (test helper)."""
    if re.search(r"https?://", document, re.I):
        raise AssertionError("remote URL leaked into session HTML")
    if "<script" in document.lower():
        raise AssertionError("script markup present in session HTML")
    if re.search(r"\son\w+\s*=", document, re.I):
        raise AssertionError("inline event handler present in session HTML")
