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
  const pendingRef = useRef(0);
  const listRef = useRef<HTMLDivElement>(null);

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
      if (paused) {
        pendingRef.current += 1;
        return;
      }
      setRows((prev) => [row, ...prev].slice(0, 200));
      if (typeof data.dropped_events === "number") {
        setDropped(data.dropped_events);
      }
    });
  }, [watchOn, paused]);

  const pending = pendingRef.current;

  if (!watchOn) {
    return (
      <PageShell title="Live" question="What are my agents doing right now?">
        <EmptyCard
          title="Watch is off"
          detail="Turn on Watch in the top bar to stream live span events."
        />
      </PageShell>
    );
  }

  return (
    <PageShell title="Live" question="What are my agents doing right now?">
      <div className="grid gap-4 lg:grid-cols-[1fr_280px]">
        <div className="card overflow-hidden">
          <div className="flex items-center justify-between border-b border-quartz-vein px-4 py-2">
            <span className="font-mono text-[10px] uppercase tracking-wide text-cinder">
              Live tail
            </span>
            {paused && pending > 0 ? (
              <button
                type="button"
                className="rounded-chip bg-granite px-2 py-1 font-mono text-[10px] text-copper"
                onClick={() => {
                  setPaused(false);
                  pendingRef.current = 0;
                }}
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
              <p className="p-4 text-sm text-cinder">
                No live agents — sessions appear here the moment an agent writes a log line.
              </p>
            ) : (
              <ul>
                {rows.map((row) => (
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
          <div className="card p-4">
            <p className="font-mono text-[10px] uppercase tracking-wide text-cinder">Stream health</p>
            <p className={`mt-2 font-mono text-sm ${dropped > 0 ? "text-ochre" : "text-malachite"}`}>
              {dropped > 0 ? `${dropped} events dropped` : "stream healthy · 0 dropped"}
            </p>
          </div>
          <div className="card p-4 text-sm text-cinder">
            Active session cards appear when trace-updated events include running cost and context
            fill. Connect an adapter and keep Watch on.
          </div>
        </div>
      </div>
    </PageShell>
  );
}
