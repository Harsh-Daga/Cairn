"""Parse-health sampling edge cases."""

from __future__ import annotations

import json
from pathlib import Path

from server.ingest.parse_health import (
    inspect_stream_shape,
    inspect_unknown_fields,
    unknown_field_spike,
)


def test_hermes_truncated_pretty_json_recovers_top_level_keys(tmp_path: Path) -> None:
    huge_messages = [{"role": "user", "content": "x" * 2000} for _ in range(40)]
    payload = {
        "session_id": "sess-large",
        "model": "hermes-test",
        "session_start": "2026-06-01T00:00:00Z",
        "last_updated": "2026-06-01T01:00:00Z",
        "base_url": "http://localhost",
        "platform": "cli",
        "system_prompt": "be helpful",
        "tools": ["bash"],
        "message_count": 40,
        "messages": huge_messages,
        "usage": {"input_tokens": 1},
    }
    path = tmp_path / "session_large.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    assert path.stat().st_size > 64 * 1024

    shape = inspect_stream_shape("hermes", path)
    assert shape["records_sampled"] >= 1
    assert "session_id" in shape["recognized_fields"]
    assert inspect_unknown_fields("hermes", path) == {}


def test_recover_ignores_nested_pretty_json_keys(tmp_path: Path) -> None:
    # Truncate after nested object so recovery must not promote nested keys.
    text = (
        "{\n"
        '  "session_id": "sess",\n'
        '  "model": "x",\n'
        '  "nested": {\n'
        '    "evil_nested_key": true,\n'
        '    "more": "' + ("y" * 70_000) + '"\n'
    )
    path = tmp_path / "truncated.json"
    path.write_text(text, encoding="utf-8")
    unknown = inspect_unknown_fields("hermes", path)
    assert "evil_nested_key" not in unknown
    assert "session_id" not in unknown  # recognized


def test_unknown_field_spike_uses_max_or_distinct_not_sum() -> None:
    assert unknown_field_spike({"a": 1, "b": 1}) is False
    assert unknown_field_spike({"a": 3}) is True
    assert unknown_field_spike({"a": 1, "b": 1, "c": 1}) is True
