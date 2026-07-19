"""Offline model pricing provenance, overrides, and staleness."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from server.api.action_handlers import (
    EmptyParams,
    _pricing_refresh_preview_action,
    _pricing_status_action,
)
from server.api.bootstrap import bootstrap_runtime
from server.api.context import ActionCtx
from server.config import Settings
from server.doctor import _check_pricing
from server.ingest.pricing import estimate_cost, pricing_refresh_preview, pricing_status
from server.ingest.pricing_data import load_price_table_meta
from server.util.private_files import write_private_text


def _ctx(tmp_path: Path, *, toml: str = "") -> tuple[object, ActionCtx]:
    settings = Settings(workspace_root=tmp_path / "ws")
    settings.workspace_root.mkdir()
    (settings.workspace_root / ".cairn").mkdir()
    if toml:
        write_private_text(settings.workspace_root / ".cairn" / "config.toml", toml)
    runtime = bootstrap_runtime(settings)
    ctx = ActionCtx(
        db=runtime.database,
        workspace_id=runtime.workspace_id,
        workspace_root=runtime.workspace_root,
        event_bus=runtime.event_bus,
        pipeline=runtime.pipeline,
        jobs=runtime.jobs,
    )
    return runtime, ctx


def _shutdown(runtime: object) -> None:
    runtime.jobs.shutdown(wait=False)  # type: ignore[attr-defined]
    runtime.pipeline.stop()  # type: ignore[attr-defined]
    runtime.database.close()  # type: ignore[attr-defined]


def test_bundled_meta_has_source_version_effective_date() -> None:
    meta = load_price_table_meta()
    assert meta.source
    assert meta.version
    assert meta.effective_date
    assert meta.model_count > 0
    assert meta.schema.startswith("cairn.model_prices")


def test_pricing_kind_matched_override_unknown(tmp_path: Path) -> None:
    runtime, ctx = _ctx(
        tmp_path,
        toml=("[pricing.overrides.custom-model]\ninput_per_mtok = 1.0\noutput_per_mtok = 2.0\n"),
    )
    usage = {"input_tokens": 1_000_000, "output_tokens": 1_000_000}
    matched = estimate_cost("claude-sonnet-4", usage, root=ctx.workspace_root)
    assert matched.pricing_kind == "matched"
    assert matched.model_matched == "claude-sonnet"
    overridden = estimate_cost("custom-model", usage, root=ctx.workspace_root)
    assert overridden.pricing_kind == "override"
    assert overridden.total == 3.0
    unknown = estimate_cost("totally-unknown-xyz", usage, root=ctx.workspace_root)
    assert unknown.pricing_kind == "unknown"
    assert unknown.model_matched is None
    assert unknown.total == 0.0
    _shutdown(runtime)


def test_stale_detection_and_doctor(tmp_path: Path) -> None:
    runtime, ctx = _ctx(tmp_path, toml="[pricing]\nstale_after_days = 30\n")
    # Bundled table effective_date is 2026-06-13; force "now" far later.
    status = pricing_status(
        ctx.workspace_root,
        now=datetime(2026, 12, 1, tzinfo=UTC),
    )
    assert status["offline"] is True
    assert status["auto_download"] is False
    assert status["stale"] is True
    assert status["age_days"] is not None and status["age_days"] > 30

    check = _check_pricing(ctx.workspace_root)
    # Real "today" (2026-07-19 era) is >30d after 2026-06-13.
    assert check.ok is False
    assert "stale" in check.detail
    action = _pricing_status_action(EmptyParams(), ctx)
    assert action["source"]
    assert action["refresh"]["available"] is False
    preview = _pricing_refresh_preview_action(EmptyParams(), ctx)
    assert preview["would_download"] is False
    _shutdown(runtime)


def test_refresh_preview_never_downloads() -> None:
    preview = pricing_refresh_preview(None)
    assert preview["would_download"] is False
    assert (
        "never" in preview["preview"]["message"].lower()
        or "not implemented" in preview["preview"]["message"].lower()
    )


def test_fresh_when_stale_after_large(tmp_path: Path) -> None:
    runtime, ctx = _ctx(tmp_path, toml="[pricing]\nstale_after_days = 3650\n")
    status = pricing_status(
        ctx.workspace_root,
        now=datetime(2026, 7, 19, tzinfo=UTC),
    )
    assert status["stale"] is False
    _shutdown(runtime)
