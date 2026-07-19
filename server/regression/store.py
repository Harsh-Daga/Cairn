"""Filesystem store for local regression artifacts under ``.cairn/regressions``."""

from __future__ import annotations

import json
from pathlib import Path

from server.regression.schema import RegressionArtifact, RegressionManifest
from server.util.private_files import ensure_private_dir, write_private_text


def regressions_root(workspace_root: Path) -> Path:
    return (workspace_root / ".cairn" / "regressions").resolve()


def regression_dir(workspace_root: Path, regression_id: str) -> Path:
    return regressions_root(workspace_root) / regression_id


def save_regression(
    workspace_root: Path,
    artifact: RegressionArtifact,
    *,
    title: str | None = None,
) -> Path:
    root = regressions_root(workspace_root)
    ensure_private_dir(root)
    target = root / artifact.regression_id
    ensure_private_dir(target)
    ensure_private_dir(target / "attachments")
    body = artifact.model_dump(mode="json")
    write_private_text(
        target / "regression.json",
        json.dumps(body, indent=2, sort_keys=True) + "\n",
    )
    manifest = RegressionManifest(
        regression_id=artifact.regression_id,
        created_at=artifact.provenance.created_at,
        source_trace_id=artifact.provenance.source_trace_id,
        content_hash=artifact.content_hash,
        title=title or artifact.scrubbed_task,
    )
    write_private_text(
        target / "manifest.json",
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
    )
    write_private_text(
        target / "privacy.json",
        json.dumps(
            artifact.privacy_inventory.model_dump(mode="json"),
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    return target


def load_regression(workspace_root: Path, regression_id: str) -> RegressionArtifact | None:
    path = regression_dir(workspace_root, regression_id) / "regression.json"
    if not path.is_file():
        return None
    return RegressionArtifact.model_validate_json(path.read_text(encoding="utf-8"))


def load_manifest(workspace_root: Path, regression_id: str) -> RegressionManifest | None:
    path = regression_dir(workspace_root, regression_id) / "manifest.json"
    if not path.is_file():
        return None
    return RegressionManifest.model_validate_json(path.read_text(encoding="utf-8"))


def list_regressions(workspace_root: Path) -> list[RegressionManifest]:
    root = regressions_root(workspace_root)
    if not root.is_dir():
        return []
    items: list[RegressionManifest] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        manifest = load_manifest(workspace_root, child.name)
        if manifest is not None:
            items.append(manifest)
    return items


def delete_regression(workspace_root: Path, regression_id: str) -> bool:
    target = regression_dir(workspace_root, regression_id)
    if not target.is_dir():
        return False
    for path in sorted(target.rglob("*"), reverse=True):
        if path.is_symlink() or path.is_file():
            path.unlink(missing_ok=True)
        elif path.is_dir():
            path.rmdir()
    if target.exists():
        target.rmdir()
    return True
