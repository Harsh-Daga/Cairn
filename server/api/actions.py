"""THE action registry — single source of CLI/UI/API parity."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from pydantic import BaseModel

from server.api.action_handlers import (
    AnnotateParams,
    ArchiveExportParams,
    ArchiveImportParams,
    ArchiveInspectParams,
    BackfillParams,
    CheckParams,
    CircuitResumeParams,
    ConfigSetParams,
    CorrectionsRebuildParams,
    DbBackupListParams,
    DbBackupParams,
    DbCompactParams,
    DbRestoreParams,
    DemoSeedParams,
    EgressExportParams,
    EmptyParams,
    ExperimentApplyParams,
    ExperimentMeasureParams,
    ExperimentRevertParams,
    ExportBundleParams,
    ExportSessionHtmlParams,
    GitExcludeParams,
    InsightSetStateParams,
    InsightSnoozeParams,
    LifecycleCleanupParams,
    LifecyclePlanParams,
    McpInstallParams,
    OptimizeEvaluateParams,
    OptimizeProposeParams,
    RebuildViewParams,
    ReflectorPreviewParams,
    ReflectorRunParams,
    RegressionCompareParams,
    RegressionCreateParams,
    RegressionDeleteParams,
    RegressionExportParams,
    RegressionImportParams,
    RegressionRunParams,
    StorageStripParams,
    SyncParams,
    VerificationRebuildParams,
    WorkspaceScanParams,
    _annotate_action,
    _archive_export_action,
    _archive_import_action,
    _archive_inspect_action,
    _backfill_action,
    _check_action,
    _circuit_resume_action,
    _circuit_status_action,
    _config_set_action,
    _corrections_rebuild_action,
    _db_backup_action,
    _db_backup_list_action,
    _db_compact_action,
    _db_integrity_action,
    _db_restore_action,
    _demo_seed_action,
    _egress_export_action,
    _egress_status_action,
    _experiment_apply_action,
    _experiment_measure_action,
    _experiment_revert_action,
    _export_bundle_action,
    _export_session_html_action,
    _git_exclude_cairn_action,
    _insight_set_state_action,
    _insight_snooze_action,
    _lifecycle_cleanup_action,
    _lifecycle_plan_action,
    _mcp_install_action,
    _optimize_evaluate_action,
    _optimize_propose_action,
    _pricing_refresh_preview_action,
    _pricing_status_action,
    _rebuild_view_action,
    _reflector_preview_action,
    _reflector_run_action,
    _regression_compare_action,
    _regression_create_action,
    _regression_delete_action,
    _regression_export_action,
    _regression_import_action,
    _regression_run_action,
    _server_stop_action,
    _source_drift_status_action,
    _storage_strip_action,
    _sync_action,
    _verification_rebuild_action,
    _workspace_scan_action,
)
from server.api.context import ActionCtx
from server.api.schemas import ActionManifestEntry

P = TypeVar("P", bound=BaseModel)

CLI_ALIASES: dict[str, str] = {
    "optimize": "optimize_propose",
}


@dataclass(frozen=True)
class ActionDef:
    """Registered action definition."""

    name: str
    title: str
    category: str
    params_model: type[BaseModel]
    handler: Callable[[BaseModel, ActionCtx], dict[str, Any]]
    async_job: bool = False


_REGISTRY: list[ActionDef] = []


def action(
    *,
    name: str,
    title: str,
    category: str,
    params: type[P],
    async_job: bool = False,
) -> Callable[[Callable[[P, ActionCtx], dict[str, Any]]], Callable[[P, ActionCtx], dict[str, Any]]]:
    """Decorator to register an action handler."""

    def decorator(
        fn: Callable[[P, ActionCtx], dict[str, Any]],
    ) -> Callable[[P, ActionCtx], dict[str, Any]]:
        def _wrapped(params_obj: BaseModel, ctx: ActionCtx) -> dict[str, Any]:
            return fn(params_obj, ctx)  # type: ignore[arg-type]

        _REGISTRY.append(
            ActionDef(
                name=name,
                title=title,
                category=category,
                params_model=params,
                handler=_wrapped,
                async_job=async_job,
            )
        )
        return fn

    return decorator


@action(
    name="sync",
    title="Sync agent logs",
    category="ingest",
    params=SyncParams,
    async_job=True,
)
def sync(params: SyncParams, ctx: ActionCtx) -> dict[str, Any]:
    return _sync_action(params, ctx)


@action(
    name="backfill",
    title="Backfill historical logs",
    category="ingest",
    params=BackfillParams,
    async_job=True,
)
def backfill(params: BackfillParams, ctx: ActionCtx) -> dict[str, Any]:
    return _backfill_action(params, ctx)


@action(
    name="rebuild_view",
    title="Rebuild analyzer view",
    category="analyze",
    params=RebuildViewParams,
    async_job=True,
)
def rebuild_view(params: RebuildViewParams, ctx: ActionCtx) -> dict[str, Any]:
    return _rebuild_view_action(params, ctx)


@action(name="check", title="Run CI quality gate", category="ci", params=CheckParams)
def check(params: CheckParams, ctx: ActionCtx) -> dict[str, Any]:
    return _check_action(params, ctx)


@action(
    name="export_bundle",
    title="Export trace bundle",
    category="export",
    params=ExportBundleParams,
)
def export_bundle(params: ExportBundleParams, ctx: ActionCtx) -> dict[str, Any]:
    return _export_bundle_action(params, ctx)


@action(
    name="export_session_html",
    title="Export scrubbed session HTML",
    category="export",
    params=ExportSessionHtmlParams,
)
def export_session_html(params: ExportSessionHtmlParams, ctx: ActionCtx) -> dict[str, Any]:
    return _export_session_html_action(params, ctx)


@action(
    name="verification_rebuild",
    title="Rebuild verification receipts",
    category="analyze",
    params=VerificationRebuildParams,
)
def verification_rebuild(params: VerificationRebuildParams, ctx: ActionCtx) -> dict[str, Any]:
    return _verification_rebuild_action(params, ctx)


@action(
    name="corrections_rebuild",
    title="Rebuild session correction ledgers",
    category="analyze",
    params=CorrectionsRebuildParams,
)
def corrections_rebuild(params: CorrectionsRebuildParams, ctx: ActionCtx) -> dict[str, Any]:
    return _corrections_rebuild_action(params, ctx)


@action(
    name="regression_create",
    title="Create local regression artifact",
    category="export",
    params=RegressionCreateParams,
)
def regression_create(params: RegressionCreateParams, ctx: ActionCtx) -> dict[str, Any]:
    return _regression_create_action(params, ctx)


@action(
    name="regression_delete",
    title="Delete local regression artifact",
    category="export",
    params=RegressionDeleteParams,
)
def regression_delete(params: RegressionDeleteParams, ctx: ActionCtx) -> dict[str, Any]:
    return _regression_delete_action(params, ctx)


@action(
    name="regression_export",
    title="Export local regression zip",
    category="export",
    params=RegressionExportParams,
)
def regression_export(params: RegressionExportParams, ctx: ActionCtx) -> dict[str, Any]:
    return _regression_export_action(params, ctx)


@action(
    name="regression_import",
    title="Import local regression zip",
    category="export",
    params=RegressionImportParams,
)
def regression_import(params: RegressionImportParams, ctx: ActionCtx) -> dict[str, Any]:
    return _regression_import_action(params, ctx)


@action(
    name="regression_run",
    title="Record a regression run from an ingested trace (no execution)",
    category="export",
    params=RegressionRunParams,
)
def regression_run(params: RegressionRunParams, ctx: ActionCtx) -> dict[str, Any]:
    return _regression_run_action(params, ctx)


@action(
    name="regression_compare",
    title="Compare expected outcome to a recorded regression run",
    category="export",
    params=RegressionCompareParams,
)
def regression_compare(params: RegressionCompareParams, ctx: ActionCtx) -> dict[str, Any]:
    return _regression_compare_action(params, ctx)


@action(
    name="mcp_install",
    title="Install MCP server config",
    category="setup",
    params=McpInstallParams,
)
def mcp_install(params: McpInstallParams, ctx: ActionCtx) -> dict[str, Any]:
    return _mcp_install_action(params, ctx)


@action(
    name="demo_seed",
    title="Seed deterministic demo workspace",
    category="setup",
    params=DemoSeedParams,
)
def demo_seed(params: DemoSeedParams, ctx: ActionCtx) -> dict[str, Any]:
    return _demo_seed_action(params, ctx)


@action(
    name="optimize_propose",
    title="Generate optimize proposals",
    category="improve",
    params=OptimizeProposeParams,
)
def optimize_propose(params: OptimizeProposeParams, ctx: ActionCtx) -> dict[str, Any]:
    return _optimize_propose_action(params, ctx)


@action(
    name="optimize_evaluate",
    title="Re-evaluate due portfolio experiments",
    category="improve",
    params=OptimizeEvaluateParams,
)
def optimize_evaluate(params: OptimizeEvaluateParams, ctx: ActionCtx) -> dict[str, Any]:
    return _optimize_evaluate_action(params, ctx)


@action(
    name="reflector_preview",
    title="Preview optional LLM disclosure",
    category="privacy",
    params=ReflectorPreviewParams,
)
def reflector_preview(params: ReflectorPreviewParams, ctx: ActionCtx) -> dict[str, Any]:
    return _reflector_preview_action(params, ctx)


@action(
    name="reflector_run",
    title="Run optional LLM reflector after preview consent",
    category="privacy",
    params=ReflectorRunParams,
)
def reflector_run(params: ReflectorRunParams, ctx: ActionCtx) -> dict[str, Any]:
    return _reflector_run_action(params, ctx)


@action(
    name="experiment_apply",
    title="Apply experiment",
    category="improve",
    params=ExperimentApplyParams,
)
def experiment_apply(params: ExperimentApplyParams, ctx: ActionCtx) -> dict[str, Any]:
    return _experiment_apply_action(params, ctx)


@action(
    name="experiment_revert",
    title="Revert experiment",
    category="improve",
    params=ExperimentRevertParams,
)
def experiment_revert(params: ExperimentRevertParams, ctx: ActionCtx) -> dict[str, Any]:
    return _experiment_revert_action(params, ctx)


@action(
    name="experiment_measure",
    title="Measure experiment",
    category="improve",
    params=ExperimentMeasureParams,
)
def experiment_measure(params: ExperimentMeasureParams, ctx: ActionCtx) -> dict[str, Any]:
    return _experiment_measure_action(params, ctx)


@action(
    name="insight_set_state",
    title="Set insight lifecycle state",
    category="insights",
    params=InsightSetStateParams,
)
def insight_set_state(params: InsightSetStateParams, ctx: ActionCtx) -> dict[str, Any]:
    return _insight_set_state_action(params, ctx)


@action(
    name="insight_snooze",
    title="Snooze insight",
    category="insights",
    params=InsightSnoozeParams,
)
def insight_snooze(params: InsightSnoozeParams, ctx: ActionCtx) -> dict[str, Any]:
    return _insight_snooze_action(params, ctx)


@action(name="annotate", title="Annotate trace or span", category="annotate", params=AnnotateParams)
def annotate(params: AnnotateParams, ctx: ActionCtx) -> dict[str, Any]:
    return _annotate_action(params, ctx)


@action(
    name="workspace_scan",
    title="Scan workspace for adapters",
    category="setup",
    params=WorkspaceScanParams,
    async_job=True,
)
def workspace_scan(params: WorkspaceScanParams, ctx: ActionCtx) -> dict[str, Any]:
    return _workspace_scan_action(params, ctx)


@action(
    name="config_set", title="Manage typed configuration", category="config", params=ConfigSetParams
)
def config_set(params: ConfigSetParams, ctx: ActionCtx) -> dict[str, Any]:
    return _config_set_action(params, ctx)


@action(
    name="storage_strip",
    title="Strip retained span text per storage mode",
    category="privacy",
    params=StorageStripParams,
    async_job=True,
)
def storage_strip(params: StorageStripParams, ctx: ActionCtx) -> dict[str, Any]:
    return _storage_strip_action(params, ctx)


@action(
    name="git_exclude_cairn",
    title="Add .cairn/ to local git exclude (approved)",
    category="privacy",
    params=GitExcludeParams,
)
def git_exclude_cairn(params: GitExcludeParams, ctx: ActionCtx) -> dict[str, Any]:
    return _git_exclude_cairn_action(params, ctx)


@action(
    name="lifecycle_plan",
    title="Dry-run data lifecycle cleanup plan",
    category="privacy",
    params=LifecyclePlanParams,
)
def lifecycle_plan(params: LifecyclePlanParams, ctx: ActionCtx) -> dict[str, Any]:
    return _lifecycle_plan_action(params, ctx)


@action(
    name="lifecycle_cleanup",
    title="Run data lifecycle cleanup (confirmed)",
    category="privacy",
    params=LifecycleCleanupParams,
    async_job=True,
)
def lifecycle_cleanup(params: LifecycleCleanupParams, ctx: ActionCtx) -> dict[str, Any]:
    return _lifecycle_cleanup_action(params, ctx)


@action(
    name="db_backup",
    title="Backup cairn.db under .cairn/backups/manual",
    category="privacy",
    params=DbBackupParams,
)
def db_backup(params: DbBackupParams, ctx: ActionCtx) -> dict[str, Any]:
    return _db_backup_action(params, ctx)


@action(
    name="db_backup_list",
    title="List cairn.db backups under .cairn/backups/manual",
    category="privacy",
    params=DbBackupListParams,
)
def db_backup_list(params: DbBackupListParams, ctx: ActionCtx) -> dict[str, Any]:
    return _db_backup_list_action(params, ctx)


@action(
    name="db_restore",
    title="Restore cairn.db from a .cairn backup (confirmed)",
    category="privacy",
    params=DbRestoreParams,
)
def db_restore(params: DbRestoreParams, ctx: ActionCtx) -> dict[str, Any]:
    return _db_restore_action(params, ctx)


@action(
    name="db_integrity",
    title="Check cairn.db integrity (quick_check + FK)",
    category="privacy",
    params=EmptyParams,
)
def db_integrity(params: EmptyParams, ctx: ActionCtx) -> dict[str, Any]:
    return _db_integrity_action(params, ctx)


@action(
    name="db_compact",
    title="Checkpoint WAL and VACUUM cairn.db (confirmed)",
    category="privacy",
    params=DbCompactParams,
    async_job=True,
)
def db_compact(params: DbCompactParams, ctx: ActionCtx) -> dict[str, Any]:
    return _db_compact_action(params, ctx)


@action(
    name="pricing_status",
    title="Show offline model pricing provenance and staleness",
    category="config",
    params=EmptyParams,
)
def pricing_status(params: EmptyParams, ctx: ActionCtx) -> dict[str, Any]:
    return _pricing_status_action(params, ctx)


@action(
    name="pricing_refresh_preview",
    title="Preview price-table refresh (never downloads)",
    category="config",
    params=EmptyParams,
)
def pricing_refresh_preview(params: EmptyParams, ctx: ActionCtx) -> dict[str, Any]:
    return _pricing_refresh_preview_action(params, ctx)


@action(
    name="archive_export",
    title="Export versioned cairn.archive.v1 ZIP",
    category="export",
    params=ArchiveExportParams,
    async_job=True,
)
def archive_export(params: ArchiveExportParams, ctx: ActionCtx) -> dict[str, Any]:
    return _archive_export_action(params, ctx)


@action(
    name="archive_import",
    title="Import cairn.archive.v1 ZIP (dry-run default)",
    category="export",
    params=ArchiveImportParams,
    async_job=True,
)
def archive_import(params: ArchiveImportParams, ctx: ActionCtx) -> dict[str, Any]:
    return _archive_import_action(params, ctx)


@action(
    name="archive_inspect",
    title="Inspect cairn.archive.v1 ZIP without applying",
    category="export",
    params=ArchiveInspectParams,
)
def archive_inspect(params: ArchiveInspectParams, ctx: ActionCtx) -> dict[str, Any]:
    return _archive_inspect_action(params, ctx)


@action(
    name="egress_status",
    title="Show privacy-minimized egress ledger status",
    category="privacy",
    params=EmptyParams,
)
def egress_status(params: EmptyParams, ctx: ActionCtx) -> dict[str, Any]:
    return _egress_status_action(params, ctx)


@action(
    name="egress_export",
    title="Export egress ledger JSON (secret-free)",
    category="privacy",
    params=EgressExportParams,
)
def egress_export(params: EgressExportParams, ctx: ActionCtx) -> dict[str, Any]:
    return _egress_export_action(params, ctx)


@action(
    name="circuit_status",
    title="Show ingest circuit-breaker / quarantine status",
    category="privacy",
    params=EmptyParams,
)
def circuit_status(params: EmptyParams, ctx: ActionCtx) -> dict[str, Any]:
    return _circuit_status_action(params, ctx)


@action(
    name="circuit_resume",
    title="Resume paused ingest adapters (explicit)",
    category="privacy",
    params=CircuitResumeParams,
)
def circuit_resume(params: CircuitResumeParams, ctx: ActionCtx) -> dict[str, Any]:
    return _circuit_resume_action(params, ctx)


@action(
    name="source_drift_status",
    title="Show reference-mode source drift status",
    category="privacy",
    params=EmptyParams,
)
def source_drift_status(params: EmptyParams, ctx: ActionCtx) -> dict[str, Any]:
    return _source_drift_status_action(params, ctx)


@action(name="server_stop", title="Stop background server", category="server", params=EmptyParams)
def server_stop(params: EmptyParams, ctx: ActionCtx) -> dict[str, Any]:
    return _server_stop_action(params, ctx)


def list_actions() -> list[ActionDef]:
    """Return all registered actions."""
    return list(_REGISTRY)


def get_action(name: str) -> ActionDef | None:
    resolved = CLI_ALIASES.get(name, name)
    for item in _REGISTRY:
        if item.name == resolved:
            return item
    return None


def build_manifest() -> list[ActionManifestEntry]:
    """Serialize action registry for GET /api/actions."""
    return [
        ActionManifestEntry(
            name=item.name,
            title=item.title,
            category=item.category,
            params_schema=item.params_model.model_json_schema(),
            async_job=item.async_job,
        )
        for item in _REGISTRY
    ]
