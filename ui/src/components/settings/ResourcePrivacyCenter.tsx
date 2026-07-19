import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { runAction } from "@/lib/api";
import { formatBytes } from "@/lib/format";
import type { ResourceStatus, WorkspaceResponse } from "@/lib/generated/api-types";
import { useToastStore } from "@/state/toast";

type ConfigRow = { key: string; value: unknown; source: string; secret: boolean };

const STORAGE_MODES = ["metrics", "balanced", "forensic", "reference"] as const;
// Match server/ingest/storage.py mode_rank (higher = more invasive raw text).
const STORAGE_RANK: Record<(typeof STORAGE_MODES)[number], number> = {
  reference: 0,
  metrics: 0,
  balanced: 1,
  forensic: 2,
};

function configSource(rows: ConfigRow[] | undefined, key: string): string {
  return rows?.find((item) => item.key === key)?.source ?? "default";
}

function storageModeValue(rows: ConfigRow[] | undefined): string {
  const raw = rows?.find((item) => item.key === "storage.mode")?.value;
  return typeof raw === "string" && raw ? raw : "balanced";
}

function isStorageUpgrade(current: string, next: string): boolean {
  const cur = STORAGE_RANK[current as (typeof STORAGE_MODES)[number]] ?? 0;
  const nxt = STORAGE_RANK[next as (typeof STORAGE_MODES)[number]] ?? 0;
  return nxt > cur;
}

export function ResourcePrivacyCenter({
  workspace,
  configRows,
  onSaveConfig,
  onSync,
  onExport,
  onRebuild,
}: {
  workspace: WorkspaceResponse;
  configRows: ConfigRow[] | undefined;
  onSaveConfig: (key: string, value: string, options?: { confirmStorageUpgrade?: boolean }) => void;
  onSync: () => void;
  onExport: () => void;
  onRebuild: () => void;
}) {
  const showToast = useToastStore((s) => s.show);
  const queryClient = useQueryClient();
  const [planSummary, setPlanSummary] = useState<string | null>(null);
  const [egressSummary, setEgressSummary] = useState<string | null>(null);
  const [circuitSummary, setCircuitSummary] = useState<string | null>(null);
  const [stripConfirmOpen, setStripConfirmOpen] = useState(false);
  const [vacuumConfirmOpen, setVacuumConfirmOpen] = useState(false);
  const [pendingStorageMode, setPendingStorageMode] = useState<string | null>(null);
  const [restoreOpen, setRestoreOpen] = useState(false);
  const [restoreConfirm, setRestoreConfirm] = useState("");
  const [selectedBackup, setSelectedBackup] = useState<string | null>(null);
  const [backups, setBackups] = useState<
    Array<{ path: string; name: string; bytes: number; mtime: string }>
  >([]);
  const [restorePreview, setRestorePreview] = useState<string | null>(null);
  const resources = workspace.resources as ResourceStatus | null | undefined;
  const mode = storageModeValue(configRows);

  const action = useMutation({
    mutationFn: async ({ name, params }: { name: string; params?: Record<string, unknown> }) =>
      runAction(name, params),
    onSuccess: async (res, vars) => {
      const result = res.result ?? {};
      if (vars.name === "lifecycle_plan") {
        const traces = result.traces_matched;
        const spans = result.spans_with_text;
        setPlanSummary(
          typeof traces === "number"
            ? `Dry-run: ${traces} trace(s), ${typeof spans === "number" ? spans : "?"} span(s) with text (no mutations).`
            : "Dry-run plan completed (no mutations).",
        );
      }
      if (vars.name === "egress_status") {
        const count = result.entry_count ?? result.count;
        setEgressSummary(
          typeof count === "number"
            ? `Egress ledger entries: ${count}. Default flows leave this empty.`
            : "Egress status loaded.",
        );
      }
      if (vars.name === "circuit_status") {
        const paused = result.paused_adapters;
        const pausedCount = paused && typeof paused === "object" ? Object.keys(paused).length : 0;
        const quarantine =
          typeof result.quarantine_count === "number" ? result.quarantine_count : 0;
        const globalPause = Boolean(result.global_pause);
        setCircuitSummary(
          globalPause
            ? `Global pause active · ${quarantine} quarantine(s) · ${pausedCount} adapter pause(s).`
            : `Circuits open · ${quarantine} quarantine(s) · ${pausedCount} adapter pause(s).`,
        );
      }
      if (vars.name === "db_backup_list") {
        const rows = Array.isArray(result.backups) ? result.backups : [];
        setBackups(
          rows
            .map((row) => ({
              path: String((row as { path?: string }).path ?? ""),
              name: String((row as { name?: string }).name ?? ""),
              bytes: Number((row as { bytes?: number }).bytes ?? 0),
              mtime: String((row as { mtime?: string }).mtime ?? ""),
            }))
            .filter((row) => row.path),
        );
      }
      if (vars.name === "db_restore" && result.dry_run) {
        const destructiveOk = result.destructive_enabled !== false;
        setRestorePreview(
          `Dry-run: would replace live DB (${formatBytes(Number(result.live_bytes ?? 0))}) ` +
            `from ${String(result.backup ?? "backup")} ` +
            `(${formatBytes(Number(result.backup_bytes ?? 0))})` +
            `${result.would_create_pre_restore_backup ? "; would write pre-restore backup" : ""}.` +
            `${destructiveOk ? "" : " Apply still requires lifecycle.destructive_enabled."}`,
        );
      }
      const quietPreview =
        vars.name === "db_backup_list" || (vars.name === "db_restore" && Boolean(result.dry_run));
      if (!quietPreview) {
        showToast("Action completed", undefined, "good");
      }
      await queryClient.invalidateQueries({ queryKey: ["workspace"] });
      await queryClient.invalidateQueries({ queryKey: ["config-list"] });
    },
    onError: () => showToast("Action failed", undefined, "error"),
  });

  const requestStorageMode = (next: string) => {
    if (next === mode) return;
    if (isStorageUpgrade(mode, next)) {
      setPendingStorageMode(next);
      return;
    }
    onSaveConfig("storage.mode", next);
  };

  return (
    <div className="space-y-4">
      <div>
        <h2 className="font-display text-sm text-bone">Resource &amp; Privacy Center</h2>
        <p className="mt-2 text-sm text-cinder">
          Local disk inventory, storage mode, lifecycle dry-runs, backup, and privacy actions. CLI
          reports remain authoritative for JSON exports (
          <code className="font-mono text-[11px]">cairn resource</code>,{" "}
          <code className="font-mono text-[11px]">cairn privacy</code>).
        </p>
      </div>

      <section className="rounded-sm border border-quartz-vein/60 p-3" aria-label="Disk inventory">
        <p className="font-mono text-[10px] uppercase tracking-wide text-cinder">Disk inventory</p>
        {resources ? (
          <>
            <dl className="mt-2 grid gap-2 font-mono text-xs text-cinder sm:grid-cols-2">
              <div className="flex justify-between gap-3">
                <dt>Total</dt>
                <dd className="text-bone">{formatBytes(resources.disk.total_bytes)}</dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt>Database</dt>
                <dd className="text-bone">{formatBytes(resources.disk.database_bytes)}</dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt>WAL</dt>
                <dd className="text-bone">{formatBytes(resources.disk.wal_bytes)}</dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt>Exports</dt>
                <dd className="text-bone">{formatBytes(resources.disk.exports_bytes)}</dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt>Backups</dt>
                <dd className="text-bone">{formatBytes(resources.disk.backups_bytes)}</dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt>Process RSS</dt>
                <dd className="text-bone">{formatBytes(resources.process_rss_bytes)}</dd>
              </div>
            </dl>
            <p className="mt-2 text-xs text-cinder">{resources.budget.message}</p>
            <p className="mt-1 text-xs text-cinder">
              Forecast: ~{formatBytes(resources.forecast.estimated_bytes_per_day)}/day (
              {resources.forecast.window_days}d window) · {resources.forecast.limitation}
            </p>
            <p className="mt-1 text-xs text-cinder">{resources.limitation}</p>
          </>
        ) : (
          <p className="mt-2 text-xs text-cinder">
            Resource inventory unavailable for this workspace response.
          </p>
        )}
      </section>

      <section className="rounded-sm border border-quartz-vein/60 p-3">
        <p className="font-mono text-[10px] uppercase tracking-wide text-cinder">
          Collection mode (backend auto-sync)
        </p>
        <p className="mt-1 text-xs text-cinder">
          {workspace.collection?.limitation ??
            "Manual / Efficient / Live control backend discovery only."}{" "}
          Browser Live updates (SSE) are a separate top-bar control.
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          {(["manual", "efficient", "live"] as const).map((item) => {
            const active = (workspace.collection?.mode ?? "efficient") === item;
            return (
              <button
                key={item}
                type="button"
                className={`rounded-sm border px-3 py-1.5 font-mono text-xs capitalize ${
                  active
                    ? "border-copper bg-copper/10 text-copper"
                    : "border-quartz-vein text-bone hover:bg-granite"
                }`}
                aria-pressed={active}
                onClick={() => onSaveConfig("collection.mode", item)}
              >
                {item}
              </button>
            );
          })}
        </div>
        <p className="mt-2 text-xs text-cinder">
          Auto-sync {workspace.collection?.auto_sync_active ? "active" : "off"} · source:{" "}
          {configSource(configRows, "collection.mode")}
        </p>
      </section>

      <section className="rounded-sm border border-quartz-vein/60 p-3">
        <p className="font-mono text-[10px] uppercase tracking-wide text-cinder">Storage mode</p>
        <p className="mt-1 text-xs text-cinder">
          Controls raw span text retention. Hashes, tokens, costs, and outcomes remain. Upgrades to
          a more invasive mode ask for confirmation here (same gate as CLI{" "}
          <code className="font-mono text-[11px]">confirm_storage_upgrade</code>). Search uses
          canonical columns — there is no FTS index to rebuild.
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          {STORAGE_MODES.map((item) => {
            const active = mode === item;
            return (
              <button
                key={item}
                type="button"
                className={`rounded-sm border px-3 py-1.5 font-mono text-xs capitalize ${
                  active
                    ? "border-copper bg-copper/10 text-copper"
                    : "border-quartz-vein text-bone hover:bg-granite"
                }`}
                aria-pressed={active}
                onClick={() => requestStorageMode(item)}
              >
                {item}
              </button>
            );
          })}
        </div>
        {pendingStorageMode ? (
          <div className="mt-3 rounded-sm border border-ochre/40 bg-ochre/10 p-3 text-xs text-cinder">
            <p>
              Confirm storage upgrade {mode} → {pendingStorageMode}. More invasive modes may retain
              more raw span text under your privacy policy.
            </p>
            <div className="mt-2 flex flex-wrap gap-2">
              <button
                type="button"
                className="rounded-sm border border-quartz-vein px-3 py-1.5 font-mono text-xs text-bone"
                onClick={() => setPendingStorageMode(null)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="rounded-sm bg-ochre px-3 py-1.5 font-mono text-xs text-anthracite"
                onClick={() => {
                  const next = pendingStorageMode;
                  setPendingStorageMode(null);
                  onSaveConfig("storage.mode", next, { confirmStorageUpgrade: true });
                }}
              >
                Confirm upgrade
              </button>
            </div>
          </div>
        ) : null}
        <p className="mt-2 text-xs text-cinder">
          source: {configSource(configRows, "storage.mode")}
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            type="button"
            className="rounded-sm border border-quartz-vein px-3 py-2 font-mono text-xs text-bone"
            disabled={action.isPending}
            onClick={() =>
              action.mutate({ name: "storage_strip", params: { dry_run: true, limit: 5000 } })
            }
          >
            Preview strip text
          </button>
          <button
            type="button"
            className="rounded-sm border border-ochre/50 px-3 py-2 font-mono text-xs text-ochre"
            disabled={action.isPending}
            onClick={() => setStripConfirmOpen(true)}
          >
            Strip text (apply)
          </button>
        </div>
        {stripConfirmOpen ? (
          <div className="mt-3 rounded-sm border border-ochre/40 bg-ochre/10 p-3 text-xs text-cinder">
            <p>
              Strip retained <code className="font-mono">text_inline</code> according to the current
              storage mode. Metrics and hashes stay. Source agent logs are not modified.
            </p>
            <div className="mt-2 flex flex-wrap gap-2">
              <button
                type="button"
                className="rounded-sm border border-quartz-vein px-3 py-1.5 font-mono text-xs text-bone"
                onClick={() => setStripConfirmOpen(false)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="rounded-sm bg-ochre px-3 py-1.5 font-mono text-xs text-anthracite"
                disabled={action.isPending}
                onClick={() => {
                  setStripConfirmOpen(false);
                  action.mutate({
                    name: "storage_strip",
                    params: { dry_run: false, limit: 5000 },
                  });
                }}
              >
                Confirm strip
              </button>
            </div>
          </div>
        ) : null}
      </section>

      <section className="rounded-sm border border-quartz-vein/60 p-3">
        <p className="font-mono text-[10px] uppercase tracking-wide text-cinder">Lifecycle</p>
        <p className="mt-1 text-xs text-cinder">
          Dry-run first. Destructive cleanup and restore need{" "}
          <code className="font-mono text-[11px]">lifecycle.destructive_enabled</code> in workspace
          config. Restore replaces the live database after a typed confirmation.
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            type="button"
            className="rounded-sm border border-quartz-vein px-3 py-2 font-mono text-xs text-bone"
            disabled={action.isPending}
            onClick={() =>
              action.mutate({
                name: "lifecycle_plan",
                params: { mode: "strip_text" },
              })
            }
          >
            Dry-run cleanup plan
          </button>
          <button
            type="button"
            className="rounded-sm border border-quartz-vein px-3 py-2 font-mono text-xs text-bone"
            disabled={action.isPending}
            onClick={() => action.mutate({ name: "db_backup", params: {} })}
          >
            Backup database
          </button>
          <button
            type="button"
            className="rounded-sm border border-quartz-vein px-3 py-2 font-mono text-xs text-bone"
            disabled={action.isPending}
            onClick={() => {
              setRestoreOpen(true);
              setRestoreConfirm("");
              setRestorePreview(null);
              action.mutate({ name: "db_backup_list", params: {} });
            }}
          >
            Restore from backup…
          </button>
          <button
            type="button"
            className="rounded-sm border border-quartz-vein px-3 py-2 font-mono text-xs text-bone"
            disabled={action.isPending}
            onClick={() => action.mutate({ name: "db_integrity", params: {} })}
          >
            Integrity check
          </button>
          <button
            type="button"
            className="rounded-sm border border-ochre/50 px-3 py-2 font-mono text-xs text-ochre"
            disabled={action.isPending}
            onClick={() => setVacuumConfirmOpen(true)}
          >
            Compact (VACUUM)
          </button>
        </div>
        {restoreOpen ? (
          <div className="mt-3 space-y-3 rounded-sm border border-cinnabar/40 bg-cinnabar/10 p-3 text-xs text-cinder">
            <p>
              Restore replaces <code className="font-mono">.cairn/cairn.db</code>. A pre-restore
              backup is written when the live DB is healthy. Source agent logs are never modified.
            </p>
            {backups.length > 0 ? (
              <ul className="max-h-40 space-y-1 overflow-y-auto">
                {backups.map((item) => (
                  <li key={item.path}>
                    <button
                      type="button"
                      className={`w-full rounded-sm border px-2 py-1.5 text-left font-mono text-[11px] ${
                        selectedBackup === item.path
                          ? "border-copper bg-copper/10 text-copper"
                          : "border-quartz-vein text-bone"
                      }`}
                      onClick={() => {
                        setSelectedBackup(item.path);
                        setRestorePreview(null);
                        action.mutate({
                          name: "db_restore",
                          params: { backup: item.path, dry_run: true },
                        });
                      }}
                    >
                      {item.name} · {formatBytes(item.bytes)} · {item.mtime}
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p>No backups listed yet. Create one with Backup database.</p>
            )}
            {restorePreview ? <p className="text-bone">{restorePreview}</p> : null}
            <label className="block">
              Type <span className="font-mono text-bone">RESTORE</span> to enable apply
              <input
                value={restoreConfirm}
                onChange={(event) => setRestoreConfirm(event.target.value)}
                className="mt-1 w-full rounded-sm border border-quartz-vein bg-slate px-3 py-2 font-mono text-xs text-bone"
                autoComplete="off"
              />
            </label>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                className="rounded-sm border border-quartz-vein px-3 py-1.5 font-mono text-xs text-bone"
                onClick={() => {
                  setRestoreOpen(false);
                  setRestoreConfirm("");
                  setSelectedBackup(null);
                  setRestorePreview(null);
                }}
              >
                Cancel
              </button>
              <button
                type="button"
                className="rounded-sm bg-cinnabar px-3 py-1.5 font-mono text-xs text-bone disabled:opacity-40"
                disabled={action.isPending || restoreConfirm !== "RESTORE" || !selectedBackup}
                onClick={() => {
                  const backup = selectedBackup;
                  setRestoreOpen(false);
                  setRestoreConfirm("");
                  if (!backup) return;
                  action.mutate({
                    name: "db_restore",
                    params: { backup, confirm: true, dry_run: false },
                  });
                }}
              >
                Replace database
              </button>
            </div>
          </div>
        ) : null}
        {vacuumConfirmOpen ? (
          <div className="mt-3 rounded-sm border border-ochre/40 bg-ochre/10 p-3 text-xs text-cinder">
            <p>
              VACUUM rewrites the local database file. Take a backup first if you need a restore
              point. This does not delete traces.
            </p>
            <div className="mt-2 flex flex-wrap gap-2">
              <button
                type="button"
                className="rounded-sm border border-quartz-vein px-3 py-1.5 font-mono text-xs text-bone"
                onClick={() => setVacuumConfirmOpen(false)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="rounded-sm bg-ochre px-3 py-1.5 font-mono text-xs text-anthracite"
                disabled={action.isPending}
                onClick={() => {
                  setVacuumConfirmOpen(false);
                  action.mutate({ name: "db_compact", params: { confirm: true } });
                }}
              >
                Confirm VACUUM
              </button>
            </div>
          </div>
        ) : null}
        {planSummary ? <p className="mt-2 text-xs text-cinder">{planSummary}</p> : null}
      </section>

      <section className="rounded-sm border border-quartz-vein/60 p-3">
        <p className="font-mono text-[10px] uppercase tracking-wide text-cinder">
          Git &amp; egress
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            type="button"
            className="rounded-sm border border-quartz-vein px-3 py-2 font-mono text-xs text-bone"
            disabled={action.isPending}
            onClick={() => action.mutate({ name: "git_exclude_cairn", params: { approve: true } })}
          >
            Add .cairn/ to git exclude
          </button>
          <button
            type="button"
            className="rounded-sm border border-quartz-vein px-3 py-2 font-mono text-xs text-bone"
            disabled={action.isPending}
            onClick={() => action.mutate({ name: "egress_status", params: {} })}
          >
            Egress ledger status
          </button>
          <button
            type="button"
            className="rounded-sm border border-quartz-vein px-3 py-2 font-mono text-xs text-bone"
            disabled={action.isPending}
            onClick={() => action.mutate({ name: "circuit_status", params: {} })}
          >
            Circuit breaker status
          </button>
        </div>
        {egressSummary ? <p className="mt-2 text-xs text-cinder">{egressSummary}</p> : null}
        {circuitSummary ? <p className="mt-2 text-xs text-cinder">{circuitSummary}</p> : null}
      </section>

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className="rounded-sm bg-copper px-3 py-2 font-mono text-xs text-anthracite"
          onClick={onSync}
        >
          Sync now
        </button>
        <button
          type="button"
          className="rounded-sm border border-quartz-vein px-3 py-2 font-mono text-xs text-bone"
          onClick={onExport}
        >
          Export scrubbed bundle
        </button>
        <button
          type="button"
          className="rounded-sm border border-cinnabar/50 px-3 py-2 font-mono text-xs text-cinnabar"
          onClick={onRebuild}
        >
          Rebuild views
        </button>
      </div>
    </div>
  );
}
