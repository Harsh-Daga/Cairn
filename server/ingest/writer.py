"""Ingest writer — persists parsed sessions to the Cairn store."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from server.ingest.map import ParsedSession, session_to_trace_spans
from server.ingest.pricing import load_overrides
from server.models.data_quality import DataQuality
from server.models.span import Span
from server.models.trace import Trace
from server.store.db import Database
from server.store.repos.data_quality import DataQualityRepo
from server.store.repos.spans import SpanRepo
from server.store.repos.traces import TraceRepo


@dataclass(frozen=True)
class IngestResult:
    trace_id: str
    external_id: str
    inserted: bool
    span_count: int


class IngestWriter:
    """Write parsed sessions into workspace database."""

    def __init__(self, database: Database, workspace_id: str, repo_root: Path) -> None:
        self._db = database
        self.workspace_id = workspace_id
        self.repo_root = repo_root.resolve()
        self._pricing_overrides = load_overrides(self.repo_root)

    def ingest(self, parsed: ParsedSession) -> IngestResult:
        """Upsert a parsed session; skip if trace already exists."""
        from server.ingest.map import normalize_source

        source = normalize_source(parsed.source)
        existing = TraceRepo.get_by_external(self._db.reader, source, parsed.external_id)
        if existing is not None:
            spans = SpanRepo.list_by_trace(self._db.reader, existing.trace_id)
            return IngestResult(
                trace_id=existing.trace_id,
                external_id=parsed.external_id,
                inserted=False,
                span_count=len(spans),
            )

        trace, spans, quality = session_to_trace_spans(
            parsed,
            workspace_id=self.workspace_id,
            repo_root=self.repo_root,
            pricing_overrides=self._pricing_overrides,
        )

        def _write(conn: object) -> IngestResult:
            import sqlite3

            assert isinstance(conn, sqlite3.Connection)
            TraceRepo.create(conn, trace)
            for span in spans:
                SpanRepo.create(conn, span)
            DataQualityRepo.create(conn, quality)
            return IngestResult(
                trace_id=trace.trace_id,
                external_id=parsed.external_id,
                inserted=True,
                span_count=len(spans),
            )

        return self._db.write(_write)

    def map_session(self, parsed: ParsedSession) -> tuple[Trace, list[Span], DataQuality]:
        """Map parsed session to models without writing."""
        return session_to_trace_spans(
            parsed,
            workspace_id=self.workspace_id,
            repo_root=self.repo_root,
            pricing_overrides=self._pricing_overrides,
        )
