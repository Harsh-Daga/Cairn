"""Phase 9 provider framework tests."""

from __future__ import annotations

from cairn.model.messages import CompletionRequest, Message, TextBlock
from cairn.providers.adapters.gemini import (
    build_gemini_payload,
    messages_to_gemini,
    parse_gemini_response,
)
from cairn.providers.capabilities import get, infer_provider
from cairn.providers.credentials import resolve_credentials


def test_infer_provider_gemini_and_openrouter() -> None:
    assert infer_provider("gemini-2.0-flash") == "gemini"
    assert infer_provider("gemini/gemini-2.0-flash") == "gemini"
    assert infer_provider("openrouter/anthropic/claude-3.5-sonnet") == "openrouter"


def test_gemini_capability_registered() -> None:
    cap = get("gemini")
    assert cap is not None
    assert cap.api_style == "gemini-generate"
    assert "gemini-2.0-flash" in cap.supported_models


def test_openrouter_capability_registered() -> None:
    cap = get("openrouter")
    assert cap is not None
    assert cap.default_base_url.endswith("/api")


def test_gemini_message_conversion() -> None:
    system, contents = messages_to_gemini(
        (
            Message(role="system", content=(TextBlock(text="Be concise"),)),
            Message(role="user", content=(TextBlock(text="Hello"),)),
        )
    )
    assert system == "Be concise"
    assert contents[0]["role"] == "user"
    assert contents[0]["parts"][0]["text"] == "Hello"


def test_build_gemini_payload() -> None:
    req = CompletionRequest(
        model="gemini-2.0-flash",
        messages=(Message(role="user", content=(TextBlock(text="Hi"),)),),
        params={"max_tokens": 256, "temperature": 0.1},
        provider="gemini",
    )
    payload = build_gemini_payload(req)
    assert payload["generationConfig"]["maxOutputTokens"] == 256
    assert payload["contents"][0]["parts"][0]["text"] == "Hi"


def test_parse_gemini_response() -> None:
    body = {
        "candidates": [{"content": {"parts": [{"text": "Done"}]}}],
        "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 3},
    }
    text, inp, out = parse_gemini_response(body)
    assert text == "Done"
    assert inp == 5
    assert out == 3


def test_resolve_credentials_env_names() -> None:
    gemini = resolve_credentials("gemini")
    openrouter = resolve_credentials("openrouter")
    assert gemini.key_env == "GEMINI_API_KEY"
    assert openrouter.key_env == "OPENROUTER_API_KEY"
