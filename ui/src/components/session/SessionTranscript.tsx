import type { Span } from "@/lib/types";
import { Chip } from "@/components/common/Chip";

const TRANSCRIPT_KINDS = new Set(["user_msg", "assistant_msg", "tool_call", "tool_result"]);

export function SessionTranscript({ spans }: { spans: Span[] }) {
  const blocks = spans.filter((span) => TRANSCRIPT_KINDS.has(span.kind));
  return (
    <section className="card overflow-hidden" aria-label="Session transcript">
      <div className="border-b border-quartz-vein px-4 py-3">
        <h2 className="font-display text-base text-bone">Readable transcript</h2>
        <p className="mt-1 text-xs text-cinder">
          Captured user, assistant, and tool blocks are rendered as text only.
        </p>
      </div>
      {blocks.length > 0 ? (
        <ol className="divide-y divide-quartz-vein/50">
          {blocks.map((span) => {
            const toolResult = span.kind === "tool_result";
            const content = span.text_inline ?? span.name ?? "Content was not retained.";
            return (
              <li key={span.span_id} id={`transcript-${span.span_id}`} className="px-4 py-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Chip label={span.kind} tone="patina" />
                  <span className="font-mono text-[10px] text-cinder">seq {span.seq}</span>
                  {span.status === "error" ? <Chip label="error" tone="cinnabar" /> : null}
                </div>
                {toolResult ? (
                  <details className="mt-2">
                    <summary className="cursor-pointer text-xs text-copper">
                      Show captured tool result
                    </summary>
                    <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap rounded-sm bg-granite/30 p-3 font-mono text-[10px] text-bone">
                      {content.slice(0, 8_000)}
                    </pre>
                  </details>
                ) : (
                  <pre className="mt-2 whitespace-pre-wrap font-ui text-sm leading-6 text-bone">
                    {content.slice(0, 8_000)}
                  </pre>
                )}
              </li>
            );
          })}
        </ol>
      ) : (
        <p className="p-6 text-sm text-cinder">
          This adapter did not retain user, assistant, or tool transcript blocks.
        </p>
      )}
    </section>
  );
}
