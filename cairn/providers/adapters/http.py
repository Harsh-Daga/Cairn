"""Async HTTP provider adapters (R5)."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from cairn.model.messages import CompletionRequest, CompletionResult, Message, TextBlock, TokenUsage
from cairn.providers.adapters.retry_policies import (
    compute_backoff,
    is_fatal_status,
    retry_policy_for,
)
from cairn.providers.capabilities import ProviderCapability, chat_endpoint, get, strip_model_prefix
from cairn.providers.completion import ensure_usable_completion
from cairn.providers.credentials import ResolvedCredentials, require_api_key
from cairn.util.tokens import estimate_tokens_from_request


def _messages_to_openai(messages: tuple[Message, ...]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for msg in messages:
        text = "".join(block.text for block in msg.content if isinstance(block, TextBlock))
        out.append({"role": msg.role, "content": text})
    return out


def _messages_to_anthropic(
    messages: tuple[Message, ...],
) -> tuple[str | None, list[dict[str, str]]]:
    system: str | None = None
    out: list[dict[str, str]] = []
    for msg in messages:
        text = "".join(block.text for block in msg.content if isinstance(block, TextBlock))
        if msg.role == "system":
            system = text
        else:
            out.append({"role": msg.role, "content": text})
    return system, out


class HttpProvider:
    def __init__(
        self,
        provider: str,
        creds: ResolvedCredentials,
        *,
        timeout_s: float = 120.0,
    ) -> None:
        self.name = provider
        self._provider = provider
        self._creds = creds
        self._timeout = timeout_s
        self._cap = get(provider)

    def estimate_tokens(self, request: CompletionRequest) -> int:
        return estimate_tokens_from_request(request)

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        cap = self._cap or ProviderCapability(
            name=self._provider,
            default_base_url=self._creds.base_url,
        )
        policy = retry_policy_for(self._provider)
        attempt = 0
        last_exc: Exception | None = None
        while attempt < 6:
            attempt += 1
            try:
                return await self._do_complete(request, cap)
            except httpx.TimeoutException as exc:
                last_exc = exc
                if not policy.retry_timeouts or attempt >= 5:
                    raise
                await asyncio.sleep(min(30.0, 2 ** attempt))
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if is_fatal_status(status):
                    raise
                rule = next((r for r in policy.rules if status in r.status_codes), None)
                if rule is None and policy.retry_5xx and 500 <= status < 600:
                    rule = policy.rules[-1] if policy.rules else None
                if rule is None or attempt >= rule.max_attempts:
                    raise
                headers = {k: v for k, v in exc.response.headers.items()}
                delay = compute_backoff(rule, attempt, headers)
                await asyncio.sleep(delay)
                last_exc = exc
        if last_exc:
            raise last_exc
        msg = "request failed after retries"
        raise RuntimeError(msg)

    async def _do_complete(
        self,
        request: CompletionRequest,
        cap: ProviderCapability,
    ) -> CompletionResult:
        api_key = self._creds.api_key
        if cap.api_style != "ollama-native" and cap.name not in ("ollama",):
            api_key = require_api_key(self._creds, self._provider)
        endpoint = chat_endpoint(self._creds.base_url, cap.api_style)
        wire_model = strip_model_prefix(request.model, cap)
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            if cap.api_style == "anthropic-messages":
                key = require_api_key(self._creds, self._provider)
                result = await self._anthropic(client, endpoint, key, wire_model, request)
            elif cap.api_style == "ollama-native":
                result = await self._ollama(client, endpoint, wire_model, request)
            else:
                result = await self._openai(client, endpoint, api_key, wire_model, request)
            return ensure_usable_completion(result)

    async def _openai(
        self,
        client: httpx.AsyncClient,
        endpoint: str,
        api_key: str | None,
        model: str,
        request: CompletionRequest,
    ) -> CompletionResult:
        payload: dict[str, Any] = {
            "model": model,
            "messages": _messages_to_openai(request.messages),
            "stream": False,
            **{k: v for k, v in request.params.items() if k in ("temperature", "max_tokens")},
        }
        headers: dict[str, str] = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        response = await client.post(endpoint, headers=headers, json=payload)
        response.raise_for_status()
        body = response.json()
        choice = body["choices"][0]
        message = choice["message"]
        content = message.get("content") or ""
        usage = body.get("usage", {})
        return CompletionResult(
            text=str(content),
            usage=TokenUsage(
                input_tokens=int(usage.get("prompt_tokens", 0)),
                output_tokens=int(usage.get("completion_tokens", 0)),
            ),
            raw=body,
            finish_reason=str(choice.get("finish_reason"))
            if choice.get("finish_reason") is not None
            else None,
        )

    async def _anthropic(
        self,
        client: httpx.AsyncClient,
        endpoint: str,
        api_key: str,
        model: str,
        request: CompletionRequest,
    ) -> CompletionResult:
        system, messages = _messages_to_anthropic(request.messages)
        payload: dict[str, Any] = {
            "model": model,
            "max_tokens": int(request.params.get("max_tokens", 1024)),
            "messages": messages,
        }
        if system:
            payload["system"] = system
        if "temperature" in request.params:
            payload["temperature"] = request.params["temperature"]
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        response = await client.post(endpoint, headers=headers, json=payload)
        response.raise_for_status()
        body = response.json()
        blocks = body.get("content", [])
        text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        usage = body.get("usage", {})
        return CompletionResult(
            text=text,
            usage=TokenUsage(
                input_tokens=int(usage.get("input_tokens", 0)),
                output_tokens=int(usage.get("output_tokens", 0)),
            ),
            raw=body,
            finish_reason=str(body.get("stop_reason"))
            if body.get("stop_reason") is not None
            else None,
        )

    async def _ollama(
        self,
        client: httpx.AsyncClient,
        endpoint: str,
        model: str,
        request: CompletionRequest,
    ) -> CompletionResult:
        payload: dict[str, Any] = {
            "model": model,
            "messages": _messages_to_openai(request.messages),
            "stream": False,
            "options": {
                "temperature": request.params.get("temperature", 0.0),
                "num_predict": request.params.get("max_tokens", 1024),
            },
        }
        response = await client.post(endpoint, json=payload)
        response.raise_for_status()
        body = response.json()
        message = body.get("message", {})
        content = message.get("content") or ""
        done = body.get("done_reason") or body.get("finish_reason")
        return CompletionResult(
            text=str(content),
            usage=TokenUsage(
                input_tokens=int(body.get("prompt_eval_count", 0)),
                output_tokens=int(body.get("eval_count", 0)),
            ),
            raw=body,
            finish_reason=str(done) if done is not None else None,
        )
