import { describe, expect, it, vi, afterEach } from "vitest";
import { connectLiveEvents } from "@/lib/sse";

class MockEventSource {
  static instances: MockEventSource[] = [];
  url: string;
  onmessage: ((ev: MessageEvent) => void) | null = null;
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
});
