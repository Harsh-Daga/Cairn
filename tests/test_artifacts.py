"""Tests for artifact registry and capture sync."""

from __future__ import annotations

from pathlib import Path

from cairn.artifacts.registry import ArtifactRegistry
from cairn.ingest.parsers.claude_code import parse_jsonl_file
from cairn.ingest.writer import CaptureWriter
from cairn.model.artifact import Artifact, FileArtifact, LineageEdge

FIXTURE = Path(__file__).parent / "fixtures" / "ingest" / "claude_code_mini.jsonl"


def test_register_file_artifact_and_lineage(tmp_path: Path) -> None:
    registry = ArtifactRegistry(tmp_path)
    try:
        parent = registry.register_file_artifact(
            FileArtifact(
                path_rel="src/main.py",
                before_hash="aaa",
                after_hash="bbb",
                first_seq=1,
                last_seq=5,
            ),
            run_id="run-1",
            session_id="sess-1",
        )
        child = registry.register_file_artifact(
            FileArtifact(
                path_rel="src/main.py",
                before_hash="bbb",
                after_hash="ccc",
                first_seq=6,
                last_seq=8,
            ),
            run_id="run-2",
            session_id="sess-2",
        )
        registry.link(
            LineageEdge("derived_from", child.content_hash, parent.content_hash),
            run_id="run-2",
        )

        listed = registry.list_for_run("run-1")
        assert len(listed) == 1
        assert listed[0].path_rel == "src/main.py"

        edges = registry.lineage(child.content_hash)
        assert any(e.relation == "derived_from" for e in edges)

        graph = registry.lineage_graph(registry.list_for_run("run-2"))
        assert graph["graph_kind"] == "artifact"
        assert len(graph["nodes"]) >= 1
    finally:
        registry.close()


def test_sync_capture_run(tmp_path: Path) -> None:
    registry = ArtifactRegistry(tmp_path)
    try:
        registered = registry.sync_capture_run(
            "run-x",
            "sess-x",
            [
                {
                    "path_rel": "a.txt",
                    "before_hash": None,
                    "after_hash": "hash-a",
                    "first_seq": 1,
                    "last_seq": 2,
                },
                {
                    "path_rel": "b.txt",
                    "before_hash": None,
                    "after_hash": "hash-b",
                    "first_seq": 3,
                    "last_seq": 4,
                },
            ],
        )
        assert len(registered) == 2
        assert {a.content_hash for a in registered} == {"hash-a", "hash-b"}
        assert len(registry.list_for_run("run-x")) == 2
    finally:
        registry.close()


def test_ingest_sync_skips_files_without_hashes(tmp_path: Path) -> None:
    repo = tmp_path / "proj"
    repo.mkdir()
    (repo / "src").mkdir()
    parsed = parse_jsonl_file(FIXTURE, repo_root=repo)
    assert parsed is not None

    writer = CaptureWriter(repo)
    try:
        result = writer.ingest_claude_session(parsed)
        registry = ArtifactRegistry(repo)
        try:
            assert registry.list_for_run(result.run_id) == []
        finally:
            registry.close()
    finally:
        writer.close()


def test_register_artifact_round_trip(tmp_path: Path) -> None:
    registry = ArtifactRegistry(tmp_path)
    try:
        artifact = Artifact(
            content_hash="report-hash",
            kind="report",
            path_rel="out/summary.md",
            mime="text/markdown",
            run_id="run-r",
            session_id="sess-r",
            size_bytes=128,
            metadata={"title": "Summary"},
        )
        registered = registry.register(artifact)
        loaded = registry.get("report-hash")
        assert loaded is not None
        assert loaded.metadata["title"] == "Summary"
        assert registered.content_hash == registered.artifact_id
    finally:
        registry.close()
