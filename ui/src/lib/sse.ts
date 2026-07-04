export type SseHandler = (event: string, data: Record<string, unknown>) => void;

export function connectLiveEvents(onEvent: SseHandler): () => void {
  const source = new EventSource("/api/live/events");

  source.onmessage = (msg) => {
    try {
      const payload = JSON.parse(msg.data) as { event?: string; data?: Record<string, unknown> };
      if (payload.event) {
        onEvent(payload.event, payload.data ?? {});
      }
    } catch {
      /* ignore malformed frames */
    }
  };

  return () => source.close();
}
