import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { MoneySlide, RecapBanner, shouldShowRecap } from "@/pages/Overview";

describe("overview money slide", () => {
  it("shows spend, estimated waste, causes, fixes, and one primary action", () => {
    render(
      <MemoryRouter>
        <MoneySlide
          money={{
            period_days: 30,
            total_spend_usd: 40,
            spend_estimated: false,
            wasted_spend_usd: 10,
            wasted_spend_pct: 25,
            waste_estimated: true,
            primary_action: "/optimize",
            top_causes: [{
              category: "retry_loop",
              waste_tokens: 1000,
              estimated_savings_usd: 10,
              cause: "The same failing tool was rerun.",
              fix: "Read the failure before retrying.",
            }],
          }}
        />
      </MemoryRouter>,
    );
    expect(screen.getByText("$40.00")).toBeTruthy();
    expect(screen.getAllByText("$10.00")).toHaveLength(2);
    expect(screen.getByText("± estimated")).toBeTruthy();
    expect(screen.getByText("The same failing tool was rerun.")).toBeTruthy();
    expect(screen.getByText("Fix: Read the failure before retrying.")).toBeTruthy();
    expect(screen.getByRole("link", { name: /Review proposed fix/ }).getAttribute("href")).toBe("/optimize");
  });
});

describe("weekly recap banner", () => {
  it("returns after seven days and can be dismissed", () => {
    const now = Date.parse("2026-07-14T00:00:00Z");
    expect(shouldShowRecap("2026-07-08T00:00:00Z", now)).toBe(false);
    expect(shouldShowRecap("2026-07-07T00:00:00Z", now)).toBe(true);
    const onDismiss = vi.fn();
    render(
      <MemoryRouter>
        <RecapBanner
          onDismiss={onDismiss}
          recap={{
            generated_at: "2026-07-14T00:00:00Z",
            period_days: 7,
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
            experiment_verdicts: [],
          }}
        />
      </MemoryRouter>,
    );
    expect(screen.getByText(/\$12.00 spent/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Dismiss weekly recap" }));
    expect(onDismiss).toHaveBeenCalledOnce();
  });
});
