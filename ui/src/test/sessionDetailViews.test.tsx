import { useState } from "react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ReplayScrubber } from "@/components/session/ReplayScrubber";
import { SessionCorrections, SessionReceipt } from "@/components/session/SessionEvidenceViews";
import { SessionShields } from "@/components/session/SessionShields";
import { SessionTranscript } from "@/components/session/SessionTranscript";
import type { SessionShield, Span, TraceDetailResponse } from "@/lib/types";

function span(partial: Partial<Span> = {}): Span {
  return {
    span_id: "span-1",
    trace_id: "trace-1",
    parent_span_id: null,
    seq: 1,
    kind: "user_msg",
    name: null,
    agent_id: null,
    agent_lane: null,
    started_at: null,
    ended_at: null,
    duration_ms: null,
    status: "ok",
    model: null,
    input_tokens: 0,
    output_tokens: 0,
    input_estimated: 0,
    output_estimated: 0,
    cache_read_tokens: null,
    cache_creation_tokens: null,
    context_tokens_after: 100,
    text_inline: "hello",
    text_hash: null,
    args_hash: null,
    path_rel: null,
    waste_category: null,
    waste_tokens: 0,
    attrs_json: {},
    ...partial,
  };
}

afterEach(() => vi.useRealTimers());

describe("session detail views", () => {
  it("renders imported transcript content only as inert text", () => {
    render(
      <SessionTranscript
        spans={[
          span({
            text_inline: '<img src=x onerror="window.pwned=true"><script>alert(1)</script>',
          }),
          span({
            span_id: "tool",
            seq: 2,
            kind: "tool_result",
            text_inline: "<svg onload=alert(1)>tool output</svg>",
          }),
        ]}
      />,
    );

    expect(screen.getByText(/<img src=x/)).toBeTruthy();
    expect(document.querySelector("img")).toBeNull();
    expect(document.querySelector("script")).toBeNull();
    expect(document.querySelector("svg")).toBeNull();
    expect(screen.getByText("Show captured tool result")).toBeTruthy();
  });

  it("keeps the four shields independent and exposes each limitation", () => {
    const shields: SessionShield[] = (
      ["verification", "scope", "privacy", "resource"] as const
    ).map((shield) => ({
      shield,
      state: "unknown",
      summary: `${shield} summary`,
      facts: [`${shield} fact`],
      limitation: `${shield} limitation`,
      action_label: "Inspect",
      action_path: "/settings",
    }));
    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <SessionShields shields={shields} />
      </MemoryRouter>,
    );

    expect(screen.getAllByText("unknown")).toHaveLength(4);
    for (const shield of shields) {
      expect(screen.getByText(`Limit: ${shield.limitation}`)).toBeTruthy();
    }
  });

  it("renders verification receipt debt and corrections without inventing claims", () => {
    const detail = {
      trace: { trace_id: "trace-1" },
      outcome: null,
      receipt: {
        schema_version: "cairn.receipt.v1",
        builder_version: "verification-receipt-v1",
        trace_id: "trace-1",
        status: "debt",
        intent: { present: true, summary: "Fix the flaky test", limitation: null, span_id: null },
        requirements: [{ status: "unknown", text: "Tests pass", span_id: null }],
        claims: [],
        claims_limitation: "Claim rows are intentionally absent in receipt v1.",
        evidence: [],
        timeline: [{ kind: "outcome", at: "2026-07-01T00:00:00Z", span_id: null, summary: "fail" }],
        debt: {
          score: 0.4,
          explanation: "Active verification debt remains.",
          components: [
            {
              id: "no_tests",
              weight: 0.4,
              active: true,
              reason: "No tests were recorded after the final edit.",
            },
          ],
        },
        outcome: {
          label: "fail",
          tests_run: null,
          tests_passed: null,
          tests_failed: null,
          build_status: null,
        },
        risk_policy: {
          evaluated: true,
          review_risk: "medium",
          findings: [],
          limitation: "Advisory only.",
          enforcement_note: null,
        },
        limitations: ["Receipt is evidence, not attestation."],
        content_hash: "abcdef0123456789deadbeef",
        markdown: "# receipt",
        persisted: false,
      },
      corrections: {
        schema_version: "cairn.corrections.v1",
        builder_version: "corrections-v1",
        trace_id: "trace-1",
        correction_count: 1,
        unresolved_count: 1,
        corrections: [
          {
            correction_id: "c1",
            span_id: "span-2",
            seq: 2,
            classification: "intent_misunderstanding",
            original_class: "intent_misunderstanding",
            confidence: "medium",
            signal: "that's not what I meant",
            excerpt: "that's not what I meant",
            recovery_status: "unresolved",
            recovery_span_id: null,
            user_relabel: null,
            kind: "observed_phrase_match",
          },
        ],
        limitations: ["Classifications are local and not for employee ranking."],
        ranking_forbidden: true,
        content_hash: "hash",
        persisted: false,
      },
    } as unknown as TraceDetailResponse;

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <SessionReceipt detail={detail} />
        <SessionCorrections detail={detail} />
      </QueryClientProvider>,
    );

    expect(screen.getByLabelText("Verification receipt")).toBeTruthy();
    expect(screen.getByText("debt")).toBeTruthy();
    expect(screen.getByText(/Claim rows are intentionally absent/)).toBeTruthy();
    expect(screen.getByText(/No tests were recorded after the final edit/)).toBeTruthy();
    expect(screen.getByLabelText("Session corrections")).toBeTruthy();
    expect(screen.getByText("intent_misunderstanding")).toBeTruthy();
    expect(screen.getByText(/not for employee ranking/)).toBeTruthy();
  });

  it("plays replay forward at the selected speed and pauses", () => {
    vi.useFakeTimers();
    function Harness() {
      const [seq, setSeq] = useState(0);
      return <ReplayScrubber maxSeq={5} seq={seq} spans={[span()]} onChange={setSeq} />;
    }
    render(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: "4×" }));
    fireEvent.click(screen.getByRole("button", { name: "Play" }));
    act(() => vi.advanceTimersByTime(200));
    expect(screen.getByText(/turn 1 of 5/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Pause" }));
    act(() => vi.advanceTimersByTime(1_000));
    expect(screen.getByText(/turn 1 of 5/)).toBeTruthy();
  });
});
