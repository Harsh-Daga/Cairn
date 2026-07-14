import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchWorkspace, runAction } from "@/lib/api";
import { formatRelative } from "@/lib/format";
import { useToastStore } from "@/state/toast";
import { PageShell } from "@/components/common/PageShell";
import { Chip } from "@/components/common/Chip";
import { ErrorCard } from "@/components/common/DataViews";

const BOOTSTRAP_PROMPT =
  "Set up Cairn (open-source agent observability, https://github.com/Harsh-Daga/Cairn) in this repo. Fetch https://raw.githubusercontent.com/Harsh-Daga/Cairn/main/AGENT_SETUP.md and follow it exactly. Do not use sudo; stop and report if any VERIFY step fails.";
const AGENT_SETUP_URL = "https://github.com/Harsh-Daga/Cairn/blob/main/AGENT_SETUP.md";

export function SettingsPage() {
  const showToast = useToastStore((s) => s.show);
  const [copied, setCopied] = useState(false);
  const [mcpClient, setMcpClient] = useState("cursor");
  const { data, isLoading, isError } = useQuery({
    queryKey: ["workspace"],
    queryFn: fetchWorkspace,
  });

  if (isLoading) {
    return (
      <PageShell title="Settings" question="Manage workspace sources, local data, integrations, and maintenance.">
        <div className="card h-32 animate-pulse bg-granite/30" />
      </PageShell>
    );
  }

  if (isError || !data) {
    return (
      <PageShell title="Settings" question="Manage workspace sources, local data, integrations, and maintenance.">
        <ErrorCard />
      </PageShell>
    );
  }

  const traceCount = Number(data.health.trace_count ?? 0);
  const insightCount = Number(data.health.insight_count ?? 0);
  const agreement = data.health.human_label_agreement as
    | { labeled_sessions?: number; agreements?: number; rate?: number | null }
    | undefined;
  const handleAction = async (
    name: string,
    success: string,
    params?: Record<string, unknown>,
  ) => {
    try {
      await runAction(name, params);
      showToast(success, undefined, "good");
    } catch {
      showToast(`${success.replace(/ started$/, "")} failed`, undefined, "error");
    }
  };

  return (
    <PageShell title="Settings" question="Manage workspace sources, local data, integrations, and maintenance.">
      <div className="mx-auto max-w-2xl space-y-6">
        <section className="card p-4">
          <h2 className="font-display text-sm text-bone">Workspace</h2>
          <dl className="mt-3 space-y-2 font-mono text-xs text-cinder">
            <div className="flex justify-between gap-4">
              <dt>Name</dt>
              <dd className="text-bone">{data.name}</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt>Root</dt>
              <dd className="truncate text-bone">{data.root_path}</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt>Sessions</dt>
              <dd className="text-bone">{traceCount}</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt>Insights</dt>
              <dd className="text-bone">{insightCount || "—"}</dd>
            </div>
          </dl>
        </section>

        <section className="card p-4">
          <h2 className="font-display text-sm text-bone">Quality diagnostics</h2>
          <p className="mt-2 text-sm text-cinder">
            Agreement compares Cairn scores of 50 or higher with human thumbs-up labels.
          </p>
          <div className="mt-3 flex items-end justify-between gap-4">
            <div>
              <p className="font-display text-2xl text-bone">
                {agreement?.rate != null ? `${(agreement.rate * 100).toFixed(0)}%` : "—"}
              </p>
              <p className="font-mono text-[10px] text-cinder">score ↔ human agreement</p>
            </div>
            <p className="font-mono text-xs text-cinder">
              {agreement?.labeled_sessions ?? 0} labeled sessions
            </p>
          </div>
        </section>

        <section className="card p-4">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="page-kicker">Maintenance</p>
              <h2 className="font-display text-lg text-bone">Keep Cairn current</h2>
              <p className="mt-1 text-sm text-cinder">
                Update your local CLI and restart the dashboard. Your workspace data stays in place.
              </p>
            </div>
            <span className="rounded-chip border border-patina/40 px-2 py-1 font-mono text-[10px] text-patina">safe local update</span>
          </div>
          <pre className="mt-4 overflow-x-auto rounded-sm border border-quartz-vein/60 bg-anthracite/40 p-3 font-mono text-[11px] text-bone">cairn upgrade</pre>
        </section>

        <section className="card overflow-hidden">
          <div className="border-b border-quartz-vein px-4 py-3">
            <h2 className="font-display text-sm text-bone">Adapters</h2>
          </div>
          {data.adapters.length > 0 ? (
            <table className="w-full text-left text-sm">
              <thead className="font-mono text-[10px] uppercase tracking-wide text-cinder">
                <tr>
                  <th className="px-4 py-2">Source</th>
                  <th className="px-4 py-2">Streams</th>
                  <th className="px-4 py-2">Parse coverage</th>
                  <th className="px-4 py-2">Last ingest</th>
                </tr>
              </thead>
              <tbody>
                {data.adapters.map((a) => (
                  <tr key={a.source} className="border-t border-quartz-vein/50">
                    <td className="px-4 py-2">
                      <Chip label={a.source} />
                    </td>
                    <td className="px-4 py-2 font-mono text-xs text-bone">{a.streams}</td>
                    <td className="px-4 py-2 font-mono text-xs text-bone">
                      {a.parse_coverage != null ? `${(a.parse_coverage * 100).toFixed(0)}%` : "—"}
                      {a.warning ? <Chip label="format warning" tone="cinnabar" /> : null}
                    </td>
                    <td className="px-4 py-2 font-mono text-xs text-cinder">
                      {a.last_success_at
                        ? formatRelative(a.last_success_at)
                        : a.cursor_updated_at
                          ? formatRelative(a.cursor_updated_at)
                          : "never"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="p-4">
              <p className="text-sm text-cinder">No adapters detected yet — run workspace scan.</p>
              <p className="mt-2 font-mono text-[10px] text-cinder">
                Adapters appear after cairn sync finds agent log streams in your workspace.
              </p>
            </div>
          )}
          <div className="border-t border-quartz-vein px-4 py-3">
            <button
              type="button"
              className="rounded-sm border border-quartz-vein px-3 py-1.5 font-mono text-xs text-bone hover:bg-granite"
              onClick={() => void handleAction("workspace_scan", "Workspace scan started")}
            >
              Rescan adapters
            </button>
          </div>
        </section>

        <section className="card p-4">
          <h2 className="font-display text-sm text-bone">Data</h2>
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              className="rounded-sm bg-copper px-3 py-2 font-mono text-xs text-anthracite"
              onClick={() => void handleAction("sync", "Sync started")}
            >
              Sync now
            </button>
            <button
              type="button"
              className="rounded-sm border border-quartz-vein px-3 py-2 font-mono text-xs text-bone"
              onClick={() => void handleAction("export_bundle", "Export started")}
            >
              Export scrubbed bundle
            </button>
            <button
              type="button"
              className="rounded-sm border border-cinnabar/50 px-3 py-2 font-mono text-xs text-cinnabar"
              onClick={() => {
                const word = window.prompt('Type "rebuild" to rebuild all views');
                if (word === "rebuild") {
                  void handleAction("rebuild_view", "Rebuild started", { view: "all" });
                }
              }}
            >
              Rebuild views
            </button>
          </div>
        </section>

        <section className="card p-4">
          <h2 className="font-display text-sm text-bone">Set up on another machine</h2>
          <p className="mt-2 text-sm text-cinder">
            Paste this into any coding agent (Claude Code, Cursor, Codex…) to install Cairn in a
            repo.
          </p>
          <pre className="mt-3 overflow-x-auto rounded-sm bg-granite/40 p-3 font-mono text-[11px] text-bone">
            {BOOTSTRAP_PROMPT}
          </pre>
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              className="rounded-sm border border-quartz-vein px-3 py-2 font-mono text-xs text-bone"
              onClick={() => {
                void navigator.clipboard.writeText(BOOTSTRAP_PROMPT).then(() => {
                  setCopied(true);
                  showToast("Bootstrap prompt copied");
                  window.setTimeout(() => setCopied(false), 2000);
                });
              }}
            >
              {copied ? "Copied" : "Copy prompt"}
            </button>
            <a
              href={AGENT_SETUP_URL}
              target="_blank"
              rel="noreferrer"
              className="rounded-sm border border-quartz-vein px-3 py-2 font-mono text-xs text-bone hover:bg-granite"
            >
              Full AGENT_SETUP.md
            </a>
          </div>
        </section>

        <section className="card p-4">
          <h2 className="font-display text-sm text-bone">MCP</h2>
          <p className="mt-2 text-sm text-cinder">
            Install Cairn MCP tools for Claude Code, Cursor, and Codex.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <select
              value={mcpClient}
              onChange={(event) => setMcpClient(event.target.value)}
              aria-label="MCP client"
              className="rounded-sm border border-quartz-vein bg-slate px-3 py-2 font-mono text-xs text-bone"
            >
              <option value="cursor">Cursor</option>
              <option value="claude-code">Claude Code</option>
              <option value="codex">Codex</option>
            </select>
            <button
              type="button"
              className="rounded-sm border border-quartz-vein px-3 py-2 font-mono text-xs text-bone"
              onClick={() =>
                void handleAction("mcp_install", "MCP config installed", {
                  client: mcpClient,
                })
              }
            >
              Install MCP config
            </button>
          </div>
        </section>
      </div>
    </PageShell>
  );
}
