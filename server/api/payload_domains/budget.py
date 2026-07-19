"""Budget burn analytics payload builders."""

from __future__ import annotations

import sqlite3

from server.analyze.budget_burn import compute_budget_burn
from server.api.schemas import (
    BudgetBurnLedger,
    BudgetBurnResponse,
    BudgetShareRow,
)


def build_budget_analytics(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    monthly_limit_usd: float | None = None,
    weekly_limit_usd: float | None = None,
    daily_limit_usd: float | None = None,
    timezone: str = "UTC",
) -> BudgetBurnResponse:
    burn = compute_budget_burn(
        conn,
        workspace_id=workspace_id,
        monthly_limit_usd=monthly_limit_usd,
        weekly_limit_usd=weekly_limit_usd,
        daily_limit_usd=daily_limit_usd,
        timezone=timezone,
    )
    if burn.budget_state == "unconfigured":
        next_action = "Set budgets.monthly_usd in Settings"
        next_href: str | None = "/settings?tab=budget"
        conclusion = "No spend ceiling is configured for this workspace."
    elif burn.budget_state == "over":
        next_action = "Review money causes and Optimize proposals"
        next_href = "/optimize"
        conclusion = "Measured spend is above a configured ceiling."
    elif burn.budget_state == "attention":
        next_action = "Inspect burn rate and month-end projections"
        next_href = "/settings?tab=budget"
        conclusion = "A projection or shorter-window ceiling needs attention."
    else:
        next_action = "Keep monitoring burn on Overview"
        next_href = "/"
        conclusion = "Measured spend is within configured ceilings."

    limitation = burn.limitations[0] if burn.limitations else burn.explanation
    return BudgetBurnResponse(
        timezone=burn.timezone,
        month_start=burn.month_start,
        month_end=burn.month_end,
        now=burn.now,
        monthly_limit_usd=burn.monthly_limit_usd,
        weekly_limit_usd=burn.weekly_limit_usd,
        daily_limit_usd=burn.daily_limit_usd,
        month_spend_usd=burn.month_spend_usd,
        week_spend_usd=burn.week_spend_usd,
        day_spend_usd=burn.day_spend_usd,
        observed_active_days=burn.observed_active_days,
        calendar_days_elapsed=burn.calendar_days_elapsed,
        days_in_month=burn.days_in_month,
        projection_state=burn.projection_state,
        linear_projected_usd=burn.linear_projected_usd,
        trailing_7d_projected_usd=burn.trailing_7d_projected_usd,
        projected_overrun_date=burn.projected_overrun_date,
        budget_state=burn.budget_state,
        explanation=burn.explanation,
        agent_shares=[
            BudgetShareRow(
                key=share.key,
                spend_usd=share.spend_usd,
                share_pct=share.share_pct,
                sessions=share.sessions,
            )
            for share in burn.agent_shares
        ],
        model_shares=[
            BudgetShareRow(
                key=share.key,
                spend_usd=share.spend_usd,
                share_pct=share.share_pct,
                sessions=share.sessions,
            )
            for share in burn.model_shares
        ],
        ledger=BudgetBurnLedger(
            conclusion=conclusion,
            budget_state=burn.budget_state,
            projection_state=burn.projection_state,
            next_action=next_action,
            next_action_href=next_href,
            limitation=limitation,
        ),
        limitations=list(burn.limitations),
    )
