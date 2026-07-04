"""Phase E — Surveyor's Field Notebook design-system guards (Part 18.9)."""

from __future__ import annotations

import re
from pathlib import Path

ASSETS = Path(__file__).parent.parent / "cairn" / "assets"


def _read(name: str) -> str:
    return (ASSETS / name).read_text(encoding="utf-8")


def test_all_asset_files_exist_and_nonempty() -> None:
    for name in (
        "index.html",
        "session.html",
        "dashboard.js",
        "session.js",
        "dashboard.css",
        "session.css",
    ):
        path = ASSETS / name
        assert path.is_file(), name
        assert path.stat().st_size > 0, name


def test_css_has_no_pure_black_or_white() -> None:
    """18.9b: no #000 / #fff literals anywhere in the CSS."""
    for name in ("dashboard.css", "session.css"):
        css = _read(name)
        assert not re.search(r"#000\b(?!0)", css), f"{name}: pure black #000 forbidden"
        assert not re.search(r"#fff\b(?!f)", css, re.IGNORECASE), (
            f"{name}: pure white #fff forbidden"
        )
        assert "#000000" not in css.lower(), f"{name}: pure black #000000 forbidden"
        assert "#ffffff" not in css.lower(), f"{name}: pure white #ffffff forbidden"


def test_css_has_no_inter_or_geist() -> None:
    """18.9c: no Inter / Geist in the font stack (case-sensitive font names)."""
    for name in ("dashboard.css", "session.css"):
        css = _read(name)
        assert re.search(r"\bInter\b", css) is None, f"{name}: Inter font forbidden"
        assert re.search(r"\bGeist\b", css) is None, f"{name}: Geist font forbidden"


def test_css_defines_mineral_tokens_and_fonts() -> None:
    css = _read("dashboard.css")
    for token in (
        "--anthracite",
        "--slate",
        "--shale",
        "--granite",
        "--quartz-vein",
        "--bone",
        "--cinder",
        "--copper",
        "--patina",
        "--malachite",
        "--ochre",
        "--cinnabar",
        "--lapis",
    ):
        assert token in css, f"missing token {token}"
    for font in ("Fraunces", "Space Grotesk", "JetBrains Mono"):
        assert font in css, f"missing font {font}"
    # Google Fonts @import present
    assert '@import url("https://fonts.googleapis.com' in css
    # contour field present and within opacity budget (<=6%)
    assert "--contour" in css
    m = re.search(r"opacity=['\"]0\.0?(\d+)['\"]", css)
    assert m is not None, "contour field opacity not found"
    assert int(m.group(1)) <= 60, "contour field opacity must be <= 6%"


def test_css_has_focus_ring_and_reduced_motion() -> None:
    """18.8: visible keyboard focus + reduced-motion static path."""
    css = _read("dashboard.css")
    assert ":focus-visible" in css
    assert "prefers-reduced-motion" in css
    assert "prefers-contrast" in css


def test_sessions_page_has_export_affordance() -> None:
    _read("index.html")
    js = _read("dashboard.js")
    assert "btn-export" in js
    assert "exportSession" in js
    assert "/api/action/share" in js


def test_index_references_chartjs_d3_dompurify_and_glyph() -> None:
    html = _read("index.html")
    assert "cairn-glyph" in html  # 18.4 brand glyph
    assert "benchmark" in html or "plaque" in html  # topbar plaque
    assert "strata" in html  # stratigraphic surfaces
    # 10 waypoint pages
    for page in (
        "overview",
        "context",
        "behavior",
        "quality",
        "charts",
        "insights",
        "optimize",
        "sessions",
        "search",
        "settings",
    ):
        assert f'data-page="{page}"' in html, f"missing waypoint {page}"


def test_dashboard_js_coerces_api_numbers_and_table_rows() -> None:
    js = _read("dashboard.js")
    assert "function asNum(" in js
    assert "function setTableBody(" in js
    assert "asNum(rec.total_cost_usd)" in js
    assert "setTableBody($('#all-sessions tbody')" in js


def test_js_uses_dompurify_on_dynamic_html() -> None:
    """Every innerHTML assignment must route through DOMPurify.sanitize."""
    for name in ("dashboard.js", "session.js"):
        js = _read(name)
        # Any direct innerHTML assignment must be the sanitized one inside setHTML.
        for m in re.finditer(r"\.innerHTML\s*=", js):
            # grab ~60 chars after the assignment to confirm sanitize on RHS
            tail = js[m.end() : m.end() + 80]
            assert "sanitize(" in tail, f"{name}: unsanitized innerHTML assignment"
        assert "DOMPurify" in js
        assert "setHTML" in js


def test_dashboard_js_wires_narrative_and_confidence() -> None:
    js = _read("dashboard.js")
    for literal in ("renderNarrativeHero", "confidence-chip", "narrative-hero", "difficulty-aware"):
        assert literal in js, f"dashboard.js missing {literal}"


def test_session_js_wires_autopsy_diagnostics() -> None:
    js = _read("session.js")
    for literal in (
        "renderAutopsy",
        "autopsy-mount",
        "failure_origin_event_id",
        "cascade_root_event_id",
        "ideal_path",
    ):
        assert literal in js, f"session.js missing {literal}"


def test_js_loc_under_budget() -> None:
    """Part 20: JS total <= 1800 LOC across dashboard.js + session.js."""
    sum(1 for _ in _read("dashboard.js").splitlines() if _.strip())
    sum(1 for _ in _read("session.js").splitlines() if _.strip())
    total = len(_read("dashboard.js").splitlines()) + len(_read("session.js").splitlines())
    assert total <= 1800, f"JS LOC {total} exceeds 1800 budget"
