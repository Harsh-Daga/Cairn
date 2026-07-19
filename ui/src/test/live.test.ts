import { afterEach, describe, expect, it, vi } from "vitest";
import { connectLiveEvents } from "@/lib/sse";

class MockEventSource {
  static instances: MockEventSource[] = [];
  url: string;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  private listeners = new Map<string, Array<(ev: MessageEvent) => void>>();

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }

  addEventListener(type: string, handler: (ev: MessageEvent) => void) {
    const list = this.listeners.get(type) ?? [];
    list.push(handler);
    this.listeners.set(type, list);
  }

  close() {
    const idx = MockEventSource.instances.indexOf(this);
    if (idx >= 0) MockEventSource.instances.splice(idx, 1);
  }

  emitNamed(type: string, data: Record<string, unknown>) {
    const msg = { data: JSON.stringify(data) } as MessageEvent;
    for (const handler of this.listeners.get(type) ?? []) {
      handler(msg);
    }
  }
}

describe("live SSE", () => {
  afterEach(() => {
    MockEventSource.instances = [];
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("connects to /api/live/events and dispatches named events", () => {
    vi.stubGlobal("EventSource", MockEventSource);
    const handler = vi.fn();
    const disconnect = connectLiveEvents(handler);

    expect(MockEventSource.instances[0]?.url).toBe("/api/live/events");

    MockEventSource.instances[0]?.emitNamed("trace-updated", {
      trace_id: "t1",
      kind: "tool_call",
    });

    expect(handler).toHaveBeenCalledWith("trace-updated", {
      trace_id: "t1",
      kind: "tool_call",
    });

    disconnect();
    expect(MockEventSource.instances).toHaveLength(0);
  });

  it("listens for insight-updated and job-progress, not legacy names", () => {
    vi.stubGlobal("EventSource", MockEventSource);
    const handler = vi.fn();
    connectLiveEvents(handler);
    const source = MockEventSource.instances[0];
    source?.emitNamed("insight-updated", { insight_id: "i1" });
    source?.emitNamed("job-progress", { job_id: "j1", status: "running" });
    expect(handler).toHaveBeenCalledWith("insight-updated", { insight_id: "i1" });
    expect(handler).toHaveBeenCalledWith("job-progress", {
      job_id: "j1",
      status: "running",
    });
  });

  it("dispatches coalesced session_cost_tick events", () => {
    vi.stubGlobal("EventSource", MockEventSource);
    const handler = vi.fn();
    connectLiveEvents(handler);
    MockEventSource.instances[0]?.emitNamed("session_cost_tick", {
      trace_id: "t-cost",
      cost: 1.25,
      total_tokens: 400,
      estimate_kind: "measured",
      cost_source: "observed",
    });
    expect(handler).toHaveBeenCalledWith("session_cost_tick", {
      trace_id: "t-cost",
      cost: 1.25,
      total_tokens: 400,
      estimate_kind: "measured",
      cost_source: "observed",
    });
  });

  it("reports connected on open/heartbeat and stale after silence", () => {
    vi.useFakeTimers();
    vi.stubGlobal("EventSource", MockEventSource);
    const states: string[] = [];
    const handler = vi.fn();
    connectLiveEvents({
      onEvent: handler,
      onState: (state) => states.push(state),
      staleMs: 1_000,
    });
    const source = MockEventSource.instances[0];
    source?.onopen?.();
    expect(states).toContain("connected");
    source?.emitNamed("heartbeat", { ok: true });
    expect(handler).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1_001);
    expect(states.at(-1)).toBe("stale");
  });
});
