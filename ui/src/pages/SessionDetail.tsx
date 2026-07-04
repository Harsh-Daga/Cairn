import { useQuery } from "@tanstack/react-query";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useMemo, useState } from "react";
import { fetchReplay, fetchTraceDetail } from "@/lib/api";
import { formatCost } from "@/lib/format";
import { PageShell } from "@/components/common/PageShell";
import { Chip } from "@/components/common/Chip";
import { flattenTree, Waterfall } from "@/components/waterfall/Waterfall";
import { ContextTimeline, ReplayScrubber } from "@/components/session/ReplayScrubber";
import { SpanInspector } from "@/components/session/SpanInspector";
import type { Span } from "@/lib/types";

export function SessionDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const seqParam = Number(searchParams.get("seq") ?? "0");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const { data: detail, isLoading, isError } = useQuery({
    queryKey: ["trace", id],
    queryFn: () => fetchTraceDetail(id!),
    enabled: Boolean(id),
  });

  const maxSeq = detail?.spans.length ? Math.max(...detail.spans.map((s) => s.seq)) : 0;
  const seq = Math.min(seqParam, maxSeq);

  const { data: replay } = useQuery({
    queryKey: ["replay", id, seq],
    queryFn: () => fetchReplay(id!, seq),
    enabled: Boolean(id) && seq > 0,
  });

  const activeSpans: Span[] = useMemo(() => {
    if (replay && seq > 0) return replay.spans;
    return detail?.spans ?? [];
  }, [detail, replay, seq]);

  const rows = useMemo(
    () => (detail ? flattenTree(detail.tree) : []).filter((r) => activeSpans.some((s) => s.span_id === r.span.span_id)),
    [detail, activeSpans],
  );

  const selectedSpan = activeSpans.find((s) => s.span_id === selectedId) ?? null;

  const setSeq = (next: number) => {
    const p = new URLSearchParams(searchParams);
    if (next <= 0) p.delete("seq");
    else p.set("seq", String(next));
    setSearchParams(p);
  };

  if (!id) return null;

  if (isLoading) {
    return (
      <PageShell title="Session" question="Replay, inspect, and understand what happened.">
        <div className="card h-64 animate-pulse bg-granite/30" />
      </PageShell>
    );
  }

  if (isError || !detail) {
    return (
      <PageShell title="Session" question="Replay, inspect, and understand what happened.">
        <div className="card p-6 text-cinnabar">Session not found.</div>
      </PageShell>
    );
  }

  const { trace } = detail;

  return (
    <PageShell title={trace.title ?? "Session"} question="Replay, inspect, and understand what happened.">
      <div className="mb-4">
        <Link to="/sessions" className="font-mono text-xs text-copper hover:underline">
          ← Sessions
        </Link>
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Chip label={trace.source} tone="patina" />
        {trace.model ? <Chip label={trace.model} /> : null}
        <Chip label={formatCost(trace.cost)} tone="copper" />
        <Chip label={`${trace.span_count} spans`} />
        {trace.cost_source === "absent" ? <Chip label="est." tone="estimated" /> : null}
      </div>

      <ReplayScrubber
        maxSeq={maxSeq}
        seq={seq}
        spans={activeSpans}
        onChange={setSeq}
      />

      <div className="mt-4 grid gap-4 lg:grid-cols-[58%_42%] lg:grid-rows-[minmax(280px,1fr)_auto]">
        <div className="min-h-[280px] lg:row-span-2">
          <Waterfall
            rows={rows.length > 0 ? rows : flattenTree(detail.tree)}
            selectedId={selectedId}
            onSelect={setSelectedId}
          />
        </div>
        <ContextTimeline
          spans={activeSpans}
          selectedId={selectedId}
          onSelect={setSelectedId}
        />
        <SpanInspector span={selectedSpan} />
      </div>
    </PageShell>
  );
}
