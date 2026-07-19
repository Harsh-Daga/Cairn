"""Static export helpers for demo snapshots."""

from __future__ import annotations

import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from server import __version__
from server.api.actions import build_manifest
from server.api.bootstrap import bootstrap_runtime
from server.api.payloads import (
    build_agents,
    build_behavior,
    build_budget_analytics,
    build_compare_analytics,
    build_evidence_chain,
    build_experiment_detail,
    build_experiments,
    build_files_analytics,
    build_guard_analytics,
    build_insights,
    build_overview,
    build_quality,
    build_recap,
    build_regions_analytics,
    build_replay_checkpoints,
    build_search,
    build_tail_analytics,
    build_tools_analytics,
    build_trace_corrections,
    build_trace_detail,
    build_trace_diff,
    build_trace_handoff,
    build_trace_receipt,
    build_traces_list,
    build_usage_analytics,
    build_waste_analytics,
    build_workspace,
)
from server.config import Settings
from server.configuration import load_config
from server.export.scrub import scrub_export_value
from server.store.pagination import iter_rows
from server.util.private_files import (
    ensure_private_dir,
    private_text_writer,
    restrict_tree,
    write_private_text,
)

_SANITIZE_RE = re.compile(r"[^A-Za-z0-9._-]+")
_DEFAULT_DAYS = (1, 7, 30, 90)
MAX_STATIC_TRACE_DETAILS = 1_000
MAX_STATIC_DIFF_PAIRS = 10
_SERVER_STATIC_DIR = Path(__file__).parent.parent / "static"
_FILE_STATIC_DIR = Path(__file__).parent.parent / "static_file"


def _slug(value: str) -> str:
    cleaned = _SANITIZE_RE.sub("-", value).strip("-")
    return cleaned or "x"


def _query_suffix(query: dict[str, Any] | None) -> str:
    if not query:
        return ""
    parts: list[str] = []
    for key, raw in sorted(query.items()):
        if raw is None or raw == "":
            continue
        parts.append(f"{_slug(str(key))}={_slug(str(raw))}")
    return f"__{'__'.join(parts)}" if parts else ""


def _write_payload(
    root: Path,
    endpoint: str,
    payload: Any,
    *,
    workspace_root: Path,
    query: dict[str, Any] | None = None,
) -> None:
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump()
    payload = scrub_export_value(payload, workspace_root)
    rel = endpoint.lstrip("/") or "root"
    file_path = root / "api" / f"{rel}{_query_suffix(query)}.json"
    write_private_text(file_path, json.dumps(payload, indent=2, sort_keys=True))


def _inject_static_flag(index_path: Path) -> None:
    html = index_path.read_text(encoding="utf-8")
    bootstrap_name = "cairn-static.js"
    bootstrap = (
        f'<script src="./cairn-data.js"></script>\n  <script src="./{bootstrap_name}"></script>'
    )
    csp = (
        '<meta http-equiv="Content-Security-Policy" content="'
        "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "font-src 'self' data:; img-src 'self' data:; connect-src 'self'; "
        "object-src 'none'; base-uri 'none'; form-action 'none'"
        '">'
    )
    if bootstrap not in html:
        insertion = f"{csp}\n  {bootstrap}"
        if "<head>" in html:
            html = html.replace("<head>", f"<head>\n  {insertion}", 1)
        else:
            html = f"{insertion}\n{html}"
    # Vite's production build uses root-relative asset URLs for the local
    # server. A Pages project site is hosted below /Cairn/, so those URLs must
    # be relative to the exported index instead.
    html = html.replace('="/assets/', '="./assets/')
    html = html.replace("='/assets/", "='./assets/")
    html = html.replace('src="/theme-bootstrap.js"', 'src="./theme-bootstrap.js"')
    html = html.replace("src='/theme-bootstrap.js'", "src='./theme-bootstrap.js'")
    # The production bundle is an IIFE so the exported page can load it as a
    # classic script. Browsers apply CORS to file:// ES modules.
    html = html.replace('<script type="module" crossorigin ', "<script defer ")
    html = html.replace("<script type='module' crossorigin ", "<script defer ")
    write_private_text(index_path.parent / bootstrap_name, "window.__CAIRN_STATIC__=true;\n")
    write_private_text(index_path, html)


def _write_static_data(root: Path) -> None:
    """Stream captured JSON into the file:// bootstrap without retaining all payloads."""
    with private_text_writer(root / "cairn-data.js") as handle:
        handle.write("window.__CAIRN_STATIC_DATA__={")
        first = True
        for path in sorted((root / "api").rglob("*.json")):
            if not first:
                handle.write(",")
            first = False
            key = f"./{path.relative_to(root).as_posix()}"
            handle.write(json.dumps(key, separators=(",", ":")))
            handle.write(":")
            with path.open(encoding="utf-8") as payload:
                json.dump(json.load(payload), handle, sort_keys=True, separators=(",", ":"))
        handle.write("};\n")


def _make_bundled_assets_file_relative(root: Path) -> None:
    """Rewrite Vite's root asset URLs inside the file-compatible IIFE."""
    for path in sorted((root / "assets").glob("*.js")):
        content = path.read_text(encoding="utf-8")
        rewritten = content.replace("/assets/", "./assets/")
        if rewritten != content:
            write_private_text(path, rewritten)


def _write_pages_hosting_files(root: Path) -> None:
    """GitHub Pages project-site helpers: skip Jekyll and cover deep-link 404s.

    The static SPA uses HashRouter, so refresh within hash routes does not need a
    server rewrite. Copying index.html to 404.html still recovers accidental
    path-style hits (e.g. /Cairn/sessions) on project sites.
    """
    index = root / "index.html"
    if not index.is_file():
        return
    write_private_text(root / ".nojekyll", "")
    write_private_text(root / "404.html", index.read_text(encoding="utf-8"))


def export_static_snapshot(workspace_root: Path | None, out_dir: Path) -> dict[str, Any]:
    """Export a static, read-only UI snapshot and API payload bundle."""
    settings = Settings(workspace_root=workspace_root)
    root_path = Path(settings.workspace_root or Path.cwd()).resolve()
    if out_dir.is_symlink():
        raise ValueError("Static export directory must not be a symlink")
    resolved_out = out_dir.resolve()
    protected = {Path("/").resolve(), Path.home().resolve(), root_path, root_path / ".cairn"}
    if resolved_out in protected:
        raise ValueError(f"Refusing to replace protected directory: {resolved_out}")
    runtime = bootstrap_runtime(settings)
    conn = runtime.database.reader
    ws_id = runtime.workspace_id
    source_rows = conn.execute(
        "SELECT DISTINCT source FROM traces WHERE workspace_id = ? ORDER BY source",
        (ws_id,),
    ).fetchall()
    sources = [str(row["source"]) for row in source_rows]
    bounds_row = conn.execute(
        """
        SELECT MIN(started_at) AS start, MAX(started_at) AS end
        FROM traces WHERE workspace_id = ? AND started_at IS NOT NULL
        """,
        (ws_id,),
    ).fetchone()
    total_trace_row = conn.execute(
        "SELECT COUNT(*) AS n FROM traces WHERE workspace_id = ?",
        (ws_id,),
    ).fetchone()
    total_trace_count = int(total_trace_row["n"] or 0) if total_trace_row is not None else 0
    try:
        if out_dir.exists():
            shutil.rmtree(out_dir)
        ensure_private_dir(out_dir)

        static_dir = settings.static_dir
        if (
            static_dir.resolve() == _SERVER_STATIC_DIR.resolve()
            and (_FILE_STATIC_DIR / "index.html").is_file()
        ):
            static_dir = _FILE_STATIC_DIR
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
        _make_bundled_assets_file_relative(out_dir)
        _inject_static_flag(out_dir / "index.html")
        restrict_tree(out_dir)

        payload_count = 0

        def write(endpoint: str, payload: Any, *, query: dict[str, Any] | None = None) -> None:
            nonlocal payload_count
            _write_payload(
                out_dir,
                endpoint,
                payload,
                workspace_root=root_path,
                query=query,
            )
            payload_count += 1

        budgets = load_config(root_path).budgets
        write("/health", {"status": "ok", "version": __version__})
        write(
            "/workspace",
            build_workspace(conn, workspace_id=ws_id, root_path=str(runtime.workspace_root)),
        )
        write("/actions", {"actions": [m.model_dump() for m in build_manifest()]})
        write("/insights", build_insights(conn))
        write("/experiments", build_experiments(conn))
        write("/recap", build_recap(conn, workspace_id=ws_id))
        write(
            "/analytics/budget",
            build_budget_analytics(
                conn,
                workspace_id=ws_id,
                monthly_limit_usd=budgets.monthly_usd,
                weekly_limit_usd=budgets.weekly_usd,
                daily_limit_usd=budgets.daily_usd,
                timezone="UTC",
            ),
        )
        write(
            "/static-manifest",
            {
                "schema_version": 1,
                "producer_version": __version__,
                "captured_at": datetime.now(UTC).isoformat(),
                "data_bounds": {
                    "start": str(bounds_row["start"])
                    if bounds_row and bounds_row["start"]
                    else None,
                    "end": str(bounds_row["end"]) if bounds_row and bounds_row["end"] else None,
                    "timezone": "UTC",
                },
                "available_days": list(_DEFAULT_DAYS),
                "capture_limits": {
                    "trace_details": MAX_STATIC_TRACE_DETAILS,
                    "total_traces": total_trace_count,
                    "session_diff_pairs": MAX_STATIC_DIFF_PAIRS,
                },
                "supported_queries": {
                    "time_ranges": {"kind": "captured_presets", "days": list(_DEFAULT_DAYS)},
                    "traces": ["days", "limit", "offset"],
                    "search": ["q", "limit"],
                    "session_diff": "captured adjacent recent pairs only",
                },
                "custom_range_behavior": "rejected",
                "mutations": False,
                "live_updates": False,
                "privacy": "scrubbed",
                "unsupported": [
                    "mutations",
                    "live_updates",
                    "arbitrary_filters",
                    "custom_time_ranges",
                    "pagination_beyond_captured_pages",
                ],
            },
        )
        for query in ("", "demo", "failure", "tool"):
            write(
                "/search",
                build_search(conn, workspace_id=ws_id, q=query, limit=20),
                query={"q": query, "limit": 20},
            )
        for days in _DEFAULT_DAYS:
            write(
                "/overview",
                build_overview(
                    conn,
                    workspace_id=ws_id,
                    days=days,
                    monthly_budget_usd=budgets.monthly_usd,
                    weekly_budget_usd=budgets.weekly_usd,
                    daily_budget_usd=budgets.daily_usd,
                    workspace_root=root_path,
                ),
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
                "/analytics/tools",
                build_tools_analytics(conn, workspace_id=ws_id, days=days),
                query={"days": days},
            )
            write(
                "/analytics/files",
                build_files_analytics(conn, workspace_id=ws_id, days=days),
                query={"days": days},
            )
            write(
                "/analytics/compare",
                build_compare_analytics(conn, workspace_id=ws_id, days=days),
                query={"days": days},
            )
            write(
                "/analytics/guard",
                build_guard_analytics(
                    conn,
                    workspace_id=ws_id,
                    workspace_root=root_path,
                    days=days,
                    rescan=False,
                ),
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
                build_traces_list(conn, workspace_id=ws_id, days=days, limit=50, offset=0),
                query={"days": days, "limit": 50, "offset": 0},
            )
            for source in sources:
                write(
                    "/traces",
                    build_traces_list(
                        conn,
                        workspace_id=ws_id,
                        days=days,
                        source=source,
                        limit=50,
                        offset=0,
                    ),
                    query={"days": days, "source": source, "limit": 50, "offset": 0},
                )

        write(
            "/traces",
            build_traces_list(conn, workspace_id=ws_id, days=30, q="failure", limit=50, offset=0),
            query={"days": 30, "q": "failure", "limit": 50, "offset": 0},
        )

        trace_count = 0
        captured_trace_ids: list[str] = []
        for row in iter_rows(
            conn,
            """
            SELECT trace_id FROM traces
            WHERE workspace_id = ?
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (ws_id, MAX_STATIC_TRACE_DETAILS),
        ):
            trace_count += 1
            trace_id = str(row["trace_id"])
            captured_trace_ids.append(trace_id)
            trace_detail = build_trace_detail(conn, trace_id)
            replay = build_replay_checkpoints(conn, trace_id)
            receipt = build_trace_receipt(conn, trace_id)
            corrections = build_trace_corrections(conn, trace_id)
            handoff = build_trace_handoff(conn, trace_id, workspace_root=root_path)
            if trace_detail is not None:
                write(f"/traces/{trace_id}", trace_detail)
            if replay is not None:
                write(f"/traces/{trace_id}/replay", replay)
            if receipt is not None:
                write(f"/traces/{trace_id}/receipt", receipt)
            if corrections is not None:
                write(f"/traces/{trace_id}/corrections", corrections)
            if handoff is not None:
                write(f"/traces/{trace_id}/handoff", handoff)

        diff_pair_count = 0
        for trace_id_a, trace_id_b in zip(captured_trace_ids, captured_trace_ids[1:], strict=False):
            if diff_pair_count >= MAX_STATIC_DIFF_PAIRS:
                break
            diff = build_trace_diff(
                conn,
                trace_id_a,
                trace_id_b,
                workspace_id=ws_id,
            )
            if diff is not None:
                write(
                    "/traces/diff",
                    diff,
                    query={"a": trace_id_a, "b": trace_id_b},
                )
                diff_pair_count += 1

        for row in iter_rows(conn, "SELECT insight_id FROM insights ORDER BY created_at DESC"):
            insight_id = str(row["insight_id"])
            chain = build_evidence_chain(conn, insight_id)
            if chain is not None:
                write(f"/insights/{insight_id}/evidence", chain)

        for row in iter_rows(
            conn,
            "SELECT experiment_id FROM experiments ORDER BY created_at DESC",
        ):
            experiment_id = str(row["experiment_id"])
            experiment_detail = build_experiment_detail(conn, experiment_id, workspace_id=ws_id)
            if experiment_detail is not None:
                write(f"/experiments/{experiment_id}", experiment_detail)
        _write_static_data(out_dir)
        _write_pages_hosting_files(out_dir)
    finally:
        runtime.database.close()

    return {
        "out_dir": str(out_dir),
        "payload_count": payload_count,
        "trace_count": trace_count,
        "diff_pair_count": diff_pair_count,
        "total_trace_count": total_trace_count,
        "sources": len(sources),
    }
