import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { fetchSearch } from "@/lib/api";
import type { SearchHit } from "@/lib/types";
import { PageShell } from "@/components/common/PageShell";
import { Chip } from "@/components/common/Chip";
import { FilterQuery } from "@/components/common/FilterQuery";
import { privacySafeFilterUrl } from "@/lib/filterPrivacy";

const EXAMPLES = ["pytest", "tool:read", "source:claude_code", "is:error"];
const RECENT_KEY = "cairn.search.recent";
const PAGE_SIZE = 20;

function readRecent(): string[] {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(RECENT_KEY) ?? "[]");
    return Array.isArray(value)
      ? value.filter((item): item is string => typeof item === "string")
      : [];
  } catch {
    return [];
  }
}

function writeRecent(values: string[]): void {
  localStorage.setItem(RECENT_KEY, JSON.stringify(values.slice(0, 8)));
}

function facetToken(field: string, value: string): string {
  const escaped = value.replaceAll("\\", "\\\\").replaceAll('"', '\\"');
  return `${field}:"${escaped}"`;
}

function HighlightedSnippet({ text, query }: { text: string; query: string }) {
  if (!query) return <>{text}</>;
  const lower = text.toLowerCase();
  const q = query.toLowerCase();
  const idx = lower.indexOf(q);
  if (idx < 0) return <>{text}</>;
  return (
    <>
      {text.slice(0, idx)}
      <mark className="bg-copper/30 text-bone">{text.slice(idx, idx + query.length)}</mark>
      {text.slice(idx + query.length)}
    </>
  );
}

export function SearchPage() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState(() => params.get("q") ?? "");
  const [debounced, setDebounced] = useState(() => params.get("q")?.trim() ?? "");
  const [recent, setRecent] = useState<string[]>(readRecent);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [linkCopied, setLinkCopied] = useState(false);
  const page = Math.max(1, Number(params.get("page")) || 1);
  const offset = (page - 1) * PAGE_SIZE;

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(q.trim()), 250);
    return () => clearTimeout(timer);
  }, [q]);

  useEffect(() => {
    const current = params.get("q") ?? "";
    if (current === debounced) return;
    const next = new URLSearchParams(params);
    if (debounced) next.set("q", debounced);
    else next.delete("q");
    next.delete("page");
    setParams(next, { replace: true });
  }, [debounced, params, setParams]);

  const { data, isFetching, isError } = useQuery({
    queryKey: ["search", debounced, page],
    queryFn: () => fetchSearch(debounced, PAGE_SIZE, offset),
    enabled: debounced.length > 0,
  });

  useEffect(() => {
    if (!debounced || !data || data.filter_errors.length > 0) return;
    setRecent((current) => {
      const next = [debounced, ...current.filter((item) => item !== debounced)].slice(0, 8);
      writeRecent(next);
      return next;
    });
  }, [data, debounced]);

  const hits = useMemo(() => data?.hits ?? [], [data?.hits]);
  const grouped = useMemo(
    () =>
      hits.reduce((acc, hit) => {
        const rows = acc.get(hit.trace_id) ?? [];
        rows.push(hit);
        acc.set(hit.trace_id, rows);
        return acc;
      }, new Map<string, SearchHit[]>()),
    [hits],
  );

  useEffect(() => {
    setSelectedIndex((index) => Math.min(index, Math.max(hits.length - 1, 0)));
  }, [hits.length]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target;
      if (
        target instanceof HTMLElement &&
        (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable)
      ) {
        return;
      }
      if (hits.length === 0) return;
      if (event.key === "j" || event.key === "k") {
        event.preventDefault();
        setSelectedIndex((index) => {
          const next =
            event.key === "j" ? Math.min(index + 1, hits.length - 1) : Math.max(index - 1, 0);
          window.requestAnimationFrame(() => {
            document.querySelector<HTMLElement>(`[data-search-index="${next}"]`)?.focus();
          });
          return next;
        });
      } else if (event.key === "Enter") {
        const hit = hits[selectedIndex];
        if (!hit) return;
        event.preventDefault();
        navigate(
          `/sessions/${hit.trace_id}${
            hit.span_id ? `?span=${encodeURIComponent(hit.span_id)}` : ""
          }`,
        );
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [hits, navigate, selectedIndex]);

  const setPage = (nextPage: number) => {
    const next = new URLSearchParams(params);
    if (nextPage <= 1) next.delete("page");
    else next.set("page", String(nextPage));
    setParams(next);
  };
  const totalPages = Math.max(1, Math.ceil((data?.total ?? 0) / PAGE_SIZE));

  return (
    <PageShell
      title="Search"
      question="Search sessions, spans, tools, models, and evidence from one place."
    >
      <div className="space-y-6">
        <div className="card p-4">
          <FilterQuery
            label="Workspace search and filters"
            value={q}
            onChange={setQ}
            onSubmit={(value) => setDebounced(value.trim())}
            tokens={data?.filter_tokens}
            errors={data?.filter_errors}
            placeholder='Search text or tool:read file:"src/app.py" cost:>1'
          />
          <div className="mt-3 flex flex-wrap gap-2" aria-label="Filter examples">
            {EXAMPLES.map((example) => (
              <button
                key={example}
                type="button"
                className="rounded-chip border border-quartz-vein px-2 py-1 font-mono text-[10px] text-cinder hover:text-bone"
                onClick={() => setQ(example)}
              >
                {example}
              </button>
            ))}
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-2" aria-label="Search facets">
            <span className="font-mono text-[9px] uppercase tracking-wide text-ash">Facets</span>
            {Object.entries(data?.facets ?? {}).flatMap(([field, values]) =>
              values.slice(0, 3).map((facet) => (
                <button
                  key={`${field}-${facet.value}`}
                  type="button"
                  className="rounded-chip border border-quartz-vein px-2 py-1 font-mono text-[10px] text-cinder hover:text-bone"
                  onClick={() =>
                    setQ((current) => `${current} ${facetToken(field, facet.value)}`.trim())
                  }
                >
                  {field}:{facet.value} ({facet.count})
                </button>
              )),
            )}
            {!data ? (
              <span className="text-[10px] text-ash">Run a search to load counts.</span>
            ) : null}
          </div>
          <button
            type="button"
            className="mt-3 text-xs text-copper hover:underline"
            onClick={async () => {
              await navigator.clipboard.writeText(
                privacySafeFilterUrl(window.location.href, data?.filter_tokens ?? []),
              );
              setLinkCopied(true);
            }}
          >
            {linkCopied ? "Privacy-safe link copied" : "Copy privacy-safe filter link"}
          </button>
        </div>

        {recent.length > 0 ? (
          <section className="card p-4" aria-label="Recent local searches">
            <div className="flex items-center justify-between gap-3">
              <h2 className="font-display text-sm text-bone">Recent on this browser</h2>
              <button
                type="button"
                className="text-xs text-cinder hover:text-cinnabar"
                onClick={() => {
                  writeRecent([]);
                  setRecent([]);
                }}
              >
                Clear all
              </button>
            </div>
            <ul className="mt-2 flex flex-wrap gap-2">
              {recent.map((query) => (
                <li key={query} className="flex items-center gap-1">
                  <button
                    type="button"
                    className="rounded-chip border border-quartz-vein px-2 py-1 font-mono text-[10px] text-cinder"
                    onClick={() => setQ(query)}
                  >
                    {query}
                  </button>
                  <button
                    type="button"
                    className="text-xs text-cinder hover:text-cinnabar"
                    aria-label={`Delete recent search ${query}`}
                    onClick={() => {
                      const next = recent.filter((item) => item !== query);
                      writeRecent(next);
                      setRecent(next);
                    }}
                  >
                    ×
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {!debounced ? (
          <div className="card p-4 text-sm text-cinder">
            Try an example query or type a tool name, relative path, or quoted phrase.
          </div>
        ) : isFetching ? (
          <div className="card h-24 animate-pulse bg-granite/30" />
        ) : isError ? (
          <div className="card p-4 text-sm text-cinnabar">
            Search failed. The local server may be unavailable.
          </div>
        ) : (data?.filter_errors.length ?? 0) > 0 ? (
          <div className="card p-4 text-sm text-cinder">
            Fix the filter above. Invalid or unavailable tokens never broaden the search.
          </div>
        ) : hits.length === 0 ? (
          <div className="card empty-state">
            <h2>No matches</h2>
            <p className="mt-2 text-sm">
              Nothing matched &ldquo;{debounced}&rdquo; in this workspace.
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="font-mono text-xs text-cinder">
                {data?.total} hit{(data?.total ?? 0) === 1 ? "" : "s"} · page {page} of {totalPages}{" "}
                · j/k navigate · Enter open
              </p>
              {data?.search_mode === "scan" ? (
                <Chip label="bounded compatibility scan" tone="estimated" />
              ) : null}
            </div>
            {data?.search_limitation ? (
              <p className="text-xs text-cinder">{data.search_limitation}</p>
            ) : null}
            {Array.from(grouped.entries()).map(([traceId, traceHits]) => (
              <div key={traceId} className="card overflow-hidden">
                <div className="flex items-center gap-2 border-b border-quartz-vein px-4 py-2">
                  <Link
                    to={`/sessions/${traceId}`}
                    className="font-mono text-xs text-copper hover:underline"
                  >
                    {traceHits[0]?.title ?? traceId.slice(0, 12)}
                  </Link>
                  <Chip label={`${traceHits.length} result${traceHits.length === 1 ? "" : "s"}`} />
                </div>
                <ul>
                  {traceHits.map((hit) => {
                    const index = hits.indexOf(hit);
                    const selected = index === selectedIndex;
                    return (
                      <li
                        key={`${hit.span_id ?? "trace"}-${index}`}
                        className="border-b border-quartz-vein/40"
                      >
                        <Link
                          to={`/sessions/${traceId}${
                            hit.span_id ? `?span=${encodeURIComponent(hit.span_id)}` : ""
                          }`}
                          data-search-index={index}
                          tabIndex={selected ? 0 : -1}
                          aria-current={selected ? "true" : undefined}
                          onFocus={() => setSelectedIndex(index)}
                          className={`block px-4 py-2 text-sm text-bone hover:text-copper ${
                            selected ? "bg-copper/10 ring-1 ring-inset ring-copper/30" : ""
                          }`}
                        >
                          <span className="font-mono text-[10px] text-cinder">{hit.kind}</span>
                          <p className="mt-1 line-clamp-2">
                            <HighlightedSnippet
                              text={hit.snippet}
                              query={data?.filter_phrase ?? ""}
                            />
                          </p>
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
            {totalPages > 1 ? (
              <div className="flex items-center justify-between">
                <button
                  type="button"
                  disabled={page <= 1}
                  className="rounded-sm border border-quartz-vein px-3 py-2 font-mono text-xs text-bone disabled:opacity-40"
                  onClick={() => setPage(page - 1)}
                >
                  ← Previous
                </button>
                <span className="font-mono text-xs text-cinder">
                  {offset + 1}–{Math.min(offset + PAGE_SIZE, data?.total ?? 0)} of {data?.total}
                </span>
                <button
                  type="button"
                  disabled={page >= totalPages}
                  className="rounded-sm border border-quartz-vein px-3 py-2 font-mono text-xs text-bone disabled:opacity-40"
                  onClick={() => setPage(page + 1)}
                >
                  Next →
                </button>
              </div>
            ) : null}
          </div>
        )}
      </div>
    </PageShell>
  );
}
