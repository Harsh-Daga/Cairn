"""Provenance bundle rendering tests (R15, R16)."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from cairn.render.bundle import bundle_json, bundle_payload_from_project
from cairn.render.extract import parse_cairn_data
from cairn.render.html import render_bundle, zip_bundle
from cairn.util.canonical import canonical_json
from tests.test_invariants import _build
from tests.test_render_embedding import _assert_no_external_resources


@pytest.fixture
def built_project(project_dir: Path, fixtures_dir: Path) -> Path:
    _build(project_dir, fixtures_dir)
    return project_dir


def test_bundle_has_lineage_for_every_node(built_project: Path) -> None:
    payload = bundle_payload_from_project(built_project)
    for node in payload["nodes"]:
        assert "inputs" in node
        assert "rendered_prompt" in node
        assert "output" in node
        if node["node_id"] == "synthesis":
            kinds = {i["kind"] for i in node["inputs"]}
            assert "upstream" in kinds
            assert "source" in kinds


def test_bundle_output_matches_cas(built_project: Path) -> None:
    payload = bundle_payload_from_project(built_project)
    report = next(n for n in payload["nodes"] if n["node_id"] == "report")
    out_path = built_project / "outputs" / "report.md"
    assert report["output"]["text"] == out_path.read_text(encoding="utf-8")


def test_render_golden_index_html(built_project: Path, tmp_path: Path) -> None:
    out = tmp_path / "bundle"
    render_bundle(built_project, out)
    html = (out / "index.html").read_text(encoding="utf-8")
    assert 'id="cairn-data"' in html
    assert (out / "assets" / "app.js").is_file()
    assert (out / "assets" / "app.css").is_file()
    _assert_no_external_resources(html)
    app_js = (out / "assets" / "app.js").read_text(encoding="utf-8")
    assert "data_path" in app_js
    data = parse_cairn_data(html)
    assert data["cairn_bundle_version"] == 1
    assert len(data["nodes"]) == 5


def test_render_deterministic_json_keys(built_project: Path) -> None:
    import json

    a = bundle_json(built_project)
    b = bundle_json(built_project)
    assert a == b
    assert a == canonical_json(json.loads(a))


def test_render_zip_e2e(built_project: Path, tmp_path: Path) -> None:
    out = tmp_path / "bundle"
    render_bundle(built_project, out)
    zip_path = tmp_path / "bundle.zip"
    zip_bundle(out, zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        assert "index.html" in names
        assert "assets/app.js" in names
        html = zf.read("index.html").decode("utf-8")
        data = parse_cairn_data(html)
        assert data["run"]["status"] == "success"


def test_split_bundle_stub_has_data_path(built_project: Path, tmp_path: Path) -> None:
    out = tmp_path / "bundle-split"
    render_bundle(built_project, out, split=True)
    data = parse_cairn_data((out / "index.html").read_text(encoding="utf-8"))
    assert data["data_path"] == "data/cairn-data.json"
    assert (out / "data" / "cairn-data.json").is_file()
    app_js = (out / "assets" / "app.js").read_text(encoding="utf-8")
    assert "SPLIT_FILE_MESSAGE" in app_js or "--split bundle" in app_js
    assert "fetch(" in app_js
