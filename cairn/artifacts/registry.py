"""Artifact registry with lineage queries."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from cairn.graph.engine import build_artifact_graph
from cairn.ledger.schema import migrate
from cairn.ledger.storage import (
    get_artifact,
    list_artifacts_for_run,
    list_lineage_edges,
    record_lineage_edge,
    register_artifact,
)
from cairn.model.artifact import Artifact, FileArtifact, LineageEdge


class ArtifactRegistry:
    """Register and query project artifacts backed by ledger + CAS."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        cairn_dir = self.project_root / ".cairn"
        cairn_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = cairn_dir / "ledger.db"
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        migrate(self._conn)

    @property
    def connection(self) -> sqlite3.Connection:
        return self._conn

    def close(self) -> None:
        self._conn.close()

    def register(self, artifact: Artifact) -> Artifact:
        return register_artifact(self._conn, artifact)

    def get(self, content_hash: str) -> Artifact | None:
        return get_artifact(self._conn, content_hash)

    def list_for_run(self, run_id: str) -> list[Artifact]:
        return list_artifacts_for_run(self._conn, run_id)

    def link(self, edge: LineageEdge, *, run_id: str | None = None) -> LineageEdge:
        return record_lineage_edge(self._conn, edge, run_id=run_id)

    def lineage(self, content_hash: str) -> list[LineageEdge]:
        return list_lineage_edges(self._conn, from_id=content_hash)

    def lineage_graph(self, artifacts: list[Artifact]) -> dict[str, object]:
        edges = []
        for artifact in artifacts:
            edges.extend(self.lineage(artifact.content_hash))
        return build_artifact_graph(artifacts, edges)

    def register_file_artifact(
        self,
        file_artifact: FileArtifact,
        *,
        run_id: str,
        session_id: str,
    ) -> Artifact:
        artifact = file_artifact.to_artifact(run_id, session_id)
        registered = self.register(artifact)
        if file_artifact.before_hash:
            self.link(
                LineageEdge("read", registered.content_hash, file_artifact.before_hash),
                run_id=run_id,
            )
        return registered

    def sync_capture_run(
        self,
        run_id: str,
        session_id: str,
        files: list[dict[str, object]],
    ) -> list[Artifact]:
        """Register file artifacts from capture ingest rows."""
        registered: list[Artifact] = []
        for row in files:
            path_rel = row.get("path_rel")
            if not isinstance(path_rel, str):
                continue
            before_hash = str(row["before_hash"]) if row.get("before_hash") else None
            after_hash = str(row["after_hash"]) if row.get("after_hash") else None
            if not before_hash and not after_hash:
                continue
            first_seq = row.get("first_seq", 0)
            last_seq = row.get("last_seq", 0)
            fa = FileArtifact(
                path_rel=path_rel,
                before_hash=before_hash,
                after_hash=after_hash,
                first_seq=first_seq if isinstance(first_seq, int) else 0,
                last_seq=last_seq if isinstance(last_seq, int) else 0,
            )
            registered.append(
                self.register_file_artifact(fa, run_id=run_id, session_id=session_id)
            )
        return registered
