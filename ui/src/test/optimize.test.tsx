import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { VerdictPreview } from "@/components/optimize/VerdictPreview";
import { fetchExperiments } from "@/lib/api";
import type { ExperimentsResponse, VerdictPreviewData } from "@/lib/types";
import { formatVerdictPreview } from "@/lib/verdictPreview";
import { ExperimentLifecycle, OptimizePage } from "@/pages/Optimize";

vi.mock("@/lib/api", () => ({
  fetchExperiments: vi.fn(),
  fetchExperimentDetail: vi.fn(),
  runAction: vi.fn(),
}));

describe("VerdictPreview", () => {
  it("shows unknown when traffic is too low", () => {
    const preview: VerdictPreviewData = {
      expected_days_to_verdict: null,
      traces_per_day: 0.2,
      n_effective_needed: 8,
      traffic_unknown: true,
    };
    expect(formatVerdictPreview(preview)).toMatchInlineSnapshot(
      `"Verdict timing unknown (<5 traces/week)"`,
    );
    render(<VerdictPreview preview={preview} />);
    expect(screen.getByText(/Verdict timing unknown/)).toBeTruthy();
  });

  it("shows rounded day estimate at healthy traffic", () => {
    const preview: VerdictPreviewData = {
      expected_days_to_verdict: 12.4,
      traces_per_day: 0.65,
      n_effective_needed: 8,
      traffic_unknown: false,
    };
    expect(formatVerdictPreview(preview)).toMatchInlineSnapshot(
      `"Verdict in ~12 days at current traffic"`,
    );
    render(<VerdictPreview preview={preview} />);
    expect(screen.getByText("Verdict in ~12 days at current traffic")).toBeTruthy();
  });
});

describe("ExperimentLifecycle", () => {
  it("shows applied date, mandatory measuring progress, verdict, and confidence interval", () => {
    render(
      <ExperimentLifecycle
        status="verdict"
        appliedAt="2026-07-01T00:00:00Z"
        nEffective={20}
        target={20}
        verdict="improved"
        ciLow={0.05}
        ciHigh={0.25}
      />,
    );
    expect(screen.getByText(/Applied/)).toBeTruthy();
    expect(screen.getByText("Measuring n=20.0/20")).toBeTruthy();
    expect(screen.getByText("Verdict improved · CI 5.0% to 25.0%")).toBeTruthy();
  });

  it("shows partial effective sample progress while measuring", () => {
    render(
      <ExperimentLifecycle
        status="measuring"
        appliedAt="2026-07-01T00:00:00Z"
        nEffective={7}
        target={20}
        verdict={null}
        ciLow={null}
        ciHigh={null}
      />,
    );
    expect(screen.getByText("Measuring n=7.0/20")).toBeTruthy();
  });
});

describe("OptimizePage", () => {
  it("shows ledger, board/portfolio tabs, and plain-language verdict first", async () => {
    const payload: ExperimentsResponse = {
      ledger: {
        conclusion: "1 proposal(s), 0 measuring, 1 in portfolio, 0 decaying/decayed.",
        proposed_count: 1,
        active_count: 0,
        portfolio_count: 1,
        decayed_count: 0,
        next_action: "Review proposal for AGENTS.md",
        next_action_href: "/optimize?experiment=exp-proposed&tab=board",
        limitation: "Verdicts use holdout difference-in-means with confound guards.",
      },
      experiments: [
        {
          experiment_id: "exp-proposed",
          status: "proposed",
          target_file: "AGENTS.md",
          created_at: "2026-07-01T00:00:00Z",
          applied_at: null,
          min_holdout: 8,
          outcome_n_effective: null,
          outcome_n_raw: null,
          sample_size: null,
          verdict: null,
          plain_verdict: null,
          lift_pct: null,
          effect_ci_low: null,
          effect_ci_high: null,
          measured_at: null,
          last_evaluated_at: null,
          eval_interval_days: 30,
          proposal_source: "local",
          decay_state: "unknown",
          confound_flag: false,
          confound_notes: [],
          effect_history: [],
          verdict_history: [],
          regression_outside_interval: false,
          guard_event_id: null,
          in_portfolio: false,
        },
        {
          experiment_id: "exp-verdict",
          status: "verdict",
          target_file: "AGENTS.md",
          created_at: "2026-06-01T00:00:00Z",
          applied_at: "2026-06-02T00:00:00Z",
          min_holdout: 8,
          outcome_n_effective: 12,
          outcome_n_raw: 14,
          sample_size: 12,
          verdict: "improved",
          plain_verdict: "Holdout evidence suggests this rule improved the metric by about 13%.",
          lift_pct: -0.13,
          effect_ci_low: -0.2,
          effect_ci_high: -0.05,
          measured_at: "2026-07-01T00:00:00Z",
          last_evaluated_at: "2026-07-01T00:00:00Z",
          eval_interval_days: 30,
          proposal_source: "local",
          decay_state: "healthy",
          confound_flag: false,
          confound_notes: [],
          effect_history: [-0.11, -0.13],
          verdict_history: [],
          regression_outside_interval: false,
          guard_event_id: null,
          in_portfolio: true,
        },
      ],
      limitations: ["Guard links use associated instruction-file events when present."],
    };
    vi.mocked(fetchExperiments).mockResolvedValue(payload);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
          <OptimizePage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await waitFor(() =>
      expect(screen.getByText("Controlled rules under holdout evidence")).toBeTruthy(),
    );
    expect(screen.getByRole("tab", { name: "Board" })).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Portfolio" })).toBeTruthy();
    expect(screen.getByText(/1 proposal\(s\), 0 measuring/)).toBeTruthy();
    expect(
      screen.getByText("Holdout evidence suggests this rule improved the metric by about 13%."),
    ).toBeTruthy();
    expect(screen.getAllByText(/Guard/i).length).toBeGreaterThan(0);
  });
});
