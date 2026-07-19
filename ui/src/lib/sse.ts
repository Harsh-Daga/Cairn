import { isStaticMode } from "./api";

export type SseHandler = (event: string, data: Record<string, unknown>) => void;

export type LiveConnectionState =
  "static" | "connecting" | "connected" | "reconnecting" | "stale" | "closed";

export interface LiveConnectOptions {
  onEvent: SseHandler;
  onState?: (state: LiveConnectionState) => void;
  /** Silence after this many ms without open/message/heartbeat marks the stream stale. */
  staleMs?: number;
}

const LIVE_EVENT_TYPES = [
  "trace-updated",
  "views-updated",
  "insight-updated",
  "job-progress",
  "session_cost_tick",
  "heartbeat",
  "message",
] as const;

const DEFAULT_STALE_MS = 45_000;

export function connectLiveEvents(onEventOrOptions: SseHandler | LiveConnectOptions): () => void {
  const options: LiveConnectOptions =
    typeof onEventOrOptions === "function" ? { onEvent: onEventOrOptions } : onEventOrOptions;
  const { onEvent, onState, staleMs = DEFAULT_STALE_MS } = options;

  if (isStaticMode()) {
    onState?.("static");
    return () => undefined;
  }

  let closed = false;
  let staleTimer: ReturnType<typeof setTimeout> | null = null;
  let source: EventSource | null = null;

  const setState = (state: LiveConnectionState) => {
    if (!closed) onState?.(state);
  };

  const touch = () => {
    if (staleTimer) clearTimeout(staleTimer);
    staleTimer = setTimeout(() => setState("stale"), staleMs);
  };

  const attach = () => {
    if (closed) return;
    setState(source ? "reconnecting" : "connecting");
    source = new EventSource("/api/live/events");

    source.onopen = () => {
      setState("connected");
      touch();
    };

    source.onerror = () => {
      if (closed) return;
      setState("reconnecting");
    };

    const dispatch =
      (eventType: string) =>
      (msg: MessageEvent): void => {
        touch();
        if (eventType === "heartbeat") {
          setState("connected");
          return;
        }
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
  };

  attach();

  return () => {
    closed = true;
    if (staleTimer) clearTimeout(staleTimer);
    source?.close();
    source = null;
    setState("closed");
  };
}
