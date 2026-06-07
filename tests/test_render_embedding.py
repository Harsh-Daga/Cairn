"""HTML JSON embedding safety and structural bundle tests (Phase 2.1)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from cairn.render.embedding import escape_json_for_html_embedding
from cairn.render.extract import extract_cairn_data_json, parse_cairn_data
from cairn.render.html import _html_shell, render_bundle
from cairn.util.canonical import canonical_json
from tests.test_invariants import _build

_EVIL = '</script><script>alert(1)</script><!-- comment -->'
_EXTERNAL_RESOURCE_RE = re.compile(
    r'<(?:link|script|img)\b[^>]*\b(?:href|src)=["\']([^"\']+)["\']',
    re.IGNORECASE,
)


def _minimal_payload(*, evil_text: str) -> dict[str, Any]:
    return {
        "cairn_bundle_version": 1,
        "project": {"name": "test", "root_label": "test"},
        "run": {
            "run_id": "test-run",
            "status": "success",
            "started_at": "2026-01-01T00:00:00+00:00",
            "ended_at": "2026-01-01T00:00:01+00:00",
            "total_cost": None,
            "total_input_tokens": 1,
            "total_output_tokens": 1,
            "cairn_version": "0.1.0",
            "key_version": 1,
            "git_commit": None,
        },
        "nodes": [
            {
                "node_id": "report",
                "step": "report",
                "item_id": None,
                "kind": "single",
                "action_key": "k",
                "output_hash": "h",
                "status": "ran",
                "model": "gpt-4o-mini",
                "params": {"max_tokens": 100},
                "input_tokens": 1,
                "output_tokens": 1,
                "cost": None,
                "duration_ms": 1,
                "started_at": "2026-01-01T00:00:00+00:00",
                "ended_at": "2026-01-01T00:00:01+00:00",
                "rendered_prompt": evil_text,
                "system_prompt": "sys",
                "inputs": [],
                "output": {
                    "text": evil_text,
                    "truncated": False,
                    "output_hash": "h",
                },
            }
        ],
    }


def test_escape_json_for_html_round_trip() -> None:
    raw = canonical_json({"text": _EVIL, "line": "a\u2028b\u2029c"})
    escaped = escape_json_for_html_embedding(raw)
    assert "</script>" not in escaped
    assert "<!--" not in escaped
    assert "<" not in escaped
    assert ">" not in escaped
    decoded = json.loads(escaped)
    assert decoded["text"] == _EVIL
    assert decoded["line"] == "a\u2028b\u2029c"


def _count_script_close_tags(html: str) -> int:
    return html.count("</script>")


def test_render_escapes_script_injection(tmp_path: Path) -> None:
    payload = _minimal_payload(evil_text=_EVIL)
    embedded = escape_json_for_html_embedding(canonical_json(payload))
    html = _html_shell(embedded)
    # cairn-data block + app.js loader — no extra closes from injected content
    assert _count_script_close_tags(html) == 2
    parsed = parse_cairn_data(html)
    node = parsed["nodes"][0]
    assert node["output"]["text"] == _EVIL
    assert node["rendered_prompt"] == _EVIL


def test_extract_cairn_data_by_id_not_greedy_regex(tmp_path: Path) -> None:
    payload = _minimal_payload(evil_text=_EVIL)
    embedded = escape_json_for_html_embedding(canonical_json(payload))
    html = _html_shell(embedded)
    block = extract_cairn_data_json(html)
    assert json.loads(block)["nodes"][0]["output"]["text"] == _EVIL


def _assert_no_external_resources(html: str) -> None:
    for match in _EXTERNAL_RESOURCE_RE.finditer(html):
        url = match.group(1)
        if url.startswith("http://") or url.startswith("https://"):
            pytest.fail(f"external resource reference in bundle HTML: {url!r}")


def test_inline_bundle_allows_https_in_content_text(
    project_dir: Path,
    fixtures_dir: Path,
    tmp_path: Path,
) -> None:
    alpha = project_dir / "inputs" / "notes" / "alpha.md"
    alpha.write_text(
        alpha.read_text(encoding="utf-8")
        + "\nReference: https://example.com/docs\n",
        encoding="utf-8",
    )
    _build(project_dir, fixtures_dir)
    out = tmp_path / "bundle"
    render_bundle(project_dir, out)
    html = (out / "index.html").read_text(encoding="utf-8")
    _assert_no_external_resources(html)
    data = parse_cairn_data(html)
    alpha_node = next(n for n in data["nodes"] if n["node_id"] == "summaries:alpha")
    assert "https://example.com/docs" in alpha_node["rendered_prompt"]
    assert "https://example.com" in html


def test_default_bundle_is_inline(project_dir: Path, fixtures_dir: Path, tmp_path: Path) -> None:
    _build(project_dir, fixtures_dir)
    out = tmp_path / "bundle"
    render_bundle(project_dir, out)
    data = parse_cairn_data((out / "index.html").read_text(encoding="utf-8"))
    assert "nodes" in data
    assert "data_path" not in data


def test_split_stub_embedded_safely(tmp_path: Path) -> None:
    stub = json.dumps({"data_path": "data/cairn-data.json"}, sort_keys=True)
    embedded = escape_json_for_html_embedding(stub)
    html = _html_shell(embedded)
    assert _count_script_close_tags(html) == 2
    assert parse_cairn_data(html)["data_path"] == "data/cairn-data.json"


def test_rel_path_rejects_outside_project_root(tmp_path: Path) -> None:
    from cairn.render.bundle import _rel_path

    root = tmp_path / "proj"
    root.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="outside project root"):
        _rel_path(root, outside)


def test_rel_path_resolves_relative_to_project_root(tmp_path: Path) -> None:
    from cairn.render.bundle import _rel_path

    root = tmp_path / "proj"
    (root / "inputs").mkdir(parents=True)
    f = root / "inputs" / "a.md"
    f.write_text("x", encoding="utf-8")
    assert _rel_path(root, "inputs/a.md") == "inputs/a.md"


def test_secret_not_in_rendered_html(
    project_dir: Path,
    fixtures_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = "ollama-sentinel-key-9f3a2b1c0d8e7f6a"
    monkeypatch.setenv("OLLAMA_CLOUD_API_KEY", sentinel)
    _build(project_dir, fixtures_dir)
    out = tmp_path / "bundle"
    render_bundle(project_dir, out)
    html = (out / "index.html").read_text(encoding="utf-8")
    assert sentinel not in html
    assert _count_script_close_tags(html) == 2
    evil_payload = _minimal_payload(evil_text=_EVIL)
    embedded = escape_json_for_html_embedding(canonical_json(evil_payload))
    evil_html = _html_shell(embedded)
    assert parse_cairn_data(evil_html)["nodes"][0]["output"]["text"] == _EVIL
