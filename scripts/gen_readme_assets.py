#!/usr/bin/env python3
# ruff: noqa: E501
"""Generate README preview assets (SVG source + PNG for GitHub/PyPI)."""

from __future__ import annotations

import sys
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
        out += (
            f'<text x="{x + 16}" y="{yy}" fill="{fill}" '
            f'font-family="monospace" font-size="11">{label}</text>'
        )
    return out


def hero_svg() -> str:
    w, h = 960, 420
    s = _svg_header(w, h)
    s += _rail(0, h)
    s += f'<rect x="120" y="0" width="{w - 120}" height="48" fill="{PANEL}" stroke="{BORDER}"/>'
    s += (
        f'<text x="140" y="30" fill="{BONE}" font-family="monospace" font-size="12">'
        "CAIRN · 85 sessions · live</text>"
    )
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
    s += (
        f'<text x="480" y="395" fill="{CINDER}" font-family="monospace" font-size="10">'
        "Overview → replay → blame</text>"
    )
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
        s += (
            f'<rect x="{150 + i * 58}" y="{360 - bh - 40}" width="36" height="{bh}" '
            f'fill="{PATINA}" opacity="0.65" rx="2"/>'
        )
    s += f'<text x="320" y="340" fill="{CINDER}" font-family="monospace" font-size="10">Overview KPIs</text>'
    return s + "</svg>"


def session_detail_svg() -> str:
    w, h = 640, 360
    s = _svg_header(w, h)
    s += f'<rect x="16" y="16" width="608" height="32" fill="{PANEL}" stroke="{BORDER}"/>'
    s += (
        f'<text x="28" y="36" fill="{BONE}" font-family="monospace" font-size="11">'
        "Session · waterfall + replay scrubber</text>"
    )
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
    s += (
        f'<text x="56" y="150" fill="{MALACHITE}" font-family="monospace" font-size="11">'
        "improved · waste ↓ 18%</text>"
    )
    s += f'<rect x="56" y="170" width="320" height="12" fill="{BORDER}"/>'
    s += f'<rect x="120" y="170" width="80" height="12" fill="{MALACHITE}" opacity="0.8"/>'
    s += (
        f'<text x="56" y="210" fill="{CINDER}" font-family="monospace" font-size="9">'
        "anytime-valid CI · n_eff=12</text>"
    )
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


def _hex(color: str) -> tuple[int, int, int]:
    value = color.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def _save_png(path: Path, size: tuple[int, int], draw_fn) -> None:
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:
        msg = (
            "pillow is required to render PNG README assets. "
            "Run: uv run --with pillow python scripts/gen_readme_assets.py"
        )
        raise RuntimeError(msg) from exc
    image = Image.new("RGB", size, _hex(BG))
    draw = ImageDraw.Draw(image)
    draw_fn(draw, size)
    image.save(path, format="PNG", optimize=True)


def _draw_rail(draw, height: int) -> None:
    draw.rectangle((0, 0, 120, height), fill=_hex(PANEL), outline=_hex(BORDER))
    for i, label in enumerate(["Overview", "Sessions", "Insights", "Optimize", "Live"]):
        color = COPPER if i == 0 else CINDER
        draw.text((16, 36 + i * 36), label, fill=_hex(color))


def _write_hero_png(path: Path) -> None:
    def draw(draw, size: tuple[int, int]) -> None:
        width, height = size
        _draw_rail(draw, height)
        draw.rectangle((120, 0, width, 48), fill=_hex(PANEL), outline=_hex(BORDER))
        draw.text((140, 16), "CAIRN · 85 sessions · live", fill=_hex(BONE))
        draw.rectangle((140, 68, 420, 140), fill=_hex(PANEL), outline=_hex(BORDER))
        draw.text((156, 82), "TRACES", fill=_hex(COPPER))
        draw.text((156, 102), "85", fill=_hex(BONE))
        draw.rectangle((440, 68, 720, 140), fill=_hex(PANEL), outline=_hex(BORDER))
        draw.text((456, 82), "WASTE", fill=_hex(COPPER))
        draw.text((456, 102), "12%", fill=_hex(OCHRE))
        draw.rectangle((140, 160, width - 40, 380), fill=_hex(PANEL), outline=_hex(BORDER))
        for i, (label, color, bar_w) in enumerate(
            [
                ("context", LAPIS, 180),
                ("tools", PATINA, 120),
                ("results", OCHRE, 240),
                ("history", MALACHITE, 160),
            ]
        ):
            x = 160 + i * 190
            draw.rectangle((x, 200, x + bar_w, 224), fill=_hex(color))
            draw.text((x, 238), label, fill=_hex(CINDER))
        draw.text((480, 385), "Overview → replay → blame", fill=_hex(CINDER))

    _save_png(path, (960, 420), draw)


def _write_overview_png(path: Path) -> None:
    def draw(draw, size: tuple[int, int]) -> None:
        _draw_rail(draw, size[1])
        draw.rectangle((130, 24, 350, 88), fill=_hex(PANEL), outline=_hex(BORDER))
        draw.text((146, 38), "SESSIONS", fill=_hex(COPPER))
        draw.text((146, 58), "85", fill=_hex(BONE))
        draw.rectangle((370, 24, 610, 88), fill=_hex(PANEL), outline=_hex(BORDER))
        draw.text((386, 38), "TAIL RISK", fill=_hex(COPPER))
        draw.text((386, 58), "$42 worst-case", fill=_hex(OCHRE))
        for i in range(8):
            bh = 40 + (i % 5) * 18
            draw.rectangle((150 + i * 58, 360 - bh - 40, 186 + i * 58, 320), fill=_hex(PATINA))
        draw.text((320, 330), "Overview KPIs", fill=_hex(CINDER))

    _save_png(path, (640, 360), draw)


def _write_session_detail_png(path: Path) -> None:
    def draw(draw, size: tuple[int, int]) -> None:
        draw.rectangle((16, 16, 624, 48), fill=_hex(PANEL), outline=_hex(BORDER))
        draw.text((28, 22), "Session · waterfall + replay scrubber", fill=_hex(BONE))
        draw.rectangle((16, 56, 436, 344), fill=_hex(PANEL), outline=_hex(BORDER))
        rows = [
            ("user_msg", LAPIS, 120),
            ("tool_call", PATINA, 200),
            ("tool_result", OCHRE, 280),
            ("assistant", MALACHITE, 160),
        ]
        for i, (kind, color, bar_w) in enumerate(rows):
            y = 80 + i * 56
            draw.text((28, y), kind, fill=_hex(CINDER))
            draw.rectangle((140, y, 140 + bar_w, y + 16), fill=_hex(color))
        draw.rectangle((448, 56, 624, 344), fill=_hex(PANEL), outline=_hex(BORDER))
        draw.text((462, 72), "INSPECTOR", fill=_hex(COPPER))
        draw.text((462, 98), "waste: oversize result", fill=_hex(BONE))

    _save_png(path, (640, 360), draw)


def _write_optimize_png(path: Path) -> None:
    def draw(draw, size: tuple[int, int]) -> None:
        for i, station in enumerate(["proposed", "applied", "measuring", "verdict"]):
            x = 40 + i * 150
            stroke = COPPER if station == "verdict" else BORDER
            draw.rectangle((x, 40, x + 120, 96), fill=_hex(PANEL), outline=_hex(stroke))
            draw.text((x + 12, 52), station, fill=_hex(CINDER))
            draw.text((x + 12, 72), "1" if station == "verdict" else "0", fill=_hex(BONE))
        draw.rectangle((40, 120, 600, 320), fill=_hex(PANEL), outline=_hex(BORDER))
        draw.text((56, 140), "improved · waste ↓ 18%", fill=_hex(MALACHITE))
        draw.rectangle((56, 170, 376, 182), fill=_hex(BORDER))
        draw.rectangle((120, 170, 200, 182), fill=_hex(MALACHITE))
        draw.text((56, 200), "anytime-valid CI · n_eff=12", fill=_hex(CINDER))

    _save_png(path, (640, 360), draw)


def _write_favicon_png(path: Path) -> None:
    def draw(draw, size: tuple[int, int]) -> None:
        draw.ellipse((6, 18, 26, 26), fill=_hex(COPPER))
        draw.ellipse((8, 12, 24, 20), fill=_hex("#8a7355"))
        draw.ellipse((10, 8, 22, 14), fill=_hex("#a89070"))

    _save_png(path, (32, 32), draw)


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

    png_writers = {
        "hero.png": _write_hero_png,
        "overview.png": _write_overview_png,
        "session-detail.png": _write_session_detail_png,
        "optimize-verdict.png": _write_optimize_png,
        "favicon.png": _write_favicon_png,
    }
    for name, writer in png_writers.items():
        path = ASSETS / name
        writer(path)
        print(f"Wrote {path}")

    for stale in ("hero.gif",):
        stale_path = ASSETS / stale
        if stale_path.exists():
            stale_path.unlink()
            print(f"Removed stale placeholder {stale_path}")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1) from exc
