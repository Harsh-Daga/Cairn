"""Deterministic narrative headlines — Phase S."""

from __future__ import annotations

from typing import Any


def _money(value: Any) -> str:
    try:
        return f"${float(value):.2f}"
    except (TypeError, ValueError):
        return f"${value}"


def _waste_pct(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return f"{float(value):.0f}"
    except (TypeError, ValueError):
        return str(value)


def overview_narrative(payload: dict[str, Any]) -> dict[str, Any]:
    """Plain-English hero from overview/diagnostics/normalized data."""
    spend = payload.get("spend")
    waste = payload.get("waste")
    diagnostics = payload.get("diagnostics_summary") or {}
    failed = int(diagnostics.get("failed_sessions") or 0)
    cascade = int(diagnostics.get("cascade_sessions") or 0)
    optim = payload.get("optimization_ready")

    parts: list[str] = []
    if spend is not None and waste is not None:
        pct = waste.get("pct") if isinstance(waste, dict) else None
        if pct is not None:
            parts.append(
                f"This period you spent {_money(spend)}; ~{_waste_pct(pct)}% looks avoidable."
            )
        else:
            parts.append(f"This period you spent {_money(spend)}.")
    elif spend is not None:
        parts.append(f"This period you spent {_money(spend)}.")
    else:
        parts.append("Spend data is incomplete — see confidence chips.")

    if failed:
        parts.append(f"{failed} session(s) did not land cleanly.")
    if cascade:
        parts.append(f"{cascade} had error cascades worth investigating.")

    cta = "Review insights"
    if optim:
        cta = "Apply the top optimization"

    return {
        "headline": " ".join(parts) if parts else "No sessions in range yet.",
        "cta": cta,
        "cta_href": "#insights" if not optim else "#optimizations",
        "sentences": [{"text": p, "href": "#sessions"} for p in parts],
    }


def session_narrative(diag: dict[str, Any], normalized: dict[str, Any]) -> str:
    """One-line session autopsy summary."""
    label = diag.get("outcome_label") or "unknown"
    primary = diag.get("primary_category")
    expected = normalized.get("label")
    chunks = [f"Outcome: {label.replace('_', ' ')}."]
    if primary:
        chunks.append(f"Primary failure: {primary.replace('_', ' ')}.")
    if expected:
        chunks.append(expected + ".")
    savings = diag.get("ideal_path_savings_tokens")
    if savings and int(savings) > 0:
        chunks.append(f"~{int(savings):,} tokens recoverable via shorter read path.")
    return " ".join(chunks)
