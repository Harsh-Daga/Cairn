"""Tests for the Tier 2 reflector (parse, evidence resolution, fallback)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

from server.improve.evidence_pack import EvidencePack
from server.improve.reflector import (
    Proposal,
    ReflectorError,
    parse_proposals,
    reflect,
    reflect_if_available,
    resolve_backend,
    resolve_evidence,
    run_backend,
)


def _sample_pack(**overrides: object) -> EvidencePack:
    base: dict[str, object] = {
        "days": 14,
        "insights": [{"detector": "identical-tool-calls", "fingerprint": "identical-tool-calls"}],
        "reread_files": [{"path": "src/app.py", "reads": 5, "head": ""}],
        "failing_commands": [{"name": "bad_cmd", "failures": 3, "last_error": ""}],
        "typed_evidence": [
            {"entry_id": "avoid-duplicate-reads", "evidence_type": "insight_proposal"}
        ],
    }
    base.update(overrides)
    return EvidencePack(
        days=int(base["days"]),  # type: ignore[arg-type]
        insights=list(base.get("insights", [])),  # type: ignore[arg-type]
        waste=dict(base.get("waste", {})),  # type: ignore[arg-type]
        reread_files=list(base.get("reread_files", [])),  # type: ignore[arg-type]
        failing_commands=list(base.get("failing_commands", [])),  # type: ignore[arg-type]
        loops=list(base.get("loops", [])),  # type: ignore[arg-type]
        current_entries=list(base.get("current_entries", [])),  # type: ignore[arg-type]
        typed_evidence=list(base.get("typed_evidence", [])),  # type: ignore[arg-type]
    )


def _json_payload(proposals: list[dict[str, object]]) -> str:
    return json.dumps({"proposals": proposals})


def test_parse_proposals_valid_json() -> None:
    text = """
    {
      "proposals": [
        {
          "op": "add",
          "kind": "file_guide",
          "entry_id": "fg_main",
          "content": "`src/main.py`: entry point",
          "rationale": "hot read path",
          "confidence": 0.9,
          "evidence_refs": ["src/main.py"]
        }
      ]
    }
    """
    proposals = parse_proposals(text)
    assert len(proposals) == 1
    p = proposals[0]
    assert p.op == "add"
    assert p.kind == "file_guide"
    assert p.entry_id == "fg_main"
    assert p.confidence == 0.9
    assert p.evidence_refs == ["src/main.py"]


def test_parse_proposals_skips_invalid_entries() -> None:
    text = _json_payload(
        [
            {"op": "add", "kind": "bad_kind", "entry_id": "x", "content": "y"},
            {"op": "add", "kind": "rule", "entry_id": "r1", "content": ""},
            {"op": "remove", "kind": "rule", "entry_id": "r2", "content": ""},
            {"op": "add", "kind": "rule", "entry_id": "r3", "content": "valid rule"},
        ]
    )
    proposals = parse_proposals(text)
    assert len(proposals) == 2
    assert {p.entry_id for p in proposals} == {"r2", "r3"}


def test_parse_proposals_invalid_json_raises() -> None:
    with pytest.raises(ReflectorError, match="invalid JSON"):
        parse_proposals("not json")


def test_parse_proposals_missing_array_raises() -> None:
    with pytest.raises(ReflectorError, match="missing 'proposals'"):
        parse_proposals('{"items": []}')


def test_resolve_evidence_file_guide() -> None:
    p = Proposal(
        op="add",
        kind="file_guide",
        entry_id="fg1",
        content="guide",
        evidence_refs=["src/app.py", "src/other.py"],
    )
    assert resolve_evidence(p) == {"path": "src/app.py"}


def test_resolve_evidence_file_guide_no_refs() -> None:
    p = Proposal(op="add", kind="file_guide", entry_id="fg1", content="guide")
    assert resolve_evidence(p) == {"path": ""}


def test_resolve_evidence_command_fix() -> None:
    p = Proposal(
        op="add",
        kind="command_fix",
        entry_id="cf1",
        content="fix",
        evidence_refs=["bad_cmd --flag"],
    )
    ev = resolve_evidence(p)
    assert ev["bad"] == "bad_cmd --flag"
    assert ev["name"] == "bad_cmd --flag"
    assert ev["tool_name"] == "bad_cmd --flag"


def test_resolve_evidence_known_issue() -> None:
    p = Proposal(
        op="add",
        kind="known_issue",
        entry_id="ki1",
        content="issue",
        evidence_refs=["failing_tool"],
    )
    ev = resolve_evidence(p)
    assert ev["tool_name"] == "failing_tool"


def test_resolve_evidence_repo_map() -> None:
    p = Proposal(
        op="add",
        kind="repo_map",
        entry_id="rm1",
        content="map",
        evidence_refs=["src", "lib"],
    )
    assert resolve_evidence(p) == {"dirs": ["src", "lib"]}


def test_resolve_evidence_rule() -> None:
    p = Proposal(op="add", kind="rule", entry_id="r1", content="rule", evidence_refs=["x"])
    assert resolve_evidence(p) == {"refs": ["x"]}


def test_resolve_evidence_validates_known_refs() -> None:
    pack = _sample_pack()
    p = Proposal(
        op="add",
        kind="file_guide",
        entry_id="fg1",
        content="guide",
        evidence_refs=["src/app.py"],
    )
    assert resolve_evidence(p, pack=pack) == {"path": "src/app.py"}


def test_resolve_evidence_rejects_unknown_refs() -> None:
    pack = _sample_pack()
    p = Proposal(
        op="add",
        kind="file_guide",
        entry_id="fg1",
        content="guide",
        evidence_refs=["does/not/exist"],
    )
    with pytest.raises(ReflectorError, match="unknown evidence refs"):
        resolve_evidence(p, pack=pack)


def test_resolve_evidence_allows_empty_refs_with_pack() -> None:
    pack = _sample_pack()
    p = Proposal(op="add", kind="file_guide", entry_id="fg1", content="guide")
    assert resolve_evidence(p, pack=pack) == {"path": ""}


def test_evidence_pack_known_refs() -> None:
    pack = _sample_pack()
    refs = pack.known_refs()
    assert "src/app.py" in refs
    assert "bad_cmd" in refs
    assert "insight:identical-tool-calls" in refs
    assert "avoid-duplicate-reads" in refs


def test_resolve_backend_none_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CAIRN_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    with patch("server.improve.reflector.shutil.which", return_value=None):
        assert resolve_backend() is None


def test_reflect_if_available_returns_empty_without_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CAIRN_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with patch("server.improve.reflector.shutil.which", return_value=None):
        pack = _sample_pack()
        assert reflect_if_available("", pack) == []


def test_reflect_raises_when_backend_fails() -> None:
    pack = _sample_pack()
    with (
        patch(
            "server.improve.reflector.run_backend",
            return_value=MagicMock(ok=False, error="offline", text=""),
        ),
        pytest.raises(ReflectorError, match="offline"),
    ):
        reflect("", pack, "provider:openai")


def test_run_backend_openai_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    response = httpx.Response(
        200,
        json={"choices": [{"message": {"content": '{"proposals":[]}'}}]},
        request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"),
    )
    with patch("server.improve.reflector.httpx.post", return_value=response) as post:
        result = run_backend("provider:openai", "prompt")
    assert result.ok is True
    assert result.text == '{"proposals":[]}'
    post.assert_called_once()


def test_reflect_parses_provider_response(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    payload = _json_payload(
        [
            {
                "op": "add",
                "kind": "rule",
                "entry_id": "r1",
                "content": "Check context before read.",
                "evidence_refs": ["insight:identical-tool-calls"],
            }
        ]
    )
    response = httpx.Response(
        200,
        json={"choices": [{"message": {"content": payload}}]},
        request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"),
    )
    with patch("server.improve.reflector.httpx.post", return_value=response):
        pack = _sample_pack()
        proposals = reflect("", pack, "provider:openai")
    assert len(proposals) == 1
    assert proposals[0].entry_id == "r1"
