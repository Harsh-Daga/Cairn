"""Task difficulty estimation — Phase B."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

_HARD_SIGNALS = re.compile(
    r"\b(migration|concurrent|mutex|async|thread|docker|kubernetes|terraform|"
    r"build\.gradle|Cargo\.toml|pyproject\.toml|package\.json)\b",
    re.I,
)
_FILE_REF = re.compile(r"[\w./-]+\.(py|ts|tsx|js|go|rs|java|md|toml|yaml|yml|json)\b", re.I)

_BUCKETS = (
    (0.25, "trivial"),
    (0.50, "standard"),
    (0.75, "hard"),
    (1.01, "epic"),
)


@dataclass
class DifficultyScore:
    difficulty: float
    bucket: str
    features: dict[str, Any] = field(default_factory=dict)
    data_notes: list[str] = field(default_factory=list)


def estimate_difficulty(
    run: dict[str, Any],
    events: list[dict[str, Any]],
) -> DifficultyScore:
    """Deterministic difficulty from prompt complexity, files, diff spread, hard signals."""
    notes: list[str] = []
    user_texts = [
        str(e.get("text_inline") or "")
        for e in events
        if e.get("type") == "user_prompt" and e.get("text_inline")
    ]
    prompt = " ".join(user_texts)
    prompt_len = len(prompt)
    file_refs = len(set(_FILE_REF.findall(prompt)))
    paths_edited = {
        str(e.get("path_rel"))
        for e in events
        if e.get("tool_norm_name") == "edit" and e.get("path_rel")
    }
    paths_read = {
        str(e.get("path_rel"))
        for e in events
        if e.get("tool_norm_name") in ("read", "search") and e.get("path_rel")
    }
    subsystems = len({p.split("/")[0] for p in paths_edited | paths_read if "/" in p})
    tool_calls = sum(1 for e in events if e.get("type") == "tool_call")
    tool_errors = sum(1 for e in events if e.get("tool_is_error"))
    hard_hits = len(_HARD_SIGNALS.findall(prompt))
    total_tokens = int(run.get("total_input_tokens") or 0) + int(
        run.get("total_output_tokens") or 0
    )

    features = {
        "prompt_chars": prompt_len,
        "file_refs_in_prompt": file_refs,
        "files_edited": len(paths_edited),
        "files_read": len(paths_read),
        "path_spread": len(paths_edited | paths_read),
        "subsystems": subsystems,
        "tool_calls": tool_calls,
        "tool_errors": tool_errors,
        "hard_signals": hard_hits,
        "total_tokens": total_tokens,
    }

    # Weighted 0–1 score (deterministic; no fabricated precision).
    score = 0.0
    score += min(prompt_len / 2000.0, 0.25)
    score += min(file_refs / 10.0, 0.15)
    score += min(len(paths_edited) / 8.0, 0.20)
    score += min(subsystems / 5.0, 0.15)
    score += min(hard_hits / 3.0, 0.15)
    score += min(tool_calls / 40.0, 0.10)
    score = round(min(max(score, 0.0), 1.0), 4)

    bucket = "standard"
    for threshold, name in _BUCKETS:
        if score < threshold:
            bucket = name
            break

    if not prompt:
        notes.append("no user prompt text; difficulty from structural features only")

    return DifficultyScore(difficulty=score, bucket=bucket, features=features, data_notes=notes)


def features_json(score: DifficultyScore) -> str:
    return json.dumps(score.features, sort_keys=True)
