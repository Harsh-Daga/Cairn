import { describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ContextTimeline } from "@/components/session/ReplayScrubber";
import { Chip } from "@/components/common/Chip";
import { QualityScoreDetails } from "@/components/quality/QualityScoreDetails";
import type { Span } from "@/lib/types";

const themeCss = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "../theme.css"),
  "utf-8",
);

const spans: Span[] = [
  {
    span_id: "s1",
    trace_id: "t1",
    parent_span_id: null,
    seq: 1,
    kind: "user_msg",
    name: "hello",
    agent_id: null,
    agent_lane: null,
    started_at: null,
    ended_at: null,
    duration_ms: 10,
    status: "ok",
    model: null,
    input_tokens: 100,
    output_tokens: 0,
    input_estimated: 0,
    output_estimated: 0,
    cache_read_tokens: null,
    cache_creation_tokens: null,
    context_tokens_after: 1000,
    text_inline: null,
    text_hash: null,
    args_hash: null,
    path_rel: null,
    waste_category: null,
    waste_tokens: 0,
    attrs_json: {},
  },
  {
    span_id: "s2",
    trace_id: "t1",
    parent_span_id: "s1",
    seq: 2,
    kind: "tool_call",
    name: "read",
    agent_id: null,
    agent_lane: null,
    started_at: null,
    ended_at: null,
    duration_ms: 20,
    status: "ok",
    model: null,
    input_tokens: 200,
    output_tokens: 50,
    input_estimated: 0,
    output_estimated: 0,
    cache_read_tokens: null,
    cache_creation_tokens: null,
    context_tokens_after: 2000,
    text_inline: null,
    text_hash: null,
    args_hash: null,
    path_rel: null,
    waste_category: null,
    waste_tokens: 0,
    attrs_json: {},
  },
];

function wrap(ui: React.ReactNode) {
  const client = new QueryClient();
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("waterfall timeline sync", () => {
  it("timeline click selects span", () => {
    const onSelect = vi.fn();
    wrap(<ContextTimeline spans={spans} selectedId={null} onSelect={onSelect} />);
    fireEvent.click(screen.getByTitle("seq 2"));
    expect(onSelect).toHaveBeenCalledWith("s2");
  });
});

describe("estimated value grammar", () => {
  it("Chip estimated tone uses estimated-chip class", () => {
    render(<Chip label="est" tone="estimated" />);
    expect(screen.getByText("est").className).toContain("estimated-chip");
  });

  it("theme defines dashed estimated-chip border", () => {
    expect(themeCss).toContain(".estimated-chip");
    expect(themeCss).toContain("border-left: 2px dashed");
  });
});

describe("quality score explanation", () => {
  it("expands into component values and weights", () => {
    render(
      <QualityScoreDetails
        score={82}
        components={{ success: 0.75, efficiency: 0.9 }}
        weights={{ success: 0.4, efficiency: 0.25 }}
      />,
    );
    fireEvent.click(screen.getByText("82.0 quality"));
    expect(screen.getByText("75% × 40%")).toBeTruthy();
    expect(screen.getByText("90% × 25%")).toBeTruthy();
  });
});

describe("reduced motion", () => {
  it("theme disables animations under prefers-reduced-motion", () => {
    expect(themeCss).toContain("prefers-reduced-motion: reduce");
    expect(themeCss).toContain("animation: none !important");
  });
});
