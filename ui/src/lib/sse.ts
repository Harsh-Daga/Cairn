export type SseHandler = (event: string, data: Record<string, unknown>) => void;

const LIVE_EVENT_TYPES = [
  "trace-updated",
  "views-updated",
  "insight-new",
  "job-done",
  "message",
] as const;

export function connectLiveEvents(onEvent: SseHandler): () => void {
  const source = new EventSource("/api/live/events");

  const dispatch =
    (eventType: string) =>
    (msg: MessageEvent): void => {
      try {
        const data = JSON.parse(msg.data) as Record<string, unknown>;
        onEvent(eventType, data);
      } catch {
        /* ignore malformed frames */
      }
    };

  for (const eventType of LIVE_EVENT_TYPES) {
    source.addEventListener(eventType, dispatch(eventType));
  }
  source.onmessage = dispatch("message");

  return () => source.close();
}
