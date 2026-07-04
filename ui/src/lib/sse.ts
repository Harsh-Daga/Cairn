export type SseHandler = (event: string, data: Record<string, unknown>) => void;

export function connectSse(onEvent: SseHandler): () => void {
  const source = new EventSource("/api/live/events");

  source.onmessage = (msg) => {
    try {
      const parsed = JSON.parse(msg.data) as { event: string; data: Record<string, unknown> };
      onEvent(parsed.event, parsed.data);
    } catch {
      // ignore malformed events
    }
  };

  return () => source.close();
}
