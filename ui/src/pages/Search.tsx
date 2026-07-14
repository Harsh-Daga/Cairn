import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { fetchSearch } from "@/lib/api";
import type { SearchHit } from "@/lib/types";
import { PageShell } from "@/components/common/PageShell";
import { Chip } from "@/components/common/Chip";

const EXAMPLES = ["pytest", "tool:read", "source:claude_code", "is:error"];

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
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");

  useEffect(() => {
    const t = setTimeout(() => setDebounced(q.trim()), 250);
    return () => clearTimeout(t);
  }, [q]);

  const { data, isFetching } = useQuery({
    queryKey: ["search", debounced],
    queryFn: () => fetchSearch(debounced),
    enabled: debounced.length > 0,
  });

  const grouped = (data?.hits ?? []).reduce(
    (acc, hit) => {
      const key = hit.trace_id;
      if (!acc[key]) acc[key] = [];
      acc[key].push(hit);
      return acc;
    },
    {} as Record<string, SearchHit[]>,
  );

  return (
    <PageShell title="Search" question="Search sessions, spans, tools, models, and evidence from one place.">
      <div className="space-y-6">
        <div className="card p-4">
          <input
            autoFocus
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search sessions and span text…"
            className="w-full rounded-sm border border-quartz-vein bg-shale px-4 py-3 font-ui text-sm text-bone placeholder:text-ash focus:border-copper focus:outline-none"
          />
          <div className="mt-3 flex flex-wrap gap-2">
            {EXAMPLES.map((ex) => (
              <button
                key={ex}
                type="button"
                className="rounded-chip border border-quartz-vein px-2 py-1 font-mono text-[10px] text-cinder hover:text-bone"
                onClick={() => setQ(ex)}
              >
                {ex}
              </button>
            ))}
          </div>
        </div>

        {!debounced ? (
          <div className="card p-4 text-sm text-cinder">
            <p>Try an example query or type a tool name, path, or phrase.</p>
            <p className="mt-2 font-mono text-[10px]">
              Syntax: <span className="text-bone">tool:read</span>,{" "}
              <span className="text-bone">source:claude_code</span>,{" "}
              <span className="text-bone">is:error</span>
            </p>
          </div>
        ) : isFetching ? (
          <div className="card h-24 animate-pulse bg-granite/30" />
        ) : (data?.hits.length ?? 0) === 0 ? (
          <div className="card empty-state">
            <h2>No matches</h2>
            <p className="mt-2 text-sm">
              Nothing matched &ldquo;{debounced}&rdquo; in this workspace.
            </p>
            <p className="mt-2 text-sm text-cinder">
              Try a shorter phrase, a tool name, or remove filters like source:.
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            <p className="font-mono text-xs text-cinder">
              {data?.total} hit{(data?.total ?? 0) === 1 ? "" : "s"}
            </p>
            {Object.entries(grouped).map(([traceId, hits]) => (
              <div key={traceId} className="card overflow-hidden">
                <div className="flex items-center gap-2 border-b border-quartz-vein px-4 py-2">
                  <Link
                    to={`/sessions/${traceId}`}
                    className="font-mono text-xs text-copper hover:underline"
                  >
                    {hits[0]?.title ?? traceId.slice(0, 12)}
                  </Link>
                  <Chip label={`${hits.length} spans`} />
                </div>
                <ul>
                  {hits.map((hit, i) => (
                    <li key={`${hit.span_id ?? i}`} className="border-b border-quartz-vein/40 px-4 py-2">
                      <Link
                        to={`/sessions/${traceId}${hit.span_id ? `?span=${hit.span_id}` : ""}`}
                        className="block text-sm text-bone hover:text-copper"
                      >
                        <span className="font-mono text-[10px] text-cinder">{hit.kind}</span>
                        <p className="mt-1 line-clamp-2">
                          <HighlightedSnippet text={hit.snippet} query={debounced} />
                        </p>
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}
      </div>
    </PageShell>
  );
}
