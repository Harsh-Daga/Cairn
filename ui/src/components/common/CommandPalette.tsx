import { useCallback, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { useUiStore } from "@/state/ui";
import { fetchActions, fetchTraces, isStaticMode, runAction } from "@/lib/api";
import type { ActionManifestEntry } from "@/lib/types";
import { useModalFocus } from "@/hooks/useModalFocus";
import { NAVIGATION_ITEMS, PALETTE_ONLY_ROUTES } from "@/lib/navigation";
import { THEME_PREFERENCES, type ThemePreference } from "@/lib/theme";
import { useTimeRangeUrlState } from "@/hooks/useTimeRangeUrlState";

function hasParams(action: ActionManifestEntry): boolean {
  const props = action.params_schema.properties;
  return Boolean(props && Object.keys(props).length > 0);
}

function defaultParams(action: ActionManifestEntry): Record<string, unknown> {
  const props = action.params_schema.properties as
    Record<string, { default?: unknown }> | undefined;
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
  const setThemePreference = useUiStore((s) => s.setThemePreference);
  const [query, setQuery] = useState("");
  const [paramDrafts, setParamDrafts] = useState<Record<string, Record<string, string>>>({});
  const navigate = useNavigate();
  const staticMode = isStaticMode();
  const dialogRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const close = useCallback(() => setOpen(false), [setOpen]);
  const { selectPreset } = useTimeRangeUrlState();
  useModalFocus(open, dialogRef, close, inputRef, '[aria-label="Open command palette"]');

  const { data } = useQuery({
    queryKey: ["actions"],
    queryFn: fetchActions,
    enabled: open && !staticMode,
  });
  const normalizedQuery = query.trim().toLowerCase();
  const { data: sessionData } = useQuery({
    queryKey: ["palette-sessions", normalizedQuery],
    queryFn: () => fetchTraces({ q: normalizedQuery, limit: 5 }),
    enabled: open && !staticMode && normalizedQuery.length >= 2,
    staleTime: 30_000,
  });

  const actions = useMemo(
    () =>
      (staticMode ? [] : (data?.actions ?? [])).filter(
        (a) =>
          !query ||
          a.name.includes(query.toLowerCase()) ||
          a.title.toLowerCase().includes(query.toLowerCase()),
      ),
    [data?.actions, query, staticMode],
  );

  const sessionActions = actions.filter(
    (a) => a.category === "ingest" || a.category === "annotate",
  );
  const insightActions = actions.filter(
    (a) => a.category === "insights" || a.category === "improve",
  );
  const otherActions = actions.filter(
    (a) => !sessionActions.includes(a) && !insightActions.includes(a),
  );

  const pageLinks = [...NAVIGATION_ITEMS, ...PALETTE_ONLY_ROUTES].filter(
    (page) => !normalizedQuery || page.label.toLowerCase().includes(normalizedQuery),
  );
  const sessionLinks = sessionData?.traces ?? [];
  const themeCommands = THEME_PREFERENCES.filter(
    (theme) => !normalizedQuery || `theme ${theme}`.includes(normalizedQuery),
  );
  const rangeCommands = (["24h", "7d", "30d", "90d"] as const).filter(
    (range) => !normalizedQuery || `time range ${range}`.includes(normalizedQuery),
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
      Record<string, { title?: string; type?: string }> | undefined;
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
        <div className="px-2 font-mono text-[10px] uppercase tracking-wider text-cinder">
          {title}
        </div>
        <ul>{items.map(renderAction)}</ul>
      </div>
    ) : null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-anthracite/40 pt-[15vh] backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="command-palette-title"
      onClick={() => setOpen(false)}
    >
      <div
        ref={dialogRef}
        tabIndex={-1}
        className="max-h-[70vh] w-full max-w-lg overflow-y-auto rounded-modal border border-quartz-vein bg-slate p-4 shadow-stone"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="command-palette-title" className="sr-only">
          Command palette
        </h2>
        <input
          ref={inputRef}
          type="text"
          aria-label="Search pages and actions"
          placeholder="Search pages and actions…"
          value={query}
          className="w-full rounded-sm border border-quartz-vein bg-shale px-3 py-2 font-ui text-sm text-bone placeholder:text-ash focus:border-copper focus:outline-none"
          autoFocus
          onChange={(e) => setQuery(e.target.value)}
        />

        {pageLinks.length > 0 ? (
          <div className="mt-3">
            <div className="px-2 font-mono text-[10px] uppercase tracking-wider text-cinder">
              Pages
            </div>
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

        {sessionLinks.length > 0 ? (
          <div className="mt-3">
            <div className="px-2 font-mono text-[10px] uppercase tracking-wider text-cinder">
              Sessions
            </div>
            <ul>
              {sessionLinks.map((session) => (
                <li key={session.trace_id}>
                  <button
                    type="button"
                    className="flex w-full items-center justify-between gap-3 rounded-sm px-2 py-2 text-left hover:bg-shale"
                    onClick={() => {
                      navigate(`/sessions/${session.trace_id}`);
                      close();
                    }}
                  >
                    <span className="truncate text-sm text-bone">
                      {session.title || session.trace_id}
                    </span>
                    <span className="shrink-0 font-mono text-[10px] text-cinder">
                      {session.source}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {themeCommands.length > 0 || rangeCommands.length > 0 ? (
          <div className="mt-3">
            <div className="px-2 font-mono text-[10px] uppercase tracking-wider text-cinder">
              Preferences
            </div>
            <ul>
              {themeCommands.map((theme) => (
                <li key={theme}>
                  <button
                    type="button"
                    className="flex w-full rounded-sm px-2 py-2 text-left text-sm text-bone hover:bg-shale"
                    onClick={() => {
                      setThemePreference(theme as ThemePreference);
                      close();
                    }}
                  >
                    Use {theme} theme
                  </button>
                </li>
              ))}
              {rangeCommands.map((range) => (
                <li key={range}>
                  <button
                    type="button"
                    className="flex w-full rounded-sm px-2 py-2 text-left text-sm text-bone hover:bg-shale"
                    onClick={() => {
                      selectPreset(range);
                      close();
                    }}
                  >
                    Use {range} time range
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {staticMode ? (
          <p className="mt-3 px-2 py-2 font-mono text-xs text-ochre">
            Actions are unavailable in this read-only snapshot.
          </p>
        ) : null}
        {renderSection("Sessions", sessionActions)}
        {renderSection("Insights", insightActions)}
        {renderSection("Actions", otherActions)}
      </div>
    </div>
  );
}
