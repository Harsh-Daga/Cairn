import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Chip } from "@/components/common/Chip";
import { EmptyCard } from "@/components/common/DataViews";
import { PageShell } from "@/components/common/PageShell";
import { EstimateBadge, MetricHelp } from "@/components/ui";
import { isStaticMode } from "@/lib/api";
import { formatCost, formatTokens } from "@/lib/format";
import { connectLiveEvents, type LiveConnectionState } from "@/lib/sse";
import { useUiStore } from "@/state/ui";

interface LiveRow {
  id: string;
  event: string;
  at: string;
  traceId?: string;
  spanId?: string;
  detail?: string;
}

interface SessionCostTick {
  traceId: string;
  cost: number;
  totalTokens: number;
  estimateKind: "measured" | "estimated" | "unavailable";
  at: string;
}

const COST_TICK_CAP = 8;

function asEstimateKind(value: unknown): SessionCostTick["estimateKind"] {
  if (value === "measured" || value === "estimated" || value === "unavailable") {
    return value;
  }
  return "unavailable";
}

function estimateLabel(kind: SessionCostTick["estimateKind"]): string {
  switch (kind) {
    case "measured":
      return "Measured";
    case "estimated":
      return "Estimated";
    case "unavailable":
      return "Cost unavailable";
    default: {
      const _exhaustive: never = kind;
      return _exhaustive;
    }
  }
}

const HISTORY_CAP = 200;

function connectionLabel(state: LiveConnectionState): string {
  switch (state) {
    case "static":
      return "Unavailable in snapshot";
    case "connecting":
      return "Connecting";
    case "connected":
      return "Connected";
    case "reconnecting":
      return "Reconnecting";
    case "stale":
      return "Stale — no heartbeat";
    case "closed":
      return "Closed";
    default: {
      const _exhaustive: never = state;
      return _exhaustive;
    }
  }
}

function connectionTone(
  state: LiveConnectionState,
): "default" | "malachite" | "ochre" | "cinnabar" | "copper" {
  switch (state) {
    case "connected":
      return "malachite";
    case "connecting":
    case "reconnecting":
      return "ochre";
    case "stale":
      return "cinnabar";
    case "static":
    case "closed":
      return "copper";
    default: {
      const _exhaustive: never = state;
      return _exhaustive;
    }
  }
}

export function LivePage() {
  const watchOn = useUiStore((s) => s.watchEnabled);
  const staticMode = isStaticMode();
  const [rows, setRows] = useState<LiveRow[]>([]);
  const [dropped, setDropped] = useState(0);
  const [paused, setPaused] = useState(false);
  const [autoFollow, setAutoFollow] = useState(true);
  const [eventFilter, setEventFilter] = useState<string | null>(null);
  const [pending, setPending] = useState(0);
  const [connection, setConnection] = useState<LiveConnectionState>(
    staticMode ? "static" : "connecting",
  );
  const [summary, setSummary] = useState("Waiting for live events.");
  const [arrivalPulse, setArrivalPulse] = useState(false);
  const [costTicks, setCostTicks] = useState<SessionCostTick[]>([]);
  const [costTickCount, setCostTickCount] = useState(0);
  const bufferRef = useRef<LiveRow[]>([]);
  const pausedRef = useRef(false);
  const autoFollowRef = useRef(true);
  const listRef = useRef<HTMLDivElement>(null);
  const costTickCountRef = useRef(0);
  const reducedMotion = useRef(
    typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  );

  useEffect(() => {
    pausedRef.current = paused;
  }, [paused]);

  useEffect(() => {
    autoFollowRef.current = autoFollow;
  }, [autoFollow]);

  useEffect(() => {
    if (!watchOn || staticMode) return;
    return connectLiveEvents({
      onState: setConnection,
      onEvent: (event, data) => {
        if (typeof data.dropped_events === "number") {
          setDropped(data.dropped_events);
        }
        const droppedCount =
          typeof data.dropped_events === "number" ? data.dropped_events : undefined;

        if (event === "session_cost_tick" && typeof data.trace_id === "string") {
          const tick: SessionCostTick = {
            traceId: data.trace_id,
            cost: typeof data.cost === "number" ? data.cost : 0,
            totalTokens: typeof data.total_tokens === "number" ? data.total_tokens : 0,
            estimateKind: asEstimateKind(data.estimate_kind),
            at: new Date().toISOString(),
          };
          setCostTicks((prev) => {
            const without = prev.filter((row) => row.traceId !== tick.traceId);
            return [tick, ...without].slice(0, COST_TICK_CAP);
          });
          costTickCountRef.current += 1;
          setCostTickCount(costTickCountRef.current);
          // Absolute totals are visible in the ticker; do not announce every tick.
          if (costTickCountRef.current === 1 || costTickCountRef.current % 5 === 0) {
            setSummary(
              `Session cost updated for ${costTickCountRef.current} tick${
                costTickCountRef.current === 1 ? "" : "s"
              }${droppedCount != null && droppedCount > 0 ? ` · ${droppedCount} dropped` : ""}`,
            );
          }
          return;
        }

        const row: LiveRow = {
          id: `${Date.now()}-${Math.random()}`,
          event,
          at: new Date().toISOString(),
          traceId: typeof data.trace_id === "string" ? data.trace_id : undefined,
          spanId: typeof data.span_id === "string" ? data.span_id : undefined,
          detail:
            typeof data.kind === "string"
              ? data.kind
              : typeof data.status === "string"
                ? data.status
                : undefined,
        };
        if (pausedRef.current) {
          bufferRef.current = [row, ...bufferRef.current].slice(0, HISTORY_CAP);
          setPending(bufferRef.current.length);
          setSummary(
            `Paused · ${bufferRef.current.length} buffered${
              droppedCount != null ? ` · ${droppedCount} dropped` : ""
            }`,
          );
          return;
        }
        setRows((prev) => [row, ...prev].slice(0, HISTORY_CAP));
        setSummary(
          `New ${event}${droppedCount != null && droppedCount > 0 ? ` · ${droppedCount} dropped` : ""}`,
        );
        if (!reducedMotion.current) {
          setArrivalPulse(true);
          window.setTimeout(() => setArrivalPulse(false), 280);
        }
        if (autoFollowRef.current && listRef.current) {
          listRef.current.scrollTop = 0;
        }
      },
    });
  }, [watchOn, staticMode]);

  const resume = () => {
    const buffered = bufferRef.current;
    bufferRef.current = [];
    setRows((current) => {
      const next = [...buffered, ...current].slice(0, HISTORY_CAP);
      setSummary(`Resumed · ${next.length} events · ${dropped} dropped`);
      return next;
    });
    setPending(0);
    setPaused(false);
  };

  const eventTypes = [...new Set(rows.map((r) => r.event))];
  const visibleRows = eventFilter ? rows.filter((r) => r.event === eventFilter) : rows;

  if (staticMode) {
    return (
      <PageShell
        title="Live"
        question="Follow active runs, ingest events, and emerging signals as they happen."
      >
        <EmptyCard
          title="Live updates unavailable in snapshot"
          detail="Static exports capture API JSON only. SSE, Live updates, and live reconnection are disabled in snapshot mode."
        />
      </PageShell>
    );
  }

  if (!watchOn) {
    return (
      <PageShell
        title="Live"
        question="Follow active runs, ingest events, and emerging signals as they happen."
      >
        <EmptyCard
          title="Live updates are off"
          detail="Turn on Live updates in the top bar to stream SSE span events. This does not control backend auto-sync."
        />
      </PageShell>
    );
  }

  return (
    <PageShell
      title="Live"
      question="Follow active runs, ingest events, and emerging signals as they happen."
    >
      <div className="space-y-4">
        <section className="card p-5" aria-labelledby="live-answer">
          <p className="page-kicker">Live ledger · workspace</p>
          <h2 id="live-answer" className="font-display text-xl text-bone">
            Stream status under Live updates
          </h2>
          <p className="mt-2 max-w-3xl text-sm text-cinder">
            Connection is {connectionLabel(connection).toLowerCase()}. History is bounded to{" "}
            {HISTORY_CAP} events; drop-oldest backpressure is reported when the server queue
            saturates.
          </p>
          <p className="mt-3 text-xs text-cinder">
            Session cost ticks arrive as coalesced absolute totals (≤1 per 2s per session) with a
            measured/estimated marker. Verified-checkpoint diminishing-return warnings wait on the
            verification surface — this page does not invent them.
          </p>
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <Chip label={connectionLabel(connection)} tone={connectionTone(connection)} />
            <Chip label={autoFollow ? "auto-follow on" : "auto-follow off"} />
            {paused ? <Chip label="paused" tone="ochre" /> : null}
          </div>
        </section>

        <div
          className="sr-only"
          aria-live="polite"
          aria-atomic="true"
          data-testid="live-sr-summary"
        >
          {summary}
        </div>

        <div className="grid gap-4 lg:grid-cols-[1fr_280px]">
          <div className={`card overflow-hidden ${arrivalPulse ? "ring-1 ring-copper/40" : ""}`}>
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-quartz-vein px-4 py-2">
              <span className="font-mono text-[10px] uppercase tracking-wide text-cinder">
                Live tail · {visibleRows.length} events
              </span>
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  className="font-mono text-[10px] text-cinder hover:text-bone"
                  aria-pressed={autoFollow}
                  onClick={() => setAutoFollow((v) => !v)}
                >
                  {autoFollow ? "Auto-follow on" : "Auto-follow off"}
                </button>
                {paused && pending > 0 ? (
                  <button
                    type="button"
                    className="rounded-chip bg-granite px-2 py-1 font-mono text-[10px] text-copper"
                    onClick={resume}
                  >
                    ▶ resume · {pending} new
                  </button>
                ) : (
                  <button
                    type="button"
                    className="font-mono text-[10px] text-cinder hover:text-bone"
                    onClick={() => setPaused(true)}
                  >
                    Pause
                  </button>
                )}
              </div>
            </div>
            <div ref={listRef} className="max-h-[60vh] overflow-auto">
              {rows.length === 0 ? (
                <div className="p-4">
                  <p className="text-sm text-cinder">
                    No live agents — sessions appear here the moment an agent writes a log line.
                  </p>
                  <p className="mt-2 font-mono text-[10px] text-cinder">
                    Tip: keep Live updates on and run an agent session locally. Heartbeats arrive
                    about every 15s while idle.
                  </p>
                </div>
              ) : (
                <ul>
                  {visibleRows.map((row) => (
                    <li
                      key={row.id}
                      className="flex items-center gap-3 border-b border-quartz-vein/40 px-4 py-2 font-mono text-xs"
                    >
                      <span className="text-cinder">{row.at.slice(11, 19)}</span>
                      <Chip label={row.event} tone="patina" />
                      {row.traceId ? (
                        <Link
                          to={`/sessions/${row.traceId}${row.spanId ? `?span=${row.spanId}` : ""}`}
                          className="truncate text-bone hover:text-copper"
                        >
                          {row.detail ?? row.traceId.slice(0, 10)}
                        </Link>
                      ) : (
                        <span className="text-cinder">{row.detail ?? "—"}</span>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>

          <div className="space-y-4">
            {eventTypes.length > 1 ? (
              <div className="card p-3">
                <p className="font-mono text-[10px] uppercase tracking-wide text-cinder">Filter</p>
                <div className="mt-2 flex flex-wrap gap-1">
                  <button
                    type="button"
                    className={`rounded-chip px-2 py-0.5 font-mono text-[10px] ${
                      !eventFilter ? "bg-copper/20 text-copper" : "text-cinder hover:text-bone"
                    }`}
                    onClick={() => setEventFilter(null)}
                  >
                    all
                  </button>
                  {eventTypes.slice(0, 6).map((ev) => (
                    <button
                      key={ev}
                      type="button"
                      className={`rounded-chip px-2 py-0.5 font-mono text-[10px] ${
                        eventFilter === ev
                          ? "bg-copper/20 text-copper"
                          : "text-cinder hover:text-bone"
                      }`}
                      onClick={() => setEventFilter(ev)}
                    >
                      {ev}
                    </button>
                  ))}
                </div>
              </div>
            ) : null}

            <div className="card p-4">
              <div className="flex items-start justify-between gap-2">
                <p className="font-mono text-[10px] uppercase tracking-wide text-cinder">
                  Stream health
                </p>
                <MetricHelp
                  definition="Server drop-oldest queue (64) plus client connection/stale state from named heartbeats."
                  limitations="Comment heartbeats keep proxies warm; named heartbeat events drive UI liveness."
                />
              </div>
              <p
                className={`mt-2 font-mono text-sm ${dropped > 0 ? "text-ochre" : "text-malachite"}`}
              >
                {dropped > 0 ? `${dropped} events dropped` : "stream healthy · 0 dropped"}
              </p>
              <p className="mt-2 text-xs text-cinder">{connectionLabel(connection)}</p>
            </div>

            <div className="card p-4" data-testid="live-cost-ticks">
              <div className="flex items-start justify-between gap-2">
                <p className="font-mono text-[10px] uppercase tracking-wide text-cinder">
                  Session cost ticks
                </p>
                <MetricHelp
                  definition="Coalesced absolute session cost and token totals from ingest/OTLP."
                  calculation="At most one session_cost_tick per session every two seconds; bursts keep the latest totals."
                  source="SSE session_cost_tick"
                  limitations="Screen readers hear a periodic summary, not every tick. Checkpoint diminishing-return stays unavailable until verification lands."
                />
              </div>
              {costTicks.length === 0 ? (
                <p className="mt-2 text-sm text-cinder">
                  No cost ticks yet. Ingest or OTLP updates publish absolute totals when cost or
                  tokens change.
                </p>
              ) : (
                <ul className="mt-2 space-y-2">
                  {costTicks.map((tick) => (
                    <li key={tick.traceId} className="font-mono text-xs">
                      <div className="flex flex-wrap items-center gap-2">
                        <Link
                          to={`/sessions/${tick.traceId}`}
                          className="text-bone hover:text-copper"
                        >
                          {tick.traceId.slice(0, 10)}…
                        </Link>
                        <span className="text-bone">{formatCost(tick.cost)}</span>
                        <span className="text-cinder">{formatTokens(tick.totalTokens)} tok</span>
                        <EstimateBadge label={estimateLabel(tick.estimateKind)} />
                      </div>
                      <p className="mt-0.5 text-[10px] text-cinder">{tick.at.slice(11, 19)}</p>
                    </li>
                  ))}
                </ul>
              )}
              {costTickCount > 0 ? (
                <p className="mt-2 text-[10px] text-cinder">
                  {costTickCount} coalesced tick{costTickCount === 1 ? "" : "s"} this stream
                </p>
              ) : null}
              <p className="mt-2 text-xs text-cinder">
                Verified-checkpoint diminishing-return warnings remain unavailable. Active Session
                Detail still uses 2s polling live-tail.
              </p>
            </div>

            <div className="card p-4 text-sm text-cinder">
              Trace and span updates appear as they are ingested. Open a linked event to jump to
              Session Detail (active sessions show live-tail polling).
            </div>
          </div>
        </div>
      </div>
    </PageShell>
  );
}
