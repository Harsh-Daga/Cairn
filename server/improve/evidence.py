"""EvidencePack builder for detector outputs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, cast

from server.models.evidence import Evidence
from server.models.insight import InsightSeverity
from server.util.ids import new_ulid


@dataclass(frozen=True)
class InsightDraft:
    """Detector output before persistence."""

    fingerprint: str
    detector: str
    detector_version: int
    severity: InsightSeverity
    title: str
    body: str
    trace_ids: list[str] = field(default_factory=list)
    span_ids: list[str] | None = None
    metrics: dict[str, object] = field(default_factory=dict)
    savings_estimate: float | None = None
    savings_ci: dict[str, object] | None = None
    action: str | None = None


def build_evidence(draft: InsightDraft) -> Evidence:
    """Create a provenance record from a detector draft."""
    producer = f"detector:{draft.detector}@{draft.detector_version}"
    return Evidence(
        evidence_id=new_ulid(),
        producer=producer,
        produced_at=datetime.now(UTC).isoformat(),
        trace_ids=draft.trace_ids,
        span_ids=draft.span_ids,
        metrics=draft.metrics,
    )


def draft_from_legacy(rule_id: str, legacy: Any, *, detector_version: int = 1) -> InsightDraft:
    """Map a legacy rules.Insight to InsightDraft."""
    evidence = getattr(legacy, "evidence", {}) or {}
    trace_ids: list[str] = []
    if run_id := evidence.get("run_id"):
        trace_ids.append(str(run_id))
    if run_ids := evidence.get("run_ids"):
        trace_ids.extend(str(r) for r in run_ids)
    savings = getattr(legacy, "savings_estimate", None)
    fix_payload = getattr(legacy, "fix", None)
    contract = {
        "savings_unavailable_reason": getattr(legacy, "savings_unavailable_reason", None),
        "fix": fix_payload.as_dict() if fix_payload is not None else None,
        "diagnostic": bool(getattr(legacy, "diagnostic", False)),
    }
    ci = None
    if savings is not None and savings > 0:
        ci = {"low": round(savings * 0.5, 2), "high": round(savings * 1.5, 2)}
    return InsightDraft(
        fingerprint=f"{rule_id}",
        detector=rule_id,
        detector_version=detector_version,
        severity=cast(InsightSeverity, getattr(legacy, "severity", "info")),
        title=str(getattr(legacy, "title", "")),
        body=str(getattr(legacy, "body", "")),
        trace_ids=trace_ids,
        metrics={**dict(evidence), "insight_contract": contract},
        savings_estimate=savings,
        savings_ci=ci,
        action=getattr(legacy, "action", None),
    )
