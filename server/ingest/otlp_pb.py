"""OTLP protobuf decoding backed by OpenTelemetry's generated schema."""

from __future__ import annotations

from typing import Any

from google.protobuf.json_format import MessageToDict
from google.protobuf.message import DecodeError
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest


def decode_export_trace_service_request(data: bytes) -> dict[str, Any]:
    """Decode an OTLP/HTTP protobuf trace request into OTLP/JSON field names.

    Using the official generated message keeps Cairn aligned with the stable
    OpenTelemetry schema and preserves fields that Cairn does not yet consume.
    """
    try:
        request = ExportTraceServiceRequest.FromString(data)
    except DecodeError as exc:
        raise ValueError("invalid OTLP protobuf payload") from exc
    return MessageToDict(request, use_integers_for_enums=True)
