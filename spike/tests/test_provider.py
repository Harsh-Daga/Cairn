"""Provider adapter tests (offline)."""

from __future__ import annotations

import pytest

from spike.provider import (
    OLLAMA_CLOUD_DEFAULT_BASE_URL,
    OLLAMA_CLOUD_OPENAI_BASE_URL,
    CompletionRequest,
    MockProvider,
    OllamaCloudProvider,
    create_provider,
    ollama_cloud_chat_endpoint,
    strip_provider_prefix,
)


def test_ollama_cloud_default_urls_match_lattice() -> None:
    assert OLLAMA_CLOUD_DEFAULT_BASE_URL == "https://ollama.com"
    assert OLLAMA_CLOUD_OPENAI_BASE_URL == "https://ollama.com/v1"


def test_ollama_cloud_chat_endpoint() -> None:
    assert (
        ollama_cloud_chat_endpoint("https://ollama.com")
        == "https://ollama.com/v1/chat/completions"
    )
    assert (
        ollama_cloud_chat_endpoint("https://ollama.com/v1")
        == "https://ollama.com/v1/chat/completions"
    )
    assert (
        ollama_cloud_chat_endpoint("https://ollama.com/api")
        == "https://ollama.com/v1/chat/completions"
    )


def test_strip_provider_prefix() -> None:
    assert strip_provider_prefix("ollama-cloud/kimi-k2.6:cloud") == "kimi-k2.6:cloud"
    assert strip_provider_prefix("ollama/llama3.2") == "llama3.2"
    assert strip_provider_prefix("gpt-4o-mini") == "gpt-4o-mini"


def test_create_provider_names() -> None:
    assert create_provider("mock").name == "mock"
    assert create_provider("ollama-cloud").name == "ollama-cloud"
    assert create_provider("ollama").name == "ollama"
    assert create_provider("openai").name == "openai"


def test_create_provider_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="Unknown provider"):
        create_provider("anthropic")


def test_ollama_cloud_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OLLAMA_CLOUD_API_KEY", raising=False)
    provider = OllamaCloudProvider()
    with pytest.raises(RuntimeError, match="OLLAMA_CLOUD_API_KEY"):
        provider.complete(
            CompletionRequest(
                model="ollama-cloud/kimi-k2.6:cloud",
                system="s",
                user="u",
                temperature=0.0,
                max_tokens=10,
            )
        )


def test_mock_provider_is_deterministic() -> None:
    provider = MockProvider()
    req = CompletionRequest(
        model="ollama-cloud/kimi-k2.6:cloud",
        system="system",
        user="user",
        temperature=0.0,
        max_tokens=100,
    )
    first = provider.complete(req)
    second = provider.complete(req)
    assert first.text == second.text
