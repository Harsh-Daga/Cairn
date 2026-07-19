import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Chip } from "@/components/common/Chip";
import { ErrorCard } from "@/components/common/DataViews";
import { PageShell } from "@/components/common/PageShell";
import { ResourcePrivacyCenter } from "@/components/settings/ResourcePrivacyCenter";
import { CopyButton, Dialog } from "@/components/ui";
import {
  fetchBudget,
  fetchHealth,
  fetchWorkspace,
  runAction,
  waitForActionJob,
} from "@/lib/api";
import { formatCost, formatRelative } from "@/lib/format";
import { THEME_PREFERENCES, type ThemePreference } from "@/lib/theme";
import { useToastStore } from "@/state/toast";
import { useUiStore } from "@/state/ui";

const BOOTSTRAP_PROMPT =
  "Set up Cairn (open-source agent observability, https://github.com/Harsh-Daga/Cairn) in this repo. Fetch https://raw.githubusercontent.com/Harsh-Daga/Cairn/main/AGENT_SETUP.md and follow it exactly. Do not use sudo; stop and report if any VERIFY step fails.";
const AGENT_SETUP_URL = "https://github.com/Harsh-Daga/Cairn/blob/main/AGENT_SETUP.md";
const DOCS_URL = "https://github.com/Harsh-Daga/Cairn/tree/main/docs";
const CHANGELOG_URL = "https://github.com/Harsh-Daga/Cairn/blob/main/CHANGELOG.md";
const LICENSE_URL = "https://github.com/Harsh-Daga/Cairn/blob/main/LICENSE";

const TABS = [
  "workspace",
  "appearance",
  "budget",
  "adapters",
  "data",
  "mcp",
  "quality",
  "privacy",
  "about",
] as const;

type SettingsTab = (typeof TABS)[number];

function asTab(value: string | null): SettingsTab {
  return TABS.includes(value as SettingsTab) ? (value as SettingsTab) : "workspace";
}

type ConfigRow = { key: string; value: unknown; source: string; secret: boolean };

function configNumber(rows: ConfigRow[] | undefined, key: string): string {
  const row = rows?.find((item) => item.key === key);
  if (row?.value == null || row.value === "") return "";
  return String(row.value);
}

function configSource(rows: ConfigRow[] | undefined, key: string): string {
  return rows?.find((item) => item.key === key)?.source ?? "default";
}

export function SettingsPage() {
  const showToast = useToastStore((s) => s.show);
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = asTab(searchParams.get("tab"));
  const [mcpClient, setMcpClient] = useState("cursor");
  const [mcpStatus, setMcpStatus] = useState<string | null>(null);
  const [monthlyUsd, setMonthlyUsd] = useState("");
  const [weeklyUsd, setWeeklyUsd] = useState("");
  const [dailyUsd, setDailyUsd] = useState("");
  const [minQuality, setMinQuality] = useState("");
  const [rebuildOpen, setRebuildOpen] = useState(false);
  const [rebuildConfirm, setRebuildConfirm] = useState("");
  const [adapterScanBusy, setAdapterScanBusy] = useState(false);
  const [adapterScanStatus, setAdapterScanStatus] = useState<string | null>(null);
  const themePreference = useUiStore((state) => state.themePreference);
  const setThemePreference = useUiStore((state) => state.setThemePreference);

  const workspaceQ = useQuery({ queryKey: ["workspace"], queryFn: fetchWorkspace });
  const healthQ = useQuery({ queryKey: ["health"], queryFn: fetchHealth });
  const budgetQ = useQuery({
    queryKey: ["analytics", "budget"],
    queryFn: () => fetchBudget(),
    enabled: tab === "budget",
  });
  const configQ = useQuery({
    queryKey: ["config-list"],
    queryFn: async () => {
      const res = await runAction("config_set", { operation: "list" });
      const values = res.result?.values;
      return Array.isArray(values) ? (values as ConfigRow[]) : [];
    },
  });

  useEffect(() => {
    if (!configQ.data) return;
    setMonthlyUsd(configNumber(configQ.data, "budgets.monthly_usd"));
    setWeeklyUsd(configNumber(configQ.data, "budgets.weekly_usd"));
    setDailyUsd(configNumber(configQ.data, "budgets.daily_usd"));
    setMinQuality(configNumber(configQ.data, "budgets.min_quality"));
    const client = configQ.data.find((row) => row.key === "mcp.client")?.value;
    if (typeof client === "string" && client) setMcpClient(client);
  }, [configQ.data]);

  const setTab = (next: SettingsTab) => {
    const params = new URLSearchParams(searchParams);
    params.set("tab", next);
    setSearchParams(params, { replace: true });
  };

  const saveConfig = useMutation({
    mutationFn: async ({
      key,
      value,
      confirmStorageUpgrade = false,
    }: {
      key: string;
      value: string;
      confirmStorageUpgrade?: boolean;
    }) => {
      if (value.trim() === "") {
        return runAction("config_set", {
          operation: "unset",
          key,
          scope: "workspace",
        });
      }
      return runAction("config_set", {
        operation: "set",
        key,
        value: value.trim(),
        scope: "workspace",
        ...(confirmStorageUpgrade ? { confirm_storage_upgrade: true } : {}),
      });
    },
    onSuccess: async () => {
      showToast("Configuration saved", undefined, "good");
      await queryClient.invalidateQueries({ queryKey: ["config-list"] });
      await queryClient.invalidateQueries({ queryKey: ["analytics", "budget"] });
      await queryClient.invalidateQueries({ queryKey: ["overview"] });
      await queryClient.invalidateQueries({ queryKey: ["workspace"] });
    },
    onError: (error: Error) =>
      showToast(error.message || "Configuration save failed", undefined, "error"),
  });

  const handleAction = async (name: string, success: string, params?: Record<string, unknown>) => {
    try {
      const result = await runAction(name, params);
      showToast(success, undefined, "good");
      if (name === "mcp_install") {
        const path = typeof result.result?.path === "string" ? result.result.path : null;
        const written = result.result?.written;
        setMcpStatus(
          path
            ? `Configured → ${path}${written === false ? " (print-only / not written)" : ""}`
            : "Install completed",
        );
      }
      if (name === "workspace_scan" || name === "sync") {
        await queryClient.invalidateQueries({ queryKey: ["workspace"] });
      }
    } catch {
      showToast(`${success.replace(/ started$/, "")} failed`, undefined, "error");
    }
  };

  const handleAdapterRescan = async () => {
    setAdapterScanBusy(true);
    setAdapterScanStatus("Queuing force rescan…");
    try {
      const queued = await runAction("workspace_scan", { force: true });
      if (queued.job_id) {
        setAdapterScanStatus("Rescanning adapter streams…");
        showToast("Adapter rescan running…", undefined, "good");
        const job = await waitForActionJob(queued.job_id, {
          onProgress: (current) => {
            const pct = Math.round((current.progress || 0) * 100);
            const detail = current.message?.trim() || "running";
            setAdapterScanStatus(`Rescanning… ${pct}% (${detail})`);
          },
        });
        if (job.status !== "done") {
          throw new Error(job.error || job.message || `Job ${job.status}`);
        }
        const result = job.result ?? {};
        const scanned = Number(result.scanned ?? 0);
        const updated = Number(result.updated ?? 0);
        const inserted = Number(result.inserted ?? 0);
        const skipped = Number(result.skipped ?? 0);
        const summary = `Rescan finished: ${scanned} streams · ${inserted} new · ${updated} updated · ${skipped} skipped`;
        setAdapterScanStatus(summary);
        showToast(summary, undefined, "good");
      } else {
        const result = queued.result ?? {};
        const summary = `Rescan finished: ${Number(result.scanned ?? 0)} streams`;
        setAdapterScanStatus(summary);
        showToast(summary, undefined, "good");
      }
      await queryClient.invalidateQueries({ queryKey: ["workspace"] });
      await queryClient.invalidateQueries({ queryKey: ["health"] });
    } catch (error) {
      const detail = error instanceof Error && error.message ? error.message : "Adapter rescan failed";
      setAdapterScanStatus(detail);
      showToast(detail, undefined, "error");
    } finally {
      setAdapterScanBusy(false);
    }
  };

  if (workspaceQ.isLoading) {
    return (
      <PageShell
        title="Settings"
        question="Manage workspace sources, local data, integrations, and maintenance."
      >
        <div className="card h-32 animate-pulse bg-granite/30" />
      </PageShell>
    );
  }

  if (workspaceQ.isError || !workspaceQ.data) {
    return (
      <PageShell
        title="Settings"
        question="Manage workspace sources, local data, integrations, and maintenance."
      >
        <ErrorCard />
      </PageShell>
    );
  }

  const data = workspaceQ.data;
  const traceCount = Number(data.health.trace_count ?? 0);
  const insightCount = Number(data.health.insight_count ?? 0);
  const agreement = data.health.human_label_agreement as
    { labeled_sessions?: number; agreements?: number; rate?: number | null } | undefined;

  return (
    <PageShell
      title="Settings"
      question="Manage workspace sources, local data, integrations, and maintenance."
    >
      <div className="mx-auto max-w-3xl space-y-6">
        <div className="flex flex-wrap gap-2" role="tablist" aria-label="Settings sections">
          {TABS.map((item) => (
            <button
              key={item}
              type="button"
              role="tab"
              aria-selected={tab === item}
              className={`rounded-sm border px-3 py-1.5 font-mono text-xs capitalize ${
                tab === item
                  ? "border-copper/50 bg-copper/10 text-bone"
                  : "border-quartz-vein text-cinder"
              }`}
              onClick={() => setTab(item)}
            >
              {item === "privacy"
                ? "Privacy & Network"
                : item === "data"
                  ? "Resource & Privacy"
                  : item}
            </button>
          ))}
        </div>

        {tab === "workspace" ? (
          <section className="card p-4" role="tabpanel">
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
            <div className="mt-4">
              <p className="page-kicker">Bootstrap another machine</p>
              <pre
                tabIndex={0}
                aria-label="Agent setup prompt"
                className="mt-2 overflow-x-auto rounded-sm bg-granite/40 p-3 font-mono text-[11px] text-bone"
              >
                {BOOTSTRAP_PROMPT}
              </pre>
              <div className="mt-3 flex flex-wrap gap-2">
                <CopyButton value={BOOTSTRAP_PROMPT} label="Copy prompt" />
                <a
                  href={AGENT_SETUP_URL}
                  target="_blank"
                  rel="noreferrer"
                  className="rounded-sm border border-quartz-vein px-3 py-2 font-mono text-xs text-bone hover:bg-granite"
                >
                  Full AGENT_SETUP.md
                </a>
              </div>
            </div>
          </section>
        ) : null}

        {tab === "appearance" ? (
          <section className="card p-4" role="tabpanel">
            <h2 className="font-display text-sm text-bone">Appearance</h2>
            <p className="mt-2 text-sm text-cinder">
              Use your operating-system appearance or keep Cairn in one theme on this device.
            </p>
            <div
              className="mt-3 inline-flex rounded-sm border border-quartz-vein bg-slate p-1"
              role="group"
              aria-label="Color theme"
            >
              {THEME_PREFERENCES.map((preference) => (
                <button
                  key={preference}
                  type="button"
                  aria-pressed={themePreference === preference}
                  className={`min-h-9 rounded-chip px-3 font-mono text-xs capitalize ${
                    themePreference === preference
                      ? "bg-granite text-bone shadow-stone"
                      : "text-cinder hover:text-bone"
                  }`}
                  onClick={() => setThemePreference(preference as ThemePreference)}
                >
                  {preference}
                </button>
              ))}
            </div>
            <p className="mt-2 font-mono text-[10px] text-cinder" aria-live="polite">
              {themePreference === "system"
                ? "Following the operating-system light/dark setting."
                : `Using ${themePreference} appearance.`}
            </p>
          </section>
        ) : null}

        {tab === "budget" ? (
          <section className="card p-4" role="tabpanel">
            <h2 className="font-display text-sm text-bone">Budget</h2>
            <p className="mt-2 text-sm text-cinder">
              Workspace spend ceilings feed Overview attention and{" "}
              <code className="font-mono text-[11px]">cairn stats</code>. Leave a field blank to
              unset. Mutations use the existing config action only.
            </p>
            {budgetQ.data ? (
              <div className="mt-4 rounded-sm border border-quartz-vein/70 bg-slate/40 p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Chip
                    label={`Burn ${budgetQ.data.budget_state}`}
                    tone={
                      budgetQ.data.budget_state === "over" ||
                      budgetQ.data.budget_state === "attention"
                        ? "cinnabar"
                        : "default"
                    }
                  />
                  <span className="font-mono text-[10px] text-cinder">
                    {budgetQ.data.timezone} · {budgetQ.data.observed_active_days} active days
                  </span>
                </div>
                <dl className="mt-3 grid gap-2 sm:grid-cols-3">
                  <div>
                    <dt className="font-mono text-[9px] uppercase tracking-wide text-cinder">
                      Month spend
                    </dt>
                    <dd className="font-mono text-sm text-bone">
                      {formatCost(budgetQ.data.month_spend_usd)}
                      {budgetQ.data.monthly_limit_usd != null
                        ? ` / ${formatCost(budgetQ.data.monthly_limit_usd)}`
                        : ""}
                    </dd>
                  </div>
                  <div>
                    <dt className="font-mono text-[9px] uppercase tracking-wide text-cinder">
                      Linear month-end
                    </dt>
                    <dd className="font-mono text-sm text-bone">
                      {budgetQ.data.linear_projected_usd == null
                        ? "Insufficient history"
                        : formatCost(budgetQ.data.linear_projected_usd)}
                    </dd>
                  </div>
                  <div>
                    <dt className="font-mono text-[9px] uppercase tracking-wide text-cinder">
                      Trailing 7d month-end
                    </dt>
                    <dd className="font-mono text-sm text-bone">
                      {budgetQ.data.trailing_7d_projected_usd == null
                        ? "Unavailable"
                        : formatCost(budgetQ.data.trailing_7d_projected_usd)}
                    </dd>
                  </div>
                </dl>
                {budgetQ.data.projected_overrun_date ? (
                  <p className="mt-2 font-mono text-[10px] text-cinnabar">
                    Projected overrun date (linear, descriptive):{" "}
                    {budgetQ.data.projected_overrun_date}
                  </p>
                ) : null}
                <p className="mt-2 text-xs text-cinder">{budgetQ.data.explanation}</p>
                {(budgetQ.data.agent_shares.length > 0 || budgetQ.data.model_shares.length > 0) && (
                  <div className="mt-3 grid gap-3 sm:grid-cols-2">
                    {budgetQ.data.agent_shares.length > 0 ? (
                      <div>
                        <p className="font-mono text-[9px] uppercase tracking-wide text-cinder">
                          Agent share
                        </p>
                        <ul className="mt-1 space-y-1 font-mono text-[11px] text-bone">
                          {budgetQ.data.agent_shares.slice(0, 5).map((share) => (
                            <li key={share.key}>
                              {share.key}: {formatCost(share.spend_usd)} ({share.share_pct}%)
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : null}
                    {budgetQ.data.model_shares.length > 0 ? (
                      <div>
                        <p className="font-mono text-[9px] uppercase tracking-wide text-cinder">
                          Model share
                        </p>
                        <ul className="mt-1 space-y-1 font-mono text-[11px] text-bone">
                          {budgetQ.data.model_shares.slice(0, 5).map((share) => (
                            <li key={share.key}>
                              {share.key}: {formatCost(share.spend_usd)} ({share.share_pct}%)
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : null}
                  </div>
                )}
              </div>
            ) : budgetQ.isError ? (
              <p className="mt-3 text-xs text-cinnabar">Budget burn readout unavailable.</p>
            ) : (
              <p className="mt-3 text-xs text-cinder">Loading burn readout…</p>
            )}
            <div className="mt-4 grid gap-3 sm:grid-cols-3">
              {(
                [
                  ["Monthly USD", monthlyUsd, setMonthlyUsd, "budgets.monthly_usd"],
                  ["Weekly USD", weeklyUsd, setWeeklyUsd, "budgets.weekly_usd"],
                  ["Daily USD", dailyUsd, setDailyUsd, "budgets.daily_usd"],
                ] as const
              ).map(([label, value, setter, key]) => (
                <label key={key} className="block text-xs text-cinder">
                  <span className="font-mono text-[10px] uppercase tracking-wide">{label}</span>
                  <input
                    type="text"
                    inputMode="decimal"
                    value={value}
                    onChange={(event) => setter(event.target.value)}
                    className="mt-1 w-full rounded-sm border border-quartz-vein bg-slate px-3 py-2 font-mono text-xs text-bone"
                  />
                  <span className="mt-1 block font-mono text-[10px]">
                    source: {configSource(configQ.data, key)}
                  </span>
                  <button
                    type="button"
                    className="mt-2 rounded-sm border border-quartz-vein px-2 py-1 font-mono text-[10px] text-bone"
                    disabled={saveConfig.isPending}
                    onClick={() => saveConfig.mutate({ key, value })}
                  >
                    Save
                  </button>
                </label>
              ))}
            </div>
          </section>
        ) : null}

        {tab === "adapters" ? (
          <section className="card overflow-hidden" role="tabpanel">
            <div className="border-b border-quartz-vein px-4 py-3">
              <h2 className="font-display text-sm text-bone">Adapters</h2>
              <p className="mt-1 text-xs text-cinder">
                Parse coverage is the local canary signal. Per-stream paths are not listed until the
                workspace payload exposes cursor streams.
              </p>
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
                <p className="text-sm text-cinder">
                  No adapters detected yet — run workspace scan.
                </p>
              </div>
            )}
            <div className="border-t border-quartz-vein px-4 py-3">
              <div className="flex flex-wrap items-center gap-3">
                <button
                  type="button"
                  className="rounded-sm border border-quartz-vein px-3 py-1.5 font-mono text-xs text-bone hover:bg-granite disabled:opacity-50"
                  disabled={adapterScanBusy}
                  onClick={() => void handleAdapterRescan()}
                >
                  {adapterScanBusy ? "Rescanning…" : "Rescan adapters"}
                </button>
                {adapterScanStatus ? (
                  <p className="font-mono text-[11px] text-cinder" role="status">
                    {adapterScanStatus}
                  </p>
                ) : (
                  <p className="font-mono text-[11px] text-cinder">
                    Force re-parses local agent logs and refreshes parse coverage.
                  </p>
                )}
              </div>
            </div>
          </section>
        ) : null}

        {tab === "data" ? (
          <section className="card p-4" role="tabpanel">
            <ResourcePrivacyCenter
              workspace={data}
              configRows={configQ.data}
              onSaveConfig={(key, value, options) =>
                saveConfig.mutate({
                  key,
                  value,
                  confirmStorageUpgrade: options?.confirmStorageUpgrade,
                })
              }
              onSync={() => void handleAction("sync", "Sync started")}
              onExport={() => void handleAction("export_bundle", "Export started")}
              onRebuild={() => {
                setRebuildConfirm("");
                setRebuildOpen(true);
              }}
            />
          </section>
        ) : null}

        {tab === "mcp" ? (
          <section className="card p-4" role="tabpanel">
            <h2 className="font-display text-sm text-bone">MCP</h2>
            <p className="mt-2 text-sm text-cinder">
              Install Cairn MCP tools for Claude Code, Cursor, and Codex. Status below reflects the
              last install result in this browser session — there is no separate MCP daemon health
              probe on Settings yet.
            </p>
            <p className="mt-2 font-mono text-[10px] text-cinder">
              Configured client: {configSource(configQ.data, "mcp.client")} ·{" "}
              {String(configQ.data?.find((row) => row.key === "mcp.client")?.value ?? "cursor")}
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
              <button
                type="button"
                className="rounded-sm border border-quartz-vein px-3 py-2 font-mono text-xs text-bone"
                onClick={() =>
                  void handleAction("mcp_install", "MCP preview ready", {
                    client: mcpClient,
                    print_only: true,
                  })
                }
              >
                Preview only
              </button>
            </div>
            {mcpStatus ? <p className="mt-3 text-xs text-cinder">{mcpStatus}</p> : null}
          </section>
        ) : null}

        {tab === "quality" ? (
          <section className="card p-4 space-y-4" role="tabpanel">
            <div>
              <h2 className="font-display text-sm text-bone">Quality</h2>
              <p className="mt-2 text-sm text-cinder">
                Minimum quality is a workspace budget gate (0–1). Agreement compares Cairn scores of
                50 or higher with human thumbs-up labels.
              </p>
            </div>
            <label className="block max-w-xs text-xs text-cinder">
              <span className="font-mono text-[10px] uppercase tracking-wide">
                budgets.min_quality
              </span>
              <input
                type="text"
                inputMode="decimal"
                value={minQuality}
                onChange={(event) => setMinQuality(event.target.value)}
                className="mt-1 w-full rounded-sm border border-quartz-vein bg-slate px-3 py-2 font-mono text-xs text-bone"
              />
              <span className="mt-1 block font-mono text-[10px]">
                source: {configSource(configQ.data, "budgets.min_quality")}
              </span>
              <button
                type="button"
                className="mt-2 rounded-sm border border-quartz-vein px-2 py-1 font-mono text-[10px] text-bone"
                disabled={saveConfig.isPending}
                onClick={() => saveConfig.mutate({ key: "budgets.min_quality", value: minQuality })}
              >
                Save
              </button>
            </label>
            <div className="flex items-end justify-between gap-4 border-t border-quartz-vein/50 pt-4">
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
        ) : null}

        {tab === "privacy" ? (
          <section className="card p-4 space-y-3" role="tabpanel">
            <h2 className="font-display text-sm text-bone">Privacy & Network</h2>
            <p className="text-sm text-cinder">
              Cairn is local-first: the dashboard and ingest stay on loopback unless you
              deliberately point them elsewhere. There is no product telemetry channel.
            </p>
            <p className="text-sm text-cinder">
              Optional provider reflection is opt-in. Preview first (`reflector_preview`) to see
              destination, model, field classes, and a content-bound consent token; only then run
              (`reflector_run`). Normal sync, analysis, API, MCP, demo, and export flows do not call
              a provider.
            </p>
            <p className="text-xs text-cinder">
              See Optimize / docs for the CLI preview-consent boundary. Settings does not send
              payloads from this tab.
            </p>
            <p className="mt-3 text-xs text-cinder">
              Storage mode, strip, lifecycle dry-run, backup, git exclude, and egress status live
              under Settings → Resource &amp; Privacy. CLI:{" "}
              <code className="font-mono text-[11px]">cairn privacy --json</code>.
            </p>
          </section>
        ) : null}

        {tab === "about" ? (
          <section className="card p-4 space-y-4" role="tabpanel">
            <div>
              <h2 className="font-display text-sm text-bone">About</h2>
              <dl className="mt-3 space-y-2 font-mono text-xs text-cinder">
                <div className="flex justify-between gap-4">
                  <dt>Version</dt>
                  <dd className="text-bone">{healthQ.data?.version ?? "—"}</dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt>Health</dt>
                  <dd className="text-bone">{healthQ.data?.status ?? "—"}</dd>
                </div>
              </dl>
            </div>
            <div className="flex flex-wrap gap-2">
              <a
                href={CHANGELOG_URL}
                target="_blank"
                rel="noreferrer"
                className="rounded-sm border border-quartz-vein px-3 py-2 font-mono text-xs text-bone hover:bg-granite"
              >
                Changelog
              </a>
              <a
                href={LICENSE_URL}
                target="_blank"
                rel="noreferrer"
                className="rounded-sm border border-quartz-vein px-3 py-2 font-mono text-xs text-bone hover:bg-granite"
              >
                License
              </a>
              <a
                href={DOCS_URL}
                target="_blank"
                rel="noreferrer"
                className="rounded-sm border border-quartz-vein px-3 py-2 font-mono text-xs text-bone hover:bg-granite"
              >
                Docs
              </a>
            </div>
            <div>
              <p className="page-kicker">Doctor summary</p>
              <p className="mt-1 text-sm text-cinder">
                Run a full local doctor from the CLI — Settings does not invent a partial doctor API
                here.
              </p>
              <pre
                tabIndex={0}
                aria-label="Doctor command"
                className="mt-2 overflow-x-auto rounded-sm border border-quartz-vein/60 bg-anthracite/40 p-3 font-mono text-[11px] text-bone"
              >
                cairn doctor
              </pre>
            </div>
            <div>
              <p className="page-kicker">Update</p>
              <pre
                tabIndex={0}
                aria-label="Upgrade command"
                className="mt-2 overflow-x-auto rounded-sm border border-quartz-vein/60 bg-anthracite/40 p-3 font-mono text-[11px] text-bone"
              >
                cairn upgrade
              </pre>
              <p className="mt-2 text-xs text-cinder">
                Update the local CLI and restart the dashboard. Workspace data stays in place.
              </p>
            </div>
          </section>
        ) : null}
      </div>

      <Dialog
        open={rebuildOpen}
        title="Rebuild derived views"
        onClose={() => setRebuildOpen(false)}
        footer={
          <>
            <button
              type="button"
              className="rounded-sm border border-quartz-vein px-3 py-2 font-mono text-xs text-bone"
              onClick={() => setRebuildOpen(false)}
            >
              Cancel
            </button>
            <button
              type="button"
              className="rounded-sm bg-cinnabar px-3 py-2 font-mono text-xs text-bone disabled:opacity-40"
              disabled={rebuildConfirm !== "rebuild"}
              onClick={() => {
                setRebuildOpen(false);
                void handleAction("rebuild_view", "Rebuild started", { view: "all" });
              }}
            >
              Rebuild
            </button>
          </>
        }
      >
        <p className="text-sm text-cinder">
          Scope: rebuilds derived analytics views only. It does not delete sessions, outcomes, or
          instruction-file experiments.
        </p>
        <label className="mt-4 block text-xs text-cinder">
          Type <span className="font-mono text-bone">rebuild</span> to confirm
          <input
            value={rebuildConfirm}
            onChange={(event) => setRebuildConfirm(event.target.value)}
            className="mt-2 w-full rounded-sm border border-quartz-vein bg-slate px-3 py-2 font-mono text-xs text-bone"
            autoComplete="off"
          />
        </label>
      </Dialog>
    </PageShell>
  );
}
