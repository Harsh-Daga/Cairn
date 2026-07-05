"""Git/test outcome capture (Phase 4)."""

from __future__ import annotations

import sqlite3
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from server.analyze.events import spans_to_events
from server.analyze.outcome_labels import derive_outcome_label
from server.analyze.outcome_tests import TestResult, run_tests, test_command_for
from server.analyze.views import IncrementalView, trace_input_hash
from server.analyze.waste import compute_waste
from server.models.outcome import Outcome
from server.store.repos.outcomes import OutcomeRepo
from server.store.repos.spans import SpanRepo
from server.store.repos.traces import TraceRepo

_GIT_TIMEOUT_SECONDS = 5
_CONTEXT_ROT_PENALTY = 1.0

_DEFAULT_QUALITY_WEIGHTS = {
    "success": 0.40,
    "efficiency": 0.25,
    "context_efficiency": 0.15,
    "stability": 0.10,
    "fingerprint_stability": 0.10,
}


@dataclass
class GitSignals:
    commit_landed: bool
    commit_sha: str | None
    files_changed: list[str] = field(default_factory=list)
    uncommitted: bool = False
    dirty: bool = False
    stashes: int = 0
    data_notes: list[str] = field(default_factory=list)


@dataclass
class QualityScore:
    score: float
    components: dict[str, float] = field(default_factory=dict)
    weights: dict[str, float] = field(default_factory=dict)


def agent_quality_score(
    *,
    commit_landed: bool,
    tests_passed: int | None,
    tests_failed: int | None,
    build_status: str | None,
    waste_tokens: int,
    total_tokens: int,
    peak_context_pct: float | None,
    context_rot_penalty: float,
    retry_rate: float,
    error_rate: float,
    mahalanobis_distance: float | None,
    drift_threshold: float | None,
    weights: dict[str, float] | None = None,
) -> QualityScore:
    """Compute outcomes quality score in the 0..100 range."""
    merged_weights = {**_DEFAULT_QUALITY_WEIGHTS, **(weights or {})}
    tests_unknown = (
        tests_passed is None and tests_failed is None and build_status in (None, "unknown")
    )
    success = (
        1.0
        if (commit_landed and (tests_unknown or (tests_passed or 0) > (tests_failed or 0)))
        else 0.0
    )
    efficiency = (
        1.0 - _clamp01(waste_tokens / max(1, total_tokens)) if total_tokens > 0 else 0.0
    )
    context_efficiency = (
        1.0 - _clamp01((peak_context_pct / 100.0) * context_rot_penalty)
        if peak_context_pct is not None
        else 0.0
    )
    stability = 1.0 - _clamp01(retry_rate + error_rate)
    if mahalanobis_distance is not None and drift_threshold:
        fingerprint_stability = 1.0 - _clamp01(mahalanobis_distance / drift_threshold)
    else:
        fingerprint_stability = 0.0
    components = {
        "success": success,
        "efficiency": efficiency,
        "context_efficiency": context_efficiency,
        "stability": stability,
        "fingerprint_stability": fingerprint_stability,
    }
    total = sum(merged_weights[name] * value for name, value in components.items())
    return QualityScore(score=round(total * 100, 2), components=components, weights=merged_weights)


def capture_git_signals(
    cwd: str | None,
    started_at: str | None,
    ended_at: str | None,
) -> GitSignals:
    """Inspect repo state for landed commits and local dirtiness."""
    if not cwd:
        return GitSignals(
            commit_landed=False,
            commit_sha=None,
            data_notes=["session has no cwd; git signals unknown"],
        )

    repo = Path(cwd)
    if not repo.is_dir():
        return GitSignals(
            commit_landed=False,
            commit_sha=None,
            data_notes=[f"cwd {cwd} is not a directory; git signals unknown"],
        )
    if not _is_git_repo(repo):
        return GitSignals(
            commit_landed=False,
            commit_sha=None,
            data_notes=[f"{cwd} is not a git repo; git signals unknown"],
        )

    notes: list[str] = []
    commits = _git_log(repo, started_at or "", _until_with_buffer(ended_at))
    commit_landed = bool(commits)
    commit_sha = commits[0] if commits else None
    files_changed = _files_for_commit(repo, commit_sha) if commit_sha else []
    dirty = _is_dirty(repo)
    stashes = _stash_count(repo)
    uncommitted = dirty or stashes > 0
    if not commit_landed and not uncommitted:
        notes.append("no commits and a clean tree: agent produced no landed or pending work")
    if uncommitted:
        notes.append("agent left uncommitted work (dirty tree or stashes)")
    return GitSignals(
        commit_landed=commit_landed,
        commit_sha=commit_sha,
        files_changed=files_changed,
        uncommitted=uncommitted,
        dirty=dirty,
        stashes=stashes,
        data_notes=notes,
    )


def _run_git(repo: Path, args: list[str]) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            args,
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def _is_git_repo(repo: Path) -> bool:
    result = _run_git(repo, ["git", "rev-parse", "--is-inside-work-tree"])
    return bool(result and result.returncode == 0 and result.stdout.strip() == "true")


def _git_log(repo: Path, since: str, until: str) -> list[str]:
    args = ["git", "log", "--format=%H"]
    if since:
        args.append(f"--since={since}")
    if until:
        args.append(f"--until={until}")
    result = _run_git(repo, args)
    if result is None or result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _files_for_commit(repo: Path, sha: str) -> list[str]:
    diff_result = _run_git(repo, ["git", "diff", "--stat", "--name-only", f"{sha}^", sha])
    if diff_result is not None and diff_result.returncode == 0:
        return [line.strip() for line in diff_result.stdout.splitlines() if line.strip()]
    show_result = _run_git(repo, ["git", "show", "--stat", "--name-only", "--format=", sha])
    if show_result is None:
        return []
    return [line.strip() for line in show_result.stdout.splitlines() if line.strip()]


def _is_dirty(repo: Path) -> bool:
    result = _run_git(repo, ["git", "status", "--porcelain"])
    return bool(result and result.returncode == 0 and result.stdout.strip())


def _stash_count(repo: Path) -> int:
    result = _run_git(repo, ["git", "stash", "list"])
    if result is None or result.returncode != 0:
        return 0
    return len([line for line in result.stdout.splitlines() if line.strip()])


def _until_with_buffer(ended_at: str | None) -> str:
    if not ended_at:
        return ""
    parsed = _parse_iso(ended_at)
    if parsed is None:
        return ended_at
    return (parsed + timedelta(hours=1)).isoformat()


def _parse_iso(timestamp: str) -> datetime | None:
    try:
        return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _run_tests_if_configured(cwd: str | None, project: str | None) -> TestResult:
    cmd = test_command_for(project)
    if not cmd:
        return TestResult(
            status="unknown",
            build_status="unknown",
            data_notes=[
                "configure test_command in ~/.cairn/config.toml to enable outcome tracking"
            ],
        )
    return run_tests(cwd, project)


def _retry_rate(events: list[dict[str, Any]]) -> float:
    waste = compute_waste(events, has_cost=False, peak_context_pct=None)
    retry = sum(
        1
        for _seq, category, _tokens in waste.tags
        if category in {"retry_loop", "blind_retry"}
    )
    tool_calls = sum(1 for event in events if event.get("type") == "tool_call")
    if tool_calls == 0:
        return 0.0
    return retry / tool_calls


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


class OutcomesView(IncrementalView):
    """Capture outcomes row per trace using git/test/session signals."""

    view_name = "outcomes"
    VERSION = 1

    def keys_for(self, trace_id: str) -> list[str]:
        return [trace_id]

    def input_hash_for(self, conn: sqlite3.Connection, key: str) -> str:
        return trace_input_hash(conn, key)

    def compute(self, conn: sqlite3.Connection, key: str) -> None:
        trace = TraceRepo.get(conn, key)
        if trace is None:
            return

        spans = SpanRepo.list_by_trace(conn, key)
        events = spans_to_events(spans)
        git = capture_git_signals(trace.cwd, trace.started_at, trace.ended_at)
        tests = _run_tests_if_configured(trace.cwd, trace.project)
        retry_rate = _retry_rate(events)
        tool_calls = trace.tool_calls or sum(
            1 for event in events if event.get("type") == "tool_call"
        )
        error_rate = (trace.tool_errors / tool_calls) if tool_calls else 0.0
        quality = agent_quality_score(
            commit_landed=git.commit_landed,
            tests_passed=tests.tests_passed,
            tests_failed=tests.tests_failed,
            build_status=tests.build_status,
            waste_tokens=int(trace.waste_tokens or 0),
            total_tokens=int(trace.input_tokens or 0) + int(trace.output_tokens or 0),
            peak_context_pct=trace.peak_context_pct,
            context_rot_penalty=_CONTEXT_ROT_PENALTY,
            retry_rate=retry_rate,
            error_rate=error_rate,
            mahalanobis_distance=None,
            drift_threshold=None,
        )
        outcome_label, label_source = derive_outcome_label(
            git_landed=git.commit_landed,
            tests_passed=tests.tests_passed,
            tests_failed=tests.tests_failed,
            status=str(trace.status or "completed"),
            events=events,
        )
        is_success = git.commit_landed and (
            tests.tests_passed is None or (tests.tests_passed or 0) > (tests.tests_failed or 0)
        )

        OutcomeRepo.upsert(
            conn,
            Outcome(
                trace_id=key,
                commit_sha=git.commit_sha,
                commit_landed=git.commit_landed,
                files_changed=git.files_changed,
                tests_run=tests.tests_run,
                tests_passed=tests.tests_passed,
                tests_failed=tests.tests_failed,
                build_status=tests.build_status,
                quality_score=quality.score,
                cost_per_success=float(trace.cost or 0.0) if is_success else None,
                outcome_label=outcome_label,
                label_source=label_source,
                captured_at=datetime.now(UTC).isoformat(),
            ),
        )


__all__ = ["OutcomesView", "capture_git_signals"]
