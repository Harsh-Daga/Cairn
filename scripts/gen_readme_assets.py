#!/usr/bin/env python3
"""Generate README preview SVGs (visible mockups, not 1×1 placeholders)."""
# ruff: noqa: E501

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "docs" / "assets"

BG = "#1a1816"
PANEL = "#2a2622"
BORDER = "#3d3830"
COPPER = "#aa9977"
BONE = "#e8e4dc"
CINDER = "#8a8278"
MALACHITE = "#6b9e78"
PATINA = "#5a8a82"
LAPIS = "#5a7a9e"
OCHRE = "#c4a055"


def _svg_header(w: int, h: int) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" role="img">'
        f'<rect width="100%" height="100%" fill="{BG}"/>'
    )


def _rail(x: int, h: int) -> str:
    items = ["Overview", "Sessions", "Insights", "Optimize", "Live"]
    out = f'<rect x="{x}" y="0" width="120" height="{h}" fill="{PANEL}" stroke="{BORDER}"/>'
    for i, label in enumerate(items):
        yy = 48 + i * 36
        active = i == 0
        fill = COPPER if active else CINDER
        out += f'<text x="{x + 16}" y="{yy}" fill="{fill}" font-family="monospace" font-size="11">{label}</text>'
    return out


def hero_svg() -> str:
    w, h = 960, 420
    s = _svg_header(w, h)
    s += _rail(0, h)
    s += f'<rect x="120" y="0" width="{w - 120}" height="48" fill="{PANEL}" stroke="{BORDER}"/>'
    s += f'<text x="140" y="30" fill="{BONE}" font-family="monospace" font-size="12">CAIRN · 85 sessions · live</text>'
    s += f'<rect x="140" y="68" width="280" height="72" fill="{PANEL}" stroke="{BORDER}" rx="4"/>'
    s += f'<text x="156" y="92" fill="{COPPER}" font-family="monospace" font-size="10">TRACES</text>'
    s += f'<text x="156" y="118" fill="{BONE}" font-family="sans-serif" font-size="22">85</text>'
    s += f'<rect x="440" y="68" width="280" height="72" fill="{PANEL}" stroke="{BORDER}" rx="4"/>'
    s += f'<text x="456" y="92" fill="{COPPER}" font-family="monospace" font-size="10">WASTE</text>'
    s += f'<text x="456" y="118" fill="{OCHRE}" font-family="sans-serif" font-size="22">12%</text>'
    s += f'<rect x="140" y="160" width="{w - 180}" height="220" fill="{PANEL}" stroke="{BORDER}" rx="4"/>'
    for i, (label, color, width) in enumerate(
        [
            ("context", LAPIS, 180),
            ("tools", PATINA, 120),
            ("results", OCHRE, 240),
            ("history", MALACHITE, 160),
        ]
    ):
        x = 160 + i * 190
        s += f'<rect x="{x}" y="200" width="{width}" height="24" fill="{color}" opacity="0.7" rx="2"/>'
        s += f'<text x="{x}" y="250" fill="{CINDER}" font-family="monospace" font-size="9">{label}</text>'
    s += f'<text x="480" y="395" fill="{CINDER}" font-family="monospace" font-size="10">Overview → replay → blame</text>'
    return s + "</svg>"


def overview_svg() -> str:
    w, h = 640, 360
    s = _svg_header(w, h)
    s += _rail(0, h)
    s += f'<rect x="130" y="24" width="220" height="64" fill="{PANEL}" stroke="{BORDER}" rx="3"/>'
    s += f'<text x="146" y="48" fill="{COPPER}" font-family="monospace" font-size="9">SESSIONS</text>'
    s += f'<text x="146" y="72" fill="{BONE}" font-size="20">85</text>'
    s += f'<rect x="370" y="24" width="240" height="64" fill="{PANEL}" stroke="{BORDER}" rx="3"/>'
    s += f'<text x="386" y="48" fill="{COPPER}" font-family="monospace" font-size="9">TAIL RISK</text>'
    s += f'<text x="386" y="72" fill="{OCHRE}" font-size="18">$42 worst-case</text>'
    for i in range(8):
        bh = 40 + (i % 5) * 18
        s += f'<rect x="{150 + i * 58}" y="{360 - bh - 40}" width="36" height="{bh}" fill="{PATINA}" opacity="0.65" rx="2"/>'
    s += f'<text x="320" y="340" fill="{CINDER}" font-family="monospace" font-size="10">Overview KPIs</text>'
    return s + "</svg>"


def session_detail_svg() -> str:
    w, h = 640, 360
    s = _svg_header(w, h)
    s += f'<rect x="16" y="16" width="608" height="32" fill="{PANEL}" stroke="{BORDER}"/>'
    s += f'<text x="28" y="36" fill="{BONE}" font-family="monospace" font-size="11">Session · waterfall + replay scrubber</text>'
    s += f'<rect x="16" y="56" width="420" height="288" fill="{PANEL}" stroke="{BORDER}"/>'
    rows = [
        ("user_msg", LAPIS, 120),
        ("tool_call", PATINA, 200),
        ("tool_result", OCHRE, 280),
        ("assistant", MALACHITE, 160),
    ]
    for i, (kind, color, bar_w) in enumerate(rows):
        y = 80 + i * 56
        s += f'<text x="28" y="{y + 12}" fill="{CINDER}" font-family="monospace" font-size="9">{kind}</text>'
        s += f'<rect x="140" y="{y}" width="{bar_w}" height="16" fill="{color}" opacity="0.75" rx="2"/>'
    s += f'<rect x="448" y="56" width="176" height="288" fill="{PANEL}" stroke="{BORDER}"/>'
    s += f'<text x="462" y="80" fill="{COPPER}" font-family="monospace" font-size="9">INSPECTOR</text>'
    s += f'<text x="462" y="110" fill="{BONE}" font-size="11">waste: oversize result</text>'
    return s + "</svg>"


def optimize_verdict_svg() -> str:
    w, h = 640, 360
    s = _svg_header(w, h)
    stations = ["proposed", "applied", "measuring", "verdict"]
    for i, st in enumerate(stations):
        x = 40 + i * 150
        active = st == "verdict"
        stroke = COPPER if active else BORDER
        s += f'<rect x="{x}" y="40" width="120" height="56" fill="{PANEL}" stroke="{stroke}" rx="3"/>'
        s += f'<text x="{x + 12}" y="62" fill="{CINDER}" font-family="monospace" font-size="8">{st}</text>'
        s += f'<text x="{x + 12}" y="82" fill="{BONE}" font-size="16">{1 if active else 0}</text>'
    s += f'<rect x="40" y="120" width="560" height="200" fill="{PANEL}" stroke="{BORDER}" rx="4"/>'
    s += f'<text x="56" y="150" fill="{MALACHITE}" font-family="monospace" font-size="11">improved · waste ↓ 18%</text>'
    s += f'<rect x="56" y="170" width="320" height="12" fill="{BORDER}"/>'
    s += f'<rect x="120" y="170" width="80" height="12" fill="{MALACHITE}" opacity="0.8"/>'
    s += f'<text x="56" y="210" fill="{CINDER}" font-family="monospace" font-size="9">anytime-valid CI · n_eff=12</text>'
    return s + "</svg>"


def favicon_svg() -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32">'
        f'<rect width="32" height="32" fill="{BG}"/>'
        f'<ellipse cx="16" cy="22" rx="10" ry="4" fill="{COPPER}"/>'
        f'<ellipse cx="16" cy="16" rx="8" ry="3.5" fill="#8a7355"/>'
        f'<ellipse cx="16" cy="11" rx="6" ry="2.5" fill="#a89070"/>'
        "</svg>"
    )


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    files = {
        "hero.svg": hero_svg(),
        "overview.svg": overview_svg(),
        "session-detail.svg": session_detail_svg(),
        "optimize-verdict.svg": optimize_verdict_svg(),
        "favicon.svg": favicon_svg(),
    }
    for name, content in files.items():
        path = ASSETS / name
        path.write_text(content, encoding="utf-8")
        print(f"Wrote {path}")
    # Remove misleading 1×1 gif and flat PNG placeholders if present
    for stale in ("hero.gif", "overview.png", "session-detail.png", "optimize-verdict.png"):
        stale_path = ASSETS / stale
        if stale_path.exists():
            stale_path.unlink()
            print(f"Removed stale placeholder {stale_path}")


if __name__ == "__main__":
    main()
