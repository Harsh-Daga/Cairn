"""First-run terminal money-slide tests."""

from server.api.schemas import MoneySummary, WasteCause
from server.cli import _render_money_slide


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
