"""Reference storage mode: no text_inline, source drift detection."""

from __future__ import annotations

from pathlib import Path

from server.ingest.contract import IngestCursor
from server.ingest.reference import detect_source_drift, list_drift, record_drift, reference_status
from server.ingest.storage import apply_content_policy, normalize_storage_mode, storage_status
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


def test_normalize_reference_aliases() -> None:
    assert normalize_storage_mode("reference") == "reference"
    assert normalize_storage_mode("zero-copy") == "reference"


def test_reference_strips_text(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    (root / ".cairn").mkdir()
    write_private_text(root / ".cairn" / "config.toml", '[storage]\nmode = "reference"\n')
    out = apply_content_policy(_span("secret from source log"), workspace_root=root)
    assert out.text_inline is None
    assert out.text_hash == "abc"
    status = storage_status(root)
    assert status["mode"] == "reference"
    assert status["reference"]["source_authoritative"] is True
    assert "hashes" in status["reference"]["does_not_claim_zero_copy_for"]


def test_detect_missing_and_rewrite(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    src = root / "session.jsonl"
    src.write_text("aaaa\n", encoding="utf-8")
    prev = IngestCursor(offset=5, mtime_ns=src.stat().st_mtime_ns, size=5)
    assert detect_source_drift(src, prev, adapter_id="cursor") is None

    src.write_text("bb\n", encoding="utf-8")  # shorter rewrite
    event = detect_source_drift(src, prev, adapter_id="cursor")
    assert event is not None
    assert event.kind == "rewritten_shorter"
    record_drift(root, event)

    src.unlink()
    missing = detect_source_drift(src, prev, adapter_id="cursor")
    assert missing is not None
    assert missing.kind == "missing"
    record_drift(root, missing)
    assert len(list_drift(root)) == 2
    assert reference_status(root)["drift_events"] == 2
