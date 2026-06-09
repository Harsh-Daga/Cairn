"""Phase 20 performance optimizations."""

from __future__ import annotations

from pathlib import Path

from cairn.cache.cas import ContentAddressableStore
from cairn.graph.session_graph import build_session_graph
from cairn.ingest.cursors import IngestCursors
from cairn.performance.bench import benchmark_cas_reads, benchmark_graph_layout
from cairn.render.capture_bundle import MAX_BUNDLE_EVENTS, assemble_capture_bundle
from cairn.render.graph_layout import layout_session_graph


def test_cas_read_cache_hits_memory(tmp_path: Path) -> None:
    cas = ContentAddressableStore(tmp_path, read_cache_size=8)
    digest = cas.put(b"payload-one")
    first = cas.read(digest)
    assert first == b"payload-one"
    path = cas._path(digest)
    path.write_bytes(b"tampered")
    second = cas.read(digest)
    assert second == b"payload-one"


def test_graph_layout_memoization() -> None:
    events = [
        {"seq": 1, "type": "user_prompt", "text_inline": "a"},
        {"seq": 2, "type": "tool_call", "name": "read"},
    ]
    graph = build_session_graph(events)
    first = layout_session_graph(graph)
    second = layout_session_graph(graph)
    assert first is second


def test_ingest_cursor_skips_unchanged_file(tmp_path: Path) -> None:
    file_path = tmp_path / "session.jsonl"
    file_path.write_text("{}\n", encoding="utf-8")
    cursors = IngestCursors(tmp_path)
    cursors.mark(file_path)
    cursors.save()

    reloaded = IngestCursors(tmp_path)
    assert reloaded.is_unchanged(file_path) is True
    file_path.write_text("{}\n{}\n", encoding="utf-8")
    assert reloaded.is_unchanged(file_path) is False


def test_large_session_bundle_truncates_events(tmp_path: Path) -> None:
    from cairn.ingest.writer import CaptureWriter

    writer = CaptureWriter(tmp_path)
    run_id = writer.begin_session(source="claude-code", external_id="big", cwd=str(tmp_path))
    try:
        for _ in range(1, MAX_BUNDLE_EVENTS + 50):
            writer.append_event(run_id, {"type": "tool_call", "name": "read"})
        writer.finish_session(run_id)
    finally:
        writer.close()

    writer = CaptureWriter(tmp_path)
    try:
        cas = ContentAddressableStore(tmp_path / ".cairn")
        payload = assemble_capture_bundle(writer, "big", cas)
    finally:
        writer.close()
    assert payload["events_truncated"] is True
    assert payload["events_total"] == MAX_BUNDLE_EVENTS + 49
    assert len(payload["events"]) == MAX_BUNDLE_EVENTS


def test_benchmark_helpers(tmp_path: Path) -> None:
    cas = ContentAddressableStore(tmp_path)
    digest = cas.put(b"bench")
    assert benchmark_cas_reads(tmp_path, digest, iterations=5) >= 0
    graph = build_session_graph([{"seq": 1, "type": "user_prompt"}])
    assert benchmark_graph_layout(graph, iterations=3) >= 0
