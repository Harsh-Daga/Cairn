"""OTLP/JSON trace receiver mapped to Cairn Trace/Span models."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from server.analyze.dirty import mark_trace_dirty, trace_day_key
from server.api.sse import EventBus
from server.ingest.otlp_pb import decode_export_trace_service_request
from server.models.data_quality import DataQuality
from server.models.span import Span, SpanKind, SpanStatus
from server.models.trace import Trace
from server.store.db import Database
from server.store.repos.data_quality import DataQualityRepo
from server.store.repos.spans import SpanRepo
from server.store.repos.traces import TraceRepo
from server.util.hash import hash_obj
from server.util.ids import new_ulid

_OTLP_KIND_TO_SPAN: dict[int, SpanKind] = {
    1: "agent",
    2: "tool_call",
    3: "system",
    4: "llm_call",
    5: "user_msg",
}


@dataclass(frozen=True)
class OtlpIngestResult:
    trace_id: str
    span_count: int
    inserted: bool


def _attr_value(raw: dict[str, Any]) -> object:
    if "stringValue" in raw:
        return raw["stringValue"]
    if "intValue" in raw:
        return int(raw["intValue"])
    if "doubleValue" in raw:
        return float(raw["doubleValue"])
    if "boolValue" in raw:
        return bool(raw["boolValue"])
    return raw


def _attrs_map(attributes: list[dict[str, Any]] | None) -> dict[str, object]:
    out: dict[str, object] = {}
    for item in attributes or []:
        key = item.get("key")
        value = item.get("value")
        if isinstance(key, str) and isinstance(value, dict):
            out[key] = _attr_value(value)
    return out


def _nano_to_iso(nano: str | int | None) -> str | None:
    if nano is None:
        return None
    try:
        sec = int(nano) / 1_000_000_000
        return datetime.fromtimestamp(sec, tz=UTC).isoformat()
    except (TypeError, ValueError):
        return None


def _span_kind(raw_kind: int | None, attrs: dict[str, object], name: str) -> SpanKind:
    if "gen_ai.tool.name" in attrs or name.startswith("tool."):
        return "tool_call"
    if "gen_ai.request.model" in attrs:
        return "llm_call"
    if raw_kind is not None and raw_kind in _OTLP_KIND_TO_SPAN:
        return _OTLP_KIND_TO_SPAN[raw_kind]
    lowered = name.lower()
    if "user" in lowered:
        return "user_msg"
    if "assistant" in lowered:
        return "assistant_msg"
    return "system"


def _span_status(raw: dict[str, Any] | None) -> SpanStatus:
    if not raw:
        return "ok"
    code = raw.get("code")
    if code == 2:
        return "error"
    if code == 3:
        return "cancelled"
    return "ok"


def _stable_otlp_trace_id(workspace_id: str, source: str, external_id: str) -> str:
    digest = hash_obj({"workspace_id": workspace_id, "source": source, "external_id": external_id})
    return digest[:26].upper()


def _stable_otlp_span_id(trace_id: str, seq: int) -> str:
    digest = hash_obj({"trace_id": trace_id, "seq": seq})
    return digest[:26].upper()


def _as_int(value: object) -> int:
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def parse_otlp_json(payload: dict[str, Any]) -> list[tuple[Trace, list[Span], DataQuality]]:
    """Parse OTLP/JSON export into Cairn models."""
    traces: list[tuple[Trace, list[Span], DataQuality]] = []
    for resource_block in payload.get("resourceSpans", []):
        resource_attrs = _attrs_map(resource_block.get("resource", {}).get("attributes"))
        service = str(resource_attrs.get("service.name", "unknown"))
        source = f"otlp:{service}"
        for scope_block in resource_block.get("scopeSpans", []):
            spans_raw = scope_block.get("spans", [])
            if not spans_raw:
                continue
            external_id = str(spans_raw[0].get("traceId", new_ulid()))
            trace_id = _stable_otlp_trace_id("workspace", source, external_id)
            mapped: list[Span] = []
            input_total = 0
            output_total = 0
            model: str | None = None
            started_at: str | None = None
            ended_at: str | None = None
            raw_to_span_id: dict[str, str] = {}
            for seq, raw in enumerate(spans_raw, start=1):
                raw_id = str(raw.get("spanId", ""))
                if raw_id:
                    raw_to_span_id[raw_id] = _stable_otlp_span_id(trace_id, seq)
            for seq, raw in enumerate(spans_raw, start=1):
                attrs = _attrs_map(raw.get("attributes"))
                name = str(raw.get("name", ""))
                kind = _span_kind(raw.get("kind"), attrs, name)
                in_tok = _as_int(attrs.get("gen_ai.usage.input_tokens", 0))
                out_tok = _as_int(attrs.get("gen_ai.usage.output_tokens", 0))
                input_total += in_tok
                output_total += out_tok
                span_model = str(attrs.get("gen_ai.request.model", "")) or None
                if span_model:
                    model = span_model
                span_started = _nano_to_iso(raw.get("startTimeUnixNano"))
                span_ended = _nano_to_iso(raw.get("endTimeUnixNano"))
                if started_at is None or (span_started and span_started < started_at):
                    started_at = span_started
                if ended_at is None or (span_ended and span_ended > ended_at):
                    ended_at = span_ended
                tool_name = attrs.get("gen_ai.tool.name")
                span_name = str(tool_name) if tool_name else (name or span_model)
                parent_raw = raw.get("parentSpanId")
                parent_span_id = None
                if parent_raw:
                    parent_span_id = raw_to_span_id.get(str(parent_raw))
                mapped.append(
                    Span(
                        span_id=_stable_otlp_span_id(trace_id, seq),
                        trace_id=trace_id,
                        parent_span_id=parent_span_id,
                        seq=seq,
                        kind=kind,
                        name=span_name,
                        started_at=span_started,
                        ended_at=span_ended,
                        status=_span_status(raw.get("status")),
                        model=span_model,
                        input_tokens=in_tok or None,
                        output_tokens=out_tok or None,
                        attrs_json=attrs,
                    )
                )
            first_name = str(spans_raw[0].get("name", ""))
            trace = Trace(
                trace_id=trace_id,
                workspace_id="workspace",
                source=source.replace("-", "_"),
                external_id=external_id,
                model=model,
                started_at=started_at,
                ended_at=ended_at,
                status="completed",
                title=first_name[:120] if first_name else None,
                input_tokens=input_total,
                output_tokens=output_total,
                span_count=len(mapped),
                tool_calls=sum(1 for s in mapped if s.kind == "tool_call"),
            )
            quality = DataQuality(
                trace_id=trace_id,
                pct_tokens_measured=100.0 if input_total or output_total else 0.0,
                pct_tokens_estimated=0.0,
                timestamps_present=bool(started_at),
                cost_source="absent",
                parser_version="otlp@1",
                computed_at=datetime.now(UTC).isoformat(),
            )
            traces.append((trace, mapped, quality))
    return traces


class OtlpReceiver:
    """Persist OTLP/JSON payloads into the workspace database."""

    def __init__(self, database: Database, workspace_id: str, event_bus: EventBus) -> None:
        self._db = database
        self.workspace_id = workspace_id
        self._bus = event_bus

    def ingest_bytes(self, raw: bytes, content_type: str | None = None) -> list[OtlpIngestResult]:
        media_type = (content_type or "").split(";", maxsplit=1)[0].strip().lower()
        if media_type in {"application/x-protobuf", "application/protobuf"}:
            payload = decode_export_trace_service_request(raw)
        else:
            payload = json.loads(raw.decode("utf-8"))
        return self.ingest_payload(payload)

    def ingest_payload(self, payload: dict[str, Any]) -> list[OtlpIngestResult]:
        parsed = parse_otlp_json(payload)
        results: list[OtlpIngestResult] = []
        for trace, spans, quality in parsed:
            trace = trace.model_copy(update={"workspace_id": self.workspace_id})
            existing = None
            if trace.external_id:
                existing = TraceRepo.get_by_external(
                    self._db.reader, trace.source, trace.external_id
                )
            if existing is not None:
                results.append(
                    OtlpIngestResult(
                        trace_id=existing.trace_id,
                        span_count=len(SpanRepo.list_by_trace(self._db.reader, existing.trace_id)),
                        inserted=False,
                    )
                )
                continue

            trace_id = self._persist_trace(trace, spans, quality)
            results.append(
                OtlpIngestResult(trace_id=trace_id, span_count=len(spans), inserted=True)
            )
            self._bus.publish(
                "trace-updated",
                {
                    "trace_id": trace_id,
                    "inserted": True,
                    "span_count": len(spans),
                    "source": trace.source,
                },
            )
            self._bus.publish("views-updated", {"trace_id": trace_id})
        return results

    def _persist_trace(self, trace: Trace, spans: list[Span], quality: DataQuality) -> str:
        def _write(conn: sqlite3.Connection) -> str:
            TraceRepo.create(conn, trace)
            for span in spans:
                SpanRepo.create(conn, span)
            DataQualityRepo.create(conn, quality)
            day = trace_day_key(trace.started_at)
            mark_trace_dirty(conn, trace.trace_id, day=day, project=trace.project or "")
            return trace.trace_id

        return self._db.write(_write)
