import { useQuery } from "@tanstack/react-query";
import { fetchInsightEvidence } from "@/lib/api";
import type { InsightRow } from "@/lib/types";
import { Chip } from "@/components/common/Chip";
import { formatCost } from "@/lib/format";

const SEVERITY_TONE: Record<string, "cinnabar" | "ochre" | "patina" | "malachite"> = {
  error: "cinnabar",
  warning: "ochre",
  suggestion: "patina",
  info: "malachite",
};

interface InsightCardProps {
  insight: InsightRow;
  onAck: (insight: InsightRow) => void;
  expanded?: boolean;
  onToggle: () => void;
}

export function InsightCard({ insight, onAck, expanded, onToggle }: InsightCardProps) {
  const { data: evidence } = useQuery({
    queryKey: ["evidence", insight.insight_id],
    queryFn: () => fetchInsightEvidence(insight.insight_id),
    enabled: expanded,
  });

  return (
    <article className="card overflow-hidden">
      <button
        type="button"
        className="flex w-full items-start gap-3 p-4 text-left hover:bg-granite/20"
        onClick={onToggle}
      >
        <Chip label={insight.severity} tone={SEVERITY_TONE[insight.severity] ?? "patina"} />
        <div className="min-w-0 flex-1">
          <h3 className="font-display text-sm font-medium text-bone">{insight.title}</h3>
          <p className="mt-1 text-sm text-cinder line-clamp-2">{insight.body}</p>
          {insight.savings_estimate != null ? (
            <p className="mt-2 font-mono text-[11px] text-malachite">
              est. savings {formatCost(insight.savings_estimate)}/wk
            </p>
          ) : null}
        </div>
        {insight.state === "new" ? (
          <button
            type="button"
            className="shrink-0 rounded-sm border border-copper/50 px-2 py-1 font-mono text-[10px] text-copper hover:bg-shale"
            onClick={(e) => {
              e.stopPropagation();
              onAck(insight);
            }}
          >
            Ack
          </button>
        ) : (
          <Chip label={insight.state} />
        )}
      </button>
      {expanded && evidence ? (
        <div className="border-t border-quartz-vein bg-granite/10 p-4">
          <h4 className="font-mono text-[10px] uppercase tracking-wide text-cinder">Evidence</h4>
          <p className="mt-2 font-mono text-[11px] text-bone">
            producer {evidence.producer} · {evidence.trace_ids.length} trace(s)
          </p>
          {evidence.spans.length > 0 ? (
            <ul className="mt-2 space-y-1 font-mono text-[10px] text-cinder">
              {evidence.spans.slice(0, 5).map((s) => (
                <li key={s.span_id}>
                  {s.kind} · {s.name ?? s.span_id.slice(0, 8)}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </article>
  );
}
