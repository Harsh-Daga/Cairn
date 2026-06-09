"""Provider capability registry (R18.1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

CacheMode = Literal["none", "auto-prefix", "explicit-breakpoint", "explicit-context"]


@dataclass(frozen=True)
class RateLimitSemantics:
    retry_after_header: str = "retry-after"
    request_limit_header: str | None = None
    request_remaining_header: str | None = None
    token_limit_header: str | None = None
    token_remaining_header: str | None = None


@dataclass(frozen=True)
class ProviderCapability:
    name: str
    default_base_url: str
    supported_models: tuple[str, ...] = ()
    max_context_tokens: int = 128_000
    max_output_tokens: int = 8_192
    api_style: Literal[
        "openai-chat",
        "anthropic-messages",
        "ollama-native",
        "gemini-generate",
    ] = "openai-chat"
    cache_mode: CacheMode = "none"
    rate_limits: RateLimitSemantics = field(default_factory=RateLimitSemantics)
    wire_model_strip_prefixes: tuple[str, ...] = ()
    reasoning: bool = False


_REGISTRY: dict[str, ProviderCapability] = {}
_BUILTIN_LOADED = False


def _register_defaults() -> None:
    global _BUILTIN_LOADED
    if _BUILTIN_LOADED:
        return
    defaults: list[ProviderCapability] = [
        ProviderCapability(
            name="openai",
            default_base_url="https://api.openai.com",
            supported_models=("gpt-4o", "gpt-4o-mini", "gpt-4.1", "o3-mini"),
            rate_limits=RateLimitSemantics(
                request_limit_header="x-ratelimit-limit-requests",
                request_remaining_header="x-ratelimit-remaining-requests",
            ),
        ),
        ProviderCapability(
            name="anthropic",
            default_base_url="https://api.anthropic.com",
            supported_models=("claude-sonnet-4-6", "claude-opus-4-6", "claude-haiku-4-5"),
            api_style="anthropic-messages",
            cache_mode="explicit-breakpoint",
            rate_limits=RateLimitSemantics(retry_after_header="retry-after"),
        ),
        ProviderCapability(
            name="ollama",
            default_base_url="http://127.0.0.1:11434",
            api_style="ollama-native",
            wire_model_strip_prefixes=("ollama/",),
        ),
        ProviderCapability(
            name="ollama-cloud",
            default_base_url="https://ollama.com",
            api_style="openai-chat",
            supported_models=("kimi-k2.6:cloud",),
            wire_model_strip_prefixes=("ollama-cloud/", "ollama/"),
            rate_limits=RateLimitSemantics(retry_after_header="retry-after"),
            reasoning=True,
        ),
        ProviderCapability(
            name="groq",
            default_base_url="https://api.groq.com/openai",
            supported_models=("llama-3.3-70b-versatile",),
        ),
        ProviderCapability(
            name="gemini",
            default_base_url="https://generativelanguage.googleapis.com",
            supported_models=("gemini-2.0-flash", "gemini-2.5-pro", "gemini-1.5-pro"),
            api_style="gemini-generate",
            wire_model_strip_prefixes=("gemini/", "google/"),
        ),
        ProviderCapability(
            name="openrouter",
            default_base_url="https://openrouter.ai/api",
            supported_models=(),
            wire_model_strip_prefixes=("openrouter/",),
        ),
    ]
    for cap in defaults:
        _REGISTRY[cap.name] = cap
    _BUILTIN_LOADED = True


def register(capability: ProviderCapability) -> None:
    _register_defaults()
    _REGISTRY[capability.name] = capability


def get(provider: str) -> ProviderCapability | None:
    _register_defaults()
    return _REGISTRY.get(provider)


def infer_provider(model: str) -> str:
    lowered = model.lower()
    if lowered.startswith("openrouter/"):
        return "openrouter"
    if lowered.startswith("gemini/") or lowered.startswith("google/") or lowered.startswith(
        "gemini-"
    ):
        return "gemini"
    if lowered.startswith("ollama-cloud/"):
        return "ollama-cloud"
    if lowered.startswith("ollama/"):
        return "ollama"
    if lowered.startswith("claude"):
        return "anthropic"
    if lowered.startswith("gpt-") or lowered.startswith("o"):
        return "openai"
    return "openai-compatible"


def strip_model_prefix(model: str, capability: ProviderCapability) -> str:
    for prefix in capability.wire_model_strip_prefixes:
        if model.lower().startswith(prefix.lower()):
            return model[len(prefix) :]
    return model


def chat_endpoint(base_url: str, api_style: str) -> str:
    root = base_url.rstrip("/")
    if api_style == "ollama-native":
        return f"{root}/api/chat"
    if api_style == "anthropic-messages":
        return f"{root}/v1/messages"
    if root.endswith("/api"):
        root = root[: -len("/api")]
    if root.endswith("/v1"):
        return f"{root}/chat/completions"
    return f"{root}/v1/chat/completions"
