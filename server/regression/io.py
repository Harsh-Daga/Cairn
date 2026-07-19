"""Export/import portable regression zip archives with hostile-path defenses."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from server.export.scrub import scrub_text
from server.regression.schema import REGRESSION_SCHEMA_VERSION, RegressionArtifact
from server.regression.store import (
    delete_regression,
    load_regression,
    regression_dir,
    save_regression,
)
from server.regression.validate import validate_artifact

_ALLOWED_ROOT_FILES = frozenset({"manifest.json", "regression.json", "privacy.json"})
_MAX_UNCOMPRESSED = 8 * 1024 * 1024
_MAX_MEMBERS = 64


class RegressionImportError(ValueError):
    """Raised when a regression archive fails safety or schema checks."""


def export_regression_zip(
    workspace_root: Path,
    regression_id: str,
    *,
    output: Path,
) -> dict[str, Any]:
    artifact = load_regression(workspace_root, regression_id)
    if artifact is None:
        return {"ok": False, "error": "regression_not_found", "regression_id": regression_id}
    source = regression_dir(workspace_root, regression_id)
    output = output.expanduser().resolve()
    if output.exists() and output.is_symlink():
        return {"ok": False, "error": "output_is_symlink", "path": str(output)}
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name in ("manifest.json", "regression.json", "privacy.json"):
            path = source / name
            if path.is_file():
                zf.write(path, arcname=name)
        attachments = source / "attachments"
        if attachments.is_dir():
            for child in sorted(attachments.iterdir()):
                if child.is_file() and not child.is_symlink():
                    zf.write(child, arcname=f"attachments/{child.name}")
    return {
        "ok": True,
        "schema": REGRESSION_SCHEMA_VERSION,
        "regression_id": regression_id,
        "path": str(output),
        "content_hash": artifact.content_hash,
    }


def import_regression_zip(
    workspace_root: Path,
    archive: Path,
    *,
    replace: bool = False,
) -> dict[str, Any]:
    archive = archive.expanduser().resolve()
    if not archive.is_file():
        return {"ok": False, "error": "archive_not_found", "path": str(archive)}
    if archive.is_symlink():
        return {"ok": False, "error": "archive_is_symlink", "path": str(archive)}

    try:
        members = _safe_zip_members(archive)
        payload = members["regression.json"].decode("utf-8")
        artifact = RegressionArtifact.model_validate_json(payload)
    except (RegressionImportError, OSError, UnicodeDecodeError, ValueError) as exc:
        return {"ok": False, "error": "import_rejected", "detail": str(exc)}

    report = validate_artifact(artifact)
    if not report["ok"]:
        return {
            "ok": False,
            "error": "validation_failed",
            "report": report,
        }

    existing = load_regression(workspace_root, artifact.regression_id)
    if existing is not None and not replace:
        return {
            "ok": False,
            "error": "already_exists",
            "regression_id": artifact.regression_id,
        }
    if existing is not None and replace:
        delete_regression(workspace_root, artifact.regression_id)

    # Re-scrub free-text fields against the destination workspace root.
    scrubbed = artifact.model_copy(
        update={
            "scrubbed_task": (
                scrub_text(artifact.scrubbed_task, workspace_root)
                if artifact.scrubbed_task
                else None
            ),
            "required_paths": [
                scrub_text(path, workspace_root) for path in artifact.required_paths
            ],
            "verification_commands": [
                cmd.model_copy(update={"command": scrub_text(cmd.command, workspace_root)})
                for cmd in artifact.verification_commands
            ],
            "setup_commands": [],
            "attachments": [],
            "privacy_inventory": artifact.privacy_inventory.model_copy(update={"scrubbed": True}),
        }
    )
    path = save_regression(workspace_root, scrubbed, title=scrubbed.scrubbed_task)
    # Attachments are not imported by default (privacy).
    _ = members
    return {
        "ok": True,
        "schema": REGRESSION_SCHEMA_VERSION,
        "regression_id": scrubbed.regression_id,
        "path": str(path),
        "content_hash": scrubbed.content_hash,
        "attachments_imported": 0,
        "limitation": (
            "Imported metadata only; attachments are skipped by default and "
            "no commands were executed."
        ),
    }


def _safe_zip_members(archive: Path) -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    total = 0
    with zipfile.ZipFile(archive, "r") as zf:
        infos = zf.infolist()
        if len(infos) > _MAX_MEMBERS:
            raise RegressionImportError(f"too many archive members ({len(infos)})")
        for info in infos:
            name = info.filename.replace("\\", "/")
            if name.endswith("/"):
                continue
            if name.startswith("/") or name.startswith("../") or "/../" in f"/{name}/":
                raise RegressionImportError(f"path traversal rejected: {name}")
            if Path(name).is_absolute() or name.startswith(".."):
                raise RegressionImportError(f"absolute or parent path rejected: {name}")
            # Reject symlink-like unix external attrs (symlink bit in upper mode).
            mode = (info.external_attr >> 16) & 0o170000
            if mode == 0o120000:
                raise RegressionImportError(f"symlink member rejected: {name}")
            if info.file_size > _MAX_UNCOMPRESSED:
                raise RegressionImportError(f"member too large: {name}")
            total += info.file_size
            if total > _MAX_UNCOMPRESSED:
                raise RegressionImportError("archive uncompressed size exceeds limit")
            if name.startswith("attachments/"):
                rel = name[len("attachments/") :]
                if not rel or "/" in rel or rel in {".", ".."}:
                    raise RegressionImportError(f"invalid attachment path: {name}")
            elif name not in _ALLOWED_ROOT_FILES:
                raise RegressionImportError(f"unexpected archive member: {name}")
            data = zf.read(info)
            out[name] = data
    if "regression.json" not in out:
        raise RegressionImportError("regression.json missing from archive")
    # Quick JSON sanity for privacy/manifest when present.
    for key in ("manifest.json", "privacy.json"):
        if key in out:
            json.loads(out[key].decode("utf-8"))
    return out
