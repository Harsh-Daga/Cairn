import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { CopyButton } from "@/components/ui";
import { isStaticMode, runAction } from "@/lib/api";
import type { WorkspaceResponse } from "@/lib/types";

type FirstRunState = "no_logs" | "parse_failed" | "ready_to_sync";

function classify(workspace: WorkspaceResponse): FirstRunState {
  if (workspace.adapters.length === 0) return "no_logs";
  if (
    workspace.adapters.some(
      (adapter) =>
        adapter.attempts > 0 &&
        adapter.fully_parsed === 0 &&
        adapter.degraded + adapter.skipped > 0,
    )
  ) {
    return "parse_failed";
  }
  return "ready_to_sync";
}

const STATE_COPY: Record<FirstRunState, { title: string; detail: string }> = {
  no_logs: {
    title: "No local agent logs found",
    detail:
      "Scan again after running a supported agent, or open the setup guide to check paths and permissions.",
  },
  parse_failed: {
    title: "Logs found, but parsing needs attention",
    detail:
      "Cairn found local streams but could not fully parse a session. Review adapter diagnostics before trusting analytics.",
  },
  ready_to_sync: {
    title: "Local logs found — ready to sync",
    detail: "Import the discovered streams into this workspace, or inspect adapter coverage first.",
  },
};

export function FirstRun({ workspace }: { workspace: WorkspaceResponse }) {
  const queryClient = useQueryClient();
  const [guideOpen, setGuideOpen] = useState(false);
  const [demoCommand, setDemoCommand] = useState("");
  const staticMode = isStaticMode();
  const state = classify(workspace);
  const copy = STATE_COPY[state];

  const [excludeNote, setExcludeNote] = useState<string | null>(null);
  const action = useMutation({
    mutationFn: ({
      name,
      params = {},
    }: {
      name: "sync" | "workspace_scan" | "demo_seed" | "git_exclude_cairn";
      params?: Record<string, unknown>;
    }) => runAction(name, params),
    onSuccess: (response, request) => {
      if (request.name === "demo_seed") {
        const root = String(response.result?.root ?? "~/.cairn-demo");
        setDemoCommand(`cairn ui --workspace ${JSON.stringify(root)}`);
      }
      if (request.name === "git_exclude_cairn") {
        const message = String(
          response.result?.message ?? "Local git exclude updated (or already present).",
        );
        setExcludeNote(message);
      }
      void queryClient.invalidateQueries({ queryKey: ["workspace"] });
    },
  });

  const pendingName = action.isPending ? action.variables?.name : null;
  // variables linger after success — use them so demo_seed isn't mislabeled.
  const completedName = action.isSuccess ? (action.variables?.name ?? null) : null;
  const ledgerPath = `${workspace.root_path.replace(/\/$/, "")}/.cairn/cairn.db`;

  return (
    <section className="card overflow-hidden border-copper/40" aria-labelledby="first-run-title">
      <div className="border-b border-quartz-vein bg-copper/5 px-6 py-5">
        <p className="page-kicker">Start locally</p>
        <h2 id="first-run-title" className="mt-1 font-display text-xl text-bone">
          {copy.title}
        </h2>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-cinder">{copy.detail}</p>
      </div>

      <div className="grid gap-6 p-6 lg:grid-cols-[1.1fr_.9fr]">
        <div>
          <h3 className="font-display text-sm text-bone">What Cairn found</h3>
          {workspace.adapters.length > 0 ? (
            <ul className="mt-3 space-y-2">
              {workspace.adapters.map((adapter) => (
                <li
                  key={adapter.source}
                  className="flex flex-wrap items-center justify-between gap-2 rounded-sm border border-quartz-vein px-3 py-2 text-sm"
                >
                  <span className="text-bone">{adapter.source.replace(/_/g, " ")}</span>
                  <span className="font-mono text-[10px] text-cinder">
                    {adapter.streams} stream{adapter.streams === 1 ? "" : "s"} ·{" "}
                    {adapter.parse_coverage == null
                      ? "not parsed yet"
                      : `${Math.round(adapter.parse_coverage * 100)}% parsed`}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-3 rounded-sm border border-dashed border-quartz-vein p-4 text-sm text-cinder">
              No adapter streams are registered for this workspace.
            </p>
          )}
          {workspace.health.adapter_warnings.length > 0 ? (
            <p className="mt-3 text-sm text-cinnabar">
              {workspace.health.adapter_warnings.length} adapter warning
              {workspace.health.adapter_warnings.length === 1 ? "" : "s"} need review in Settings.
            </p>
          ) : null}

          {!staticMode ? (
            <div className="mt-5 flex flex-wrap gap-2">
              <button
                type="button"
                className="min-h-10 rounded-sm bg-copper px-4 text-sm font-semibold text-anthracite disabled:opacity-50"
                disabled={action.isPending}
                onClick={() => action.mutate({ name: "sync" })}
              >
                {pendingName === "sync" ? "Sync queued…" : "Sync now"}
              </button>
              <button
                type="button"
                className="min-h-10 rounded-sm border border-quartz-vein px-4 text-sm text-bone disabled:opacity-50"
                disabled={action.isPending}
                onClick={() => action.mutate({ name: "workspace_scan", params: { force: true } })}
              >
                {pendingName === "workspace_scan" ? "Rescan queued…" : "Rescan adapters"}
              </button>
              <button
                type="button"
                className="min-h-10 rounded-sm border border-quartz-vein px-4 text-sm text-bone"
                onClick={() => setGuideOpen((open) => !open)}
                aria-expanded={guideOpen}
              >
                View setup guide
              </button>
              <button
                type="button"
                className="min-h-10 rounded-sm border border-patina/60 px-4 text-sm text-patina disabled:opacity-50"
                disabled={action.isPending}
                onClick={() => action.mutate({ name: "demo_seed" })}
              >
                {pendingName === "demo_seed" ? "Creating demo…" : "Load deterministic demo"}
              </button>
            </div>
          ) : null}

          {action.isError ? (
            <p className="mt-3 text-sm text-cinnabar" role="alert">
              The local action failed. Check the server and adapter diagnostics, then retry.
            </p>
          ) : null}
          {action.isSuccess && completedName !== "demo_seed" ? (
            <p className="mt-3 text-sm text-patina" role="status">
              {action.data.job_id
                ? "The local job is queued; this page will update when ingest finishes."
                : "The local action completed."}
            </p>
          ) : null}

          {demoCommand ? (
            <div className="mt-4 rounded-sm border border-patina/50 bg-patina/5 p-4">
              <p className="text-sm text-bone">
                Demo data is ready in a separate workspace, so it cannot mix with your data.
              </p>
              <code className="mt-2 block overflow-x-auto font-mono text-xs text-patina">
                {demoCommand}
              </code>
              <div className="mt-3">
                <CopyButton value={demoCommand} label="Copy demo launch command" />
              </div>
            </div>
          ) : null}

          {guideOpen ? (
            <div className="mt-4 rounded-sm border border-quartz-vein bg-anthracite/25 p-4">
              <h3 className="font-display text-sm text-bone">Local setup checklist</h3>
              <ol className="mt-2 list-decimal space-y-2 pl-5 text-sm text-cinder">
                <li>Run a supported agent in this workspace so its local log stream exists.</li>
                <li>Use Scan again, then review discovered streams and parse coverage.</li>
                <li>
                  Use Sync now. Cairn never edits agent or MCP configuration during discovery.
                </li>
                <li>
                  For path or permission diagnostics, open <Link to="/settings">Settings</Link> or
                  run <code className="text-copper">cairn doctor</code>.
                </li>
              </ol>
            </div>
          ) : null}
        </div>

        <div>
          <div className="rounded-sm border border-patina/40 bg-patina/5 p-4">
            <h3 className="font-display text-sm text-bone">Private by default</h3>
            <p className="mt-2 text-sm leading-6 text-cinder">
              Cairn is account-free, zero-telemetry, and loopback-only by default. Data stays on
              this device. This workspace ledger is:
            </p>
            <code className="mt-2 block break-all font-mono text-xs text-bone">{ledgerPath}</code>
            {!staticMode ? (
              <div className="mt-4 border-t border-patina/30 pt-3">
                <p className="text-sm text-cinder">
                  Optional: add <code className="text-copper">.cairn/</code> to local{" "}
                  <code className="text-copper">.git/info/exclude</code> so git does not track the
                  ledger (does not change shared <code className="text-copper">.gitignore</code>).
                </p>
                <button
                  type="button"
                  className="mt-3 min-h-10 rounded-sm border border-patina/60 px-3 text-sm text-patina disabled:opacity-50"
                  disabled={action.isPending}
                  onClick={() =>
                    action.mutate({ name: "git_exclude_cairn", params: { approve: true } })
                  }
                >
                  {pendingName === "git_exclude_cairn"
                    ? "Updating exclude…"
                    : "Approve local git exclude"}
                </button>
                {excludeNote ? (
                  <p className="mt-2 text-xs text-patina" role="status">
                    {excludeNote}
                  </p>
                ) : null}
              </div>
            ) : null}
          </div>
          <div className="mt-4">
            <h3 className="font-display text-sm text-bone">A useful session unlocks</h3>
            <ul className="mt-2 space-y-2 text-sm text-cinder">
              <li>• cost, token flow, and avoidable-context evidence;</li>
              <li>• searchable sessions and a turn-by-turn investigation view;</li>
              <li>• quality, behavior, and adapter data-coverage signals;</li>
              <li>• local insights and controlled optimization experiments.</li>
            </ul>
          </div>
        </div>
      </div>
    </section>
  );
}
