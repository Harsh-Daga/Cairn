"""Budget burn math — month bounds, linear vs trailing-7d projection, overrun date."""

from __future__ import annotations

import sqlite3
from calendar import monthrange
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

MIN_ACTIVE_DAYS = 7

ProjectionState = Literal["available", "insufficient_history"]
BudgetState = Literal["unconfigured", "healthy", "attention", "over"]


@dataclass(frozen=True)
class BudgetShare:
    key: str
    spend_usd: float
    share_pct: float
    sessions: int


@dataclass(frozen=True)
class BudgetBurnSnapshot:
    timezone: str
    month_start: str
    month_end: str
    now: str
    monthly_limit_usd: float | None
    weekly_limit_usd: float | None
    daily_limit_usd: float | None
    month_spend_usd: float
    week_spend_usd: float
    day_spend_usd: float
    observed_active_days: int
    calendar_days_elapsed: int
    days_in_month: int
    projection_state: ProjectionState
    linear_projected_usd: float | None
    trailing_7d_projected_usd: float | None
    projected_overrun_date: str | None
    budget_state: BudgetState
    explanation: str
    agent_shares: list[BudgetShare] = field(default_factory=list)
    model_shares: list[BudgetShare] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)


def resolve_zone(timezone: str | None) -> ZoneInfo:
    name = timezone or "UTC"
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def compute_budget_burn(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    monthly_limit_usd: float | None = None,
    weekly_limit_usd: float | None = None,
    daily_limit_usd: float | None = None,
    timezone: str = "UTC",
    now: datetime | None = None,
) -> BudgetBurnSnapshot:
    """Compute current-month burn using the workspace timezone calendar month."""
    zone = resolve_zone(timezone)
    effective_tz = getattr(zone, "key", None) or timezone or "UTC"
    now_utc = (now or datetime.now(UTC)).astimezone(UTC)
    now_local = now_utc.astimezone(zone)
    month_start_local = now_local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    days_in_month = monthrange(now_local.year, now_local.month)[1]
    if now_local.month == 12:
        next_month = now_local.replace(
            year=now_local.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0
        )
    else:
        next_month = now_local.replace(
            month=now_local.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0
        )
    month_start_utc = month_start_local.astimezone(UTC).isoformat()
    month_end_utc = next_month.astimezone(UTC).isoformat()
    now_iso = now_utc.isoformat()
    week_start_utc = (now_utc - timedelta(days=7)).isoformat()
    day_start_utc = (now_utc - timedelta(days=1)).isoformat()

    month_row = conn.execute(
        """
        SELECT COALESCE(SUM(cost), 0) AS spend,
               COUNT(DISTINCT substr(started_at, 1, 10)) AS active_days
        FROM traces
        WHERE workspace_id = ? AND started_at >= ? AND started_at < ?
        """,
        (workspace_id, month_start_utc, now_iso),
    ).fetchone()
    week_row = conn.execute(
        """
        SELECT COALESCE(SUM(cost), 0) AS spend,
               COUNT(DISTINCT substr(started_at, 1, 10)) AS active_days
        FROM traces
        WHERE workspace_id = ? AND started_at >= ? AND started_at < ?
        """,
        (workspace_id, week_start_utc, now_iso),
    ).fetchone()
    day_row = conn.execute(
        """
        SELECT COALESCE(SUM(cost), 0) AS spend
        FROM traces
        WHERE workspace_id = ? AND started_at >= ? AND started_at < ?
        """,
        (workspace_id, day_start_utc, now_iso),
    ).fetchone()

    month_spend = float(month_row["spend"] or 0)
    week_spend = float(week_row["spend"] or 0)
    day_spend = float(day_row["spend"] or 0)
    active_days = int(month_row["active_days"] or 0)
    week_active = int(week_row["active_days"] or 0)
    days_elapsed = max(now_local.day, 1)

    limitations = [
        "Projections are descriptive extrapolations, not forecasts with confidence intervals.",
        f"Month bounds use timezone {effective_tz}.",
    ]
    linear: float | None = None
    trailing: float | None = None
    overrun: str | None = None
    projection_state: ProjectionState
    if active_days < MIN_ACTIVE_DAYS or days_elapsed < MIN_ACTIVE_DAYS:
        projection_state = "insufficient_history"
        explanation = (
            f"At least {MIN_ACTIVE_DAYS} active days in the current month are required "
            "before month-end projection or overrun dates."
        )
    else:
        projection_state = "available"
        linear = round(month_spend / days_elapsed * days_in_month, 4)
        if week_active >= MIN_ACTIVE_DAYS and week_spend > 0:
            trailing = round((week_spend / 7.0) * days_in_month, 4)
        else:
            limitations.append(
                "Trailing-seven-day projection unavailable until seven active days exist "
                "in the trailing window."
            )
        explanation = (
            "Linear projection uses current-month spend ÷ elapsed calendar days × days in month. "
            "Trailing-seven-day projection uses average daily spend over the last seven days × "
            "days in month when enough active days exist."
        )
        under_monthly = (
            monthly_limit_usd is not None
            and monthly_limit_usd > 0
            and month_spend < monthly_limit_usd
        )
        if under_monthly and monthly_limit_usd is not None:
            daily_rate = month_spend / days_elapsed
            if daily_rate > 0:
                remaining = monthly_limit_usd - month_spend
                days_to_overrun = remaining / daily_rate
                if 0 < days_to_overrun <= (days_in_month - days_elapsed + 1):
                    overrun_local = (now_local + timedelta(days=days_to_overrun)).date().isoformat()
                    overrun = overrun_local
                else:
                    limitations.append(
                        "No projected overrun date inside this calendar month at the linear rate."
                    )

    budget_state = _budget_state(
        monthly_limit_usd=monthly_limit_usd,
        month_spend=month_spend,
        linear=linear,
        trailing=trailing,
        weekly_limit_usd=weekly_limit_usd,
        week_spend=week_spend,
        daily_limit_usd=daily_limit_usd,
        day_spend=day_spend,
    )
    if monthly_limit_usd is None:
        budget_explanation = "No monthly budget is configured."
    elif budget_state == "over":
        budget_explanation = "Measured spend is above a configured ceiling."
    elif budget_state == "attention":
        budget_explanation = "A projection or shorter-window ceiling needs attention."
    else:
        budget_explanation = "Measured spend is within configured ceilings."

    agent_shares = _shares(
        conn,
        workspace_id=workspace_id,
        start=month_start_utc,
        end=now_iso,
        dimension="agent",
    )
    model_shares = _shares(
        conn,
        workspace_id=workspace_id,
        start=month_start_utc,
        end=now_iso,
        dimension="model",
    )

    return BudgetBurnSnapshot(
        timezone=effective_tz,
        month_start=month_start_utc,
        month_end=month_end_utc,
        now=now_iso,
        monthly_limit_usd=monthly_limit_usd,
        weekly_limit_usd=weekly_limit_usd,
        daily_limit_usd=daily_limit_usd,
        month_spend_usd=round(month_spend, 4),
        week_spend_usd=round(week_spend, 4),
        day_spend_usd=round(day_spend, 4),
        observed_active_days=active_days,
        calendar_days_elapsed=days_elapsed,
        days_in_month=days_in_month,
        projection_state=projection_state,
        linear_projected_usd=linear,
        trailing_7d_projected_usd=trailing,
        projected_overrun_date=overrun,
        budget_state=budget_state,
        explanation=f"{explanation} {budget_explanation}".strip(),
        agent_shares=agent_shares,
        model_shares=model_shares,
        limitations=limitations,
    )


def _budget_state(
    *,
    monthly_limit_usd: float | None,
    month_spend: float,
    linear: float | None,
    trailing: float | None,
    weekly_limit_usd: float | None,
    week_spend: float,
    daily_limit_usd: float | None,
    day_spend: float,
) -> BudgetState:
    if monthly_limit_usd is None and weekly_limit_usd is None and daily_limit_usd is None:
        return "unconfigured"
    if monthly_limit_usd is not None and month_spend > monthly_limit_usd:
        return "over"
    if weekly_limit_usd is not None and week_spend > weekly_limit_usd:
        return "over"
    if daily_limit_usd is not None and day_spend > daily_limit_usd:
        return "over"
    projected_over = False
    if monthly_limit_usd is not None:
        if linear is not None and linear > monthly_limit_usd:
            projected_over = True
        if trailing is not None and trailing > monthly_limit_usd:
            projected_over = True
    if projected_over:
        return "attention"
    return "healthy"


def _shares(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    start: str,
    end: str,
    dimension: str,
) -> list[BudgetShare]:
    if dimension == "model":
        sql = """
            SELECT COALESCE(NULLIF(t.model, ''), '(unknown)') AS key,
                   COALESCE(SUM(t.cost), 0) AS spend,
                   COUNT(*) AS sessions
            FROM traces t
            WHERE t.workspace_id = ? AND t.started_at >= ? AND t.started_at < ?
            GROUP BY COALESCE(NULLIF(t.model, ''), '(unknown)')
            ORDER BY spend DESC, key
            LIMIT 8
            """
    else:
        sql = """
            WITH agent_trace AS (
              SELECT s.trace_id,
                     COALESCE(NULLIF(s.agent_id, ''), t.actor_id, '(default)') AS agent_id,
                     SUM(COALESCE(s.input_tokens, 0) + COALESCE(s.output_tokens, 0)) AS tokens
              FROM spans s
              JOIN traces t ON t.trace_id = s.trace_id
              WHERE t.workspace_id = ? AND t.started_at >= ? AND t.started_at < ?
              GROUP BY s.trace_id, COALESCE(NULLIF(s.agent_id, ''), t.actor_id, '(default)')
            ), ranked AS (
              SELECT *,
                     ROW_NUMBER() OVER (
                       PARTITION BY trace_id ORDER BY tokens DESC, agent_id ASC
                     ) AS rn
              FROM agent_trace
            )
            SELECT r.agent_id AS key,
                   COALESCE(SUM(t.cost), 0) AS spend,
                   COUNT(*) AS sessions
            FROM traces t
            JOIN ranked r ON r.trace_id = t.trace_id AND r.rn = 1
            WHERE t.workspace_id = ? AND t.started_at >= ? AND t.started_at < ?
            GROUP BY r.agent_id
            ORDER BY spend DESC, key
            LIMIT 8
            """
    if dimension == "model":
        rows = conn.execute(sql, (workspace_id, start, end)).fetchall()
    else:
        rows = conn.execute(sql, (workspace_id, start, end, workspace_id, start, end)).fetchall()
    total = sum(float(row["spend"] or 0) for row in rows) or 0.0
    shares: list[BudgetShare] = []
    for row in rows:
        spend = float(row["spend"] or 0)
        shares.append(
            BudgetShare(
                key=str(row["key"]),
                spend_usd=round(spend, 4),
                share_pct=round((spend / total * 100) if total else 0.0, 2),
                sessions=int(row["sessions"] or 0),
            )
        )
    return shares
