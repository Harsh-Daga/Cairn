"""Provider adapters for the spike — HTTP (real) and mock (tests)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

# Lattice ``capabilities.py`` default for ``ollama-cloud``; OpenAI-compat lives at ``/v1``.
OLLAMA_CLOUD_DEFAULT_BASE_URL = "https://ollama.com"
OLLAMA_CLOUD_OPENAI_BASE_URL = f"{OLLAMA_CLOUD_DEFAULT_BASE_URL}/v1"


@dataclass(frozen=True)
class CompletionRequest:
    model: str
    system: str
    user: str
    temperature: float
    max_tokens: int


@dataclass(frozen=True)
class CompletionResult:
    text: str
    input_tokens: int
    output_tokens: int


class Provider(Protocol):
    name: str

    def complete(self, request: CompletionRequest) -> CompletionResult: ...


def strip_provider_prefix(model: str) -> str:
    """Strip ``ollama-cloud/`` or ``ollama/`` before sending to the wire."""
    lowered = model.lower()
    for prefix in ("ollama-cloud/", "ollama/"):
        if lowered.startswith(prefix):
            return model[len(prefix) :]
    return model


def _require_env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        msg = (
            f"Missing credential: set environment variable {name!r} "
            "(secrets from env only — R3)"
        )
        raise RuntimeError(msg)
    return value


def ollama_cloud_chat_endpoint(base_url: str) -> str:
    """OpenAI-compat chat URL for Ollama Cloud.

    Matches Lattice: host ``https://ollama.com`` → ``…/v1/chat/completions``.
    Also accepts ``https://ollama.com/v1`` (agent ``baseURL`` style). Normalizes the
    native API root ``https://ollama.com/api`` so it does not become ``…/api/v1/…``.
    """
    root = base_url.rstrip("/")
    if root.endswith("/api"):
        root = root[: -len("/api")]
    if root.endswith("/v1"):
        return f"{root}/chat/completions"
    return f"{root}/v1/chat/completions"


def _openai_chat_endpoint(base_url: str) -> str:
    root = base_url.rstrip("/")
    if root.endswith("/v1"):
        return f"{root}/chat/completions"
    return f"{root}/v1/chat/completions"


def _post_chat_completion(
    *,
    endpoint: str,
    api_key: str | None,
    request: CompletionRequest,
    timeout_s: float,
    wire_model: str | None = None,
) -> CompletionResult:
    model = wire_model if wire_model is not None else request.model
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": request.system},
            {"role": "user", "content": request.user},
        ],
        "temperature": request.temperature,
        "max_tokens": request.max_tokens,
        "stream": False,
    }
    headers: dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    with httpx.Client(timeout=timeout_s) as client:
        response = client.post(endpoint, headers=headers, json=payload)
        response.raise_for_status()
        body = response.json()
    message = body["choices"][0]["message"]
    content = message.get("content") or ""
    if not content and message.get("thinking"):
        content = str(message["thinking"])
    usage = body.get("usage", {})
    return CompletionResult(
        text=content,
        input_tokens=int(usage.get("prompt_tokens", 0)),
        output_tokens=int(usage.get("completion_tokens", 0)),
    )


def _openai_chat_complete(
    *,
    base_url: str,
    api_key: str | None,
    request: CompletionRequest,
    timeout_s: float,
    wire_model: str | None = None,
) -> CompletionResult:
    """POST ``/v1/chat/completions`` (OpenAI-compatible)."""
    return _post_chat_completion(
        endpoint=_openai_chat_endpoint(base_url),
        api_key=api_key,
        request=request,
        timeout_s=timeout_s,
        wire_model=wire_model,
    )


def _ollama_native_complete(
    *,
    base_url: str,
    api_key: str | None,
    request: CompletionRequest,
    timeout_s: float,
) -> CompletionResult:
    """POST ``/api/chat`` (local Ollama native API)."""
    payload: dict[str, Any] = {
        "model": strip_provider_prefix(request.model),
        "messages": [
            {"role": "system", "content": request.system},
            {"role": "user", "content": request.user},
        ],
        "stream": False,
        "options": {
            "temperature": request.temperature,
            "num_predict": request.max_tokens,
        },
    }
    headers: dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    endpoint = f"{base_url.rstrip('/')}/api/chat"
    with httpx.Client(timeout=timeout_s) as client:
        response = client.post(endpoint, headers=headers, json=payload)
        response.raise_for_status()
        body = response.json()
    message = body.get("message", {})
    content = message.get("content") or message.get("thinking") or ""
    return CompletionResult(
        text=str(content),
        input_tokens=int(body.get("prompt_eval_count", 0)),
        output_tokens=int(body.get("eval_count", 0)),
    )


class MockProvider:
    """Deterministic provider for offline tests."""

    name = "mock"

    def complete(self, request: CompletionRequest) -> CompletionResult:
        digest = abs(hash((request.system, request.user, request.model))) % 10_000
        text = f"[mock:{digest}] {request.user[:80]}"
        return CompletionResult(text=text, input_tokens=42, output_tokens=17)


class OpenAICompatibleProvider:
    """HTTP chat provider against an OpenAI-compatible endpoint (R5 subset)."""

    name = "openai"

    def __init__(
        self,
        *,
        api_key_env: str = "OPENAI_API_KEY",
        base_url: str = "https://api.openai.com",
        timeout_s: float = 120.0,
    ) -> None:
        self.api_key_env = api_key_env
        self.base_url = base_url
        self.timeout_s = timeout_s

    def complete(self, request: CompletionRequest) -> CompletionResult:
        api_key = _require_env(self.api_key_env)
        return _openai_chat_complete(
            base_url=self.base_url,
            api_key=api_key,
            request=request,
            timeout_s=self.timeout_s,
        )


class OllamaCloudProvider:
    """Ollama Cloud — OpenAI-compatible ``/v1/chat/completions`` at ollama.com."""

    name = "ollama-cloud"

    def __init__(
        self,
        *,
        api_key_env: str = "OLLAMA_CLOUD_API_KEY",
        base_url_env: str = "OLLAMA_CLOUD_BASE_URL",
        default_base_url: str = OLLAMA_CLOUD_DEFAULT_BASE_URL,
        timeout_s: float = 180.0,
    ) -> None:
        self.api_key_env = api_key_env
        self.base_url_env = base_url_env
        self.default_base_url = default_base_url
        self.timeout_s = timeout_s

    def complete(self, request: CompletionRequest) -> CompletionResult:
        api_key = _require_env(self.api_key_env)
        base_url = os.environ.get(self.base_url_env, self.default_base_url)
        return _post_chat_completion(
            endpoint=ollama_cloud_chat_endpoint(base_url),
            api_key=api_key,
            request=request,
            timeout_s=self.timeout_s,
            wire_model=strip_provider_prefix(request.model),
        )


class OllamaProvider:
    """Local Ollama — native ``/api/chat`` endpoint."""

    name = "ollama"

    def __init__(
        self,
        *,
        base_url_env: str = "OLLAMA_HOST",
        default_base_url: str = "http://127.0.0.1:11434",
        timeout_s: float = 180.0,
    ) -> None:
        self.base_url_env = base_url_env
        self.default_base_url = default_base_url
        self.timeout_s = timeout_s

    def complete(self, request: CompletionRequest) -> CompletionResult:
        base_url = os.environ.get(self.base_url_env, self.default_base_url)
        return _ollama_native_complete(
            base_url=base_url,
            api_key=None,
            request=request,
            timeout_s=self.timeout_s,
        )


_PROVIDER_FACTORIES: dict[str, type[object]] = {
    "mock": MockProvider,
    "openai": OpenAICompatibleProvider,
    "ollama-cloud": OllamaCloudProvider,
    "ollama": OllamaProvider,
}


def create_provider(name: str = "ollama-cloud") -> Provider:
    """Construct a spike provider by name."""
    factory = _PROVIDER_FACTORIES.get(name)
    if factory is None:
        allowed = ", ".join(sorted(_PROVIDER_FACTORIES))
        msg = f"Unknown provider {name!r}; expected one of: {allowed}"
        raise ValueError(msg)
    instance = factory()
    assert isinstance(
        instance,
        (MockProvider, OpenAICompatibleProvider, OllamaCloudProvider, OllamaProvider),
    )
    return instance
