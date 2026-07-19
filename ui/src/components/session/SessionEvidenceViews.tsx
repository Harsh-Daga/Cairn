import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import type { ReceiptResponse, TraceDetailResponse } from "@/lib/types";
import { Chip } from "@/components/common/Chip";
import { CopyButton, EstimateBadge } from "@/components/ui";
import { fetchTraceReceipt } from "@/lib/api";

function statusTone(
  status: ReceiptResponse["status"],
): "default" | "malachite" | "ochre" | "cinnabar" | "copper" {
  switch (status) {
    case "verified":
      return "malachite";
    case "failed":
      return "cinnabar";
    case "debt":
      return "ochre";
    case "unverified":
    case "unknown":
      return "copper";
    default: {
      const _exhaustive: never = status;
      return _exhaustive;
    }
  }
}

export function SessionReceipt({ detail }: { detail: TraceDetailResponse }) {
  const receiptQ = useQuery({
    queryKey: ["trace-receipt", detail.trace.trace_id],
    queryFn: () => fetchTraceReceipt(detail.trace.trace_id),
    initialData: detail.receipt ?? undefined,
  });
  const receipt = receiptQ.data ?? detail.receipt;
  if (!receipt) {
    return (
      <section className="card p-5" aria-label="Verification receipt">
        <p className="text-sm text-cinder">Verification receipt is unavailable for this session.</p>
      </section>
    );
  }

  const activeDebt = receipt.debt.components.filter((component) => component.active);
  return (
    <section className="card p-5" aria-label="Verification receipt">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="page-kicker">
            Receipt · {receipt.schema_version}
            {receipt.persisted ? " · persisted" : " · computed"}
          </p>
          <h2 className="font-display text-lg text-bone">What this ledger can currently prove</h2>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Chip label={receipt.status} tone={statusTone(receipt.status)} />
          <EstimateBadge label={`debt ${receipt.debt.score.toFixed(2)}`} />
          {receipt.markdown ? <CopyButton value={receipt.markdown} label="Copy Markdown" /> : null}
        </div>
      </div>
      <dl className="mt-4 grid gap-3 sm:grid-cols-2">
        <ReceiptFact
          label="Intent"
          value={
            receipt.intent.present
              ? (receipt.intent.summary ?? "Intent retained.")
              : (receipt.intent.limitation ?? "Original user goal was not retained.")
          }
        />
        <ReceiptFact
          label="Outcome"
          value={receipt.outcome.label ?? "No outcome label was recorded."}
        />
        <ReceiptFact
          label="Tests"
          value={
            receipt.outcome.tests_run == null
              ? "Test execution was not recorded."
              : `${receipt.outcome.tests_run} run · ${receipt.outcome.tests_passed ?? 0} passed · ${receipt.outcome.tests_failed ?? 0} failed`
          }
        />
        <ReceiptFact
          label="Build"
          value={receipt.outcome.build_status ?? "Build status was not recorded."}
        />
        <ReceiptFact label="Claims" value={receipt.claims_limitation} />
        <ReceiptFact label="Content hash" value={receipt.content_hash.slice(0, 16) + "…"} />
      </dl>
      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <ReceiptList
          label="Requirements"
          values={
            receipt.requirements.length > 0
              ? receipt.requirements.map((req) => `[${req.status}] ${req.text}`)
              : ["No requirements recorded."]
          }
        />
        <ReceiptList
          label="Verification timeline"
          values={
            receipt.timeline.length > 0
              ? receipt.timeline.map((event) => `${event.at}: ${event.summary}`)
              : ["No verification-shaped event was recorded."]
          }
        />
        <ReceiptList
          label="Debt components"
          values={
            activeDebt.length > 0
              ? activeDebt.map(
                  (component) => `${component.id} (w=${component.weight}): ${component.reason}`,
                )
              : ["No active debt components."]
          }
        />
      </div>
      <p className="mt-3 text-xs text-cinder">{receipt.debt.explanation}</p>
      <div className="mt-4 rounded-sm border border-ochre/40 bg-ochre/5 p-3 text-xs text-cinder">
        {receipt.limitations.map((note) => (
          <p key={note} className="mt-1 first:mt-0">
            {note}
          </p>
        ))}
      </div>
    </section>
  );
}

export function SessionCorrections({ detail }: { detail: TraceDetailResponse }) {
  const label = detail.outcome?.human_label;
  const note = detail.outcome?.human_note;
  const corrections = detail.corrections;
  const events = corrections?.corrections ?? [];
  return (
    <section className="card p-5" aria-label="Session corrections">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="page-kicker">
            Corrections · {corrections?.schema_version ?? "cairn.corrections.v1"}
          </p>
          <h2 className="font-display text-lg text-bone">Supervision signals in this session</h2>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Chip label={`${corrections?.correction_count ?? 0} matched`} tone="patina" />
          <Chip
            label={`${corrections?.unresolved_count ?? 0} unresolved`}
            tone={(corrections?.unresolved_count ?? 0) > 0 ? "ochre" : "default"}
          />
        </div>
      </div>
      {events.length > 0 ? (
        <ul className="mt-4 space-y-3">
          {events.map((event) => (
            <li
              key={event.correction_id}
              className="rounded-sm border border-quartz-vein p-3 text-sm text-bone"
            >
              <div className="flex flex-wrap items-center gap-2">
                <Chip label={event.classification} tone="copper" />
                <Chip label={event.recovery_status} tone="default" />
                <span className="font-mono text-[10px] text-cinder">span {event.span_id}</span>
              </div>
              <p className="mt-2 text-xs text-cinder">
                Signal <span className="text-bone">{event.signal}</span>
                {event.user_relabel ? ` · relabeled from ${event.original_class}` : null}
              </p>
              <p className="mt-1 text-sm text-bone">{event.excerpt}</p>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-3 text-sm text-cinder">
          No high-precision correction phrases were classified. Absence of matches is not proof of
          zero supervision tax.
        </p>
      )}
      {label ? (
        <div className="mt-4 rounded-sm border border-quartz-vein p-4">
          <Chip label={label === "up" ? "human success" : "human failure"} tone="patina" />
          <p className="mt-2 text-sm text-bone">{note || "No correction note was supplied."}</p>
        </div>
      ) : null}
      <p className="mt-3 text-xs text-cinder">
        {(corrections?.limitations ?? []).slice(0, 2).join(" ") ||
          "Classifications are local and not for employee ranking."}
      </p>
    </section>
  );
}

function ReceiptFact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="font-mono text-[10px] uppercase tracking-wide text-cinder">{label}</dt>
      <dd className="mt-1 text-sm text-bone">{value}</dd>
    </div>
  );
}

function ReceiptList({ label, values }: { label: string; values: string[] }) {
  return (
    <div>
      <p className="font-mono text-[10px] uppercase tracking-wide text-cinder">{label}</p>
      <ul className="mt-2 space-y-1 text-xs text-cinder">
        {values.map((value) => (
          <li key={value}>{value}</li>
        ))}
      </ul>
    </div>
  );
}

export function SessionPostmortem({ detail }: { detail: TraceDetailResponse }) {
  const postmortem = detail.postmortem;
  const diagnostic = detail.diagnostics;
  const errors = detail.spans.filter((span) => span.status === "error");
  if (!postmortem) {
    return (
      <section className="card p-5" aria-label="Session post-mortem">
        <h2 className="font-display text-lg text-bone">Recorded failure localization</h2>
        <p className="mt-3 text-sm text-cinder">
          No postmortem is available for this session
          {diagnostic ? " beyond the raw diagnose row" : ""}. {errors.length} error span
          {errors.length === 1 ? " is" : "s are"} visible in the transcript/waterfall.
        </p>
        <p className="mt-4 text-xs text-cinder">
          Postmortems require failed/low-quality outcomes, diagnose rows, or error spans. They are
          deterministic recorded localization, not causal narratives.
        </p>
      </section>
    );
  }
  return (
    <section className="card p-5" aria-label="Session post-mortem">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="page-kicker">Diagnose cascade · deterministic</p>
          <h2 className="font-display text-lg text-bone">Session postmortem</h2>
        </div>
        <CopyButton value={postmortem.markdown} label="Copy Markdown" />
      </div>
      <dl className="mt-4 grid gap-3 sm:grid-cols-2">
        <ReceiptFact
          label="Primary category"
          value={postmortem.primary_category ?? "Unavailable"}
        />
        <ReceiptFact
          label="Failure signature"
          value={postmortem.failure_signature ?? "Unavailable"}
        />
        <ReceiptFact label="Outcome" value={postmortem.outcome_label ?? "Unavailable"} />
        <ReceiptFact
          label="Quality"
          value={
            postmortem.quality_score == null ? "Unavailable" : String(postmortem.quality_score)
          }
        />
      </dl>
      <ol className="mt-5 space-y-3">
        {postmortem.steps.map((step) => (
          <li key={step.kind} className="rounded-sm border border-quartz-vein/60 p-3">
            <p className="font-mono text-[10px] uppercase tracking-wide text-cinder">
              {step.label}
            </p>
            <p className="mt-1 text-sm text-bone">{step.summary}</p>
            {step.span_id ? (
              <Link
                className="mt-2 inline-block font-mono text-[11px] text-copper underline"
                to={`/sessions/${detail.trace.trace_id}?span=${step.span_id}&tab=postmortem`}
              >
                Open span {step.span_id.slice(0, 12)}
              </Link>
            ) : null}
          </li>
        ))}
      </ol>
      {postmortem.span_links.length > 0 ? (
        <ul className="mt-4 flex flex-wrap gap-2">
          {postmortem.span_links.map((link) => (
            <li key={link.span_id}>
              <Link
                className="rounded-sm border border-quartz-vein px-2 py-1 font-mono text-[10px] text-bone"
                to={link.href}
              >
                {link.label}
              </Link>
            </li>
          ))}
        </ul>
      ) : null}
      <div className="mt-4">
        <p className="font-mono text-[10px] uppercase tracking-wide text-cinder">Uncertainty</p>
        <ul className="mt-1 list-disc space-y-1 pl-5 text-xs text-cinder">
          {postmortem.uncertainty.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      </div>
      <p className="mt-4 text-xs text-cinder">{postmortem.limitation}</p>
      <p className="mt-2 text-xs text-cinder">
        Optional reflector enhancement is not included and must stay explicitly opt-in and labeled.
      </p>
    </section>
  );
}
