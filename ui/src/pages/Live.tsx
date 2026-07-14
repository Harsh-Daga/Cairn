import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { connectLiveEvents } from "@/lib/sse";
import { useUiStore } from "@/state/ui";
import { PageShell } from "@/components/common/PageShell";
import { Chip } from "@/components/common/Chip";
import { EmptyCard } from "@/components/common/DataViews";

interface LiveRow {
  id: string;
  event: string;
  at: string;
  traceId?: string;
  spanId?: string;
  detail?: string;
}

export function LivePage() {
  const watchOn = useUiStore((s) => s.watchEnabled);
  const [rows, setRows] = useState<LiveRow[]>([]);
  const [dropped, setDropped] = useState(0);
  const [paused, setPaused] = useState(false);
  const [eventFilter, setEventFilter] = useState<string | null>(null);
  const [pending, setPending] = useState(0);
  const bufferRef = useRef<LiveRow[]>([]);
  const pausedRef = useRef(false);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    pausedRef.current = paused;
  }, [paused]);

  useEffect(() => {
    if (!watchOn) return;
    return connectLiveEvents((event, data) => {
      const row: LiveRow = {
        id: `${Date.now()}-${Math.random()}`,
        event,
        at: new Date().toISOString(),
        traceId: typeof data.trace_id === "string" ? data.trace_id : undefined,
        spanId: typeof data.span_id === "string" ? data.span_id : undefined,
        detail: typeof data.kind === "string" ? data.kind : undefined,
      };
      if (pausedRef.current) {
        bufferRef.current = [row, ...bufferRef.current].slice(0, 200);
        setPending(bufferRef.current.length);
        return;
      }
      setRows((prev) => [row, ...prev].slice(0, 200));
      if (typeof data.dropped_events === "number") {
        setDropped(data.dropped_events);
      }
    });
  }, [watchOn]);

  const resume = () => {
    const buffered = bufferRef.current;
    bufferRef.current = [];
    setRows((current) => [...buffered, ...current].slice(0, 200));
    setPending(0);
    setPaused(false);
  };
  const eventTypes = [...new Set(rows.map((r) => r.event))];
  const visibleRows = eventFilter ? rows.filter((r) => r.event === eventFilter) : rows;

  if (!watchOn) {
    return (
      <PageShell title="Live" question="Follow active runs, ingest events, and emerging signals as they happen.">
        <EmptyCard
          title="Watch is off"
          detail="Turn on Watch in the top bar to stream live span events."
        />
      </PageShell>
    );
  }

  return (
    <PageShell title="Live" question="Follow active runs, ingest events, and emerging signals as they happen.">
      <div className="grid gap-4 lg:grid-cols-[1fr_280px]">
        <div className="card overflow-hidden">
          <div className="flex items-center justify-between border-b border-quartz-vein px-4 py-2">
            <span className="font-mono text-[10px] uppercase tracking-wide text-cinder">
              Live tail · {visibleRows.length} events
            </span>
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
          <div ref={listRef} className="max-h-[60vh] overflow-auto">
            {rows.length === 0 ? (
              <div className="p-4">
                <p className="text-sm text-cinder">
                  No live agents — sessions appear here the moment an agent writes a log line.
                </p>
                <p className="mt-2 font-mono text-[10px] text-cinder">
                  Tip: enable Watch in the top bar and run an agent session locally.
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
                      eventFilter === ev ? "bg-copper/20 text-copper" : "text-cinder hover:text-bone"
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
            <p className="font-mono text-[10px] uppercase tracking-wide text-cinder">Stream health</p>
            <p className={`mt-2 font-mono text-sm ${dropped > 0 ? "text-ochre" : "text-malachite"}`}>
              {dropped > 0 ? `${dropped} events dropped` : "stream healthy · 0 dropped"}
            </p>
          </div>
          <div className="card p-4 text-sm text-cinder">
            Trace and span updates appear here as they are ingested. Open any linked event to jump
            directly to its session and inspect the affected span.
          </div>
        </div>
      </div>
    </PageShell>
  );
}
