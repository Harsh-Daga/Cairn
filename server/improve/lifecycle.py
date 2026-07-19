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
SNOOZE_DAYS = 14
_SEVERITY_RANK = {"info": 0, "suggestion": 1, "warning": 2, "error": 3}


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
        if state is not None:
            next_state = state.state
            snoozed_until = state.snoozed_until
            baseline = state.snooze_savings_baseline
            if state.state == "fixed" or (
                state.state == "muted" and _should_unsnooze(state, draft)
            ):
                next_state = "regressed"
                snoozed_until = None
                baseline = None
            InsightRepo.set_state(
                conn,
                InsightState(
                    insight_id=existing.insight_id,
                    state=next_state,
                    changed_at=now,
                    changed_by="system",
                    snoozed_until=snoozed_until,
                    snooze_savings_baseline=baseline,
                    see_count=int(state.see_count) + 1,
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
        InsightState(insight_id=insight.insight_id, state="new", changed_at=now, see_count=1),
    )
    return insight


def _should_unsnooze(state: InsightState, draft: InsightDraft) -> bool:
    """Unsnooze when severity worsens or savings estimate grows materially."""
    if state.snoozed_until and state.snoozed_until <= datetime.now(UTC).isoformat():
        return True
    baseline = state.snooze_savings_baseline
    if (
        baseline is not None
        and draft.savings_estimate is not None
        and float(draft.savings_estimate) > float(baseline) * 1.15 + 0.01
    ):
        return True
    _ = _SEVERITY_RANK  # reserved for future severity-delta unsnooze
    return False


def set_state(
    conn: sqlite3.Connection,
    insight_id: str,
    state: InsightLifecycle,
    *,
    changed_by: str | None = None,
) -> InsightState:
    """Transition insight lifecycle state."""
    now = datetime.now(UTC).isoformat()
    previous = InsightRepo.get_state(conn, insight_id)
    see_count = previous.see_count if previous is not None else 1
    row = InsightState(
        insight_id=insight_id,
        state=state,
        changed_at=now,
        changed_by=changed_by,
        snoozed_until=None if state != "muted" else (previous.snoozed_until if previous else None),
        snooze_savings_baseline=(
            None if state != "muted" else (previous.snooze_savings_baseline if previous else None)
        ),
        see_count=see_count,
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
