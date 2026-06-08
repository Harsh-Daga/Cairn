"""Storage layer: artifacts, context assets, workflow runs, lineage (Phase 4)."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime

from cairn.model.artifact import Artifact, LineageEdge
from cairn.model.workflow import WorkflowRun


@dataclass(frozen=True)
class ContextAssetRecord:
    path_rel: str
    content_hash: str
    mime: str | None
    git_blob: str | None
    tags: tuple[str, ...]
    updated_at: str


def _now() -> str:
    return datetime.now(UTC).isoformat()


def upsert_context_asset(
    conn: sqlite3.Connection,
    *,
    path_rel: str,
    content_hash: str,
    mime: str | None = None,
    git_blob: str | None = None,
    tags: tuple[str, ...] = (),
) -> ContextAssetRecord:
    now = _now()
    conn.execute(
        """
        INSERT INTO context_assets (path_rel, content_hash, mime, git_blob, tags_json, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(path_rel) DO UPDATE SET
          content_hash = excluded.content_hash,
          mime = excluded.mime,
          git_blob = excluded.git_blob,
          tags_json = excluded.tags_json,
          updated_at = excluded.updated_at
        """,
        (path_rel, content_hash, mime, git_blob, json.dumps(list(tags)), now),
    )
    conn.commit()
    return ContextAssetRecord(
        path_rel=path_rel,
        content_hash=content_hash,
        mime=mime,
        git_blob=git_blob,
        tags=tags,
        updated_at=now,
    )


def list_context_assets(conn: sqlite3.Connection) -> list[ContextAssetRecord]:
    rows = conn.execute(
        "SELECT path_rel, content_hash, mime, git_blob, tags_json, updated_at "
        "FROM context_assets ORDER BY path_rel"
    ).fetchall()
    return [_row_to_context_asset(row) for row in rows]


def register_artifact(conn: sqlite3.Connection, artifact: Artifact) -> Artifact:
    now = _now()
    conn.execute(
        """
        INSERT INTO artifacts (
          content_hash, kind, path_rel, mime, run_id, session_id,
          size_bytes, metadata_json, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(content_hash) DO UPDATE SET
          kind = excluded.kind,
          path_rel = COALESCE(excluded.path_rel, artifacts.path_rel),
          mime = COALESCE(excluded.mime, artifacts.mime),
          run_id = COALESCE(excluded.run_id, artifacts.run_id),
          session_id = COALESCE(excluded.session_id, artifacts.session_id),
          size_bytes = COALESCE(excluded.size_bytes, artifacts.size_bytes),
          metadata_json = excluded.metadata_json
        """,
        (
            artifact.content_hash,
            artifact.kind,
            artifact.path_rel,
            artifact.mime,
            artifact.run_id,
            artifact.session_id,
            artifact.size_bytes,
            json.dumps(artifact.metadata),
            now,
        ),
    )
    conn.commit()
    return artifact


def get_artifact(conn: sqlite3.Connection, content_hash: str) -> Artifact | None:
    row = conn.execute(
        """
        SELECT content_hash, kind, path_rel, mime, run_id, session_id,
               size_bytes, metadata_json
        FROM artifacts WHERE content_hash = ?
        """,
        (content_hash,),
    ).fetchone()
    if row is None:
        return None
    return _row_to_artifact(row)


def list_artifacts_for_run(conn: sqlite3.Connection, run_id: str) -> list[Artifact]:
    rows = conn.execute(
        """
        SELECT content_hash, kind, path_rel, mime, run_id, session_id,
               size_bytes, metadata_json
        FROM artifacts WHERE run_id = ? ORDER BY created_at
        """,
        (run_id,),
    ).fetchall()
    return [_row_to_artifact(row) for row in rows]


def record_workflow_run(conn: sqlite3.Connection, workflow_run: WorkflowRun) -> WorkflowRun:
    conn.execute(
        """
        INSERT INTO workflow_runs (run_id, workflow_ref, context_digest, git_commit, created_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(run_id) DO UPDATE SET
          workflow_ref = excluded.workflow_ref,
          context_digest = excluded.context_digest,
          git_commit = excluded.git_commit
        """,
        (
            workflow_run.run_id,
            workflow_run.workflow_ref,
            workflow_run.context_digest,
            workflow_run.git_commit,
            _now(),
        ),
    )
    conn.commit()
    return workflow_run


def list_workflow_runs(
    conn: sqlite3.Connection,
    *,
    limit: int = 20,
) -> list[WorkflowRun]:
    rows = conn.execute(
        """
        SELECT run_id, workflow_ref, context_digest, git_commit
        FROM workflow_runs
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [
        WorkflowRun(
            run_id=str(row[0]),
            workflow_ref=str(row[1]),
            context_digest=str(row[2]),
            git_commit=str(row[3]) if row[3] is not None else None,
        )
        for row in rows
    ]


def get_workflow_run(conn: sqlite3.Connection, run_id: str) -> WorkflowRun | None:
    row = conn.execute(
        """
        SELECT run_id, workflow_ref, context_digest, git_commit
        FROM workflow_runs WHERE run_id = ?
        """,
        (run_id,),
    ).fetchone()
    if row is None:
        return None
    return WorkflowRun(
        run_id=str(row[0]),
        workflow_ref=str(row[1]),
        context_digest=str(row[2]),
        git_commit=str(row[3]) if row[3] is not None else None,
    )


def record_lineage_edge(
    conn: sqlite3.Connection,
    edge: LineageEdge,
    *,
    run_id: str | None = None,
) -> LineageEdge:
    conn.execute(
        """
        INSERT INTO lineage_edges (relation, from_id, to_id, metadata_json, run_id)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            edge.relation,
            edge.from_id,
            edge.to_id,
            json.dumps(edge.metadata or {}),
            run_id,
        ),
    )
    conn.commit()
    return edge


def list_lineage_edges(
    conn: sqlite3.Connection,
    *,
    run_id: str | None = None,
    from_id: str | None = None,
) -> list[LineageEdge]:
    if run_id is not None:
        rows = conn.execute(
            """
            SELECT relation, from_id, to_id, metadata_json
            FROM lineage_edges WHERE run_id = ? ORDER BY edge_id
            """,
            (run_id,),
        ).fetchall()
    elif from_id is not None:
        rows = conn.execute(
            """
            SELECT relation, from_id, to_id, metadata_json
            FROM lineage_edges WHERE from_id = ? ORDER BY edge_id
            """,
            (from_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT relation, from_id, to_id, metadata_json
            FROM lineage_edges ORDER BY edge_id
            """
        ).fetchall()
    return [_row_to_lineage_edge(row) for row in rows]


def _row_to_context_asset(row: sqlite3.Row) -> ContextAssetRecord:
    tags_raw = json.loads(str(row["tags_json"]))
    tags = tuple(str(t) for t in tags_raw) if isinstance(tags_raw, list) else ()
    return ContextAssetRecord(
        path_rel=str(row["path_rel"]),
        content_hash=str(row["content_hash"]),
        mime=str(row["mime"]) if row["mime"] is not None else None,
        git_blob=str(row["git_blob"]) if row["git_blob"] is not None else None,
        tags=tags,
        updated_at=str(row["updated_at"]),
    )


def _row_to_artifact(row: sqlite3.Row) -> Artifact:
    metadata_raw = json.loads(str(row["metadata_json"]))
    metadata = metadata_raw if isinstance(metadata_raw, dict) else {}
    return Artifact(
        content_hash=str(row["content_hash"]),
        kind=str(row["kind"]),  # type: ignore[arg-type]
        path_rel=str(row["path_rel"]) if row["path_rel"] is not None else None,
        mime=str(row["mime"]) if row["mime"] is not None else None,
        run_id=str(row["run_id"]) if row["run_id"] is not None else None,
        session_id=str(row["session_id"]) if row["session_id"] is not None else None,
        size_bytes=int(row["size_bytes"]) if row["size_bytes"] is not None else None,
        metadata=metadata,
    )


def _row_to_lineage_edge(row: sqlite3.Row) -> LineageEdge:
    metadata_raw = json.loads(str(row["metadata_json"]))
    metadata = metadata_raw if isinstance(metadata_raw, dict) else {}
    return LineageEdge(
        relation=str(row["relation"]),  # type: ignore[arg-type]
        from_id=str(row["from_id"]),
        to_id=str(row["to_id"]),
        metadata=metadata,
    )


@dataclass(frozen=True)
class PromptRecord:
    name: str
    version: str
    path_rel: str
    content_hash: str
    body_cas_hash: str
    model_override: str | None
    params: dict[str, object]
    description: str | None
    created_at: str
    deprecated: bool

    @property
    def prompt_ref(self) -> str:
        return f"{self.name}@{self.version}"


def register_prompt(
    conn: sqlite3.Connection,
    *,
    name: str,
    version: str,
    path_rel: str,
    content_hash: str,
    body_cas_hash: str,
    model_override: str | None = None,
    params: dict[str, object] | None = None,
    description: str | None = None,
) -> PromptRecord:
    now = _now()
    conn.execute(
        """
        INSERT INTO prompt_registry (
          name, version, path_rel, content_hash, body_cas_hash,
          model_override, params_json, description, created_at, deprecated
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        """,
        (
            name,
            version,
            path_rel,
            content_hash,
            body_cas_hash,
            model_override,
            json.dumps(params or {}),
            description,
            now,
        ),
    )
    conn.commit()
    return PromptRecord(
        name=name,
        version=version,
        path_rel=path_rel,
        content_hash=content_hash,
        body_cas_hash=body_cas_hash,
        model_override=model_override,
        params=params or {},
        description=description,
        created_at=now,
        deprecated=False,
    )


def get_prompt(
    conn: sqlite3.Connection,
    name: str,
    version: str | None = None,
) -> PromptRecord | None:
    if version is None:
        row = conn.execute(
            """
            SELECT name, version, path_rel, content_hash, body_cas_hash,
                   model_override, params_json, description, created_at, deprecated
            FROM prompt_registry
            WHERE name = ?
            ORDER BY version DESC
            LIMIT 1
            """,
            (name,),
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT name, version, path_rel, content_hash, body_cas_hash,
                   model_override, params_json, description, created_at, deprecated
            FROM prompt_registry WHERE name = ? AND version = ?
            """,
            (name, version),
        ).fetchone()
    if row is None:
        return None
    return _row_to_prompt(row)


def list_prompts(conn: sqlite3.Connection) -> list[PromptRecord]:
    rows = conn.execute(
        """
        SELECT name, version, path_rel, content_hash, body_cas_hash,
               model_override, params_json, description, created_at, deprecated
        FROM prompt_registry
        ORDER BY name, version
        """
    ).fetchall()
    return [_row_to_prompt(row) for row in rows]


def link_prompt_ref(
    conn: sqlite3.Connection,
    *,
    workflow_ref: str,
    prompt_name: str,
    prompt_version: str,
) -> None:
    conn.execute(
        """
        INSERT INTO prompt_refs (workflow_ref, prompt_name, prompt_version)
        VALUES (?, ?, ?)
        ON CONFLICT(workflow_ref, prompt_name) DO UPDATE SET
          prompt_version = excluded.prompt_version
        """,
        (workflow_ref, prompt_name, prompt_version),
    )
    conn.commit()


def _row_to_prompt(row: sqlite3.Row) -> PromptRecord:
    params_raw = json.loads(str(row["params_json"]))
    params = params_raw if isinstance(params_raw, dict) else {}
    return PromptRecord(
        name=str(row["name"]),
        version=str(row["version"]),
        path_rel=str(row["path_rel"]),
        content_hash=str(row["content_hash"]),
        body_cas_hash=str(row["body_cas_hash"]),
        model_override=str(row["model_override"]) if row["model_override"] is not None else None,
        params={str(k): v for k, v in params.items()},
        description=str(row["description"]) if row["description"] is not None else None,
        created_at=str(row["created_at"]),
        deprecated=bool(row["deprecated"]),
    )

