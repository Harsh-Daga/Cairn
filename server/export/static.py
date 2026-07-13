"""Static export helpers for demo snapshots."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from server import __version__
from server.api.actions import build_manifest
from server.api.bootstrap import bootstrap_runtime
from server.api.payloads import (
    build_agents,
    build_behavior,
    build_evidence_chain,
    build_experiment_detail,
    build_experiments,
    build_insights,
    build_overview,
    build_quality,
    build_regions_analytics,
    build_replay_checkpoints,
    build_search,
    build_tail_analytics,
    build_trace_detail,
    build_traces_list,
    build_usage_analytics,
    build_waste_analytics,
    build_workspace,
)
from server.config import Settings

_SANITIZE_RE = re.compile(r"[^A-Za-z0-9._-]+")
_DEFAULT_DAYS = (1, 7, 30, 90)


def _slug(value: str) -> str:
    cleaned = _SANITIZE_RE.sub("-", value).strip("-")
    return cleaned or "x"


def _query_suffix(query: dict[str, Any] | None) -> str:
    if not query:
        return ""
    parts: list[str] = []
    for key, raw in sorted(query.items()):
        if raw is None:
            continue
        parts.append(f"{_slug(str(key))}={_slug(str(raw))}")
    return f"__{'__'.join(parts)}" if parts else ""


def _write_payload(
    root: Path,
    endpoint: str,
    payload: Any,
    *,
    query: dict[str, Any] | None = None,
) -> None:
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump()
    rel = endpoint.lstrip("/") or "root"
    file_path = root / "api" / f"{rel}{_query_suffix(query)}.json"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _inject_static_flag(index_path: Path) -> None:
    html = index_path.read_text(encoding="utf-8")
    marker = "window.__CAIRN_STATIC__=true;"
    if marker not in html:
        script = "<script>window.__CAIRN_STATIC__=true;</script>"
        if "<head>" in html:
            html = html.replace("<head>", f"<head>\n  {script}", 1)
        else:
            html = f"{script}\n{html}"
    # Vite's production build uses root-relative asset URLs for the local
    # server. A Pages project site is hosted below /Cairn/, so those URLs must
    # be relative to the exported index instead.
    html = html.replace('="/assets/', '="./assets/')
    html = html.replace("='/assets/", "='./assets/")
    index_path.write_text(html, encoding="utf-8")


def export_static_snapshot(workspace_root: Path | None, out_dir: Path) -> dict[str, Any]:
    """Export a static, read-only UI snapshot and API payload bundle."""
    settings = Settings(workspace_root=workspace_root)
    runtime = bootstrap_runtime(settings)
    conn = runtime.database.reader
    ws_id = runtime.workspace_id
    source_rows = conn.execute(
        "SELECT DISTINCT source FROM traces WHERE workspace_id = ? ORDER BY source",
        (ws_id,),
    ).fetchall()
    sources = [str(row["source"]) for row in source_rows]
    trace_ids = [
        str(row["trace_id"])
        for row in conn.execute(
            "SELECT trace_id FROM traces WHERE workspace_id = ? ORDER BY started_at DESC",
            (ws_id,),
        ).fetchall()
    ]
    try:
        if out_dir.exists():
            shutil.rmtree(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        static_dir = settings.static_dir
        index_html = static_dir / "index.html"
        if not index_html.is_file():
            msg = "Built UI assets missing. Run `python scripts/build_ui.py` first."
            raise FileNotFoundError(msg)
        for child in static_dir.iterdir():
            dst = out_dir / child.name
            if child.is_dir():
                shutil.copytree(child, dst)
            else:
                shutil.copy2(child, dst)
        _inject_static_flag(out_dir / "index.html")

        payload_count = 0

        def write(endpoint: str, payload: Any, *, query: dict[str, Any] | None = None) -> None:
            nonlocal payload_count
            _write_payload(out_dir, endpoint, payload, query=query)
            payload_count += 1

        write("/health", {"status": "ok", "version": __version__})
        write(
            "/workspace",
            build_workspace(conn, workspace_id=ws_id, root_path=str(runtime.workspace_root)),
        )
        write("/actions", {"actions": [m.model_dump() for m in build_manifest()]})
        write("/insights", build_insights(conn))
        write("/experiments", build_experiments(conn))
        for query in ("", "demo", "failure", "tool"):
            write(
                "/search",
                build_search(conn, workspace_id=ws_id, q=query, limit=20),
                query={"q": query},
            )
        for days in _DEFAULT_DAYS:
            write(
                "/overview",
                build_overview(conn, workspace_id=ws_id, days=days),
                query={"days": days},
            )
            write(
                "/agents", build_agents(conn, workspace_id=ws_id, days=days), query={"days": days}
            )
            write(
                "/behavior",
                build_behavior(conn, workspace_id=ws_id, days=days),
                query={"days": days},
            )
            write(
                "/quality", build_quality(conn, workspace_id=ws_id, days=days), query={"days": days}
            )
            write(
                "/analytics/usage",
                build_usage_analytics(conn, workspace_id=ws_id, days=days, group_by="day"),
                query={"days": days, "group_by": "day"},
            )
            write(
                "/analytics/regions",
                build_regions_analytics(conn, workspace_id=ws_id, days=days),
                query={"days": days},
            )
            write(
                "/analytics/waste",
                build_waste_analytics(conn, workspace_id=ws_id, days=days),
                query={"days": days},
            )
            write(
                "/analytics/tail",
                build_tail_analytics(conn, workspace_id=ws_id, days=days),
                query={"days": days},
            )
            write(
                "/traces",
                build_traces_list(conn, workspace_id=ws_id, days=days, limit=100, offset=0),
                query={"days": days, "limit": 100, "offset": 0},
            )
            for source in sources:
                write(
                    "/traces",
                    build_traces_list(
                        conn,
                        workspace_id=ws_id,
                        days=days,
                        source=source,
                        limit=100,
                        offset=0,
                    ),
                    query={"days": days, "source": source, "limit": 100, "offset": 0},
                )

        write(
            "/traces",
            build_traces_list(conn, workspace_id=ws_id, days=30, q="failure", limit=100, offset=0),
            query={"days": 30, "q": "failure", "limit": 100, "offset": 0},
        )

        for trace_id in trace_ids:
            trace_detail = build_trace_detail(conn, trace_id)
            replay = build_replay_checkpoints(conn, trace_id)
            if trace_detail is not None:
                write(f"/traces/{trace_id}", trace_detail)
            if replay is not None:
                write(f"/traces/{trace_id}/replay", replay)

        insight_ids = [
            str(row["insight_id"])
            for row in conn.execute(
                "SELECT insight_id FROM insights ORDER BY created_at DESC"
            ).fetchall()
        ]
        for insight_id in insight_ids:
            chain = build_evidence_chain(conn, insight_id)
            if chain is not None:
                write(f"/insights/{insight_id}/evidence", chain)

        experiment_ids = [
            str(row["experiment_id"])
            for row in conn.execute(
                "SELECT experiment_id FROM experiments ORDER BY created_at DESC"
            ).fetchall()
        ]
        for experiment_id in experiment_ids:
            experiment_detail = build_experiment_detail(conn, experiment_id, workspace_id=ws_id)
            if experiment_detail is not None:
                write(f"/experiments/{experiment_id}", experiment_detail)
    finally:
        runtime.database.close()

    return {
        "out_dir": str(out_dir),
        "payload_count": payload_count,
        "trace_count": len(trace_ids),
        "sources": len(sources),
    }
