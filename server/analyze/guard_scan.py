"""Scan local git history for instruction-file edits (Guard)."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from server.analyze.git_local import is_dirty, is_git_repo, parse_iso, run_git
from server.export.scrub import scrub_text
from server.models.guard_event import GuardEvent, GuardEventKind, GuardGitState
from server.store.repos.experiments import ExperimentRepo
from server.store.repos.guard_events import GuardEventRepo

INSTRUCTION_PATHS = (
    "AGENTS.md",
    "CLAUDE.md",
    ".cursor/rules",
)
ASSOCIATION_WINDOW_DAYS = 7
MIN_ASSOCIATION_N = 5


@dataclass(frozen=True)
class GuardScanResult:
    scanned: int
    upserted: int
    git_state: GuardGitState
    notes: list[str]


def scan_instruction_events(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    repo_root: Path,
    since: str,
    until: str,
) -> GuardScanResult:
    """Persist scrubbed instruction-file events for the half-open [since, until) window."""
    now = datetime.now(UTC).isoformat()
    if not is_git_repo(repo_root):
        event = GuardEvent(
            event_id=_deterministic_id(workspace_id, "no_git", since),
            workspace_id=workspace_id,
            occurred_at=since,
            path_rel="(workspace)",
            event_kind="unavailable",
            git_state="no_git",
            source="git",
            confound_notes=["Workspace is not a git repository; Guard cannot observe history."],
            created_at=now,
        )
        GuardEventRepo.upsert(conn, event)
        return GuardScanResult(
            scanned=0,
            upserted=1,
            git_state="no_git",
            notes=list(event.confound_notes),
        )

    dirty = is_dirty(repo_root)
    git_state: GuardGitState = "dirty" if dirty else "clean"
    notes: list[str] = []
    if dirty:
        notes.append("Worktree is dirty; association windows may include uncommitted edits.")

    result = run_git(
        repo_root,
        [
            "git",
            "log",
            "--format=%H%x00%cI%x00%P%x00%s",
            f"--since={since}",
            f"--until={until}",
            "--",
            *INSTRUCTION_PATHS,
        ],
    )
    upserted = 0
    scanned = 0
    if result is None or result.returncode != 0:
        notes.append("git log for instruction paths failed or timed out.")
        return GuardScanResult(scanned=0, upserted=0, git_state=git_state, notes=notes)

    for line in result.stdout.splitlines():
        parts = line.split("\x00")
        if len(parts) < 4:
            continue
        sha, committed_at, parents, subject = parts[0], parts[1], parts[2], parts[3]
        scanned += 1
        parent_list = [p for p in parents.split() if p]
        paths = _paths_touched(repo_root, sha)
        for path_rel, status in paths:
            kind = _classify_kind(status=status, subject=subject, parents=parent_list)
            state = _git_state_for(kind=kind, dirty=dirty, parents=parent_list)
            before_hash, after_hash = _blob_hashes(repo_root, sha, path_rel)
            summary = _diff_summary(repo_root, sha, path_rel)
            linked = _link_experiment(conn, path_rel=path_rel, occurred_at=committed_at)
            event = GuardEvent(
                event_id=_deterministic_id(workspace_id, sha, path_rel),
                workspace_id=workspace_id,
                occurred_at=committed_at or since,
                path_rel=path_rel,
                event_kind=kind,
                commit_sha=sha,
                parent_sha=parent_list[0] if parent_list else None,
                before_hash=before_hash,
                after_hash=after_hash,
                diff_summary=scrub_text(summary, repo_root) if summary else None,
                git_state=state,
                source="git",
                confound_notes=list(notes),
                linked_experiment_id=linked,
                created_at=now,
            )
            GuardEventRepo.upsert(conn, event)
            upserted += 1
            if linked:
                _attach_experiment(conn, linked, event.event_id)

    if dirty:
        dirty_paths = _dirty_instruction_paths(repo_root)
        for path_rel in dirty_paths:
            event = GuardEvent(
                event_id=_deterministic_id(workspace_id, "dirty", path_rel, until[:10]),
                workspace_id=workspace_id,
                occurred_at=until,
                path_rel=path_rel,
                event_kind="dirty_snapshot",
                git_state="dirty",
                source="worktree",
                confound_notes=[
                    "Uncommitted instruction-file changes observed; not attributed to a commit."
                ],
                created_at=now,
            )
            GuardEventRepo.upsert(conn, event)
            upserted += 1

    return GuardScanResult(
        scanned=scanned,
        upserted=upserted,
        git_state=git_state,
        notes=notes,
    )


def _paths_touched(repo: Path, sha: str) -> list[tuple[str, str]]:
    result = run_git(repo, ["git", "diff-tree", "--no-commit-id", "--name-status", "-r", "-M", sha])
    if result is None or result.returncode != 0:
        return []
    out: list[tuple[str, str]] = []
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status, path = parts[0], parts[-1]
        if _is_instruction_path(path):
            out.append((path, status))
    return out


def _is_instruction_path(path: str) -> bool:
    normalized = path.replace("\\", "/")
    if normalized in {"AGENTS.md", "CLAUDE.md", ".cursor/rules"}:
        return True
    return normalized.startswith(".cursor/rules/")


def _classify_kind(*, status: str, subject: str, parents: list[str]) -> GuardEventKind:
    lowered = subject.strip().lower()
    if lowered.startswith("revert") or "this reverts commit" in lowered:
        return "revert"
    if len(parents) > 1:
        return "merge"
    if status.startswith("R"):
        return "rename"
    return "edit"


def _git_state_for(*, kind: GuardEventKind, dirty: bool, parents: list[str]) -> GuardGitState:
    if kind == "rename":
        return "rename"
    if kind == "merge" or len(parents) > 1:
        return "merge"
    if dirty:
        return "dirty"
    return "clean"


def _blob_hashes(repo: Path, sha: str, path_rel: str) -> tuple[str | None, str | None]:
    after = run_git(repo, ["git", "rev-parse", f"{sha}:{path_rel}"])
    after_hash = (
        after.stdout.strip()
        if after is not None and after.returncode == 0 and after.stdout.strip()
        else None
    )
    before = run_git(repo, ["git", "rev-parse", f"{sha}^:{path_rel}"])
    before_hash = (
        before.stdout.strip()
        if before is not None and before.returncode == 0 and before.stdout.strip()
        else None
    )
    return before_hash, after_hash


def _diff_summary(repo: Path, sha: str, path_rel: str) -> str:
    result = run_git(
        repo,
        ["git", "show", "--stat", "--format=%s", sha, "--", path_rel],
    )
    if result is None or result.returncode != 0:
        return f"Instruction file change in {path_rel}"
    text = " ".join(result.stdout.split())
    return text[:500] if text else f"Instruction file change in {path_rel}"


def _dirty_instruction_paths(repo: Path) -> list[str]:
    result = run_git(repo, ["git", "status", "--porcelain", "--", *INSTRUCTION_PATHS])
    if result is None or result.returncode != 0:
        return []
    paths: list[str] = []
    for line in result.stdout.splitlines():
        if len(line) < 4:
            continue
        path = line[3:].strip().split(" -> ")[-1]
        if _is_instruction_path(path):
            paths.append(path)
    return paths


def _link_experiment(conn: sqlite3.Connection, *, path_rel: str, occurred_at: str) -> str | None:
    occurred = parse_iso(occurred_at)
    if occurred is None:
        return None
    window_start = (occurred - timedelta(days=2)).isoformat()
    window_end = (occurred + timedelta(days=2)).isoformat()
    for experiment in ExperimentRepo.list_all(conn, limit=200):
        if experiment.target_file != path_rel:
            continue
        applied = experiment.applied_at
        if not applied:
            continue
        if window_start <= applied < window_end:
            return experiment.experiment_id
    return None


def _attach_experiment(conn: sqlite3.Connection, experiment_id: str, event_id: str) -> None:
    experiment = ExperimentRepo.get(conn, experiment_id)
    if experiment is None or experiment.guard_event_id:
        return
    ExperimentRepo.update(conn, experiment.model_copy(update={"guard_event_id": event_id}))


def _deterministic_id(*parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:26]
    return f"grd_{digest}"


def association_windows(
    occurred_at: str,
    *,
    window_days: int = ASSOCIATION_WINDOW_DAYS,
) -> tuple[str, str, str] | None:
    """Return (pre_start, event_at, post_end); event_at splits pre/post half-open windows."""
    occurred = parse_iso(occurred_at)
    if occurred is None:
        return None
    pre_start = (occurred - timedelta(days=window_days)).isoformat()
    event_at = occurred.isoformat()
    post_end = (occurred + timedelta(days=window_days)).isoformat()
    return pre_start, event_at, post_end
