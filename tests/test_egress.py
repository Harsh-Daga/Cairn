"""Privacy-minimized egress ledger."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from server.improve.reflector import run_backend
from server.util.egress import (
    egress_path,
    egress_status,
    export_egress,
    list_egress,
    origin_from_url,
    record_egress,
)


def test_origin_strips_path_and_userinfo() -> None:
    assert origin_from_url("https://user:secret@api.openai.com/v1/chat") == (
        "https://api.openai.com"
    )
    assert origin_from_url("http://127.0.0.1:11434/api/chat") == "http://127.0.0.1:11434"


def test_record_has_no_secrets_or_prompt(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    (root / ".cairn").mkdir()
    entry = record_egress(
        root,
        trigger="reflector_provider",
        destination="https://api.openai.com/v1/chat/completions",
        purpose="opt-in optimize reflector LLM call",
        provider="provider:openai",
        field_classes=["typed evidence summary"],
        byte_estimate=123,
        consent_source="explicit_consent",
        success=True,
    )
    assert entry.destination_origin == "https://api.openai.com"
    text = egress_path(root).read_text(encoding="utf-8")
    assert "Bearer" not in text
    assert "sk-" not in text
    assert "prompt" not in text.lower() or "purpose" in text
    assert "secret" not in text
    status = egress_status(root)
    assert status["entry_count"] == 1
    assert status["successes"] == 1


def test_default_workspace_has_empty_ledger(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    (root / ".cairn").mkdir()
    assert list_egress(root) == []
    assert egress_status(root)["entry_count"] == 0


def test_provider_call_records_egress(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    (root / ".cairn").mkdir()
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-should-not-appear")
    monkeypatch.setenv("CAIRN_LLM_BASE_URL", "https://api.openai.com/v1")

    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"choices": [{"message": {"content": '{"proposals":[]}'}}]}
    response.request = MagicMock()

    with patch("server.improve.reflector.httpx.post", return_value=response):
        result = run_backend(
            "provider:openai",
            "private evidence must not be logged",
            allow_network=True,
            workspace_root=root,
        )
    assert result.ok is True
    rows = list_egress(root)
    assert len(rows) == 1
    assert rows[0]["success"] is True
    assert rows[0]["destination_origin"] == "https://api.openai.com"
    blob = egress_path(root).read_text(encoding="utf-8")
    assert "sk-test-should-not-appear" not in blob
    assert "private evidence" not in blob

    exported = export_egress(root)
    assert exported["ok"] is True
    assert Path(exported["path"]).is_file()


def test_failed_provider_call_records_failure(tmp_path: Path, monkeypatch) -> None:
    import httpx2 as httpx

    root = tmp_path / "ws"
    root.mkdir()
    (root / ".cairn").mkdir()
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CAIRN_LLM_BASE_URL", "https://api.openai.com/v1")

    with patch(
        "server.improve.reflector.httpx.post",
        side_effect=httpx.ConnectError("boom"),
    ):
        result = run_backend(
            "provider:openai",
            "x",
            allow_network=True,
            workspace_root=root,
        )
    assert result.ok is False
    rows = list_egress(root)
    assert len(rows) == 1
    assert rows[0]["success"] is False
    assert rows[0]["error_class"] == "http_error"
