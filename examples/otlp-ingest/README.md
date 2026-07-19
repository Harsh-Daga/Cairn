# OTLP ingest

Send OpenTelemetry traces to a running local Cairn server.

```bash
cairn ui --no-open
curl -X POST http://127.0.0.1:8787/v1/traces \
  -H 'Content-Type: application/json' \
  --data-binary @examples/otlp-ingest/sample_trace.json
```

`sample_trace.json` is the same deterministic fixture used in `tests/test_otlp.py`
(`tests/fixtures/otlp/sample_trace.json`). Successful responses return `partialSuccess`
and per-trace `inserted` flags.

## Limits

- OTLP is interoperable telemetry, not a lossless Cairn archive — see [docs/otlp.md](../../docs/otlp.md).
- Use [export-archive](../export-archive/) for portable Cairn-native evidence.
