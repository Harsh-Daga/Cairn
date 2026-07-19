"""Metrics / Balanced / Forensic content storage modes."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from server.api.action_handlers import ConfigSetParams, _config_set_action
from server.api.bootstrap import bootstrap_runtime
from server.api.context import ActionCtx
from server.config import Settings
from server.configuration import ConfigError
from server.ingest.storage import (
    apply_content_policy,
    is_upgrade,
    normalize_storage_mode,
    strip_inline_content,
)
from server.models.span import Span
from server.util.ids import new_ulid
from server.util.private_files import write_private_text


def _span(text: str | None) -> Span:
    return Span(
        span_id=new_ulid(),
        trace_id=new_ulid(),
        seq=1,
        kind="user_msg",
        text_inline=text,
        text_hash="abc",
    )


def test_mode_upgrade_detection() -> None:
    assert is_upgrade("metrics", "balanced")
    assert is_upgrade("balanced", "forensic")
    assert not is_upgrade("forensic", "balanced")
    assert normalize_storage_mode("metrics_only") == "metrics"


def test_metrics_strips_text_at_policy(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    (root / ".cairn").mkdir()
    write_private_text(root / ".cairn" / "config.toml", '[storage]\nmode = "metrics"\n')
    out = apply_content_policy(_span("secret prompt text"), workspace_root=root)
    assert out.text_inline is None
    assert out.text_hash == "abc"


def test_balanced_truncates(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    (root / ".cairn").mkdir()
    write_private_text(
        root / ".cairn" / "config.toml",
        '[storage]\nmode = "balanced"\ntext_inline_max = 10\n',
    )
    out = apply_content_policy(_span("0123456789ABCDEF"), workspace_root=root)
    assert out.text_inline == "0123456789"


def test_forensic_keeps_longer_cap(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    (root / ".cairn").mkdir()
    write_private_text(
        root / ".cairn" / "config.toml",
        '[storage]\nmode = "forensic"\ntext_inline_max = 20\n',
    )
    out = apply_content_policy(_span("x" * 25), workspace_root=root)
    assert out.text_inline == "x" * 20


def test_config_set_blocks_silent_upgrade(tmp_path: Path) -> None:
    settings = Settings(workspace_root=tmp_path / "ws")
    (settings.workspace_root).mkdir()
    (settings.workspace_root / ".cairn").mkdir()
    write_private_text(
        settings.workspace_root / ".cairn" / "config.toml",
        '[storage]\nmode = "metrics"\n',
    )
    runtime = bootstrap_runtime(settings)
    ctx = ActionCtx(
        db=runtime.database,
        workspace_id=runtime.workspace_id,
        workspace_root=runtime.workspace_root,
        event_bus=runtime.event_bus,
        pipeline=runtime.pipeline,
        jobs=runtime.jobs,
    )
    with pytest.raises(ConfigError, match="silent storage upgrade"):
        _config_set_action(
            ConfigSetParams(operation="set", key="storage.mode", value="forensic"),
            ctx,
        )
    result = _config_set_action(
        ConfigSetParams(
            operation="set",
            key="storage.mode",
            value="forensic",
            confirm_storage_upgrade=True,
        ),
        ctx,
    )
    assert result["value"] == "forensic"
    runtime.jobs.shutdown(wait=False)
    runtime.pipeline.stop()
    runtime.database.close()


def test_strip_keeps_hashes(tmp_path: Path) -> None:
    settings = Settings(workspace_root=tmp_path / "ws")
    settings.workspace_root.mkdir()
    (settings.workspace_root / ".cairn").mkdir()
    write_private_text(
        settings.workspace_root / ".cairn" / "config.toml",
        '[storage]\nmode = "metrics"\n',
    )
    runtime = bootstrap_runtime(settings)
    ws_id = runtime.workspace_id
    trace_id = new_ulid()
    span_id = new_ulid()
    old = (datetime.now(UTC) - timedelta(days=30)).isoformat()

    def _seed(conn: object) -> None:
        import sqlite3

        assert isinstance(conn, sqlite3.Connection)
        conn.execute(
            "INSERT INTO traces (trace_id, workspace_id, source, started_at, status, title, "
            "input_tokens, output_tokens, cost, cost_source, span_count, waste_tokens) "
            "VALUES (?, ?, 'cursor', ?, 'completed', 't', 1, 1, 0.0, 'priced', 1, 0)",
            (trace_id, ws_id, old),
        )
        conn.execute(
            "INSERT INTO spans (span_id, trace_id, seq, kind, status, text_inline, text_hash) "
            "VALUES (?, ?, 1, 'user_msg', 'ok', 'retain me', 'hash1')",
            (span_id, trace_id),
        )

    runtime.database.write(_seed)
    report = runtime.database.write(
        lambda conn: strip_inline_content(conn, workspace_id=ws_id, mode="metrics", limit=100)
    )
    assert report["stripped"] == 1
    row = runtime.database.reader.execute(
        "SELECT text_inline, text_hash FROM spans WHERE span_id = ?",
        (span_id,),
    ).fetchone()
    assert row["text_inline"] is None
    assert row["text_hash"] == "hash1"
    runtime.jobs.shutdown(wait=False)
    runtime.pipeline.stop()
    runtime.database.close()
