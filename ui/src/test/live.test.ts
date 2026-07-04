import { describe, expect, it, vi, afterEach } from "vitest";
import { connectLiveEvents } from "@/lib/sse";

class MockEventSource {
  static instances: MockEventSource[] = [];
  url: string;
  onmessage: ((ev: MessageEvent) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }

  close() {
    const idx = MockEventSource.instances.indexOf(this);
    if (idx >= 0) MockEventSource.instances.splice(idx, 1);
  }

  emit(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) } as MessageEvent);
  }
}

describe("live SSE", () => {
  afterEach(() => {
    MockEventSource.instances = [];
    vi.unstubAllGlobals();
  });

  it("connects to /api/live/events and dispatches events", () => {
    vi.stubGlobal("EventSource", MockEventSource);
    const handler = vi.fn();
    const disconnect = connectLiveEvents(handler);

    expect(MockEventSource.instances[0]?.url).toBe("/api/live/events");

    MockEventSource.instances[0]?.emit({
      event: "trace-updated",
      data: { trace_id: "t1", kind: "tool_call" },
    });

    expect(handler).toHaveBeenCalledWith("trace-updated", {
      trace_id: "t1",
      kind: "tool_call",
    });

    disconnect();
    expect(MockEventSource.instances).toHaveLength(0);
  });
});
