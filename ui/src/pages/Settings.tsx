import { useQuery } from "@tanstack/react-query";
import { fetchWorkspace, runAction } from "@/lib/api";
import { formatRelative } from "@/lib/format";
import { useToastStore } from "@/state/toast";
import { PageShell } from "@/components/common/PageShell";
import { Chip } from "@/components/common/Chip";
import { ErrorCard } from "@/components/common/DataViews";

export function SettingsPage() {
  const showToast = useToastStore((s) => s.show);
  const { data, isLoading, isError } = useQuery({
    queryKey: ["workspace"],
    queryFn: fetchWorkspace,
  });

  if (isLoading) {
    return (
      <PageShell title="Settings" question="See what Cairn sees; change what it does.">
        <div className="card h-32 animate-pulse bg-granite/30" />
      </PageShell>
    );
  }

  if (isError || !data) {
    return (
      <PageShell title="Settings" question="See what Cairn sees; change what it does.">
        <ErrorCard />
      </PageShell>
    );
  }

  const traceCount = Number(data.health.trace_count ?? 0);

  return (
    <PageShell title="Settings" question="See what Cairn sees; change what it does.">
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
          </dl>
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
                    <td className="px-4 py-2 font-mono text-xs text-cinder">
                      {a.cursor_updated_at ? formatRelative(a.cursor_updated_at) : "never"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="p-4 text-sm text-cinder">No adapters detected yet — run workspace scan.</p>
          )}
          <div className="border-t border-quartz-vein px-4 py-3">
            <button
              type="button"
              className="rounded-sm border border-quartz-vein px-3 py-1.5 font-mono text-xs text-bone hover:bg-granite"
              onClick={() =>
                runAction("workspace_scan").then(() => showToast("Workspace scan started"))
              }
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
              onClick={() => runAction("sync").then(() => showToast("Sync started"))}
            >
              Sync now
            </button>
            <button
              type="button"
              className="rounded-sm border border-quartz-vein px-3 py-2 font-mono text-xs text-bone"
              onClick={() => runAction("export_bundle").then(() => showToast("Export started"))}
            >
              Export scrubbed bundle
            </button>
            <button
              type="button"
              className="rounded-sm border border-cinnabar/50 px-3 py-2 font-mono text-xs text-cinnabar"
              onClick={() => {
                const word = window.prompt('Type "rebuild" to rebuild all views');
                if (word === "rebuild") {
                  runAction("rebuild_view", { view: "all" }).then(() =>
                    showToast("Rebuild started"),
                  );
                }
              }}
            >
              Rebuild views
            </button>
          </div>
        </section>

        <section className="card p-4">
          <h2 className="font-display text-sm text-bone">MCP</h2>
          <p className="mt-2 text-sm text-cinder">
            Install Cairn MCP tools for Claude Code, Cursor, and Codex.
          </p>
          <button
            type="button"
            className="mt-3 rounded-sm border border-quartz-vein px-3 py-2 font-mono text-xs text-bone"
            onClick={() => runAction("mcp_install").then(() => showToast("MCP install started"))}
          >
            Install MCP config
          </button>
        </section>
      </div>
    </PageShell>
  );
}
