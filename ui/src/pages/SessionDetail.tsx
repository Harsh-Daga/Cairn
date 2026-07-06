import { useQuery } from "@tanstack/react-query";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useEffect, useMemo, useState } from "react";
import { fetchReplayCheckpoints, fetchTraceDetail } from "@/lib/api";
import { interpolateReplayAtSeq } from "@/lib/replay";
import { formatCost } from "@/lib/format";
import { PageShell } from "@/components/common/PageShell";
import { Chip } from "@/components/common/Chip";
import { flattenTree, Waterfall } from "@/components/waterfall/Waterfall";
import { ContextTimeline, ReplayScrubber } from "@/components/session/ReplayScrubber";
import { SpanInspector } from "@/components/session/SpanInspector";
import type { Span } from "@/lib/types";
import {
  formatZoomParam,
  parseZoomParam,
  spansMissingTimestamps,
  traceDurationMs,
  zoomDomainForSpan,
  type WaterfallMode,
} from "@/lib/waterfallLayout";

export function SessionDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const seqParam = Number(searchParams.get("seq") ?? "0");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [blameMode, setBlameMode] = useState(false);
  const [foldSubagents, setFoldSubagents] = useState(false);
  const modeParam = searchParams.get("mode");
  const waterfallMode: WaterfallMode = modeParam === "time" ? "time" : "tokens";
  const timeZoom = parseZoomParam(searchParams.get("zoom"));

  const { data: detail, isLoading, isError } = useQuery({
    queryKey: ["trace", id],
    queryFn: () => fetchTraceDetail(id!),
    enabled: Boolean(id),
  });

  const maxSeq = detail?.spans.length ? Math.max(...detail.spans.map((s) => s.seq)) : 0;
  const seq = Math.min(seqParam, maxSeq);

  const { data: replayData } = useQuery({
    queryKey: ["replay-checkpoints", id],
    queryFn: () => fetchReplayCheckpoints(id!),
    enabled: Boolean(id),
  });

  const activeSpans: Span[] = useMemo(() => {
    if (seq <= 0) return detail?.spans ?? [];
    if (replayData?.checkpoints?.length) {
      return interpolateReplayAtSeq(replayData.checkpoints, seq).spans;
    }
    return (detail?.spans ?? []).filter((s) => s.seq <= seq);
  }, [detail, replayData, seq]);

  const allRows = useMemo(
    () => (detail ? flattenTree(detail.tree, 0, foldSubagents) : []),
    [detail, foldSubagents],
  );

  const rows = useMemo(
    () => allRows.filter((r) => activeSpans.some((s) => s.span_id === r.span.span_id)),
    [allRows, activeSpans],
  );

  const selectedSpan = activeSpans.find((s) => s.span_id === selectedId) ?? null;

  const setSeq = (next: number) => {
    const p = new URLSearchParams(searchParams);
    if (next <= 0) p.delete("seq");
    else p.set("seq", String(next));
    setSearchParams(p);
  };

  const setWaterfallMode = (next: WaterfallMode) => {
    const p = new URLSearchParams(searchParams);
    if (next === "tokens") {
      p.delete("mode");
      p.delete("zoom");
    } else {
      p.set("mode", "time");
    }
    setSearchParams(p);
  };

  const setTimeZoom = (zoom: { startMs: number; endMs: number } | null) => {
    const p = new URLSearchParams(searchParams);
    if (zoom == null) p.delete("zoom");
    else p.set("zoom", formatZoomParam(zoom));
    setSearchParams(p);
  };

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && searchParams.get("zoom")) {
        const p = new URLSearchParams(searchParams);
        p.delete("zoom");
        setSearchParams(p);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [searchParams, setSearchParams]);

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
  const wasteCount = activeSpans.filter((s) => s.waste_tokens > 0 || s.waste_category).length;
  const traceDuration = traceDurationMs(trace.started_at, trace.ended_at, activeSpans);
  const traceStartMs = trace.started_at ? Date.parse(trace.started_at) : 0;
  const showTimestampNote = waterfallMode === "time" && spansMissingTimestamps(activeSpans);

  const handleZoomSpan = (span: Span) => {
    if (waterfallMode !== "time") return;
    const domain = zoomDomainForSpan(span, traceStartMs, traceDuration);
    if (domain) setTimeZoom(domain);
  };

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

      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          className={`rounded-chip border px-2 py-1 font-mono text-[10px] uppercase tracking-wide ${
            waterfallMode === "time"
              ? "border-lapis/60 bg-lapis/10 text-lapis"
              : "border-quartz-vein text-cinder hover:text-bone"
          }`}
          onClick={() => setWaterfallMode(waterfallMode === "time" ? "tokens" : "time")}
        >
          {waterfallMode === "time" ? "Time mode" : "Token mode"}
        </button>
        {timeZoom ? (
          <button
            type="button"
            className="rounded-chip border border-quartz-vein px-2 py-1 font-mono text-[10px] text-cinder hover:text-bone"
            onClick={() => setTimeZoom(null)}
          >
            Reset zoom (Esc)
          </button>
        ) : null}
        <button
          type="button"
          className={`rounded-chip border px-2 py-1 font-mono text-[10px] uppercase tracking-wide ${
            blameMode
              ? "border-ochre/60 bg-ochre/10 text-ochre"
              : "border-quartz-vein text-cinder hover:text-bone"
          }`}
          onClick={() => setBlameMode((v) => !v)}
        >
          Blame {wasteCount > 0 ? `(${wasteCount})` : ""}
        </button>
        <button
          type="button"
          className={`rounded-chip border px-2 py-1 font-mono text-[10px] uppercase tracking-wide ${
            foldSubagents
              ? "border-patina/60 bg-patina/10 text-patina"
              : "border-quartz-vein text-cinder hover:text-bone"
          }`}
          onClick={() => setFoldSubagents((v) => !v)}
        >
          {foldSubagents ? "Expand subagents" : "Fold subagents"}
        </button>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-[58%_42%] lg:grid-rows-[minmax(280px,1fr)_auto]">
        <div className="min-h-[280px] lg:row-span-2">
          <Waterfall
            rows={rows.length > 0 ? rows : allRows}
            selectedId={selectedId}
            onSelect={setSelectedId}
            blameMode={blameMode}
            mode={waterfallMode}
            traceStartedAt={trace.started_at}
            traceDurationMs={traceDuration}
            timeDomain={timeZoom}
            showTimestampNote={showTimestampNote}
            onZoomSpan={handleZoomSpan}
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
