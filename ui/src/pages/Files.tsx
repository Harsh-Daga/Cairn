import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fetchFiles } from "@/lib/api";
import { formatNumber, formatPercent, formatTokens } from "@/lib/format";
import { useSelectedTimeRange } from "@/hooks/useSelectedTimeRange";
import { PageShell } from "@/components/common/PageShell";
import { ChartFrame } from "@/components/common/Chip";
import { EmptyCard, ErrorCard } from "@/components/common/DataViews";
import { HorizontalBars, StackedArea } from "@/components/charts";
import { EstimateBadge, Stat } from "@/components/ui";
import type { FilesAnalyticsResponse } from "@/lib/types";

export function FilesPage() {
  const { range, rangeKey } = useSelectedTimeRange();
  const filesQ = useQuery({
    queryKey: ["files", rangeKey],
    queryFn: () => fetchFiles(range),
  });

  if (filesQ.isLoading) {
    return (
      <PageShell title="Files" question="Which paths are read, re-read, edited, and churned?">
        <div className="card h-32 animate-pulse bg-granite/30" />
      </PageShell>
    );
  }

  if (filesQ.isError || !filesQ.data) {
    return (
      <PageShell title="Files" question="Which paths are read, re-read, edited, and churned?">
        <ErrorCard />
      </PageShell>
    );
  }

  const data = filesQ.data;
  const ledger = data.ledger;
  const churnRows = data.churn.map((point) => ({
    day: point.day.slice(5),
    reads: point.reads,
    edits: point.edits,
    re_reads: point.re_reads,
  }));

  return (
    <PageShell title="Files" question="Which paths are read, re-read, edited, and churned?">
      <div className="space-y-6">
        <section className="card p-5" aria-labelledby="files-answer">
          <p className="page-kicker">File ledger · selected range</p>
          <h2 id="files-answer" className="font-display text-xl text-bone">
            Path hotspots under evidence
          </h2>
          <p className="mt-2 max-w-3xl text-sm text-cinder">{ledger.conclusion}</p>
          <p className="mt-3 text-xs text-cinder">{ledger.limitation}</p>
          {ledger.next_action_href ? (
            <Link
              to={ledger.next_action_href}
              className="mt-4 inline-flex min-h-11 items-center font-mono text-xs text-copper"
            >
              {ledger.next_action}
            </Link>
          ) : (
            <p className="mt-4 font-mono text-xs text-cinder">{ledger.next_action}</p>
          )}
        </section>

        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <Stat
            label="Distinct files"
            value={formatNumber(ledger.distinct_files)}
            detail="Repo-relative only"
          />
          <Stat
            label="Reads"
            value={formatNumber(ledger.reads)}
            detail={`${ledger.re_reads} re-reads`}
          />
          <Stat
            label="Edits"
            value={formatNumber(ledger.edits)}
            detail={`${ledger.revert_fixup_sessions} revert/fixup sessions`}
          />
          <Stat
            label="Ignored/vendor"
            value={formatNumber(ledger.ignored_files)}
            detail="Flagged prefixes; still listed"
            help={{
              definition: "Paths under node_modules, vendor, dist, .git, and similar prefixes.",
              limitations: "Flagging is prefix-based, not .gitignore evaluation.",
            }}
          />
        </div>

        {data.files.length > 0 ? (
          <ChartFrame
            title="Hottest paths"
            subtitle="Ranked by re-reads, then edits, then reads"
            summary={`${data.files.length} bounded paths. Cost share is token-proportional.`}
            rows={data.files.slice(0, 20)}
            columns={[
              { key: "path", label: "Path", value: (row) => row.path_rel },
              {
                key: "reads",
                label: "Reads",
                value: (row) => formatNumber(row.reads),
                numeric: true,
              },
              {
                key: "reread",
                label: "Re-reads",
                value: (row) => formatNumber(row.re_reads),
                numeric: true,
              },
              {
                key: "edits",
                label: "Edits",
                value: (row) => formatNumber(row.edits),
                numeric: true,
              },
              {
                key: "cost",
                label: "Est. cost share",
                value: (row) => formatPercent(row.estimated_cost_share),
                numeric: true,
              },
            ]}
          >
            <HorizontalBars
              items={data.files.slice(0, 12).map((file) => ({
                label: file.path_rel,
                value: file.re_reads * 2 + file.edits + file.reads,
              }))}
              width={560}
            />
          </ChartFrame>
        ) : (
          <EmptyCard
            title="No path-bearing spans"
            detail="Adapters may not have emitted repo-relative paths for this range."
          />
        )}

        <ChartFrame
          title="Read/edit churn"
          subtitle="Timezone-aware daily path activity"
          summary={`${churnRows.length} daily points for read, re-read, and edit events.`}
          rows={data.churn}
          columns={[
            { key: "day", label: "Day", value: (row) => row.day },
            {
              key: "reads",
              label: "Reads",
              value: (row) => formatNumber(row.reads),
              numeric: true,
            },
            {
              key: "edits",
              label: "Edits",
              value: (row) => formatNumber(row.edits),
              numeric: true,
            },
            {
              key: "rereads",
              label: "Re-reads",
              value: (row) => formatNumber(row.re_reads),
              numeric: true,
            },
          ]}
        >
          {churnRows.length > 1 ? (
            <StackedArea
              data={churnRows}
              keys={["reads", "edits", "re_reads"]}
              xKey="day"
              width={720}
              height={220}
            />
          ) : (
            <p className="text-sm text-cinder">Not enough daily points for a churn trend.</p>
          )}
        </ChartFrame>

        <FileTable data={data} />

        <section className="card p-4" aria-label="Files limitations">
          <h2 className="font-display text-base text-bone">Interpretation limits</h2>
          <ul className="mt-2 space-y-1 text-xs leading-5 text-cinder">
            {data.limitations.map((limitation) => (
              <li key={limitation}>• {limitation}</li>
            ))}
          </ul>
        </section>
      </div>
    </PageShell>
  );
}


function FileTable({ data }: { data: FilesAnalyticsResponse }) {
  return (
    <section className="card overflow-hidden" aria-labelledby="files-table-heading">
      <div className="border-b border-quartz-vein px-4 py-3">
        <h2 id="files-table-heading" className="font-display text-base text-bone">
          Path evidence
        </h2>
      </div>
      {data.files.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[880px] text-sm">
            <caption className="sr-only">
              Repo-relative file hotspots with reads, edits, and evidence links
            </caption>
            <thead className="bg-slate font-mono text-[10px] uppercase text-cinder">
              <tr>
                <th scope="col" className="px-3 py-2 text-left">
                  Path
                </th>
                <th scope="col" className="px-3 py-2 text-right">
                  Reads
                </th>
                <th scope="col" className="px-3 py-2 text-right">
                  Re-reads
                </th>
                <th scope="col" className="px-3 py-2 text-right">
                  Edits
                </th>
                <th scope="col" className="px-3 py-2 text-right">
                  Tokens
                </th>
                <th scope="col" className="px-3 py-2 text-right">
                  Est. share
                </th>
                <th scope="col" className="px-3 py-2 text-left">
                  Evidence
                </th>
              </tr>
            </thead>
            <tbody>
              {data.files.map((file) => (
                <tr key={file.path_rel} className="border-t border-quartz-vein/50">
                  <td className="px-3 py-3">
                    <div className="font-mono text-xs text-bone">{file.path_rel}</div>
                    {file.ignored ? (
                      <div className="mt-1">
                        <EstimateBadge label="Ignored prefix" />
                      </div>
                    ) : null}
                  </td>
                  <td className="px-3 py-3 text-right font-mono text-xs">{file.reads}</td>
                  <td className="px-3 py-3 text-right font-mono text-xs">{file.re_reads}</td>
                  <td className="px-3 py-3 text-right font-mono text-xs">{file.edits}</td>
                  <td className="px-3 py-3 text-right font-mono text-xs">
                    {formatTokens(file.tokens)}
                  </td>
                  <td className="px-3 py-3 text-right font-mono text-xs estimated-chip">
                    {formatPercent(file.estimated_cost_share)}
                  </td>
                  <td className="px-3 py-3 text-xs">
                    {file.evidence ? (
                      <Link
                        to={`/sessions/${encodeURIComponent(file.evidence.trace_id)}?span=${encodeURIComponent(file.evidence.span_id)}`}
                        className="inline-flex min-h-11 items-center font-mono text-[10px] text-copper"
                      >
                        {file.evidence.label}
                      </Link>
                    ) : (
                      <span className="text-cinder">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="p-4 text-sm text-cinder">No repo-relative paths in this range.</p>
      )}
    </section>
  );
}
