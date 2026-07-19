"""Typer CLI — subcommands auto-generated from action registry."""

from __future__ import annotations

import importlib
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any

import typer

from server import __version__
from server.api.actions import build_manifest, get_action
from server.api.bootstrap import bootstrap_runtime
from server.api.context import ActionCtx
from server.config import Settings

# `python -m server.cli` executes this file as `__main__`. Command modules import
# the canonical name so both the module entry point and console-script import
# register against the same Typer object.
if __name__ == "__main__":
    sys.modules["server.cli"] = sys.modules[__name__]

app = typer.Typer(
    name="cairn",
    help="Local-first observability and self-improvement for AI coding agents.",
    invoke_without_command=True,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def main_callback(
    ctx: typer.Context,
    version: Annotated[
        bool | None,
        typer.Option("--version", callback=_version_callback, is_eager=True),
    ] = None,
) -> None:
    """Cairn CLI — local-first agent observability."""
    if ctx.invoked_subcommand is not None or version:
        return
    sync_result = _run_action("sync", {}, None)
    typer.echo(_render_sync_next_step(sync_result))
    _print_money_slide()
    operations.ui()


action_app = typer.Typer(help="Run any registered action by name.")
app.add_typer(action_app, name="action")


def _make_ctx(root: Path | None = None) -> ActionCtx:
    settings = Settings(workspace_root=root)
    runtime = bootstrap_runtime(settings)
    return ActionCtx(
        db=runtime.database,
        workspace_id=runtime.workspace_id,
        workspace_root=runtime.workspace_root,
        event_bus=runtime.event_bus,
        pipeline=runtime.pipeline,
        jobs=runtime.jobs,
    )


def _run_action(name: str, params: dict[str, Any], root: Path | None = None) -> dict[str, Any]:
    action_def = get_action(name)
    if action_def is None:
        typer.echo(f"Unknown action: {name}", err=True)
        raise typer.Exit(code=1)
    ctx = _make_ctx(root)
    validated = action_def.params_model.model_validate(params)
    return action_def.handler(validated, ctx)


def _render_money_slide(money: Any) -> str:
    estimate = " ± est." if money.waste_estimated else ""
    lines = [
        f"Cairn · last {money.period_days} days",
        f"Spend      ${money.total_spend_usd:,.2f}",
        (f"Waste      ${money.wasted_spend_usd:,.2f}{estimate} ({money.wasted_spend_pct:.1f}%)"),
    ]
    if money.top_causes:
        lines.append("Top causes")
        for index, cause in enumerate(money.top_causes, 1):
            label = cause.category.replace("_", " ")
            lines.append(f"  {index}. ${cause.estimated_savings_usd:,.2f} · {label}")
            lines.append(f"     Fix: {cause.fix}")
    else:
        lines.append("Top causes  waiting for priced waste data")
    lines.append("Action      Review proposed fix → http://127.0.0.1:8787/optimize")
    return "\n".join(lines)


def _render_sync_next_step(result: dict[str, Any]) -> str:
    scanned = int(result.get("scanned") or 0)
    imported = int(result.get("inserted") or 0) + int(result.get("updated") or 0)
    if scanned == 0:
        return (
            "No local agent logs found. Next: run a supported agent in this workspace, "
            "then run `cairn sync`; use `cairn doctor` for path and permission diagnostics, "
            "or `cairn demo` for separate deterministic data."
        )
    if imported == 0:
        return (
            f"Scanned {scanned} local log stream(s); no new sessions were imported. "
            "Open Overview for current data or run `cairn doctor` if parsing looks incomplete."
        )
    return (
        f"Imported or updated {imported} session(s) from {scanned} local log stream(s). "
        "Next: open Overview to inspect cost, context, quality, and behavior evidence."
    )


def _print_money_slide(workspace: Path | None = None) -> None:
    from server.api.payloads import build_overview

    action_ctx = _make_ctx(workspace)
    overview = build_overview(
        action_ctx.db.reader,
        workspace_id=action_ctx.workspace_id,
        days=30,
        workspace_root=action_ctx.workspace_root,
    )
    typer.echo(_render_money_slide(overview.money))


def _render_recap(recap: Any) -> str:
    lines = [
        "CAIRN WEEKLY RECAP",
        f"Period  {getattr(recap, 'period_start', '?')} → {getattr(recap, 'period_end', '?')} "
        f"({getattr(recap, 'timezone', 'UTC')} {getattr(recap, 'period_kind', 'rolling_7d')})",
        f"Spend  ${recap.money.total_spend_usd:,.2f}",
        (
            f"Waste  ${recap.money.wasted_spend_usd:,.2f} ± est. "
            f"({recap.money.wasted_spend_pct:.1f}%)"
        ),
    ]
    if recap.money.top_causes:
        lines.append("Top causes")
        for cause in recap.money.top_causes:
            lines.append(
                f"  ${cause.estimated_savings_usd:,.2f} · {cause.category.replace('_', ' ')}"
            )
            lines.append(f"  Fix: {cause.fix}")
    trend = recap.quality_trend
    if trend.current_mean is None:
        lines.append("Quality  waiting for scored sessions")
    elif trend.delta is None:
        lines.append(f"Quality  {trend.current_mean:.1f} · no prior-week baseline")
    else:
        lines.append(f"Quality  {trend.current_mean:.1f} · {trend.delta:+.1f} vs prior week")
    cps = getattr(recap, "cost_per_success_trend", None)
    if cps is not None:
        if cps.current_mean is None:
            lines.append("Cost/success  unavailable")
        elif cps.delta is None:
            lines.append(f"Cost/success  ${cps.current_mean:,.2f} · no prior baseline")
        else:
            lines.append(f"Cost/success  ${cps.current_mean:,.2f} · {cps.delta:+.2f} vs prior week")
    action = getattr(recap, "recommended_action", None)
    if action is not None:
        lines.append(f"Next  {action.label} → {action.href}")
    if recap.experiment_verdicts:
        lines.append("Verdicts reached")
        for verdict in recap.experiment_verdicts:
            lines.append(f"  {verdict.verdict} · {verdict.experiment_id[:12]}")
    else:
        lines.append("Verdicts  none reached this week")
    for rule in getattr(recap, "decayed_rules", []) or []:
        lines.append(f"Decay  {rule.decay_state} · {rule.experiment_id[:12]}")
    for event in getattr(recap, "guard_events", []) or []:
        lines.append(f"Guard  {event.event_kind} · {event.path_rel}")
    return "\n".join(lines)


def _render_budget_stats(budget: Any) -> str:
    lines = [
        "CAIRN BUDGET STATS",
        f"Timezone  {budget.timezone}",
        f"Month     {budget.month_start[:10]} → {budget.month_end[:10]}",
        f"State     {budget.budget_state} · projection {budget.projection_state}",
        f"Spend     ${budget.month_spend_usd:,.2f} this month"
        + (f" / ${budget.monthly_limit_usd:,.2f}" if budget.monthly_limit_usd is not None else ""),
        f"Week      ${budget.week_spend_usd:,.2f}"
        + (f" / ${budget.weekly_limit_usd:,.2f}" if budget.weekly_limit_usd is not None else ""),
        f"Day       ${budget.day_spend_usd:,.2f}"
        + (f" / ${budget.daily_limit_usd:,.2f}" if budget.daily_limit_usd is not None else ""),
    ]
    if budget.linear_projected_usd is not None:
        lines.append(f"Linear    ${budget.linear_projected_usd:,.2f} month-end")
    else:
        lines.append("Linear    insufficient history")
    if budget.trailing_7d_projected_usd is not None:
        lines.append(f"Trailing7 ${budget.trailing_7d_projected_usd:,.2f} month-end")
    if budget.projected_overrun_date:
        lines.append(f"Overrun   {budget.projected_overrun_date} (linear rate, descriptive)")
    if budget.agent_shares:
        lines.append("Agents")
        for share in budget.agent_shares[:5]:
            lines.append(f"  {share.key}: ${share.spend_usd:,.2f} ({share.share_pct:.1f}%)")
    if budget.model_shares:
        lines.append("Models")
        for share in budget.model_shares[:5]:
            lines.append(f"  {share.key}: ${share.spend_usd:,.2f} ({share.share_pct:.1f}%)")
    lines.append(budget.ledger.limitation)
    lines.append(f"Next  {budget.ledger.next_action}")
    return "\n".join(lines)


operations: Any


def _register_command_modules() -> None:
    """Import command modules after the shared app and helpers exist."""
    global operations
    operations_module = importlib.import_module("server.cli_commands.operations")
    improvement = importlib.import_module("server.cli_commands.improvement")
    integrations = importlib.import_module("server.cli_commands.integrations")
    regression = importlib.import_module("server.cli_commands.regression")
    archive = importlib.import_module("server.cli_commands.archive")

    # Importing registers decorators on ``app``. Keep the modules live for Click
    # callbacks and expose operations for the default no-command journey.
    _ = (improvement, integrations, regression, archive)
    operations = operations_module


_register_command_modules()


def _register_action_commands() -> None:
    for entry in build_manifest():
        action_name = entry.name
        title = entry.title

        def _make_cmd(resolved_name: str, doc: str) -> Callable[..., None]:
            def _cmd(
                params_json: Annotated[
                    str | None,
                    typer.Option("--params-json", help="JSON params object"),
                ] = None,
                workspace: Annotated[Path | None, typer.Option("--workspace")] = None,
            ) -> None:
                params: dict[str, Any] = {}
                if params_json:
                    params = json.loads(params_json)
                result = _run_action(resolved_name, params, workspace)
                typer.echo(json.dumps(result, indent=2))

            _cmd.__doc__ = doc
            return _cmd

        action_app.command(name=action_name)(_make_cmd(action_name, title))


_register_action_commands()


def main() -> None:
    """Entry point for the cairn console script."""
    app()


if __name__ == "__main__":
    main()
