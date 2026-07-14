"""Private-by-default local rendering for weekly recap cards."""

from __future__ import annotations

import html
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from server.api.payloads import build_recap

WIDTH = 1200
HEIGHT = 630


@dataclass(frozen=True)
class ShareCardData:
    total_spend_usd: float
    waste_pct: float
    reread_label: str
    reread_count: int
    failure_pattern: str
    archetype: str
    repo_name: str | None = None


def _safe_file_label(path: str | None) -> str:
    suffix = Path(path or "").suffix.lower()
    labels = {
        ".py": "a Python file",
        ".ts": "a TypeScript file",
        ".tsx": "a React file",
        ".js": "a JavaScript file",
        ".jsx": "a React file",
        ".md": "a Markdown file",
        ".json": "a JSON file",
        ".yaml": "a YAML file",
        ".yml": "a YAML file",
        ".rs": "a Rust file",
        ".go": "a Go file",
    }
    return labels.get(suffix, "a source file")


def _archetype(
    *, read_write_ratio: float, exploration_ratio: float, retry_rate: float, tool_entropy: float
) -> str:
    if retry_rate >= 0.2 or read_write_ratio >= 4:
        return "The Anxious Re-reader"
    if tool_entropy >= 1.5:
        return "The Tool Hoarder"
    if exploration_ratio >= 3:
        return "The Trail Mapper"
    return "The Steady Builder"


def build_share_card_data(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    repo_name: str | None = None,
) -> ShareCardData:
    """Aggregate share-safe labels; raw paths and commands never enter the result."""
    recap = build_recap(conn, workspace_id=workspace_id)
    since = (datetime.now(UTC) - timedelta(days=7)).isoformat()
    reread = conn.execute(
        """
        SELECT s.path_rel, COUNT(*) AS reads
        FROM spans s JOIN traces t ON t.trace_id = s.trace_id
        WHERE t.workspace_id = ? AND t.started_at >= ? AND s.name = 'read'
          AND s.path_rel IS NOT NULL
        GROUP BY s.path_rel
        ORDER BY reads DESC
        LIMIT 1
        """,
        (workspace_id, since),
    ).fetchone()
    failure = conn.execute(
        """
        SELECT COUNT(*) AS failures
        FROM spans s JOIN traces t ON t.trace_id = s.trace_id
        WHERE t.workspace_id = ? AND t.started_at >= ? AND s.status = 'error'
        GROUP BY s.name
        ORDER BY failures DESC
        LIMIT 1
        """,
        (workspace_id, since),
    ).fetchone()
    fingerprint = conn.execute(
        """
        SELECT AVG(f.read_write_ratio) AS read_write_ratio,
               AVG(f.exploration_ratio) AS exploration_ratio,
               AVG(f.retry_rate) AS retry_rate,
               AVG(f.tool_entropy) AS tool_entropy
        FROM fingerprints f JOIN traces t ON t.trace_id = f.trace_id
        WHERE t.workspace_id = ? AND t.started_at >= ?
        """,
        (workspace_id, since),
    ).fetchone()
    failures = int(failure["failures"] or 0) if failure else 0
    if failures > 1:
        failure_pattern = f"Ran the same failing command {failures} times"
    elif failures == 1:
        failure_pattern = "One failing command, then a change of course"
    else:
        failure_pattern = "No repeated failures — suspiciously serene"
    return ShareCardData(
        total_spend_usd=recap.money.total_spend_usd,
        waste_pct=recap.money.wasted_spend_pct,
        reread_label=_safe_file_label(str(reread["path_rel"]) if reread else None),
        reread_count=int(reread["reads"] or 0) if reread else 0,
        failure_pattern=failure_pattern,
        archetype=_archetype(
            read_write_ratio=float(fingerprint["read_write_ratio"] or 0) if fingerprint else 0,
            exploration_ratio=(
                float(fingerprint["exploration_ratio"] or 0) if fingerprint else 0
            ),
            retry_rate=float(fingerprint["retry_rate"] or 0) if fingerprint else 0,
            tool_entropy=float(fingerprint["tool_entropy"] or 0) if fingerprint else 0,
        ),
        repo_name=repo_name,
    )


def render_share_card(data: ShareCardData, output: Path) -> tuple[Path, Path]:
    """Write SVG source and a matching PNG card to local disk."""
    output = output.with_suffix(".png")
    output.parent.mkdir(parents=True, exist_ok=True)
    svg_path = output.with_suffix(".svg")
    svg_path.write_text(_render_svg(data), encoding="utf-8")
    _render_png(data, output)
    return output, svg_path


def _render_svg(data: ShareCardData) -> str:
    esc = html.escape
    repo = (
        f'<text x="1080" y="72" text-anchor="end" class="meta">{esc(data.repo_name)}</text>'
        if data.repo_name
        else ""
    )
    parts = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" '
            f'viewBox="0 0 {WIDTH} {HEIGHT}">'
        ),
        "<defs>",
        '<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">',
        '<stop stop-color="#111827"/><stop offset="1" stop-color="#090b10"/>',
        "</linearGradient>",
        "<style>",
        ".label{font:600 18px ui-monospace,monospace;fill:#9aa3b2;letter-spacing:2px}",
        ".value{font:700 58px ui-sans-serif,sans-serif;fill:#f7f8fa}",
        ".body{font:500 22px ui-sans-serif,sans-serif;fill:#d8dce5}",
        ".meta{font:500 17px ui-monospace,monospace;fill:#9aa3b2}",
        "</style></defs>",
        '<rect width="1200" height="630" rx="36" fill="url(#bg)"/>',
        '<circle cx="1080" cy="-20" r="270" fill="#8b7cff" opacity=".16"/>',
        '<circle cx="160" cy="650" r="230" fill="#4de2c5" opacity=".10"/>',
        '<text x="70" y="75" class="label">CAIRN · AGENT WRAPPED</text>',
        repo,
        (
            '<text x="70" y="145" class="body">'
            "Your local coding-agent week, measured.</text>"
        ),
        '<text x="70" y="235" class="label">TOTAL SPEND</text>',
        f'<text x="70" y="300" class="value">${data.total_spend_usd:,.2f}</text>',
        '<text x="430" y="235" class="label">EST. WASTE</text>',
        f'<text x="430" y="300" class="value">{data.waste_pct:.1f}%</text>',
        '<text x="790" y="235" class="label">MOST RE-READ</text>',
        f'<text x="790" y="275" class="body">{esc(data.reread_label)}</text>',
        f'<text x="790" y="307" class="meta">{data.reread_count} reads</text>',
        '<rect x="70" y="365" width="1060" height="1" fill="#343b4b"/>',
        '<text x="70" y="420" class="label">SIGNATURE MOVE</text>',
        f'<text x="70" y="462" class="body">{esc(data.failure_pattern)}</text>',
        '<text x="70" y="535" class="label">YOUR ARCHETYPE</text>',
        (
            '<text x="70" y="588" class="value" style="font-size:44px;fill:#a99cff">'
            f"{esc(data.archetype)}</text>"
        ),
        "</svg>",
    ]
    return "\n".join(part for part in parts if part)


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    return ImageFont.load_default(size=size)


def _render_png(data: ShareCardData, output: Path) -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), "#0b0e14")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, WIDTH - 1, HEIGHT - 1), radius=36, outline="#343b4b", width=2)
    draw.ellipse((910, -200, 1290, 180), fill="#211f3d")
    draw.ellipse((-100, 500, 290, 890), fill="#102b2b")
    draw.text((70, 52), "CAIRN · AGENT WRAPPED", font=_font(20), fill="#9aa3b2")
    if data.repo_name:
        draw.text((1130, 52), data.repo_name, font=_font(17), fill="#9aa3b2", anchor="ra")
    draw.text((70, 112), "Your local coding-agent week, measured.", font=_font(25), fill="#d8dce5")
    _metric(draw, 70, "TOTAL SPEND", f"${data.total_spend_usd:,.2f}")
    _metric(draw, 430, "EST. WASTE", f"{data.waste_pct:.1f}%")
    draw.text((790, 212), "MOST RE-READ", font=_font(18), fill="#9aa3b2")
    draw.text((790, 254), data.reread_label, font=_font(22), fill="#d8dce5")
    draw.text((790, 287), f"{data.reread_count} reads", font=_font(17), fill="#9aa3b2")
    draw.line((70, 365, 1130, 365), fill="#343b4b", width=1)
    draw.text((70, 398), "SIGNATURE MOVE", font=_font(18), fill="#9aa3b2")
    draw.text((70, 438), data.failure_pattern, font=_font(24), fill="#d8dce5")
    draw.text((70, 515), "YOUR ARCHETYPE", font=_font(18), fill="#9aa3b2")
    draw.text((70, 552), data.archetype, font=_font(42), fill="#a99cff")
    image.save(output, format="PNG", optimize=True)


def _metric(draw: ImageDraw.ImageDraw, x: int, label: str, value: str) -> None:
    draw.text((x, 212), label, font=_font(18), fill="#9aa3b2")
    draw.text((x, 250), value, font=_font(56), fill="#f7f8fa")
