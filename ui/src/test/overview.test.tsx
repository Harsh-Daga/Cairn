import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { MoneySlide } from "@/pages/Overview";

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
