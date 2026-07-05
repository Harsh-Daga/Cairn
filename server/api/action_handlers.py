"""Registered action handler implementations."""

from __future__ import annotations

import json
import os
import signal
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from server.analyze.registry import build_views
from server.analyze.views import ViewScheduler
from server.api.context import ActionCtx
from server.improve.engine import evaluate as evaluate_insights
from server.improve.proposals import generate_proposals
from server.models.annotation import Annotation
from server.models.insight import InsightLifecycle, InsightState
from server.store.repos.annotations import AnnotationRepo
from server.store.repos.experiments import ExperimentRepo
from server.store.repos.insights import InsightRepo
from server.store.repos.views import ViewStateRepo
from server.util.ids import new_ulid


class EmptyParams(BaseModel):
    pass


class SyncParams(BaseModel):
    source: str | None = None


class BackfillParams(BaseModel):
    days: int = Field(default=30, ge=1, le=365)


class RebuildViewParams(BaseModel):
    view: str


class CheckParams(BaseModel):
    min_quality: float | None = Field(default=None, ge=0.0, le=1.0)
    max_waste_pct: float | None = Field(default=None, ge=0.0, le=100.0)


class ExportBundleParams(BaseModel):
    trace_id: str | None = None
    scrub: bool = True


class OptimizeProposeParams(BaseModel):
    llm: bool = False
    apply: bool = False
    limit: int = Field(default=5, ge=1, le=50)


class ExperimentApplyParams(BaseModel):
    experiment_id: str


class ExperimentRevertParams(BaseModel):
    experiment_id: str


class ExperimentMeasureParams(BaseModel):
    experiment_id: str


class InsightSetStateParams(BaseModel):
    insight_id: str
    state: InsightLifecycle


class AnnotateParams(BaseModel):
    trace_id: str
    text: str
    span_id: str | None = None


class ConfigSetParams(BaseModel):
    key: str
    value: str


class McpInstallParams(BaseModel):
    client: str = "cursor"
    print_only: bool = False


def _sync_action(params: SyncParams, ctx: ActionCtx) -> dict[str, Any]:
    report = ctx.pipeline.sync_all()
    return {
        "scanned": report.scanned,
        "inserted": report.inserted,
        "skipped": report.skipped,
        "source": params.source,
    }


def _backfill_action(params: BackfillParams, ctx: ActionCtx) -> dict[str, Any]:
    report = ctx.pipeline.sync_all()
    return {"days": params.days, "inserted": report.inserted, "scanned": report.scanned}


def _rebuild_view_action(params: RebuildViewParams, ctx: ActionCtx) -> dict[str, Any]:
    deleted = ViewStateRepo.delete_by_view(ctx.db.reader, params.view)
    ctx.db.reader.commit()
    views = build_views(ctx.workspace_id)
    scheduler = ViewScheduler(ctx.db.reader, views)
    trace_ids = [
        str(r["trace_id"])
        for r in ctx.db.reader.execute(
            "SELECT trace_id FROM traces WHERE workspace_id = ?",
            (ctx.workspace_id,),
        ).fetchall()
    ]
    dirty = [f"{params.view}:{tid}" for tid in trace_ids]
    updated = scheduler.run(dirty)
    ctx.db.reader.commit()
    return {"view": params.view, "cleared": deleted, "recomputed": len(updated)}


def _check_action(params: CheckParams, ctx: ActionCtx) -> dict[str, Any]:
    failures: list[str] = []
    rows = ctx.db.reader.execute(
        """
        SELECT t.trace_id, t.waste_tokens, t.input_tokens, o.quality_score
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
        if (
            params.min_quality is not None
            and quality is not None
            and float(quality) < params.min_quality
        ):
            failures.append(f"{row['trace_id']}: quality {quality}")
    return {"ok": len(failures) == 0, "failures": failures}


def _export_bundle_action(params: ExportBundleParams, ctx: ActionCtx) -> dict[str, Any]:
    out_dir = ctx.workspace_root / ".cairn" / "exports"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"bundle-{stamp}.json"
    if params.trace_id:
        rows = ctx.db.reader.execute(
            "SELECT * FROM traces WHERE trace_id = ?",
            (params.trace_id,),
        ).fetchall()
    else:
        rows = ctx.db.reader.execute(
            "SELECT * FROM traces WHERE workspace_id = ? ORDER BY started_at DESC LIMIT 50",
            (ctx.workspace_id,),
        ).fetchall()
    trace_rows = [dict(r) for r in rows]
    payload: dict[str, Any] = {"traces": trace_rows, "scrubbed": params.scrub}
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {"path": str(out_path), "count": len(trace_rows)}


def _mcp_install_action(params: McpInstallParams, ctx: ActionCtx) -> dict[str, Any]:
    from server.mcp.install import install_mcp_config

    allowed = {"claude-code", "cursor", "codex", "other"}
    client = params.client if params.client in allowed else "cursor"
    return install_mcp_config(
        workspace_root=ctx.workspace_root,
        client=client,  # type: ignore[arg-type]
        write=not params.print_only,
    )


def _optimize_propose_action(params: OptimizeProposeParams, ctx: ActionCtx) -> dict[str, Any]:
    evaluate_insights(ctx.db.reader, workspace_id=ctx.workspace_id)
    ctx.db.reader.commit()
    proposals = generate_proposals(ctx.db.reader, limit=params.limit)
    return {
        "proposals": [
            {
                "target_file": p.target_file,
                "block_key": p.block_key,
                "kind": p.kind,
                "content": p.content,
                "evidence_id": p.evidence_id,
            }
            for p in proposals
        ],
        "llm": params.llm,
        "apply": params.apply,
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
    backup_dir = ctx.workspace_root / ".cairn" / "backups"
    backups = sorted(backup_dir.glob(f"{Path(exp.target_file).name}.*.bak"))
    if not backups:
        msg = "no backup found"
        raise ValueError(msg)
    from server.improve.experiments import revert_experiment

    revert_experiment(ctx.db.reader, exp, repo_root=ctx.workspace_root, backup=backups[-1])
    ctx.db.reader.commit()
    return {"experiment_id": params.experiment_id, "status": "reverted"}


def _experiment_measure_action(params: ExperimentMeasureParams, ctx: ActionCtx) -> dict[str, Any]:
    exp = ExperimentRepo.get(ctx.db.reader, params.experiment_id)
    if exp is None:
        msg = "experiment not found"
        raise ValueError(msg)

    def _metric(trace_id: str) -> float:
        row = ctx.db.reader.execute(
            "SELECT waste_tokens, input_tokens FROM traces WHERE trace_id = ?",
            (trace_id,),
        ).fetchone()
        if row is None:
            return 0.0
        inp = int(row["input_tokens"] or 0)
        waste = int(row["waste_tokens"] or 0)
        return waste / inp if inp else 0.0

    trace_ids = [
        str(r["trace_id"])
        for r in ctx.db.reader.execute(
            "SELECT trace_id FROM traces WHERE workspace_id = ? ORDER BY started_at DESC LIMIT 40",
            (ctx.workspace_id,),
        ).fetchall()
    ]
    mid = max(1, len(trace_ids) // 2)
    from server.improve.experiments import measure_experiment

    result = measure_experiment(
        ctx.db.reader,
        exp,
        pre_trace_ids=trace_ids[mid:],
        post_trace_ids=trace_ids[:mid],
        metric_fn=_metric,
    )
    ctx.db.reader.commit()
    return {
        "experiment_id": params.experiment_id,
        "verdict": result.verdict,
        "effect_estimate": result.effect_estimate,
        "n_effective": result.n_effective,
        "gated": result.gated,
    }


def _insight_set_state_action(params: InsightSetStateParams, ctx: ActionCtx) -> dict[str, Any]:
    insight = InsightRepo.get(ctx.db.reader, params.insight_id)
    if insight is None:
        msg = "insight not found"
        raise ValueError(msg)
    InsightRepo.set_state(
        ctx.db.reader,
        InsightState(
            insight_id=params.insight_id,
            state=params.state,
            changed_at=datetime.now(UTC).isoformat(),
            changed_by="api",
        ),
    )
    ctx.db.reader.commit()
    ctx.event_bus.publish(
        "insight-updated",
        {"insight_id": params.insight_id, "state": params.state},
    )
    return {"insight_id": params.insight_id, "state": params.state}


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


def _workspace_scan_action(_params: EmptyParams, ctx: ActionCtx) -> dict[str, Any]:
    paths = ctx.pipeline.watch_paths()
    return {"paths": [str(p) for p in paths], "count": len(paths)}


def _config_set_action(params: ConfigSetParams, _ctx: ActionCtx) -> dict[str, Any]:
    os.environ[f"CAIRN_{params.key.upper()}"] = params.value
    return {"key": params.key, "value": params.value}


def _server_stop_action(_params: EmptyParams, _ctx: ActionCtx) -> dict[str, Any]:
    os.kill(os.getpid(), signal.SIGTERM)
    return {"stopping": True}
