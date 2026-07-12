"""Minimal OTLP protobuf decoder for ExportTraceServiceRequest.

This decoder intentionally supports only the subset needed by Cairn ingest:
- resourceSpans/resource.attributes
- scopeSpans/spans
- span status + common scalar attribute value types
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

_WT_VARINT = 0
_WT_FIXED64 = 1
_WT_LEN = 2
_WT_FIXED32 = 5


@dataclass
class _Reader:
    data: bytes
    pos: int = 0

    def done(self) -> bool:
        return self.pos >= len(self.data)

    def read_varint(self) -> int:
        shift = 0
        out = 0
        while True:
            if self.pos >= len(self.data):
                raise ValueError("truncated varint")
            b = self.data[self.pos]
            self.pos += 1
            out |= (b & 0x7F) << shift
            if not (b & 0x80):
                return out
            shift += 7
            if shift > 63:
                raise ValueError("varint too large")

    def read_fixed64(self) -> bytes:
        end = self.pos + 8
        if end > len(self.data):
            raise ValueError("truncated fixed64")
        chunk = self.data[self.pos : end]
        self.pos = end
        return chunk

    def read_fixed32(self) -> bytes:
        end = self.pos + 4
        if end > len(self.data):
            raise ValueError("truncated fixed32")
        chunk = self.data[self.pos : end]
        self.pos = end
        return chunk

    def read_len(self) -> bytes:
        size = self.read_varint()
        end = self.pos + size
        if end > len(self.data):
            raise ValueError("truncated length-delimited field")
        chunk = self.data[self.pos : end]
        self.pos = end
        return chunk


def _decode_message(data: bytes) -> dict[int, list[tuple[int, object]]]:
    out: dict[int, list[tuple[int, object]]] = {}
    r = _Reader(data)
    while not r.done():
        key = r.read_varint()
        field_no = key >> 3
        wt = key & 0x07
        if wt == _WT_VARINT:
            value: object = r.read_varint()
        elif wt == _WT_FIXED64:
            value = r.read_fixed64()
        elif wt == _WT_LEN:
            value = r.read_len()
        elif wt == _WT_FIXED32:
            value = r.read_fixed32()
        else:
            raise ValueError(f"unsupported wire type: {wt}")
        out.setdefault(field_no, []).append((wt, value))
    return out


def _first_len(msg: dict[int, list[tuple[int, object]]], field_no: int) -> bytes | None:
    for wt, value in msg.get(field_no, []):
        if wt == _WT_LEN and isinstance(value, bytes):
            return value
    return None


def _first_varint(msg: dict[int, list[tuple[int, object]]], field_no: int) -> int | None:
    for wt, value in msg.get(field_no, []):
        if wt == _WT_VARINT and isinstance(value, int):
            return value
    return None


def _decode_any_value(blob: bytes) -> dict[str, object]:
    msg = _decode_message(blob)
    if (string_value := _first_len(msg, 1)) is not None:
        return {"stringValue": string_value.decode("utf-8", errors="replace")}
    if (bool_value := _first_varint(msg, 2)) is not None:
        return {"boolValue": bool(bool_value)}
    if (int_value := _first_varint(msg, 3)) is not None:
        return {"intValue": str(int_value)}
    for wt, value in msg.get(4, []):
        if wt == _WT_FIXED64 and isinstance(value, bytes):
            return {"doubleValue": struct.unpack("<d", value)[0]}
    return {}


def _decode_key_value(blob: bytes) -> dict[str, object] | None:
    msg = _decode_message(blob)
    key_raw = _first_len(msg, 1)
    value_raw = _first_len(msg, 2)
    if key_raw is None or value_raw is None:
        return None
    return {
        "key": key_raw.decode("utf-8", errors="replace"),
        "value": _decode_any_value(value_raw),
    }


def _decode_status(blob: bytes) -> dict[str, int]:
    msg = _decode_message(blob)
    code = _first_varint(msg, 2) or 0
    return {"code": int(code)}


def _decode_span(blob: bytes) -> dict[str, object]:
    msg = _decode_message(blob)
    out: dict[str, object] = {}
    if (trace_id := _first_len(msg, 1)) is not None:
        out["traceId"] = trace_id.hex()
    if (span_id := _first_len(msg, 2)) is not None:
        out["spanId"] = span_id.hex()
    if (parent_id := _first_len(msg, 4)) is not None and parent_id:
        out["parentSpanId"] = parent_id.hex()
    if (name := _first_len(msg, 5)) is not None:
        out["name"] = name.decode("utf-8", errors="replace")
    if (kind := _first_varint(msg, 6)) is not None:
        out["kind"] = int(kind)
    if (start := _first_varint(msg, 7)) is not None:
        out["startTimeUnixNano"] = str(start)
    if (end := _first_varint(msg, 8)) is not None:
        out["endTimeUnixNano"] = str(end)
    attrs: list[dict[str, object]] = []
    for wt, value in msg.get(9, []):
        if wt == _WT_LEN and isinstance(value, bytes):
            kv = _decode_key_value(value)
            if kv is not None:
                attrs.append(kv)
    if attrs:
        out["attributes"] = attrs
    if (status := _first_len(msg, 15)) is not None:
        out["status"] = _decode_status(status)
    return out


def _decode_scope_spans(blob: bytes) -> dict[str, object]:
    msg = _decode_message(blob)
    spans: list[dict[str, object]] = []
    for wt, value in msg.get(2, []):
        if wt == _WT_LEN and isinstance(value, bytes):
            spans.append(_decode_span(value))
    return {"spans": spans}


def _decode_resource(blob: bytes) -> dict[str, object]:
    msg = _decode_message(blob)
    attrs: list[dict[str, object]] = []
    for wt, value in msg.get(1, []):
        if wt == _WT_LEN and isinstance(value, bytes):
            kv = _decode_key_value(value)
            if kv is not None:
                attrs.append(kv)
    return {"attributes": attrs}


def _decode_resource_spans(blob: bytes) -> dict[str, object]:
    msg = _decode_message(blob)
    resource: dict[str, object] = {"attributes": []}
    if (raw_resource := _first_len(msg, 1)) is not None:
        resource = _decode_resource(raw_resource)
    scopes: list[dict[str, object]] = []
    for wt, value in msg.get(2, []):
        if wt == _WT_LEN and isinstance(value, bytes):
            scopes.append(_decode_scope_spans(value))
    return {"resource": resource, "scopeSpans": scopes}


def decode_export_trace_service_request(data: bytes) -> dict[str, object]:
    """Decode OTLP /v1/traces protobuf payload into OTLP/JSON-like structure."""
    msg = _decode_message(data)
    resource_spans: list[dict[str, object]] = []
    for wt, value in msg.get(1, []):
        if wt == _WT_LEN and isinstance(value, bytes):
            resource_spans.append(_decode_resource_spans(value))
    return {"resourceSpans": resource_spans}
