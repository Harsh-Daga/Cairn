import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { useUiStore } from "@/state/ui";
import { fetchActions, runAction } from "@/lib/api";
import type { ActionManifestEntry } from "@/lib/types";

const PAGE_LINKS = [
  { to: "/", label: "Overview" },
  { to: "/sessions", label: "Sessions" },
  { to: "/sessions/diff", label: "Session diff" },
  { to: "/insights", label: "Insights" },
  { to: "/optimize", label: "Optimize" },
  { to: "/live", label: "Live" },
] as const;

function hasParams(action: ActionManifestEntry): boolean {
  const props = action.params_schema.properties;
  return Boolean(props && Object.keys(props).length > 0);
}

function defaultParams(action: ActionManifestEntry): Record<string, unknown> {
  const props = action.params_schema.properties as Record<string, { default?: unknown }> | undefined;
  if (!props) return {};
  const out: Record<string, unknown> = {};
  for (const [key, schema] of Object.entries(props)) {
    if (schema.default !== undefined) out[key] = schema.default;
  }
  return out;
}

export function CommandPalette() {
  const open = useUiStore((s) => s.paletteOpen);
  const setOpen = useUiStore((s) => s.setPaletteOpen);
  const [query, setQuery] = useState("");
  const [paramDrafts, setParamDrafts] = useState<Record<string, Record<string, string>>>({});
  const navigate = useNavigate();

  const { data } = useQuery({
    queryKey: ["actions"],
    queryFn: fetchActions,
    enabled: open,
  });

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen(!open);
      }
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, setOpen]);

  const actions = useMemo(
    () =>
      (data?.actions ?? []).filter(
        (a) =>
          !query ||
          a.name.includes(query.toLowerCase()) ||
          a.title.toLowerCase().includes(query.toLowerCase()),
      ),
    [data?.actions, query],
  );

  const sessionActions = actions.filter((a) => a.category === "ingest" || a.category === "annotate");
  const insightActions = actions.filter((a) => a.category === "insights" || a.category === "improve");
  const otherActions = actions.filter(
    (a) => !sessionActions.includes(a) && !insightActions.includes(a),
  );

  const pageLinks = PAGE_LINKS.filter(
    (p) => !query || p.label.toLowerCase().includes(query.toLowerCase()),
  );

  if (!open) return null;

  const runWithParams = (action: ActionManifestEntry) => {
    const raw = paramDrafts[action.name] ?? {};
    const params: Record<string, unknown> = { ...defaultParams(action) };
    for (const [key, value] of Object.entries(raw)) {
      if (value.trim()) params[key] = value;
    }
    runAction(action.name, params).catch(console.error);
    setOpen(false);
  };

  const renderAction = (action: ActionManifestEntry) => {
    const schemaProps = action.params_schema.properties as
      | Record<string, { title?: string; type?: string }>
      | undefined;
    const fields = schemaProps ? Object.keys(schemaProps) : [];

    return (
      <li key={action.name} className="rounded-sm px-2 py-2 hover:bg-shale">
        <button
          type="button"
          className="flex w-full items-center justify-between text-left text-sm text-bone"
          onClick={() => (hasParams(action) ? undefined : runWithParams(action))}
        >
          <span>{action.title}</span>
          <span className="font-mono text-[10px] text-cinder">{action.name}</span>
        </button>
        {hasParams(action) && fields.length > 0 ? (
          <div className="mt-2 flex flex-wrap items-end gap-2">
            {fields.map((field) => (
              <label key={field} className="flex flex-col gap-0.5">
                <span className="font-mono text-[10px] text-cinder">{field}</span>
                <input
                  type="text"
                  className="rounded-sm border border-quartz-vein bg-shale px-2 py-1 font-mono text-xs text-bone"
                  value={paramDrafts[action.name]?.[field] ?? ""}
                  onChange={(e) =>
                    setParamDrafts((prev) => ({
                      ...prev,
                      [action.name]: { ...prev[action.name], [field]: e.target.value },
                    }))
                  }
                />
              </label>
            ))}
            <button
              type="button"
              className="rounded-sm border border-copper-dim px-2 py-1 text-xs text-copper"
              onClick={() => runWithParams(action)}
            >
              Run
            </button>
          </div>
        ) : null}
      </li>
    );
  };

  const renderSection = (title: string, items: ActionManifestEntry[]) =>
    items.length > 0 ? (
      <div className="mt-3">
        <div className="px-2 font-mono text-[10px] uppercase tracking-wider text-cinder">{title}</div>
        <ul>{items.map(renderAction)}</ul>
      </div>
    ) : null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-anthracite/40 pt-[15vh] backdrop-blur-sm"
      role="dialog"
      aria-label="Command palette"
      onClick={() => setOpen(false)}
    >
      <div
        className="w-full max-w-lg rounded-modal border border-quartz-vein bg-slate p-4 shadow-stone"
        onClick={(e) => e.stopPropagation()}
      >
        <input
          type="text"
          placeholder="Search pages and actions…"
          value={query}
          className="w-full rounded-sm border border-quartz-vein bg-shale px-3 py-2 font-ui text-sm text-bone placeholder:text-ash focus:border-copper focus:outline-none"
          autoFocus
          onChange={(e) => setQuery(e.target.value)}
        />

        {pageLinks.length > 0 ? (
          <div className="mt-3">
            <div className="px-2 font-mono text-[10px] uppercase tracking-wider text-cinder">Pages</div>
            <ul>
              {pageLinks.map((page) => (
                <li key={page.to}>
                  <button
                    type="button"
                    className="flex w-full rounded-sm px-2 py-2 text-left text-sm text-bone hover:bg-shale"
                    onClick={() => {
                      navigate(page.to);
                      setOpen(false);
                    }}
                  >
                    {page.label}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {renderSection("Sessions", sessionActions)}
        {renderSection("Insights", insightActions)}
        {renderSection("Actions", otherActions)}
      </div>
    </div>
  );
}
