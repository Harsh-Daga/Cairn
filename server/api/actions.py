"""THE action registry — single source of CLI/UI/API parity."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from pydantic import BaseModel

from server.api.action_handlers import (
    AnnotateParams,
    BackfillParams,
    CheckParams,
    ConfigSetParams,
    EmptyParams,
    ExperimentApplyParams,
    ExperimentMeasureParams,
    ExperimentRevertParams,
    ExportBundleParams,
    InsightSetStateParams,
    McpInstallParams,
    OptimizeProposeParams,
    RebuildViewParams,
    SyncParams,
    _annotate_action,
    _backfill_action,
    _check_action,
    _config_set_action,
    _experiment_apply_action,
    _experiment_measure_action,
    _experiment_revert_action,
    _export_bundle_action,
    _insight_set_state_action,
    _mcp_install_action,
    _optimize_propose_action,
    _rebuild_view_action,
    _server_stop_action,
    _sync_action,
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
    name="mcp_install",
    title="Install MCP server config",
    category="setup",
    params=McpInstallParams,
)
def mcp_install(params: McpInstallParams, ctx: ActionCtx) -> dict[str, Any]:
    return _mcp_install_action(params, ctx)


@action(
    name="optimize_propose",
    title="Generate optimize proposals",
    category="improve",
    params=OptimizeProposeParams,
)
def optimize_propose(params: OptimizeProposeParams, ctx: ActionCtx) -> dict[str, Any]:
    return _optimize_propose_action(params, ctx)


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


@action(name="annotate", title="Annotate trace or span", category="annotate", params=AnnotateParams)
def annotate(params: AnnotateParams, ctx: ActionCtx) -> dict[str, Any]:
    return _annotate_action(params, ctx)


@action(
    name="workspace_scan",
    title="Scan workspace for adapters",
    category="setup",
    params=EmptyParams,
    async_job=True,
)
def workspace_scan(params: EmptyParams, ctx: ActionCtx) -> dict[str, Any]:
    return _workspace_scan_action(params, ctx)


@action(name="config_set", title="Set runtime config", category="config", params=ConfigSetParams)
def config_set(params: ConfigSetParams, ctx: ActionCtx) -> dict[str, Any]:
    return _config_set_action(params, ctx)


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
