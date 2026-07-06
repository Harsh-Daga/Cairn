import { useVirtualizer } from "@tanstack/react-virtual";
import { useMemo, useRef } from "react";
import type { Span, SpanNode } from "@/lib/types";
import { formatTokens } from "@/lib/format";
import {
  formatTimeRulerLabel,
  parseIsoMs,
  timeBarLayout,
  tokenBarLayout,
  type BarLayout,
  type TimeDomain,
  type WaterfallMode,
} from "@/lib/waterfallLayout";
import { LinkConnectors } from "@/components/waterfall/LinkConnectors";
import { pairLinkConnectors, type SpanLinkRow } from "@/lib/spanLinks";

const KIND_COLORS: Record<string, string> = {
  user_msg: "bg-lapis/60",
  assistant_msg: "bg-malachite/60",
  tool_call: "bg-patina/60",
  tool_result: "bg-ochre/60",
  llm_call: "bg-malachite/50",
  subagent: "bg-patina/40",
  compaction: "bg-cinder/40",
  system: "bg-copper/40",
};

export interface FlatRow {
  span: Span;
  depth: number;
}

export function flattenTree(
  nodes: SpanNode[],
  depth = 0,
  foldSubagents = false,
): FlatRow[] {
  const rows: FlatRow[] = [];
  for (const node of nodes) {
    rows.push({ span: node.span, depth });
    if (node.children.length > 0) {
      const skipChildren = foldSubagents && node.span.kind === "subagent";
      if (!skipChildren) {
        rows.push(...flattenTree(node.children, depth + 1, foldSubagents));
      }
    }
  }
  return rows;
}

interface WaterfallProps {
  rows: FlatRow[];
  selectedId: string | null;
  onSelect: (spanId: string) => void;
  maxTokens?: number;
  blameMode?: boolean;
  mode?: WaterfallMode;
  traceStartedAt?: string | null;
  traceDurationMs?: number;
  timeDomain?: TimeDomain | null;
  showTimestampNote?: boolean;
  onZoomSpan?: (span: Span) => void;
  links?: SpanLinkRow[];
  highlightedLinkId?: string | null;
  onLinkHover?: (connectorId: string | null) => void;
}

function barStyle(layout: BarLayout): React.CSSProperties {
  return {
    marginLeft: `${layout.leftPct}%`,
    width: `${layout.widthPct}%`,
    minWidth: layout.hatched ? undefined : "2px",
  };
}

export function Waterfall({
  rows,
  selectedId,
  onSelect,
  maxTokens,
  blameMode,
  mode = "tokens",
  traceStartedAt,
  traceDurationMs = 1,
  timeDomain,
  showTimestampNote = false,
  onZoomSpan,
  links = [],
  highlightedLinkId = null,
  onLinkHover,
}: WaterfallProps) {
  const parentRef = useRef<HTMLDivElement>(null);
  const tokenMax =
    maxTokens ??
    Math.max(
      1,
      ...rows.map((r) => (r.span.input_tokens ?? 0) + (r.span.output_tokens ?? 0)),
    );
  const traceStartMs = parseIsoMs(traceStartedAt) ?? 0;

  const spanIndex = useMemo(() => {
    const map = new Map<string, number>();
    rows.forEach((row, index) => map.set(row.span.span_id, index));
    return map;
  }, [rows]);

  const connectors = useMemo(
    () => pairLinkConnectors(links, spanIndex),
    [links, spanIndex],
  );

  const highlightedSpanIds = useMemo(() => {
    if (!highlightedLinkId) return new Set<string>();
    const connector = connectors.find((c) => c.id === highlightedLinkId);
    if (!connector) return new Set<string>();
    const ids = new Set<string>();
    for (const row of rows) {
      const index = spanIndex.get(row.span.span_id);
      if (index === connector.fromIndex || index === connector.toIndex) {
        ids.add(row.span.span_id);
      }
    }
    return ids;
  }, [connectors, highlightedLinkId, rows, spanIndex]);

  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 32,
    overscan: 12,
  });

  const domainStart = timeDomain?.startMs ?? traceStartMs;
  const domainEnd = timeDomain?.endMs ?? traceStartMs + traceDurationMs;

  return (
    <div
      ref={parentRef}
      className={`h-full overflow-auto rounded-sm border border-quartz-vein bg-granite/20 ${
        connectors.length > 0 ? "pl-5" : ""
      }`}
    >
      {showTimestampNote && mode === "time" ? (
        <div className="border-b border-quartz-vein bg-ochre/10 px-3 py-2 font-mono text-[10px] text-ochre">
          Some spans lack timestamps from this source — shown as hatched full-row bars.
        </div>
      ) : null}
      <div className="sticky top-0 z-10 border-b border-quartz-vein bg-slate px-3 py-2 font-mono text-[10px] text-cinder">
        {mode === "time" ? (
          <div className="flex justify-between">
            <span>{formatTimeRulerLabel(domainStart, traceStartMs)}</span>
            <span>{formatTimeRulerLabel(domainEnd, traceStartMs)}</span>
          </div>
        ) : (
          <div className="flex">
            <span className="w-[45%]">span</span>
            <span className="w-[30%]">bar</span>
            <span className="w-[12%] text-right">in</span>
            <span className="w-[13%] text-right">cost</span>
          </div>
        )}
      </div>
      <div style={{ height: virtualizer.getTotalSize(), position: "relative" }}>
        <LinkConnectors
          connectors={connectors}
          totalRows={rows.length}
          highlightedId={highlightedLinkId}
          onHover={onLinkHover ?? (() => undefined)}
        />
        {virtualizer.getVirtualItems().map((item) => {
          const row = rows[item.index];
          if (!row) return null;
          const { span, depth } = row;
          const layout =
            mode === "time"
              ? timeBarLayout(span, traceStartMs, traceDurationMs, timeDomain)
              : tokenBarLayout(span, tokenMax);
          const barClass = KIND_COLORS[span.kind] ?? "bg-granite";
          const selected = selectedId === span.span_id;
          const linked = highlightedSpanIds.has(span.span_id);
          const estimated = span.input_estimated > 0 || span.output_estimated > 0;
          const wasted = blameMode && (span.waste_tokens > 0 || span.waste_category != null);

          return (
            <button
              key={span.span_id}
              type="button"
              data-span-id={span.span_id}
              className={`absolute left-0 flex w-full items-center border-b border-quartz-vein/40 px-3 py-1 text-left hover:bg-shale/60 ${
                selected ? "border-l-2 border-l-copper bg-shale/80" : ""
              } ${linked ? "bg-patina/10 ring-1 ring-inset ring-patina/30" : ""} ${
                wasted ? "bg-ochre/10 ring-1 ring-inset ring-ochre/40" : ""
              } ${span.status === "error" ? "text-cinnabar" : "text-bone"}`}
              style={{
                height: item.size,
                transform: `translateY(${item.start}px)`,
                paddingLeft: `${12 + depth * 16}px`,
              }}
              onClick={() => onSelect(span.span_id)}
              onDoubleClick={() => onZoomSpan?.(span)}
            >
              <span className="w-[45%] truncate font-mono text-[11px]">
                {span.kind} · {span.name ?? "—"}
              </span>
              <span className="relative w-[30%] px-2">
                <span
                  className={`block h-3 rounded-sm ${barClass} ${
                    layout.hatched
                      ? "border border-dashed border-cinder bg-[repeating-linear-gradient(135deg,rgba(255,255,255,0.08)_0_4px,transparent_4px_8px)]"
                      : estimated
                        ? "border border-dashed border-cinder"
                        : ""
                  }`}
                  style={{
                    ...barStyle(layout),
                    animation: layout.hatched ? undefined : "strata-rise 0.3s ease-out",
                  }}
                />
              </span>
              <span className={`w-[12%] text-right font-mono text-[10px] ${estimated ? "estimated-chip" : ""}`}>
                {formatTokens(span.input_tokens ?? 0)}
              </span>
              <span className="w-[13%] text-right font-mono text-[10px] text-cinder">—</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
