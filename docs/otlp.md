# OTLP ingest

Cairn accepts OpenTelemetry trace exports at `POST /v1/traces`. The endpoint is local to the Cairn server; it is not under the `/api` prefix.

Start the server first:

```bash
cairn ui --no-open
```

## OTLP/JSON

Send an OTLP/JSON `ExportTraceServiceRequest` with `Content-Type: application/json`:

```bash
curl -X POST http://127.0.0.1:8787/v1/traces \
  -H 'Content-Type: application/json' \
  --data-binary @traces.json
```

## Protobuf

Send an encoded `ExportTraceServiceRequest` with `Content-Type: application/x-protobuf`:

```bash
curl -X POST http://127.0.0.1:8787/v1/traces \
  -H 'Content-Type: application/x-protobuf' \
  --data-binary @traces.pb
```

## Response and idempotency

Successful requests return `partialSuccess` and one result per trace. Re-sending a trace with the same OTLP service and trace ID returns the existing Cairn trace with `inserted: false`.

```json
{
  "partialSuccess": {},
  "results": [{ "trace_id": "…", "inserted": true, "span_count": 12 }]
}
```

Cairn stores standard span names, timestamps, parent relationships, status, common attributes, and `gen_ai.*` token/model attributes. Unsupported fields are retained only when they are represented by the supported ingest mapping; validate an exporter against your own telemetry before relying on it for production reporting.
