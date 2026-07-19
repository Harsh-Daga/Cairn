import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useEffect, useMemo, useState } from "react";
import {
  fetchReplayCheckpoints,
  fetchTraceDetail,
  isStaticMode,
  runAction,
  setHumanLabel,
} from "@/lib/api";
import { interpolateReplayAtSeq } from "@/lib/replay";
import { formatCost, formatDuration, formatTokens } from "@/lib/format";
import { mergeConsultationRows } from "@/lib/mcpConsultations";
import { PageShell } from "@/components/common/PageShell";
import { Chip } from "@/components/common/Chip";
import { Waterfall } from "@/components/waterfall/Waterfall";
import { flattenTree } from "@/lib/waterfallTree";
import { LinkLegend } from "@/components/waterfall/LinkConnectors";
import { ContextTimeline, ReplayScrubber } from "@/components/session/ReplayScrubber";
import { SpanInspector } from "@/components/session/SpanInspector";
import {
  SessionCorrections,
  SessionPostmortem,
  SessionReceipt,
} from "@/components/session/SessionEvidenceViews";
import { SessionShields } from "@/components/session/SessionShields";
import { SessionTranscript } from "@/components/session/SessionTranscript";
import { QualityScoreDetails } from "@/components/quality/QualityScoreDetails";
import { SidePanel } from "@/components/ui";
import type { Span } from "@/lib/types";
import {
  formatZoomParam,
  parseZoomParam,
  spansMissingTimestamps,
  traceDurationMs,
  zoomDomainForSpan,
  type WaterfallMode,
} from "@/lib/waterfallLayout";

const DETAIL_TABS = ["investigate", "transcript", "receipt", "corrections", "postmortem"] as const;
type DetailTab = (typeof DETAIL_TABS)[number];

export function SessionDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const seqParam = Number(searchParams.get("seq") ?? "0");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [blameMode, setBlameMode] = useState(false);
  const [foldSubagents, setFoldSubagents] = useState(false);
  const [highlightedLinkId, setHighlightedLinkId] = useState<string | null>(null);
  const [humanLabel, setHumanLabelValue] = useState<"up" | "down" | null>(null);
  const [humanNote, setHumanNote] = useState("");
  const [actionMessage, setActionMessage] = useState("");
  const queryClient = useQueryClient();
  const modeParam = searchParams.get("mode");
  const waterfallMode: WaterfallMode = modeParam === "time" ? "time" : "tokens";
  const timeZoom = parseZoomParam(searchParams.get("zoom"));
  const spanParam = searchParams.get("span");
  const requestedTab = searchParams.get("tab");
  const detailTab: DetailTab = DETAIL_TABS.includes(requestedTab as DetailTab)
    ? (requestedTab as DetailTab)
    : "investigate";

  const {
    data: detail,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ["trace", id],
    queryFn: () => fetchTraceDetail(id!),
    enabled: Boolean(id),
    refetchInterval: (query) => {
      const status = query.state.data?.trace.status.toLowerCase();
      return status && ["active", "running", "in_progress"].includes(status) ? 2_000 : false;
    },
  });

  const maxSeq = detail?.spans.length ? Math.max(...detail.spans.map((s) => s.seq)) : 0;
  const seq = Math.min(seqParam, maxSeq);

  const { data: replayData } = useQuery({
    queryKey: ["replay-checkpoints", id],
    queryFn: () => fetchReplayCheckpoints(id!),
    enabled: Boolean(id),
  });

  useEffect(() => {
    setHumanLabelValue(detail?.outcome?.human_label ?? null);
    setHumanNote(detail?.outcome?.human_note ?? "");
  }, [detail?.outcome?.human_label, detail?.outcome?.human_note]);

  const labelMutation = useMutation({
    mutationFn: () => setHumanLabel(id!, humanLabel, humanNote),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["trace", id] }),
  });
  const exportMutation = useMutation({
    mutationFn: () => runAction("export_bundle", { trace_id: id, scrub: true }),
    onSuccess: (result) => {
      const path = typeof result.result?.path === "string" ? result.result.path : "local exports";
      setActionMessage(`Scrubbed export saved to ${path}.`);
    },
    onError: () => setActionMessage("Scrubbed export failed. No file was reported."),
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

  const rows = useMemo(() => {
    const spanRows = allRows.filter((r) => activeSpans.some((s) => s.span_id === r.span.span_id));
    return mergeConsultationRows(
      spanRows,
      detail?.mcp_consultations ?? [],
      seq > 0 ? seq : Number.POSITIVE_INFINITY,
    );
  }, [allRows, activeSpans, detail?.mcp_consultations, seq]);

  const selectedSpan = rows.find((row) => row.span.span_id === selectedId)?.span ?? null;

  useEffect(() => {
    if (spanParam && detail?.spans.some((span) => span.span_id === spanParam)) {
      setSelectedId(spanParam);
    }
  }, [detail?.spans, spanParam]);

  const setSeq = (next: number) => {
    const p = new URLSearchParams(searchParams);
    if (next <= 0) p.delete("seq");
    else p.set("seq", String(next));
    setSearchParams(p);
  };

  const setDetailTab = (next: DetailTab) => {
    const p = new URLSearchParams(searchParams);
    if (next === "investigate") p.delete("tab");
    else p.set("tab", next);
    setSearchParams(p);
  };

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setActionMessage("Exact local deep link copied.");
    } catch {
      setActionMessage("Copy was unavailable; use the current address bar URL.");
    }
  };

  const selectSpan = (spanId: string | null) => {
    setSelectedId(spanId);
    const p = new URLSearchParams(searchParams);
    if (spanId) p.set("span", spanId);
    else p.delete("span");
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
      if (event.defaultPrevented) return;
      const target = event.target;
      if (
        target instanceof HTMLElement &&
        (target.tagName === "INPUT" || target.tagName === "TEXTAREA")
      ) {
        return;
      }
      if (event.key === "Escape") {
        if (searchParams.get("zoom")) {
          const p = new URLSearchParams(searchParams);
          p.delete("zoom");
          setSearchParams(p);
        } else if (selectedId) {
          setSelectedId(null);
          const p = new URLSearchParams(searchParams);
          p.delete("span");
          setSearchParams(p);
        }
      } else if ((event.key === "j" || event.key === "k") && rows.length > 0) {
        event.preventDefault();
        const current = rows.findIndex((row) => row.span.span_id === selectedId);
        const delta = event.key === "j" ? 1 : -1;
        const origin = current >= 0 ? current : delta > 0 ? -1 : rows.length;
        const next = rows[Math.max(0, Math.min(rows.length - 1, origin + delta))];
        if (next) {
          setSelectedId(next.span.span_id);
          const p = new URLSearchParams(searchParams);
          p.set("span", next.span.span_id);
          setSearchParams(p);
        }
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [rows, searchParams, selectedId, setSearchParams]);

  if (!id) return null;

  if (isLoading) {
    return (
      <PageShell
        title="Session"
        question="Replay the run, inspect every span, and localize where behavior changed."
      >
        <div className="card h-64 animate-pulse bg-granite/30" />
      </PageShell>
    );
  }

  if (isError || !detail) {
    return (
      <PageShell
        title="Session"
        question="Replay the run, inspect every span, and localize where behavior changed."
      >
        <div className="card p-6 text-cinnabar">Session not found.</div>
      </PageShell>
    );
  }

  const { trace } = detail;
  const wasteCount = activeSpans.filter((s) => s.waste_tokens > 0 || s.waste_category).length;
  const traceDuration = traceDurationMs(trace.started_at, trace.ended_at, activeSpans);
  const totalTokens =
    trace.input_tokens +
    trace.output_tokens +
    trace.cache_read_tokens +
    trace.cache_creation_tokens +
    trace.reasoning_tokens;
  const models = [
    ...new Set([trace.model, ...detail.spans.map((span) => span.model)].filter(Boolean)),
  ] as string[];
  const activeSession = ["active", "running", "in_progress"].includes(trace.status.toLowerCase());
  const dataQualityLabel = detail.quality
    ? detail.quality.dropped_events > 0
      ? `degraded · ${detail.quality.dropped_events} dropped`
      : detail.quality.pct_tokens_estimated
        ? `${detail.quality.pct_tokens_estimated.toFixed(0)}% estimated`
        : "measured"
    : "data quality unavailable";
  const traceStartMs = trace.started_at ? Date.parse(trace.started_at) : 0;
  const showTimestampNote = waterfallMode === "time" && spansMissingTimestamps(activeSpans);
  const visibleLinks = detail.links.filter((link) =>
    activeSpans.some(
      (span) => span.span_id === link.from_span_id || span.span_id === link.to_span_id,
    ),
  );

  const handleZoomSpan = (span: Span) => {
    if (waterfallMode !== "time") return;
    const domain = zoomDomainForSpan(span, traceStartMs, traceDuration);
    if (domain) setTimeZoom(domain);
  };

  return (
    <PageShell
      title={trace.title ?? "Session"}
      question="Replay the run, inspect every span, and localize where behavior changed."
    >
      <div className="mb-4">
        <Link to="/sessions" className="font-mono text-xs text-copper hover:underline">
          ← Sessions
        </Link>
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Chip label={detail.outcome?.outcome_label ?? trace.status} tone="patina" />
        <Chip label={trace.source} tone="patina" />
        {models.length > 0 ? <Chip label={models.join(", ")} /> : <Chip label="model unknown" />}
        <Chip label={formatCost(trace.cost)} tone="copper" />
        <Chip label={`${formatTokens(totalTokens)} tokens`} />
        <Chip label={formatDuration(traceDuration)} />
        <Chip label={`${trace.span_count} spans`} />
        <Chip label={dataQualityLabel} tone={detail.quality ? "estimated" : "cinnabar"} />
        {activeSession ? <Chip label="live tail · polling 2s" tone="cinnabar" /> : null}
        {trace.cost_source === "absent" ? <Chip label="est." tone="estimated" /> : null}
        {detail.outcome?.quality_score != null ? (
          <QualityScoreDetails
            score={Number(detail.outcome.quality_score)}
            components={detail.outcome.quality_components}
            weights={detail.outcome.quality_weights}
          />
        ) : null}
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-2" aria-label="Session actions">
        <Link
          to={`/sessions?selected=${encodeURIComponent(trace.trace_id)}`}
          className="rounded-sm border border-quartz-vein px-3 py-1.5 font-mono text-xs text-copper hover:bg-shale"
        >
          Compare
        </Link>
        <button
          type="button"
          className="rounded-sm border border-quartz-vein px-3 py-1.5 font-mono text-xs text-copper hover:bg-shale"
          onClick={() => setDetailTab("postmortem")}
        >
          Post-mortem
        </button>
        <button
          type="button"
          disabled={isStaticMode() || exportMutation.isPending}
          className="rounded-sm border border-quartz-vein px-3 py-1.5 font-mono text-xs text-copper hover:bg-shale disabled:opacity-50"
          onClick={() => exportMutation.mutate()}
        >
          {exportMutation.isPending ? "Exporting…" : "Scrubbed export"}
        </button>
        <button
          type="button"
          className="rounded-sm border border-quartz-vein px-3 py-1.5 font-mono text-xs text-copper hover:bg-shale"
          onClick={() => void copyLink()}
        >
          Copy link
        </button>
        {actionMessage ? (
          <span className="text-xs text-cinder" role="status">
            {actionMessage}
          </span>
        ) : null}
      </div>

      <SessionShields shields={detail.shields} />

      <section className="mb-4 card p-4" aria-label="Human session label">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-display text-sm text-bone">Was this session successful?</span>
          <button
            type="button"
            aria-pressed={humanLabel === "up"}
            className={`rounded-chip border px-3 py-1 text-sm ${
              humanLabel === "up"
                ? "border-malachite bg-malachite/10 text-malachite"
                : "border-quartz-vein text-cinder"
            }`}
            onClick={() => setHumanLabelValue("up")}
          >
            👍
          </button>
          <button
            type="button"
            aria-pressed={humanLabel === "down"}
            className={`rounded-chip border px-3 py-1 text-sm ${
              humanLabel === "down"
                ? "border-cinnabar bg-cinnabar/10 text-cinnabar"
                : "border-quartz-vein text-cinder"
            }`}
            onClick={() => setHumanLabelValue("down")}
          >
            👎
          </button>
          <input
            value={humanNote}
            onChange={(event) => setHumanNote(event.target.value)}
            maxLength={1000}
            placeholder="Optional note"
            aria-label="Human label note"
            className="min-w-52 flex-1 rounded-sm border border-quartz-vein bg-shale px-3 py-1.5 text-sm text-bone"
          />
          <button
            type="button"
            disabled={humanLabel === null || labelMutation.isPending}
            onClick={() => labelMutation.mutate()}
            className="rounded-sm bg-copper px-3 py-1.5 font-mono text-xs text-anthracite disabled:opacity-50"
          >
            {labelMutation.isPending ? "Saving…" : "Save feedback"}
          </button>
        </div>
      </section>

      <div
        className="mb-4 flex overflow-x-auto border-b border-quartz-vein"
        role="tablist"
        aria-label="Session detail views"
      >
        {DETAIL_TABS.map((tab) => (
          <button
            key={tab}
            type="button"
            role="tab"
            aria-selected={detailTab === tab}
            className={`px-4 py-3 font-mono text-[10px] uppercase tracking-wide ${
              detailTab === tab
                ? "border-b-2 border-copper text-bone"
                : "text-cinder hover:text-bone"
            }`}
            onClick={() => setDetailTab(tab)}
          >
            {tab}
          </button>
        ))}
      </div>

      {detailTab === "investigate" ? (
        <>
          <ReplayScrubber maxSeq={maxSeq} seq={seq} spans={activeSpans} onChange={setSeq} />

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
            {trace.cost > 0 ? (
              <span className="self-center font-mono text-[10px] text-cinder">
                ~ span cost is token-proportional allocation, not measured attribution.
              </span>
            ) : null}
          </div>

          <div className="mt-4 grid gap-4 lg:grid-cols-[58%_42%] lg:grid-rows-[minmax(280px,1fr)_auto]">
            <div className="min-h-[280px] lg:row-span-2">
              <LinkLegend links={visibleLinks} />
              <Waterfall
                rows={rows.length > 0 ? rows : allRows}
                selectedId={selectedId}
                onSelect={selectSpan}
                blameMode={blameMode}
                mode={waterfallMode}
                traceStartedAt={trace.started_at}
                traceDurationMs={traceDuration}
                timeDomain={timeZoom}
                showTimestampNote={showTimestampNote}
                onZoomSpan={handleZoomSpan}
                links={visibleLinks}
                highlightedLinkId={highlightedLinkId}
                onLinkHover={setHighlightedLinkId}
                traceCost={trace.cost}
              />
            </div>
            <ContextTimeline spans={activeSpans} selectedId={selectedId} onSelect={selectSpan} />
          </div>
          <SidePanel
            open={selectedSpan != null}
            title="Span inspector"
            onClose={() => selectSpan(null)}
          >
            <SpanInspector
              span={selectedSpan}
              regions={detail.regions}
              links={visibleLinks}
              onSelectSpan={selectSpan}
            />
          </SidePanel>
        </>
      ) : null}
      {detailTab === "transcript" ? <SessionTranscript spans={detail.spans} /> : null}
      {detailTab === "receipt" ? <SessionReceipt detail={detail} /> : null}
      {detailTab === "corrections" ? <SessionCorrections detail={detail} /> : null}
      {detailTab === "postmortem" ? <SessionPostmortem detail={detail} /> : null}
    </PageShell>
  );
}
