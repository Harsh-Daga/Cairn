"""Inline payload into index.html; copy assets (R15)."""

from __future__ import annotations

import json
import shutil
import zipfile
from importlib import resources
from pathlib import Path
from typing import Any

from cairn.render.bundle import bundle_payload_from_project
from cairn.render.embedding import escape_json_for_html_embedding
from cairn.util.canonical import canonical_json

_ASSETS_PKG = "cairn.render.assets"


def _html_shell(payload_json: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Cairn Provenance</title>
  <link rel="stylesheet" href="assets/app.css">
</head>
<body>
  <header class="banner">
    <h1>Cairn Provenance</h1>
    <p id="run-summary"></p>
  </header>
  <div class="layout">
    <nav id="node-list" class="sidebar" aria-label="Nodes"></nav>
    <main id="node-detail" class="detail"></main>
  </div>
  <script type="application/json" id="cairn-data">{payload_json}</script>
  <script src="assets/app.js"></script>
</body>
</html>
"""


def _copy_assets(dest: Path) -> None:
    assets_dir = dest / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    pkg = resources.files(_ASSETS_PKG)
    for name in ("app.css", "app.js"):
        src = pkg / name
        with resources.as_file(src) as src_path:
            shutil.copyfile(src_path, assets_dir / name)


def render_bundle(
    project_root: Path,
    output_dir: Path,
    *,
    run_id: str | None = None,
    split: bool = False,
    inline_cap: int = 256 * 1024,
) -> Path:
    payload = bundle_payload_from_project(
        project_root,
        run_id,
        inline_cap=inline_cap,
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    if split:
        data_dir = output_dir / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        data_path = data_dir / "cairn-data.json"
        data_path.write_text(canonical_json(payload) + "\n", encoding="utf-8")
        stub = json.dumps({"data_path": "data/cairn-data.json"}, sort_keys=True)
        embedded = escape_json_for_html_embedding(stub)
    else:
        embedded = escape_json_for_html_embedding(canonical_json(payload))

    index_path = output_dir / "index.html"
    index_path.write_text(_html_shell(embedded), encoding="utf-8")
    _copy_assets(output_dir)
    return index_path


def zip_bundle(bundle_dir: Path, zip_path: Path) -> Path:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(bundle_dir.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(bundle_dir).as_posix())
    return zip_path


def write_split_data(payload: dict[str, Any], output_dir: Path) -> None:
    data_dir = output_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "cairn-data.json").write_text(
        canonical_json(payload) + "\n",
        encoding="utf-8",
    )
