"""Opt-in fleet export/merge — Phase T."""

from __future__ import annotations

import json
import shutil
import sqlite3
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cairn.ledger.schema import migrate
from cairn.render.scrub import scrub_path

_EXPORT_TABLES = (
    "runs",
    "events",
    "data_quality",
    "diagnostics",
    "expectation_baselines",
    "outcomes",
    "optimizations",
    "rollup_daily",
    "episodes",
)


def export_bundle(
    project_root: Path,
    output: Path,
    *,
    since: str | None = None,
    with_snippets: bool = False,
) -> dict[str, Any]:
    """Export scrubbed ledger slice to a .cairn zip bundle."""
    src_db = project_root / ".cairn" / "ledger.db"
    if not src_db.is_file():
        return {"error": "no ledger", "manifest": []}

    tmp = output.with_suffix(".db.tmp")
    if tmp.exists():
        tmp.unlink()
    shutil.copy(src_db, tmp)
    conn = sqlite3.connect(tmp)
    conn.row_factory = sqlite3.Row
    manifest: list[str] = []

    if since:
        conn.execute(
            "DELETE FROM runs WHERE started_at IS NULL OR date(started_at) < date(?)",
            (since,),
        )
        conn.execute("DELETE FROM events WHERE run_id NOT IN (SELECT run_id FROM runs)")
        manifest.append(f"filtered since {since}")

    if not with_snippets:
        conn.execute("UPDATE events SET text_inline = NULL")
        manifest.append("text_inline stripped (default scrub)")

    # Scrub path-like fields in events when not exporting snippets.
    if not with_snippets:
        rows = conn.execute(
            "SELECT event_id, path_rel FROM events WHERE path_rel IS NOT NULL"
        ).fetchall()
        for r in rows:
            scrubbed = scrub_path(str(r["path_rel"]))
            if scrubbed != r["path_rel"]:
                conn.execute(
                    "UPDATE events SET path_rel = ? WHERE event_id = ?",
                    (scrubbed, r["event_id"]),
                )
        manifest.append("path_rel scrubbed")

    conn.commit()
    counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in _EXPORT_TABLES}
    conn.close()

    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(tmp, "ledger.db")
        zf.writestr(
            "manifest.json",
            json.dumps(
                {
                    "exported_at": datetime.now(UTC).isoformat(),
                    "tables": counts,
                    "with_snippets": with_snippets,
                    "notes": manifest,
                },
                indent=2,
            ),
        )
    tmp.unlink()
    manifest.extend(f"{k}: {v} rows" for k, v in counts.items())
    return {"path": str(output), "manifest": manifest, "tables": counts}


def merge_bundles(bundle_paths: list[Path], output: Path) -> dict[str, Any]:
    """Merge bundles into a read-only aggregate fleet.db."""
    if output.exists():
        output.unlink()
    fleet = sqlite3.connect(output)
    migrate(fleet)
    total_runs = 0
    for bp in bundle_paths:
        extract_dir = output.parent / f"_extract_{bp.stem}"
        extract_dir.mkdir(exist_ok=True)
        with zipfile.ZipFile(bp) as zf:
            zf.extract("ledger.db", extract_dir)
        src = sqlite3.connect(extract_dir / "ledger.db")
        src.row_factory = sqlite3.Row
        for row in src.execute("SELECT * FROM runs"):
            cols = row.keys()
            placeholders = ",".join("?" * len(cols))
            try:
                fleet.execute(
                    f"INSERT OR IGNORE INTO runs ({','.join(cols)}) VALUES ({placeholders})",
                    tuple(row[c] for c in cols),
                )
                total_runs += 1
            except sqlite3.IntegrityError:
                pass
        src.close()
        shutil.rmtree(extract_dir, ignore_errors=True)
    fleet.commit()
    fleet.close()
    return {"runs_merged": total_runs, "output": str(output)}
