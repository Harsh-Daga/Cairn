import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { formatVerdictPreview, VerdictPreview } from "@/components/optimize/VerdictPreview";
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
