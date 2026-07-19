"""Registered action handler implementations."""

from __future__ import annotations

import json
import os
import secrets
import signal
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, Field

from server.analyze.registry import build_views
from server.analyze.tail import return_level
from server.analyze.views import ViewScheduler
from server.api.context import ActionCtx
from server.demo.seed import seed_demo_workspace
from server.improve.engine import evaluate as evaluate_insights
from server.improve.proposals import generate_proposals
from server.models.annotation import Annotation
from server.models.insight import InsightLifecycle, InsightState
from server.store.repos.annotations import AnnotationRepo
from server.store.repos.experiments import ExperimentRepo
from server.store.repos.insights import InsightRepo
from server.store.repos.views import ViewStateRepo
from server.util.ids import new_ulid
from server.util.private_files import ensure_private_dir, write_private_text


class EmptyParams(BaseModel):
    pass


class SyncParams(BaseModel):
    source: str | None = None
    force: bool = False


class WorkspaceScanParams(BaseModel):
    """Rediscover adapter streams and ingest new/changed files.

    Pass ``force=true`` (Settings → Rescan adapters) to re-parse unchanged
    streams and rebuild parse-health from that pass.
    """

    force: bool = False


class BackfillParams(BaseModel):
    days: int = Field(default=30, ge=1, le=365)


class RebuildViewParams(BaseModel):
    view: str


class CheckParams(BaseModel):
    min_quality: float | None = Field(default=None, ge=0.0, le=1.0)
    max_waste_pct: float | None = Field(default=None, ge=0.0, le=100.0)
    max_tail_cost: float | None = Field(default=None, ge=0.0)


class ExportBundleParams(BaseModel):
    trace_id: str | None = None
    scrub: bool = True


class ExportSessionHtmlParams(BaseModel):
    trace_id: str
    output: str | None = None


class VerificationRebuildParams(BaseModel):
    trace_id: str | None = None
    limit: int = Field(default=200, ge=1, le=2000)


class RegressionCreateParams(BaseModel):
    trace_id: str


class RegressionDeleteParams(BaseModel):
    regression_id: str


class RegressionExportParams(BaseModel):
    regression_id: str
    output: str


class RegressionImportParams(BaseModel):
    archive: str
    replace: bool = False


class RegressionRunParams(BaseModel):
    regression_id: str
    trace_id: str


class RegressionCompareParams(BaseModel):
    regression_id: str
    run_id: str | None = None
    against: str = "expected"


class CorrectionsRebuildParams(BaseModel):
    trace_id: str | None = None
    limit: int = Field(default=200, ge=1, le=2000)


class OptimizeProposeParams(BaseModel):
    llm: bool = False
    apply: bool = False
    limit: int = Field(default=5, ge=1, le=50)


class ReflectorPreviewParams(BaseModel):
    backend: str | None = Field(default=None, max_length=500)
    days: int = Field(default=14, ge=1, le=365)


class ReflectorRunParams(ReflectorPreviewParams):
    consent_token: str = Field(pattern=r"^[0-9a-f]{64}$")


class ExperimentApplyParams(BaseModel):
    experiment_id: str


class ExperimentRevertParams(BaseModel):
    experiment_id: str


class ExperimentMeasureParams(BaseModel):
    experiment_id: str


class OptimizeEvaluateParams(BaseModel):
    force: bool = False
    limit: int = Field(default=20, ge=1, le=100)


class InsightSetStateParams(BaseModel):
    insight_id: str
    state: InsightLifecycle


class InsightSnoozeParams(BaseModel):
    insight_id: str
    days: int = Field(default=14, ge=1, le=90)


class AnnotateParams(BaseModel):
    trace_id: str
    text: str
    span_id: str | None = None


class ConfigSetParams(BaseModel):
    operation: Literal["get", "set", "unset", "list"] = "set"
    key: str | None = None
    value: str | None = None
    scope: Literal["user", "workspace"] = "workspace"
    reveal_secrets: bool = False
    confirm_storage_upgrade: bool = False


class StorageStripParams(BaseModel):
    """Strip retained text_inline according to storage mode (metrics/hashes kept)."""

    limit: int = Field(default=5000, ge=1, le=50_000)
    dry_run: bool = False


class GitExcludeParams(BaseModel):
    """Approve writing `.cairn/` to `.git/info/exclude` (local only)."""

    approve: bool = False


class LifecyclePlanParams(BaseModel):
    """Dry-run cleanup counts (never mutates)."""

    mode: Literal["strip_text", "delete_traces"] = "strip_text"
    retain_days: int | None = Field(default=None, ge=0, le=3650)


class LifecycleCleanupParams(BaseModel):
    """Strip text or delete Cairn traces after confirm (source logs untouched)."""

    mode: Literal["strip_text", "delete_traces"] = "strip_text"
    retain_days: int | None = Field(default=None, ge=0, le=3650)
    confirm: bool = False
    limit: int = Field(default=5000, ge=1, le=50_000)


class DbBackupParams(BaseModel):
    """Copy cairn.db into .cairn/backups/manual via sqlite backup API."""

    label: str | None = None


class DbRestoreParams(BaseModel):
    """Replace cairn.db from a backup under .cairn/ (destructive, confirmed)."""

    backup: str
    confirm: bool = False
    dry_run: bool = False


class DbBackupListParams(BaseModel):
    """List SQLite backups under .cairn/backups/manual."""


class DbCompactParams(BaseModel):
    """WAL checkpoint + VACUUM (confirmed)."""

    confirm: bool = False


class ArchiveExportParams(BaseModel):
    """Export a versioned cairn.archive.v1 ZIP (ADR-10)."""

    mode: Literal["full", "scrubbed", "metadata_only"] = "scrubbed"
    limit: int = Field(default=500, ge=1, le=5_000)
    output: str | None = None
    dry_run: bool = False


class ArchiveImportParams(BaseModel):
    """Import a cairn.archive.v1 ZIP (default dry-run)."""

    archive: str
    dry_run: bool = True
    conflict: Literal["skip", "replace", "fail"] = "fail"


class ArchiveInspectParams(BaseModel):
    """Inspect archive envelope without applying."""

    archive: str


class EgressExportParams(BaseModel):
    """Export privacy-minimized egress ledger JSON."""

    output: str | None = None


class CircuitResumeParams(BaseModel):
    """Clear ingest circuit-breaker pauses (optional adapter scope)."""

    adapter_id: str | None = None


class McpInstallParams(BaseModel):
    client: str | None = None
    print_only: bool = False


class DemoSeedParams(BaseModel):
    reset: bool = False


def _sync_action(params: SyncParams, ctx: ActionCtx) -> dict[str, Any]:
    from server.configuration import load_config
    from server.improve.experiments import reevaluate_due_experiments

    report = ctx.pipeline.sync_all(params.source, force=params.force)
    result: dict[str, Any] = {
        "scanned": report.scanned,
        "inserted": report.inserted,
        "updated": report.updated,
        "skipped": report.skipped,
        "mcp_consultations": report.mcp_consultations,
        "source": params.source,
        "force": params.force,
    }
    mcp_config = load_config(ctx.workspace_root).mcp
    if mcp_config.auto_install:
        from server.mcp.install import install_mcp_config

        result["mcp_auto_install"] = install_mcp_config(
            workspace_root=ctx.workspace_root,
            client=mcp_config.client,
            write=True,
        )
    portfolio = reevaluate_due_experiments(
        ctx.db.reader, workspace_id=ctx.workspace_id, force=False
    )
    ctx.db.reader.commit()
    result["portfolio_reeval"] = {
        "evaluated_count": portfolio["evaluated_count"],
        "decay_refreshed": portfolio["decay_refreshed"],
        "daemon": False,
    }
    return result


def _backfill_action(params: BackfillParams, ctx: ActionCtx) -> dict[str, Any]:
    # Filter by stream file mtime — adapters do not all expose session timestamps.
    since = datetime.now(UTC) - timedelta(days=params.days)
    report = ctx.pipeline.sync_all(since=since)
    return {
        "days": params.days,
        "since": since.isoformat(),
        "inserted": report.inserted,
        "updated": report.updated,
        "scanned": report.scanned,
        "skipped": report.skipped,
        "mcp_consultations": report.mcp_consultations,
    }


def _rebuild_view_action(params: RebuildViewParams, ctx: ActionCtx) -> dict[str, Any]:
    from server.analyze.views import VIEW_ORDER
    from server.store.pagination import iter_rows

    if params.view == "all":
        views_to_rebuild = list(VIEW_ORDER)
    elif params.view in VIEW_ORDER:
        views_to_rebuild = [params.view]
    else:
        msg = f"unknown view {params.view!r}; use one of {VIEW_ORDER} or 'all'"
        raise ValueError(msg)

    deleted = 0
    for view_name in views_to_rebuild:
        deleted += ViewStateRepo.delete_by_view(ctx.db.reader, view_name)
    ctx.db.reader.commit()
    views = build_views(ctx.workspace_id)
    scheduler = ViewScheduler(ctx.db.reader, views)
    recomputed = 0
    traces_seen = 0
    for row in iter_rows(
        ctx.db.reader,
        "SELECT trace_id FROM traces WHERE workspace_id = ? ORDER BY started_at, trace_id",
        (ctx.workspace_id,),
    ):
        traces_seen += 1
        tid = str(row["trace_id"])
        dirty = [f"{view_name}:{tid}" for view_name in views_to_rebuild]
        recomputed += len(scheduler.run(dirty))
    ctx.db.reader.commit()
    return {
        "view": params.view,
        "views": views_to_rebuild,
        "cleared": deleted,
        "traces": traces_seen,
        "recomputed": recomputed,
    }


def _check_action(params: CheckParams, ctx: ActionCtx) -> dict[str, Any]:
    from server.analyze.policy import evaluate_session_policy
    from server.configuration import load_config
    from server.store.repos.outcomes import OutcomeRepo
    from server.store.repos.spans import SpanRepo

    config = load_config(ctx.workspace_root)
    configured_budget = config.budgets
    policy = config.policy
    min_quality = (
        params.min_quality if params.min_quality is not None else configured_budget.min_quality
    )
    failures: list[str] = []
    policy_findings: list[dict[str, Any]] = []
    rows = ctx.db.reader.execute(
        """
        SELECT t.trace_id, t.waste_tokens, t.input_tokens, t.cost, o.quality_score
        FROM traces t
        LEFT JOIN outcomes o ON o.trace_id = t.trace_id
        WHERE t.workspace_id = ?
        ORDER BY t.started_at DESC
        LIMIT 200
        """,
        (ctx.workspace_id,),
    ).fetchall()
    for row in rows:
        inp = int(row["input_tokens"] or 0)
        waste = int(row["waste_tokens"] or 0)
        if params.max_waste_pct is not None and inp > 0:
            pct = waste / inp * 100
            if pct > params.max_waste_pct:
                failures.append(f"{row['trace_id']}: waste {pct:.1f}%")
        quality = row["quality_score"]
        if min_quality is not None and quality is not None and float(quality) < min_quality:
            failures.append(f"{row['trace_id']}: quality {quality}")
        trace_id = str(row["trace_id"])
        spans = SpanRepo.list_by_trace(ctx.db.reader, trace_id)
        outcome = OutcomeRepo.get(ctx.db.reader, trace_id)
        risk = evaluate_session_policy(spans=spans, outcome=outcome, policy=policy)
        for finding in risk.get("findings") or []:
            if finding.get("enforcement_source") == "allowlisted_exception":
                continue
            if finding.get("risk") == "high" or finding.get("enforcement_source") == (
                "observed_violation"
            ):
                failures.append(
                    f"{trace_id}: policy {finding['rule_id']} "
                    f"[{finding['enforcement_source']}] {finding['message']}"
                )
                policy_findings.append({"trace_id": trace_id, **finding})
    if params.max_tail_cost is not None:
        costs = np.array([float(r["cost"] or 0.0) for r in rows], dtype=float)
        if costs.size >= 5:
            worst = return_level(costs, 1000)
            if worst > params.max_tail_cost:
                failures.append(
                    f"projected worst session cost ${worst:.2f} > ${params.max_tail_cost}"
                )
    return {
        "ok": len(failures) == 0,
        "failures": failures,
        "policy_findings": policy_findings,
        "enforcement_note": (
            "Policy failures are advisory observations from the ledger; "
            "Cairn does not claim to have blocked the underlying actions."
        ),
    }


def _export_session_html_action(params: ExportSessionHtmlParams, ctx: ActionCtx) -> dict[str, Any]:
    from server.export.session_html import export_session_html as write_session_html

    output = Path(params.output).expanduser() if params.output else None
    return write_session_html(
        ctx.db.reader,
        workspace_id=ctx.workspace_id,
        workspace_root=ctx.workspace_root,
        trace_id=params.trace_id,
        output=output,
    )


def _verification_rebuild_action(
    params: VerificationRebuildParams, ctx: ActionCtx
) -> dict[str, Any]:
    from server.analyze.verification import build_receipt_for_trace
    from server.store.repos.receipts import ReceiptRepo

    built_at = datetime.now(UTC).isoformat()
    if params.trace_id:
        trace_ids = [params.trace_id]
    else:
        rows = ctx.db.reader.execute(
            """
            SELECT trace_id FROM traces
            WHERE workspace_id = ?
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (ctx.workspace_id, params.limit),
        ).fetchall()
        trace_ids = [str(row["trace_id"]) for row in rows]

    rebuilt = 0
    unchanged = 0
    missing = 0
    for trace_id in trace_ids:
        receipt = build_receipt_for_trace(ctx.db.reader, trace_id)
        if receipt is None:
            missing += 1
            continue
        prior = ReceiptRepo.get_hash(ctx.db.reader, trace_id)
        if prior == receipt["content_hash"]:
            unchanged += 1
            continue

        def _write(
            conn: sqlite3.Connection,
            *,
            _receipt: dict[str, Any] = receipt,
            _at: str = built_at,
        ) -> None:
            ReceiptRepo.upsert(conn, _receipt, built_at=_at)

        ctx.db.write(_write)
        rebuilt += 1
    return {
        "ok": True,
        "rebuilt": rebuilt,
        "unchanged": unchanged,
        "missing": missing,
        "considered": len(trace_ids),
        "schema_version": "cairn.receipt.v1",
    }


def _regression_create_action(params: RegressionCreateParams, ctx: ActionCtx) -> dict[str, Any]:
    from server.regression.create import create_regression_from_trace

    return create_regression_from_trace(
        ctx.db.reader,
        workspace_root=ctx.workspace_root,
        workspace_id=ctx.workspace_id,
        trace_id=params.trace_id,
    )


def _regression_delete_action(params: RegressionDeleteParams, ctx: ActionCtx) -> dict[str, Any]:
    from server.regression.store import delete_regression

    deleted = delete_regression(ctx.workspace_root, params.regression_id)
    return {
        "ok": deleted,
        "regression_id": params.regression_id,
        "error": None if deleted else "regression_not_found",
    }


def _regression_export_action(params: RegressionExportParams, ctx: ActionCtx) -> dict[str, Any]:
    from server.regression.io import export_regression_zip

    return export_regression_zip(
        ctx.workspace_root,
        params.regression_id,
        output=Path(params.output),
    )


def _regression_import_action(params: RegressionImportParams, ctx: ActionCtx) -> dict[str, Any]:
    from server.regression.io import import_regression_zip

    return import_regression_zip(
        ctx.workspace_root,
        Path(params.archive),
        replace=params.replace,
    )


def _regression_run_action(params: RegressionRunParams, ctx: ActionCtx) -> dict[str, Any]:
    from server.regression.run import record_run_from_trace

    return record_run_from_trace(
        ctx.db.reader,
        workspace_root=ctx.workspace_root,
        workspace_id=ctx.workspace_id,
        regression_id=params.regression_id,
        trace_id=params.trace_id,
    )


def _regression_compare_action(params: RegressionCompareParams, ctx: ActionCtx) -> dict[str, Any]:
    from server.regression.compare import compare_regression

    return compare_regression(
        ctx.workspace_root,
        regression_id=params.regression_id,
        run_id=params.run_id,
        against=params.against,
    )


def _corrections_rebuild_action(params: CorrectionsRebuildParams, ctx: ActionCtx) -> dict[str, Any]:
    from server.analyze.corrections import build_corrections_for_trace
    from server.store.repos.corrections import CorrectionRepo

    built_at = datetime.now(UTC).isoformat()
    if params.trace_id:
        trace_ids = [params.trace_id]
    else:
        rows = ctx.db.reader.execute(
            """
            SELECT trace_id FROM traces
            WHERE workspace_id = ?
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (ctx.workspace_id, params.limit),
        ).fetchall()
        trace_ids = [str(row["trace_id"]) for row in rows]

    rebuilt = 0
    unchanged = 0
    missing = 0
    for trace_id in trace_ids:
        payload = build_corrections_for_trace(ctx.db.reader, trace_id)
        if payload is None:
            missing += 1
            continue
        prior = CorrectionRepo.get_hash(ctx.db.reader, trace_id)
        if prior == payload["content_hash"]:
            unchanged += 1
            continue

        def _write(
            conn: sqlite3.Connection,
            *,
            _payload: dict[str, Any] = payload,
            _at: str = built_at,
        ) -> None:
            CorrectionRepo.upsert(conn, _payload, built_at=_at)

        ctx.db.write(_write)
        rebuilt += 1
    return {
        "ok": True,
        "rebuilt": rebuilt,
        "unchanged": unchanged,
        "missing": missing,
        "considered": len(trace_ids),
        "schema_version": "cairn.corrections.v1",
    }


def _export_bundle_action(params: ExportBundleParams, ctx: ActionCtx) -> dict[str, Any]:
    from server.export.scrub import scrub_export_value

    out_dir = ctx.workspace_root / ".cairn" / "exports"
    ensure_private_dir(out_dir)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"bundle-{stamp}.json"
    if params.trace_id:
        rows = ctx.db.reader.execute(
            "SELECT * FROM traces WHERE trace_id = ? AND workspace_id = ?",
            (params.trace_id, ctx.workspace_id),
        ).fetchall()
    else:
        rows = ctx.db.reader.execute(
            "SELECT * FROM traces WHERE workspace_id = ? ORDER BY started_at DESC LIMIT 50",
            (ctx.workspace_id,),
        ).fetchall()
    trace_rows = [dict(r) for r in rows]
    trace_ids = [str(row["trace_id"]) for row in trace_rows]
    session_payload: dict[str, Any] = {"traces": trace_rows}
    if params.trace_id and trace_ids:
        trace_id = trace_ids[0]
        session_payload.update(
            {
                "spans": [
                    dict(row)
                    for row in ctx.db.reader.execute(
                        "SELECT * FROM spans WHERE trace_id = ? ORDER BY seq, span_id",
                        (trace_id,),
                    ).fetchall()
                ],
                "span_links": [
                    dict(row)
                    for row in ctx.db.reader.execute(
                        """
                        SELECT from_span_id, to_span_id, link_type
                        FROM span_links
                        WHERE from_span_id IN (
                            SELECT span_id FROM spans WHERE trace_id = ?
                        )
                        OR to_span_id IN (
                            SELECT span_id FROM spans WHERE trace_id = ?
                        )
                        ORDER BY from_span_id, to_span_id, link_type
                        """,
                        (trace_id, trace_id),
                    ).fetchall()
                ],
                "outcomes": [
                    dict(row)
                    for row in ctx.db.reader.execute(
                        "SELECT * FROM outcomes WHERE trace_id = ?",
                        (trace_id,),
                    ).fetchall()
                ],
                "data_quality": [
                    dict(row)
                    for row in ctx.db.reader.execute(
                        "SELECT * FROM data_quality WHERE trace_id = ?",
                        (trace_id,),
                    ).fetchall()
                ],
                "diagnostics": [
                    dict(row)
                    for row in ctx.db.reader.execute(
                        "SELECT * FROM diagnostics WHERE trace_id = ?",
                        (trace_id,),
                    ).fetchall()
                ],
            }
        )
    if params.scrub:
        session_payload = scrub_export_value(session_payload, ctx.workspace_root)
    payload: dict[str, Any] = {
        "schema_version": 1,
        "exported_at": datetime.now(UTC).isoformat(),
        "scrubbed": params.scrub,
        "field_classes": {
            "included": [
                "session metadata",
                "normalized spans",
                "span links",
                "outcomes",
                "data quality",
                "diagnostics",
            ],
            "redacted": [
                "titles and raw content",
                "paths and repository identifiers",
                "URLs and credential-like strings",
            ]
            if params.scrub
            else [],
        },
        **session_payload,
    }
    write_private_text(out_path, json.dumps(payload, indent=2))
    from server.analyze.git_privacy import export_path_warnings

    warnings = export_path_warnings(ctx.workspace_root, out_path)
    return {
        "path": str(out_path),
        "count": len(trace_rows),
        "scrubbed": params.scrub,
        "included_field_classes": payload["field_classes"]["included"],
        "warnings": warnings,
    }


def _mcp_install_action(params: McpInstallParams, ctx: ActionCtx) -> dict[str, Any]:
    from server.configuration import load_config
    from server.mcp.install import install_mcp_config

    allowed = {"claude-code", "cursor", "codex", "other"}
    configured = load_config(ctx.workspace_root).mcp.client
    client = params.client if params.client in allowed else configured
    return install_mcp_config(
        workspace_root=ctx.workspace_root,
        client=client,  # type: ignore[arg-type]
        write=not params.print_only,
    )


def _demo_seed_action(params: DemoSeedParams, _ctx: ActionCtx) -> dict[str, Any]:
    result = seed_demo_workspace(reset=params.reset)
    return {
        "root": str(result.root),
        "workspace_id": result.workspace_id,
        "trace_count": result.trace_count,
        "actor_count": result.actor_count,
        "source_count": result.source_count,
        "reset": result.reset,
    }


def _optimize_propose_action(params: OptimizeProposeParams, ctx: ActionCtx) -> dict[str, Any]:
    from server.configuration import load_config
    from server.improve.experiments import create_experiment

    if params.apply:
        msg = (
            "optimize_propose does not apply experiments; "
            "omit apply (or set apply=false) and call experiment_apply "
            "with a returned experiment_id"
        )
        raise ValueError(msg)
    if params.llm:
        msg = (
            "optimize_propose --llm does not call a provider; "
            "use reflector_preview / reflector_run for optional LLM reflection, "
            "or omit --llm for local proposal generation"
        )
        raise ValueError(msg)

    optimize_config = load_config(ctx.workspace_root).optimize
    evaluate_insights(ctx.db.reader, workspace_id=ctx.workspace_id)
    proposals = generate_proposals(ctx.db.reader, limit=params.limit)
    experiments = []
    for proposal in proposals:
        experiment = ExperimentRepo.get_active_for_block(
            ctx.db.reader, proposal.target_file, proposal.block_key
        )
        if experiment is None:
            experiment = create_experiment(
                ctx.db.reader,
                target_file=proposal.target_file,
                block_key=proposal.block_key,
                kind=proposal.kind,
                content=proposal.content,
                evidence_id=proposal.evidence_id,
                min_holdout=optimize_config.holdout,
                proposal_source="local",
            )
        experiments.append(experiment)
    ctx.db.reader.commit()
    return {
        "proposals": [
            {
                "target_file": p.target_file,
                "block_key": p.block_key,
                "kind": p.kind,
                "content": p.content,
                "evidence_id": p.evidence_id,
                "experiment_id": experiments[index].experiment_id,
            }
            for index, p in enumerate(proposals)
        ],
        "llm": False,
        "apply": False,
    }


def _reflector_inputs(
    params: ReflectorPreviewParams,
    ctx: ActionCtx,
) -> tuple[str, str, Any, Any]:
    from server.configuration import load_config
    from server.improve.evidence_pack import build_evidence_pack
    from server.improve.reflector import build_prompt, preview_backend, resolve_backend

    backend = resolve_backend(params.backend or load_config(ctx.workspace_root).optimize.backend)
    if backend is None:
        msg = "No reflector backend is configured"
        raise ValueError(msg)
    pack = build_evidence_pack(
        ctx.db.reader,
        ctx.workspace_root,
        workspace_id=ctx.workspace_id,
        days=params.days,
    )
    agents = ctx.workspace_root / "AGENTS.md"
    current = agents.read_text(encoding="utf-8")[:65_536] if agents.is_file() else ""
    prompt = build_prompt(current, pack)
    return backend, current, pack, preview_backend(backend, prompt)


def _reflector_preview_action(
    params: ReflectorPreviewParams,
    ctx: ActionCtx,
) -> dict[str, Any]:
    _backend, _current, _pack, preview = _reflector_inputs(params, ctx)
    return {"preview": preview.__dict__, "network_attempted": False}


def _reflector_run_action(
    params: ReflectorRunParams,
    ctx: ActionCtx,
) -> dict[str, Any]:
    from server.improve.reflector import reflect

    backend, current, pack, preview = _reflector_inputs(params, ctx)
    if not secrets.compare_digest(params.consent_token, preview.consent_token):
        return {
            "preview": preview.__dict__,
            "network_attempted": False,
            "error": {
                "code": "consent_mismatch",
                "message": "Preview changed; review it and use its new consent_token",
            },
        }
    proposals = reflect(
        current,
        pack,
        backend,
        allow_network=True,
        workspace_root=ctx.workspace_root,
    )
    return {
        "preview": preview.__dict__,
        "network_attempted": True,
        "proposals": [proposal.__dict__ for proposal in proposals],
    }


def _experiment_apply_action(params: ExperimentApplyParams, ctx: ActionCtx) -> dict[str, Any]:
    exp = ExperimentRepo.get(ctx.db.reader, params.experiment_id)
    if exp is None:
        msg = "experiment not found"
        raise ValueError(msg)
    from server.improve.experiments import apply_experiment

    apply_experiment(ctx.db.reader, exp, repo_root=ctx.workspace_root)
    ctx.db.reader.commit()
    return {"experiment_id": params.experiment_id, "status": "applied"}


def _experiment_revert_action(params: ExperimentRevertParams, ctx: ActionCtx) -> dict[str, Any]:
    exp = ExperimentRepo.get(ctx.db.reader, params.experiment_id)
    if exp is None:
        msg = "experiment not found"
        raise ValueError(msg)
    from server.improve.apply import find_backup

    backup_dir = ctx.workspace_root / ".cairn" / "backups"
    target = ctx.workspace_root / exp.target_file
    backup = find_backup(backup_dir, target, backup_key=exp.experiment_id)
    if backup is None:
        msg = "no backup found"
        raise ValueError(msg)
    from server.improve.experiments import revert_experiment

    revert_experiment(ctx.db.reader, exp, repo_root=ctx.workspace_root, backup=backup)
    ctx.db.reader.commit()
    return {"experiment_id": params.experiment_id, "status": "reverted"}


def _experiment_measure_action(params: ExperimentMeasureParams, ctx: ActionCtx) -> dict[str, Any]:
    exp = ExperimentRepo.get(ctx.db.reader, params.experiment_id)
    if exp is None:
        msg = "experiment not found"
        raise ValueError(msg)

    from server.improve.experiments import measure_experiment, waste_rate_metric

    trace_ids = [
        str(r["trace_id"])
        for r in ctx.db.reader.execute(
            "SELECT trace_id FROM traces WHERE workspace_id = ? ORDER BY started_at DESC LIMIT 40",
            (ctx.workspace_id,),
        ).fetchall()
    ]
    mid = max(1, len(trace_ids) // 2)
    result = measure_experiment(
        ctx.db.reader,
        exp,
        pre_trace_ids=trace_ids[mid:],
        post_trace_ids=trace_ids[:mid],
        metric_fn=lambda tid: waste_rate_metric(ctx.db.reader, tid),
    )
    ctx.db.reader.commit()
    return {
        "experiment_id": params.experiment_id,
        "verdict": result.verdict,
        "effect_estimate": result.effect_estimate,
        "n_effective": result.n_effective,
        "gated": result.gated,
    }


def _optimize_evaluate_action(params: OptimizeEvaluateParams, ctx: ActionCtx) -> dict[str, Any]:
    from server.improve.experiments import reevaluate_due_experiments

    result = reevaluate_due_experiments(
        ctx.db.reader,
        workspace_id=ctx.workspace_id,
        force=params.force,
        limit=params.limit,
    )
    ctx.db.reader.commit()
    return result


def _insight_set_state_action(params: InsightSetStateParams, ctx: ActionCtx) -> dict[str, Any]:
    insight = InsightRepo.get(ctx.db.reader, params.insight_id)
    if insight is None:
        msg = "insight not found"
        raise ValueError(msg)
    previous = InsightRepo.get_state(ctx.db.reader, params.insight_id)
    see_count = previous.see_count if previous is not None else 1
    snoozed_until = previous.snoozed_until if previous is not None else None
    baseline = previous.snooze_savings_baseline if previous is not None else None
    if params.state != "muted":
        snoozed_until = None
        baseline = None
    InsightRepo.set_state(
        ctx.db.reader,
        InsightState(
            insight_id=params.insight_id,
            state=params.state,
            changed_at=datetime.now(UTC).isoformat(),
            changed_by="api",
            snoozed_until=snoozed_until,
            snooze_savings_baseline=baseline,
            see_count=see_count,
        ),
    )
    ctx.db.reader.commit()
    ctx.event_bus.publish(
        "insight-updated",
        {"insight_id": params.insight_id, "state": params.state},
    )
    return {"insight_id": params.insight_id, "state": params.state}


def _insight_snooze_action(params: InsightSnoozeParams, ctx: ActionCtx) -> dict[str, Any]:
    insight = InsightRepo.get(ctx.db.reader, params.insight_id)
    if insight is None:
        msg = "insight not found"
        raise ValueError(msg)
    previous = InsightRepo.get_state(ctx.db.reader, params.insight_id)
    now = datetime.now(UTC)
    snoozed_until = (now + timedelta(days=params.days)).isoformat()
    InsightRepo.set_state(
        ctx.db.reader,
        InsightState(
            insight_id=params.insight_id,
            state="muted",
            changed_at=now.isoformat(),
            changed_by="api",
            snoozed_until=snoozed_until,
            snooze_savings_baseline=insight.savings_estimate,
            see_count=previous.see_count if previous is not None else 1,
        ),
    )
    ctx.db.reader.commit()
    ctx.event_bus.publish(
        "insight-updated",
        {
            "insight_id": params.insight_id,
            "state": "muted",
            "snoozed_until": snoozed_until,
        },
    )
    return {
        "insight_id": params.insight_id,
        "state": "muted",
        "snoozed_until": snoozed_until,
        "days": params.days,
    }


def _annotate_action(params: AnnotateParams, ctx: ActionCtx) -> dict[str, Any]:
    subject_type = "span" if params.span_id else "trace"
    subject_id = params.span_id or params.trace_id
    ann = Annotation(
        annotation_id=new_ulid(),
        subject_type=subject_type,
        subject_id=subject_id,
        body=params.text,
        author="api",
        created_at=datetime.now(UTC).isoformat(),
    )
    AnnotationRepo.create(ctx.db.reader, ann)
    ctx.db.reader.commit()
    return {"annotation_id": ann.annotation_id}


def _workspace_scan_action(params: WorkspaceScanParams, ctx: ActionCtx) -> dict[str, Any]:
    paths = ctx.pipeline.watch_paths()
    report = ctx.pipeline.sync_all(force=params.force)
    return {
        "paths": [str(p) for p in paths],
        "count": len(paths),
        "scanned": report.scanned,
        "inserted": report.inserted,
        "updated": report.updated,
        "skipped": report.skipped,
        "mcp_consultations": report.mcp_consultations,
        "force": params.force,
    }


def _config_set_action(params: ConfigSetParams, _ctx: ActionCtx) -> dict[str, Any]:
    from server.configuration import (
        ConfigError,
        get_config_value,
        list_config_values,
        load_config,
        mutate_config,
    )

    if params.operation == "list":
        return {
            "values": list_config_values(_ctx.workspace_root, reveal_secrets=params.reveal_secrets)
        }
    if not params.key:
        raise ConfigError(f"config {params.operation} requires a key")
    if params.operation == "get":
        return get_config_value(
            params.key,
            _ctx.workspace_root,
            reveal_secrets=params.reveal_secrets,
        )
    if params.operation == "set" and params.value is None:
        raise ConfigError("config set requires a value")
    key = (params.key or "").strip().lower().replace("-", "_")
    if (
        params.operation == "set"
        and key == "storage.mode"
        and params.value is not None
        and not params.confirm_storage_upgrade
    ):
        from server.ingest.storage import is_upgrade, normalize_storage_mode

        current = normalize_storage_mode(load_config(_ctx.workspace_root).storage.mode)
        requested = normalize_storage_mode(str(params.value))
        if is_upgrade(current, requested):
            raise ConfigError(
                f"Refusing silent storage upgrade {current!r} → {requested!r}. "
                "Re-run with confirm_storage_upgrade=true after reviewing privacy impact."
            )
    result = mutate_config(
        params.operation,
        params.key,
        value=params.value,
        workspace_root=_ctx.workspace_root,
        scope=params.scope,
    )
    if key in {"collection.mode"} and params.operation in {"set", "unset"}:
        runtime = _ctx.pipeline.reload_collection_mode()
        result = {
            **result,
            "collection": {
                "mode": runtime.mode,
                "label": runtime.label,
                "auto_sync_active": runtime.watcher_enabled or runtime.refresh_enabled,
                "limitation": runtime.limitation,
            },
        }
    if key.startswith("storage.") and params.operation in {"set", "unset"}:
        from server.ingest.storage import storage_status

        result = {**result, "storage": storage_status(_ctx.workspace_root)}
    return result


def _storage_strip_action(params: StorageStripParams, ctx: ActionCtx) -> dict[str, Any]:
    from server.configuration import load_config
    from server.ingest.storage import normalize_storage_mode, strip_inline_content

    config = load_config(ctx.workspace_root).storage
    mode = normalize_storage_mode(config.mode)
    if params.dry_run:
        remaining = ctx.db.reader.execute(
            """
            SELECT COUNT(*) AS n
            FROM spans s
            JOIN traces t ON t.trace_id = s.trace_id
            WHERE t.workspace_id = ?
              AND s.text_inline IS NOT NULL
              AND s.text_inline != ''
            """,
            (ctx.workspace_id,),
        ).fetchone()
        return {
            "dry_run": True,
            "mode": mode,
            "would_consider": int(remaining["n"] or 0) if remaining else 0,
            "limit": params.limit,
            "limitation": "Dry run only — no rows modified.",
        }

    def _strip(conn: sqlite3.Connection) -> dict[str, Any]:
        return strip_inline_content(
            conn,
            workspace_id=ctx.workspace_id,
            mode=mode,
            retain_days=config.balanced_retain_days,
            limit=params.limit,
        )

    return ctx.db.write(_strip)


def _git_exclude_cairn_action(params: GitExcludeParams, ctx: ActionCtx) -> dict[str, Any]:
    from server.analyze.git_privacy import (
        assess_git_privacy,
        ensure_git_exclude_cairn,
        report_as_dict,
    )

    result = ensure_git_exclude_cairn(ctx.workspace_root, approve=params.approve)
    result["git_privacy"] = report_as_dict(assess_git_privacy(ctx.workspace_root))
    return result


def _lifecycle_plan_action(params: LifecyclePlanParams, ctx: ActionCtx) -> dict[str, Any]:
    from dataclasses import asdict

    from server.store.lifecycle import _resolve_retain_days, lifecycle_status, plan_cleanup

    days = _resolve_retain_days(ctx.workspace_root, params.retain_days)
    plan = plan_cleanup(
        ctx.db.reader,
        workspace_id=ctx.workspace_id,
        mode=params.mode,
        retain_days=days,
    )
    return {
        "ok": True,
        "dry_run": True,
        **asdict(plan),
        "lifecycle": lifecycle_status(ctx.workspace_root),
    }


def _lifecycle_cleanup_action(params: LifecycleCleanupParams, ctx: ActionCtx) -> dict[str, Any]:
    from server.store.lifecycle import run_cleanup

    def _run(conn: sqlite3.Connection) -> dict[str, Any]:
        return run_cleanup(
            conn,
            workspace_id=ctx.workspace_id,
            workspace_root=ctx.workspace_root,
            mode=params.mode,
            retain_days=params.retain_days,
            confirm=params.confirm,
            limit=params.limit,
        )

    return ctx.db.write(_run)


def _db_backup_action(params: DbBackupParams, ctx: ActionCtx) -> dict[str, Any]:
    from server.store.lifecycle import backup_database

    return backup_database(ctx.workspace_root, label=params.label)


def _db_restore_action(params: DbRestoreParams, ctx: ActionCtx) -> dict[str, Any]:
    from server.store.lifecycle import restore_database

    return restore_database(
        ctx.workspace_root,
        backup=Path(params.backup),
        confirm=params.confirm,
        dry_run=params.dry_run,
    )


def _db_backup_list_action(_params: DbBackupListParams, ctx: ActionCtx) -> dict[str, Any]:
    from server.store.lifecycle import list_database_backups

    return list_database_backups(ctx.workspace_root)


def _db_integrity_action(_params: EmptyParams, ctx: ActionCtx) -> dict[str, Any]:
    from server.store.lifecycle import db_path, verify_integrity

    return verify_integrity(db_path(ctx.workspace_root))


def _db_compact_action(params: DbCompactParams, ctx: ActionCtx) -> dict[str, Any]:
    from server.store.lifecycle import compact_database

    return compact_database(ctx.workspace_root, confirm=params.confirm)


def _pricing_status_action(_params: EmptyParams, ctx: ActionCtx) -> dict[str, Any]:
    from server.ingest.pricing import pricing_status

    return pricing_status(ctx.workspace_root)


def _pricing_refresh_preview_action(_params: EmptyParams, ctx: ActionCtx) -> dict[str, Any]:
    from server.ingest.pricing import pricing_refresh_preview

    return pricing_refresh_preview(ctx.workspace_root)


def _archive_export_action(params: ArchiveExportParams, ctx: ActionCtx) -> dict[str, Any]:
    from server.archive.export import export_archive, preview_archive

    if params.dry_run:
        return preview_archive(
            ctx.db.reader,
            workspace_id=ctx.workspace_id,
            workspace_root=ctx.workspace_root,
            mode=params.mode,
            limit=params.limit,
        )
    output = Path(params.output) if params.output else None
    return export_archive(
        ctx.db.reader,
        workspace_id=ctx.workspace_id,
        workspace_root=ctx.workspace_root,
        output=output,
        mode=params.mode,
        limit=params.limit,
    )


def _archive_import_action(params: ArchiveImportParams, ctx: ActionCtx) -> dict[str, Any]:
    from server.archive.import_archive import import_archive

    def _run(conn: sqlite3.Connection) -> dict[str, Any]:
        return import_archive(
            conn,
            workspace_id=ctx.workspace_id,
            workspace_root=ctx.workspace_root,
            archive=Path(params.archive),
            dry_run=params.dry_run,
            conflict=params.conflict,
        )

    if params.dry_run:
        return _run(ctx.db.reader)
    return ctx.db.write(_run)


def _archive_inspect_action(params: ArchiveInspectParams, _ctx: ActionCtx) -> dict[str, Any]:
    from server.archive.inspect_archive import inspect_archive

    return inspect_archive(Path(params.archive))


def _egress_status_action(_params: EmptyParams, ctx: ActionCtx) -> dict[str, Any]:
    from server.util.egress import egress_status

    return egress_status(ctx.workspace_root)


def _egress_export_action(params: EgressExportParams, ctx: ActionCtx) -> dict[str, Any]:
    from server.util.egress import export_egress

    return export_egress(
        ctx.workspace_root,
        output=Path(params.output) if params.output else None,
    )


def _circuit_status_action(_params: EmptyParams, ctx: ActionCtx) -> dict[str, Any]:
    from server.ingest.circuit_breakers import circuit_status

    return circuit_status(ctx.workspace_root)


def _circuit_resume_action(params: CircuitResumeParams, ctx: ActionCtx) -> dict[str, Any]:
    from server.ingest.circuit_breakers import resume_circuits

    return resume_circuits(ctx.workspace_root, adapter_id=params.adapter_id)


def _source_drift_status_action(_params: EmptyParams, ctx: ActionCtx) -> dict[str, Any]:
    from server.ingest.reference import reference_status
    from server.ingest.storage import normalize_storage_mode, storage_status

    status = storage_status(ctx.workspace_root)
    return {
        "storage_mode": normalize_storage_mode(status["mode"]),
        "reference": reference_status(ctx.workspace_root),
        "storage": status,
    }


def _server_stop_action(_params: EmptyParams, _ctx: ActionCtx) -> dict[str, Any]:
    os.kill(os.getpid(), signal.SIGTERM)
    return {"stopping": True}
