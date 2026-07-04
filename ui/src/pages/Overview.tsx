import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { fetchOverview, timeRangeDays } from "@/lib/api";
import { formatCost, formatTokens } from "@/lib/format";
import { useUiStore } from "@/state/ui";
import { PageShell } from "@/components/common/PageShell";
import { ChartFrame, Chip } from "@/components/common/Chip";

export function OverviewPage() {
  const timeRange = useUiStore((s) => s.timeRange);
  const days = timeRangeDays(timeRange);
  const navigate = useNavigate();

  const { data, isLoading, isError } = useQuery({
    queryKey: ["overview", days],
    queryFn: () => fetchOverview(days),
  });

  if (isLoading) {
    return (
      <PageShell title="Overview" question="What happened, and what should I look at?">
        <div className="card h-32 animate-pulse bg-granite/30" />
      </PageShell>
    );
  }

  if (isError || !data) {
    return (
      <PageShell title="Overview" question="What happened, and what should I look at?">
        <div className="card p-6 text-cinnabar">
          Couldn&apos;t reach the local server — is <span className="mono">cairn ui</span> running?
        </div>
      </PageShell>
    );
  }

  const traces = Number(data.kpis.traces ?? 0);
  const cost = Number(data.kpis.cost ?? 0);
  const waste = Number(data.kpis.waste_tokens ?? 0);

  return (
    <PageShell title="Overview" question="What happened, and what should I look at?">
      <div className="space-y-6">
        <div className="card p-6">
          {data.narrative.length > 0 ? (
            <div className="space-y-2">
              {data.narrative.map((sentence, i) => (
                <button
                  key={i}
                  type="button"
                  className="display block text-left text-lg text-bone hover:text-copper"
                  onClick={() => {
                    if (sentence.filter?.days) {
                      navigate(`/sessions?days=${sentence.filter.days}`);
                    } else if (sentence.filter?.view === "waste") {
                      navigate("/sessions?sort=waste");
                    } else {
                      navigate("/sessions");
                    }
                  }}
                >
                  {sentence.text}
                </button>
              ))}
            </div>
          ) : (
            <p className="display text-xl text-bone">
              No sessions yet — run <span className="mono text-copper">cairn sync</span> to begin.
            </p>
          )}
        </div>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Kpi label="Sessions" value={String(traces)} />
          <Kpi label="Spend" value={formatCost(cost)} />
          <Kpi
            label="Input tokens"
            value={formatTokens(Number(data.kpis.input_tokens ?? 0))}
          />
          <Kpi label="Waste tokens" value={formatTokens(waste)} estimated={waste > 0} />
        </div>

        {data.tail_risk.expected_worst_cost != null ? (
          <ChartFrame title="Tail risk" subtitle="Expected worst-week cost (GPD)">
            <p className="font-mono text-sm text-ochre">
              {formatCost(data.tail_risk.expected_worst_cost)} expected worst
            </p>
          </ChartFrame>
        ) : null}

        {data.data_notes.length > 0 ? (
          <div className="card p-4">
            <h3 className="font-mono text-[10px] uppercase tracking-wide text-cinder">Data notes</h3>
            <ul className="mt-2 space-y-2 text-sm text-cinder">
              {data.data_notes.map((note, i) => (
                <li key={i}>
                  <Chip label={note.source} /> {note.message}
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {traces > 0 ? (
          <Link
            to="/sessions"
            className="inline-flex font-mono text-sm text-copper hover:underline"
          >
            View all sessions →
          </Link>
        ) : null}
      </div>
    </PageShell>
  );
}

function Kpi({
  label,
  value,
  estimated,
}: {
  label: string;
  value: string;
  estimated?: boolean;
}) {
  return (
    <div className={`card p-4 ${estimated ? "estimated-chip" : ""}`}>
      <p className="font-mono text-[10px] uppercase tracking-wide text-cinder">{label}</p>
      <p className="mt-1 font-display text-2xl text-bone">{value}</p>
    </div>
  );
}
