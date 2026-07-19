import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { MoneySlide, RecapBanner } from "@/pages/Overview";
import { recapPeriodKey, shouldShowRecap } from "@/lib/recap";

describe("overview money slide", () => {
  it("shows spend, estimated waste, causes, fixes, and one primary action", () => {
    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <MoneySlide
          money={{
            period_days: 30,
            total_spend_usd: 40,
            spend_estimated: false,
            wasted_spend_usd: 10,
            wasted_spend_pct: 25,
            waste_estimated: true,
            primary_action: "/optimize",
            top_causes: [
              {
                category: "retry_loop",
                waste_tokens: 1000,
                estimated_savings_usd: 10,
                cause: "The same failing tool was rerun.",
                fix: "Read the failure before retrying.",
                confidence: "low",
                confidence_explanation: "Only one supporting span is available.",
                evidence_count: 0,
                evidence: [],
              },
            ],
          }}
        />
      </MemoryRouter>,
    );
    expect(screen.getByText("$40.00")).toBeTruthy();
    expect(screen.getAllByText("$10.00")).toHaveLength(2);
    expect(screen.getByText("± estimated")).toBeTruthy();
    expect(screen.getByText("The same failing tool was rerun.")).toBeTruthy();
    expect(screen.getByText("Fix: Read the failure before retrying.")).toBeTruthy();
    expect(screen.getByRole("link", { name: /Review proposed fix/ }).getAttribute("href")).toBe(
      "/optimize",
    );
  });

  it("shows honest hero states, independent shields, and evidence actions", () => {
    const onEvidence = vi.fn();
    const cause = {
      category: "retry_loop",
      waste_tokens: 1000,
      estimated_savings_usd: 4,
      cause: "A retry loop repeated.",
      fix: "Change the diagnostic step.",
      confidence: "medium" as const,
      confidence_explanation: "Three observed spans support this cause.",
      evidence_count: 2,
      evidence: [],
    };
    render(
      <MemoryRouter>
        <MoneySlide
          money={{
            period_days: 30,
            total_spend_usd: 20,
            spend_estimated: false,
            wasted_spend_usd: 4,
            wasted_spend_pct: 20,
            waste_estimated: true,
            primary_action: "/optimize",
            top_causes: [cause],
          }}
          hero={{
            quality_mean: 82,
            quality_sessions: 5,
            cost_per_success_usd: 2.5,
            successful_sessions: 4,
            quality_sparkline: [70, 75, 82],
            projection: {
              state: "insufficient_history",
              projected_usd: null,
              trailing_7d_projected_usd: null,
              projected_overrun_date: null,
              month_spend_usd: 20,
              observed_active_days: 2,
              calendar_days_elapsed: 3,
              days_in_month: 31,
              explanation: "At least seven active days are required.",
            },
            budget: {
              state: "attention",
              monthly_limit_usd: 25,
              weekly_limit_usd: null,
              daily_limit_usd: null,
              month_spend_usd: 20,
              week_spend_usd: 8,
              day_spend_usd: 2,
              projected_usd: null,
              trailing_7d_projected_usd: null,
              projected_overrun_date: null,
              explanation: "Projection is unavailable.",
            },
            deltas: {},
          }}
          shields={[
            {
              shield: "verification",
              state: "unknown",
              summary: "5 of 10 sessions have outcome scores.",
              facts: ["Outcome coverage: 50%."],
              limitation: "Claim receipts are unavailable.",
              action_label: "Review quality",
              action_path: "/quality",
            },
          ]}
          onEvidence={onEvidence}
        />
      </MemoryRouter>,
    );
    expect(screen.getByText("82.0")).toBeTruthy();
    expect(screen.getByText("$2.50")).toBeTruthy();
    expect(screen.getByText("Insufficient history")).toBeTruthy();
    expect(screen.getByText("unknown")).toBeTruthy();
    expect(screen.getByText(/not one trust score/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Review fix" }));
    expect(onEvidence).toHaveBeenCalledWith(cause);
    fireEvent.click(screen.getByRole("button", { name: "Evidence (2)" }));
    expect(onEvidence).toHaveBeenCalledTimes(2);
  });
});

describe("weekly recap banner", () => {
  it("returns for a new weekly period and can be dismissed", () => {
    const now = Date.parse("2026-07-14T00:00:00Z");
    expect(recapPeriodKey(now)).toBe("2026-07-13");
    expect(shouldShowRecap("2026-07-14T00:00:00Z", now)).toBe(false);
    expect(shouldShowRecap("2026-07-13", now)).toBe(false);
    expect(shouldShowRecap("2026-07-08T00:00:00Z", now)).toBe(true);
    expect(shouldShowRecap("2026-07-07T00:00:00Z", now)).toBe(true);
    const onDismiss = vi.fn();
    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <RecapBanner
          onDismiss={onDismiss}
          recap={{
            generated_at: "2026-07-14T00:00:00Z",
            period_days: 7,
            period_start: "2026-07-07T00:00:00Z",
            period_end: "2026-07-14T00:00:00Z",
            timezone: "UTC",
            period_kind: "rolling_7d",
            money: {
              period_days: 7,
              total_spend_usd: 12,
              spend_estimated: false,
              wasted_spend_usd: 3,
              wasted_spend_pct: 25,
              waste_estimated: true,
              top_causes: [],
              primary_action: "/optimize",
            },
            quality_trend: {
              current_mean: 80,
              previous_mean: 75,
              delta: 5,
              current_sessions: 5,
              previous_sessions: 4,
            },
            cost_per_success_trend: {
              current_mean: 1.2,
              previous_mean: 1.5,
              delta: -0.3,
              current_sessions: 3,
              previous_sessions: 2,
            },
            experiment_verdicts: [],
            decayed_rules: [],
            guard_events: [],
            best_session: null,
            worst_session: null,
            recommended_action: null,
            limitations: [],
          }}
        />
      </MemoryRouter>,
    );
    expect(screen.getByText(/\$12.00 spent/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Dismiss weekly recap" }));
    expect(onDismiss).toHaveBeenCalledOnce();
  });
});
