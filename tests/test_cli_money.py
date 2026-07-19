"""First-run terminal money-slide tests."""

from server.api.schemas import MoneySummary, QualityTrend, RecapResponse, WasteCause
from server.cli import _render_money_slide, _render_recap, _render_sync_next_step


def test_terminal_money_slide_answers_cost_cause_and_fix() -> None:
    text = _render_money_slide(
        MoneySummary(
            period_days=30,
            total_spend_usd=42.5,
            spend_estimated=False,
            wasted_spend_usd=8.5,
            wasted_spend_pct=20,
            waste_estimated=True,
            top_causes=[
                WasteCause(
                    category="retry_loop",
                    waste_tokens=1000,
                    estimated_savings_usd=6.25,
                    cause="The same failure repeated.",
                    fix="Read the error before retrying.",
                )
            ],
            primary_action="/optimize",
        )
    )
    assert "Spend      $42.50" in text
    assert "Waste      $8.50 ± est. (20.0%)" in text
    assert "$6.25 · retry loop" in text
    assert "Fix: Read the error before retrying." in text
    assert "/optimize" in text


def test_weekly_recap_renders_quality_and_verdicts_on_one_screen() -> None:
    money = MoneySummary(
        period_days=7,
        total_spend_usd=20,
        spend_estimated=False,
        wasted_spend_usd=5,
        wasted_spend_pct=25,
        waste_estimated=True,
        top_causes=[],
        primary_action="/optimize",
    )
    text = _render_recap(
        RecapResponse(
            generated_at="2026-01-01T00:00:00Z",
            period_days=7,
            period_start="2025-12-25T00:00:00Z",
            period_end="2026-01-01T00:00:00Z",
            timezone="UTC",
            period_kind="rolling_7d",
            money=money,
            quality_trend=QualityTrend(
                current_mean=82,
                previous_mean=75,
                delta=7,
                current_sessions=8,
                previous_sessions=7,
            ),
            cost_per_success_trend=QualityTrend(
                current_mean=1.5,
                previous_mean=2.0,
                delta=-0.5,
                current_sessions=4,
                previous_sessions=3,
            ),
            experiment_verdicts=[
                {
                    "experiment_id": "experiment-123456",
                    "verdict": "improved",
                    "effect_estimate": 0.2,
                    "effect_ci_low": 0.1,
                    "effect_ci_high": 0.3,
                    "measured_at": "2026-01-01T00:00:00Z",
                }
            ],
            recommended_action={
                "label": "Review controlled fixes",
                "href": "/optimize",
                "reason": "Top waste cause available",
            },
        )
    )
    assert "CAIRN WEEKLY RECAP" in text
    assert "Spend  $20.00" in text
    assert "Waste  $5.00 ± est. (25.0%)" in text
    assert "Quality  82.0 · +7.0 vs prior week" in text
    assert "improved · experiment-1" in text


def test_sync_next_steps_match_empty_and_populated_first_run_states() -> None:
    empty = _render_sync_next_step({"scanned": 0, "inserted": 0, "updated": 0})
    assert "No local agent logs found" in empty
    assert "cairn doctor" in empty
    assert "cairn demo" in empty

    unchanged = _render_sync_next_step({"scanned": 2, "inserted": 0, "updated": 0})
    assert "no new sessions were imported" in unchanged
    assert "parsing looks incomplete" in unchanged

    imported = _render_sync_next_step({"scanned": 2, "inserted": 3, "updated": 1})
    assert "Imported or updated 4 session(s)" in imported
    assert "open Overview" in imported
