"""Google Gemini generateContent request/response helpers."""

from __future__ import annotations

from typing import Any

from cairn.model.messages import CompletionRequest, Message, TextBlock


def messages_to_gemini(
    messages: tuple[Message, ...],
) -> tuple[str | None, list[dict[str, Any]]]:
    system: str | None = None
    contents: list[dict[str, Any]] = []
    for msg in messages:
        text = "".join(block.text for block in msg.content if isinstance(block, TextBlock))
        if msg.role == "system":
            system = text
            continue
        role = "user" if msg.role == "user" else "model"
        contents.append({"role": role, "parts": [{"text": text}]})
    return system, contents


def gemini_endpoint(base_url: str, model: str) -> str:
    root = base_url.rstrip("/")
    return f"{root}/v1beta/models/{model}:generateContent"


def parse_gemini_response(body: dict[str, Any]) -> tuple[str, int, int]:
    candidates = body.get("candidates", [])
    text = ""
    if candidates and isinstance(candidates[0], dict):
        parts = candidates[0].get("content", {}).get("parts", [])
        if isinstance(parts, list):
            text = "".join(
                str(p.get("text", "")) for p in parts if isinstance(p, dict) and "text" in p
            )
    usage = body.get("usageMetadata", {})
    input_tokens = int(usage.get("promptTokenCount", 0)) if isinstance(usage, dict) else 0
    output_tokens = int(usage.get("candidatesTokenCount", 0)) if isinstance(usage, dict) else 0
    return text, input_tokens, output_tokens


def build_gemini_payload(request: CompletionRequest) -> dict[str, Any]:
    system, contents = messages_to_gemini(request.messages)
    payload: dict[str, Any] = {
        "contents": contents,
        "generationConfig": {
            "temperature": request.params.get("temperature", 0.0),
            "maxOutputTokens": int(request.params.get("max_tokens", 1024)),
        },
    }
    if system:
        payload["systemInstruction"] = {"parts": [{"text": system}]}
    return payload
