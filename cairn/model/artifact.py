"""First-class artifact and lineage types (charter §5, Phase 3)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

ArtifactKind = Literal[
    "file",
    "report",
    "summary",
    "document",
    "code",
    "image",
    "trajectory",
    "bundle",
    "other",
]

LineageRelation = Literal[
    "produced_by",
    "derived_from",
    "read",
    "wrote",
    "invoked",
    "depends_on",
]


@dataclass(frozen=True)
class LineageEdge:
    """Directed relationship between artifacts, runs, or context assets."""

    relation: LineageRelation
    from_id: str
    to_id: str
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class Artifact:
    """A generated or captured output stored in CAS with registry metadata."""

    content_hash: str
    kind: ArtifactKind
    path_rel: str | None
    mime: str | None
    run_id: str | None
    session_id: str | None
    size_bytes: int | None
    metadata: dict[str, Any]

    @property
    def artifact_id(self) -> str:
        return self.content_hash

    def to_dict(self) -> dict[str, Any]:
        return {
            "content_hash": self.content_hash,
            "artifact_id": self.artifact_id,
            "kind": self.kind,
            "path_rel": self.path_rel,
            "mime": self.mime,
            "run_id": self.run_id,
            "session_id": self.session_id,
            "size_bytes": self.size_bytes,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class FileArtifact:
    """Repo-relative file touched during capture (maps to ledger file_artifacts)."""

    path_rel: str
    before_hash: str | None
    after_hash: str | None
    first_seq: int
    last_seq: int

    def snapshot_quality(self) -> Literal["exact", "inferred", "partial"]:
        if self.before_hash and self.after_hash:
            return "exact"
        if self.after_hash or self.before_hash:
            return "partial"
        return "inferred"

    def to_artifact(self, run_id: str, session_id: str) -> Artifact:
        content_hash = self.after_hash or self.before_hash or ""
        return Artifact(
            content_hash=content_hash,
            kind="file",
            path_rel=self.path_rel,
            mime=None,
            run_id=run_id,
            session_id=session_id,
            size_bytes=None,
            metadata={
                "before_hash": self.before_hash,
                "after_hash": self.after_hash,
                "snapshot_quality": self.snapshot_quality(),
                "first_seq": self.first_seq,
                "last_seq": self.last_seq,
            },
        )
