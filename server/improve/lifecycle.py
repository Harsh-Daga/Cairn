"""Insight lifecycle: new/ack/fixed/regressed/muted with fingerprint dedupe."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

from server.improve.evidence import InsightDraft, build_evidence
from server.models.insight import Insight, InsightLifecycle, InsightState
from server.store.repos.evidence import EvidenceRepo
from server.store.repos.insights import InsightRepo
from server.util.ids import new_ulid

DETECTOR_VERSION = 1
FIXED_ABSENCE_DAYS = 14


def upsert_insight(conn: sqlite3.Connection, draft: InsightDraft) -> Insight:
    """Insert or refresh an insight keyed by fingerprint."""
    now = datetime.now(UTC).isoformat()
    existing = InsightRepo.get_by_fingerprint(conn, draft.fingerprint)
    evidence = build_evidence(draft)
    EvidenceRepo.create(conn, evidence)

    if existing is not None:
        updated = existing.model_copy(
            update={
                "title": draft.title,
                "body": draft.body,
                "severity": draft.severity,
                "evidence_id": evidence.evidence_id,
                "savings_estimate": draft.savings_estimate,
                "savings_ci": draft.savings_ci,
                "action": draft.action,
                "last_seen_at": now,
                "detector_version": draft.detector_version,
            }
        )
        InsightRepo.update(conn, updated)
        state = InsightRepo.get_state(conn, existing.insight_id)
        if state is not None and state.state == "fixed":
            InsightRepo.set_state(
                conn,
                InsightState(
                    insight_id=existing.insight_id,
                    state="regressed",
                    changed_at=now,
                    changed_by="system",
                ),
            )
        return updated

    insight = Insight(
        insight_id=new_ulid(),
        fingerprint=draft.fingerprint,
        detector=draft.detector,
        detector_version=draft.detector_version,
        severity=draft.severity,
        title=draft.title,
        body=draft.body,
        evidence_id=evidence.evidence_id,
        savings_estimate=draft.savings_estimate,
        savings_ci=draft.savings_ci,
        action=draft.action,
        created_at=now,
        last_seen_at=now,
    )
    InsightRepo.create(conn, insight)
    InsightRepo.create_state(
        conn,
        InsightState(insight_id=insight.insight_id, state="new", changed_at=now),
    )
    return insight


def set_state(
    conn: sqlite3.Connection,
    insight_id: str,
    state: InsightLifecycle,
    *,
    changed_by: str | None = None,
) -> InsightState:
    """Transition insight lifecycle state."""
    now = datetime.now(UTC).isoformat()
    row = InsightState(
        insight_id=insight_id,
        state=state,
        changed_at=now,
        changed_by=changed_by,
    )
    InsightRepo.set_state(conn, row)
    return row


def mark_stale_fixed(conn: sqlite3.Connection, active_fingerprints: set[str]) -> list[str]:
    """Acknowledged insights absent for 14d become fixed."""
    cutoff = (datetime.now(UTC) - timedelta(days=FIXED_ABSENCE_DAYS)).isoformat()
    fixed: list[str] = []
    rows = InsightRepo.list_by_state(conn, "ack", limit=500)
    for row in rows:
        if row.insight.fingerprint in active_fingerprints:
            continue
        if row.insight.last_seen_at >= cutoff:
            continue
        set_state(conn, row.insight.insight_id, "fixed", changed_by="system")
        fixed.append(row.insight.insight_id)
    return fixed
