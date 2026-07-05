import { useVirtualizer } from "@tanstack/react-virtual";
import { useRef } from "react";
import type { Span, SpanNode } from "@/lib/types";
import { formatTokens } from "@/lib/format";

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
}

export function Waterfall({ rows, selectedId, onSelect, maxTokens, blameMode }: WaterfallProps) {
  const parentRef = useRef<HTMLDivElement>(null);
  const tokenMax =
    maxTokens ??
    Math.max(
      1,
      ...rows.map((r) => (r.span.input_tokens ?? 0) + (r.span.output_tokens ?? 0)),
    );

  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 32,
    overscan: 12,
  });

  return (
    <div ref={parentRef} className="h-full overflow-auto rounded-sm border border-quartz-vein bg-granite/20">
      <div className="sticky top-0 z-10 flex border-b border-quartz-vein bg-slate px-3 py-2 font-mono text-[10px] text-cinder">
        <span className="w-[45%]">span</span>
        <span className="w-[30%]">bar</span>
        <span className="w-[12%] text-right">in</span>
        <span className="w-[13%] text-right">cost</span>
      </div>
      <div style={{ height: virtualizer.getTotalSize(), position: "relative" }}>
        {virtualizer.getVirtualItems().map((item) => {
          const row = rows[item.index];
          if (!row) return null;
          const { span, depth } = row;
          const tokens = (span.input_tokens ?? 0) + (span.output_tokens ?? 0);
          const widthPct = Math.max(4, (tokens / tokenMax) * 100);
          const barClass = KIND_COLORS[span.kind] ?? "bg-granite";
          const selected = selectedId === span.span_id;
          const estimated = span.input_estimated > 0 || span.output_estimated > 0;
          const wasted = blameMode && (span.waste_tokens > 0 || span.waste_category != null);

          return (
            <button
              key={span.span_id}
              type="button"
              data-span-id={span.span_id}
              className={`absolute left-0 flex w-full items-center border-b border-quartz-vein/40 px-3 py-1 text-left hover:bg-shale/60 ${
                selected ? "border-l-2 border-l-copper bg-shale/80" : ""
              } ${wasted ? "bg-ochre/10 ring-1 ring-inset ring-ochre/40" : ""} ${
                span.status === "error" ? "text-cinnabar" : "text-bone"
              }`}
              style={{
                height: item.size,
                transform: `translateY(${item.start}px)`,
                paddingLeft: `${12 + depth * 16}px`,
              }}
              onClick={() => onSelect(span.span_id)}
            >
              <span className="w-[45%] truncate font-mono text-[11px]">
                {span.kind} · {span.name ?? "—"}
              </span>
              <span className="w-[30%] px-2">
                <span
                  className={`block h-3 rounded-sm ${barClass} ${estimated ? "border border-dashed border-cinder" : ""}`}
                  style={{ width: `${widthPct}%`, animation: "strata-rise 0.3s ease-out" }}
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
