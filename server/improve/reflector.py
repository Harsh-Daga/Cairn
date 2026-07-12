"""Tier 2 reflector: turn an evidence pack into managed-block proposals via an LLM."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx2 as httpx

from server.improve.evidence_pack import EvidencePack

TIMEOUT_S = 120

_CLI_BACKENDS: tuple[tuple[str, str, list[str]], ...] = (
    ("claude-cli", "claude", ["-p", "--output-format", "json"]),
    ("codex-cli", "codex", ["exec", "--sandbox", "read-only", "-"]),
    ("gemini-cli", "gemini", ["-p", "--output-format", "json"]),
)

_PROVIDER_ENV: dict[str, tuple[str, str, str]] = {
    "provider:anthropic": (
        "ANTHROPIC_API_KEY",
        "https://api.anthropic.com",
        "claude-3-5-sonnet-latest",
    ),
    "provider:openai": ("OPENAI_API_KEY", "https://api.openai.com/v1", "gpt-4o-mini"),
    "provider:ollama": ("", "http://127.0.0.1:11434", "llama3.2"),
}


@dataclass
class BackendResult:
    backend: str
    ok: bool
    text: str = ""
    error: str | None = None


def resolve_backend(override: str | None = None) -> str | None:
    """Return the backend to use, or None if nothing is available."""
    if override:
        return override
    for name, exe, _ in _CLI_BACKENDS:
        if shutil.which(exe):
            return name
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "provider:anthropic"
    if os.environ.get("OPENAI_API_KEY"):
        return "provider:openai"
    ollama_host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
    if os.environ.get("OLLAMA_HOST") or shutil.which("ollama"):
        model = os.environ.get("CAIRN_LLM_MODEL", "llama3.2")
        return f"provider:ollama|{ollama_host.rstrip('/')}|{model}"
    if os.environ.get("CAIRN_LLM_BASE_URL"):
        return "provider:http"
    return None


def run_backend(name: str, prompt: str, *, timeout: int = TIMEOUT_S) -> BackendResult:
    """Run a backend with ``prompt`` on stdin and return its final text message."""
    if name.startswith("provider:"):
        return _run_provider(name, prompt, timeout=timeout)
    spec = next((s for s in _CLI_BACKENDS if s[0] == name), None)
    if spec is None:
        return BackendResult(backend=name, ok=False, error=f"unknown backend {name!r}")
    _, exe, args = spec
    if shutil.which(exe) is None:
        return BackendResult(backend=name, ok=False, error=f"{exe} not on PATH")
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [exe, *args],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return BackendResult(backend=name, ok=False, error="timeout")
    except OSError as exc:
        return BackendResult(backend=name, ok=False, error=str(exc))
    if proc.returncode != 0:
        return BackendResult(backend=name, ok=False, error=proc.stderr.strip()[:500])
    return BackendResult(backend=name, ok=True, text=_extract_text(proc.stdout))


def _extract_text(stdout: str) -> str:
    stripped = stdout.strip()
    if stripped.startswith("{"):
        try:
            obj = json.loads(stripped)
        except json.JSONDecodeError:
            return stripped
        for key in ("result", "response", "text", "content", "message"):
            val = obj.get(key)
            if isinstance(val, str):
                return val
        return stripped
    return stripped


def _provider_config(name: str) -> tuple[str, str, str, str] | None:
    """Return (api_style, base_or_url, model, api_key) for a provider backend."""
    if name in ("provider:http", "provider:openai"):
        base = os.environ.get("CAIRN_LLM_BASE_URL")
        if name == "provider:openai" and not base:
            base = _PROVIDER_ENV["provider:openai"][1]
        if not base:
            return None
        model = os.environ.get("CAIRN_LLM_MODEL", "gpt-4o-mini")
        key = os.environ.get("OPENAI_API_KEY", os.environ.get("CAIRN_LLM_API_KEY", ""))
        return ("openai", base, model, key)
    if name == "provider:anthropic":
        key = os.environ.get("ANTHROPIC_API_KEY", os.environ.get("CAIRN_LLM_API_KEY", ""))
        if not key:
            return None
        model = os.environ.get("CAIRN_LLM_MODEL", _PROVIDER_ENV["provider:anthropic"][2])
        return ("anthropic", _PROVIDER_ENV["provider:anthropic"][1], model, key)
    spec = name[len("provider:") :]
    if spec == "ollama":
        host = os.environ.get("OLLAMA_HOST", _PROVIDER_ENV["provider:ollama"][1])
        model = os.environ.get("CAIRN_LLM_MODEL", _PROVIDER_ENV["provider:ollama"][2])
        return ("ollama", host.rstrip("/"), model, "")
    if "|" in spec:
        provider_kind, rest = spec.split("|", 1)
        if provider_kind == "ollama" and "|" in rest:
            host, model = rest.split("|", 1)
            return ("ollama", host.rstrip("/"), model, "")
        default_model = os.environ.get("CAIRN_LLM_MODEL", "gpt-4o-mini")
        base, model = rest.split("|", 1) if "|" in rest else (rest, default_model)
        if provider_kind in ("anthropic", "openai", "ollama"):
            key_env = _PROVIDER_ENV.get(f"provider:{provider_kind}", ("", "", ""))[0]
            fallback_key = os.environ.get("CAIRN_LLM_API_KEY", "")
            key = os.environ.get(key_env, fallback_key) if key_env else ""
            return (provider_kind, base, model, key)
        return ("openai", base, model, os.environ.get("CAIRN_LLM_API_KEY", ""))
    if not spec:
        return None
    base = spec
    model = os.environ.get("CAIRN_LLM_MODEL", "gpt-4o-mini")
    return ("openai", base, model, os.environ.get("CAIRN_LLM_API_KEY", ""))


def _run_provider(name: str, prompt: str, *, timeout: int) -> BackendResult:
    cfg = _provider_config(name)
    if cfg is None:
        return BackendResult(backend=name, ok=False, error="provider not configured")
    api_style, base, model, key = cfg
    system = "You are Cairn's optimization reflector. Output valid JSON only."
    try:
        if api_style == "anthropic":
            text = _anthropic_chat(base, model, key, system, prompt, timeout=timeout)
        elif api_style == "ollama":
            text = _ollama_chat(base, model, system, prompt, timeout=timeout)
        else:
            text = _openai_chat(base, model, key, system, prompt, timeout=timeout)
    except httpx.HTTPError as exc:
        return BackendResult(backend=name, ok=False, error=f"httpx request failed: {exc}")
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        return BackendResult(backend=name, ok=False, error=f"malformed response: {exc}")
    return BackendResult(backend=name, ok=True, text=text)


def _openai_chat(
    base: str, model: str, key: str, system: str, prompt: str, *, timeout: int
) -> str:
    url = base.rstrip("/")
    if not url.endswith("/chat/completions"):
        url = url + "/chat/completions"
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
    }
    resp = httpx.post(url, json=payload, headers=headers, timeout=timeout)
    if resp.status_code != 200:
        raise httpx.HTTPStatusError(
            f"HTTP {resp.status_code}", request=resp.request, response=resp
        )
    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    return str(content)


def _anthropic_chat(
    base: str, model: str, key: str, system: str, prompt: str, *, timeout: int
) -> str:
    url = base.rstrip("/") + "/v1/messages"
    headers = {
        "Content-Type": "application/json",
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
    }
    payload = {
        "model": model,
        "max_tokens": 4096,
        "system": system,
        "messages": [{"role": "user", "content": prompt}],
    }
    resp = httpx.post(url, json=payload, headers=headers, timeout=timeout)
    if resp.status_code != 200:
        raise httpx.HTTPStatusError(
            f"HTTP {resp.status_code}", request=resp.request, response=resp
        )
    data = resp.json()
    blocks = data["content"]
    parts = [str(b.get("text", "")) for b in blocks if isinstance(b, dict)]
    return "".join(parts)


def _ollama_chat(base: str, model: str, system: str, prompt: str, *, timeout: int) -> str:
    url = base.rstrip("/") + "/api/chat"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
    }
    resp = httpx.post(url, json=payload, timeout=timeout)
    if resp.status_code != 200:
        raise httpx.HTTPStatusError(
            f"HTTP {resp.status_code}", request=resp.request, response=resp
        )
    data = resp.json()
    return str(data["message"]["content"])


_PROMPT_PATH = Path(__file__).parent / "reflector_prompt.md"
MAX_PROPOSALS = 10
_VALID_OPS = {"add", "update", "remove"}
_VALID_KINDS = {"file_guide", "known_issue", "command_fix", "repo_map", "rule"}


@dataclass
class Proposal:
    op: str
    kind: str
    entry_id: str
    content: str
    rationale: str = ""
    confidence: float = 0.8
    evidence_refs: list[str] = field(default_factory=list)


class ReflectorError(Exception):
    """Raised when the backend cannot produce valid proposals."""


def resolve_evidence(
    proposal: Proposal, pack: EvidencePack | None = None
) -> dict[str, Any]:
    """Convert evidence_refs into a measurable evidence dict.

    When ``pack`` is supplied, unknown ``evidence_refs`` raise ``ReflectorError``.
    """
    refs = proposal.evidence_refs
    if pack is not None and refs:
        known = pack.known_refs()
        unknown = [r for r in refs if r not in known]
        if unknown:
            raise ReflectorError(f"unknown evidence refs: {unknown}")

    kind = proposal.kind
    if kind == "file_guide":
        first_path = refs[0] if refs else ""
        return {"path": first_path}
    if kind in ("command_fix", "known_issue"):
        first_ref = refs[0] if refs else ""
        return {"bad": first_ref, "name": first_ref, "tool_name": first_ref}
    if kind == "repo_map":
        return {"dirs": refs}
    return {"refs": refs}


def load_prompt_template() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def build_prompt(current_block: str, pack: EvidencePack) -> str:
    return (
        load_prompt_template()
        + "\n\n## Current managed block\n"
        + (current_block or "(empty)")
        + "\n\n## Evidence\n"
        + pack.to_json()
        + "\n"
    )


def parse_proposals(text: str) -> list[Proposal]:
    """Strict parse of the backend's JSON response into Proposals.

    Raises ReflectorError on malformed JSON or an unexpected shape.
    """
    try:
        obj = json.loads(text.strip())
    except json.JSONDecodeError as exc:
        raise ReflectorError(f"invalid JSON: {exc}") from exc
    if not isinstance(obj, dict) or not isinstance(obj.get("proposals"), list):
        raise ReflectorError("missing 'proposals' array")
    out: list[Proposal] = []
    for raw in obj["proposals"][:MAX_PROPOSALS]:
        if not isinstance(raw, dict):
            continue
        op = str(raw.get("op", "")).strip()
        kind = str(raw.get("kind", "")).strip()
        entry_id = str(raw.get("entry_id", "")).strip()
        content = str(raw.get("content", "")).strip()
        if op not in _VALID_OPS or kind not in _VALID_KINDS or not entry_id:
            continue
        if op != "remove" and not content:
            continue
        try:
            confidence = float(raw.get("confidence", 0.8))
        except (TypeError, ValueError):
            confidence = 0.8
        refs_raw = raw.get("evidence_refs", [])
        out.append(
            Proposal(
                op=op,
                kind=kind,
                entry_id=entry_id,
                content=content,
                rationale=str(raw.get("rationale", "")),
                confidence=max(0.0, min(1.0, confidence)),
                evidence_refs=[str(r) for r in refs_raw] if isinstance(refs_raw, list) else [],
            )
        )
    return out


def reflect(current_block: str, pack: EvidencePack, backend: str) -> list[Proposal]:
    """Run the reflector against ``backend``.

    Tries once, retries once appending a stricter instruction, then raises
    ReflectorError so the caller can fall back to Tier 1.
    """
    prompt = build_prompt(current_block, pack)
    result = run_backend(backend, prompt)
    _require_ok(result)
    try:
        return parse_proposals(result.text)
    except ReflectorError:
        pass

    retry = run_backend(backend, prompt + "\n\nOutput valid JSON only.")
    _require_ok(retry)
    return parse_proposals(retry.text)


def reflect_if_available(
    current_block: str,
    pack: EvidencePack,
    backend_override: str | None = None,
) -> list[Proposal]:
    """Run reflector when a backend exists; otherwise return an empty list."""
    backend = resolve_backend(backend_override)
    if backend is None:
        return []
    return reflect(current_block, pack, backend)


def _require_ok(result: BackendResult) -> None:
    if not result.ok:
        raise ReflectorError(result.error or "backend failed")
