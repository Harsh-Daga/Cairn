import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { formatVerdictPreview, VerdictPreview } from "@/components/optimize/VerdictPreview";
import { ExperimentLifecycle } from "@/pages/Optimize";
import type { VerdictPreviewData } from "@/lib/types";

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
