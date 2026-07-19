import type { InsightRow } from "@/lib/types";
import { Chip } from "@/components/common/Chip";
import { formatCost, formatDecimal } from "@/lib/format";

const SEVERITY_TONE: Record<string, "cinnabar" | "ochre" | "patina" | "malachite"> = {
  error: "cinnabar",
  warning: "ochre",
  suggestion: "patina",
  info: "malachite",
};

interface InsightCardProps {
  insight: InsightRow;
  onAck: (insight: InsightRow) => void;
  onSnooze: (insight: InsightRow) => void;
  selected?: boolean;
  onSelect: () => void;
}

export function InsightCard({ insight, onAck, onSnooze, selected, onSelect }: InsightCardProps) {
  return (
    <article
      className={`card overflow-hidden ${selected ? "border-copper/50" : ""}`}
      aria-current={selected ? "true" : undefined}
    >
      <div className="flex items-start gap-3 p-4 hover:bg-granite/20">
        <button
          type="button"
          className="flex min-w-0 flex-1 items-start gap-3 text-left"
          onClick={onSelect}
          aria-pressed={selected}
        >
          <Chip label={insight.severity} tone={SEVERITY_TONE[insight.severity] ?? "patina"} />
          <div className="min-w-0 flex-1">
            <h3 className="font-display text-sm font-medium text-bone">{insight.title}</h3>
            <p className="mt-1 text-sm text-cinder line-clamp-2">{insight.body}</p>
            <div className="mt-2 flex flex-wrap gap-2 font-mono text-[10px] text-cinder">
              <span>rank {formatDecimal(insight.rank_score, 2)}</span>
              <span>conf {insight.confidence}</span>
              <span>n={insight.recurrence}</span>
              {insight.savings_estimate != null ? (
                <span className="text-malachite">
                  est. {formatCost(insight.savings_estimate)}/wk
                </span>
              ) : (
                <span>unpriced</span>
              )}
            </div>
          </div>
        </button>
        <div className="flex shrink-0 flex-col gap-2">
          {insight.state === "new" || insight.state === "regressed" ? (
            <>
              <button
                type="button"
                className="rounded-sm border border-copper/50 px-2 py-1 font-mono text-[10px] text-copper hover:bg-shale"
                onClick={() => onAck(insight)}
              >
                Ack
              </button>
              <button
                type="button"
                className="rounded-sm border border-quartz-vein px-2 py-1 font-mono text-[10px] text-cinder hover:bg-shale"
                onClick={() => onSnooze(insight)}
              >
                Snooze 14d
              </button>
            </>
          ) : (
            <Chip label={insight.state} />
          )}
        </div>
      </div>
    </article>
  );
}
