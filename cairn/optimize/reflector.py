"""Tier 2 reflector: turn an evidence pack into managed-block proposals via an LLM."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cairn.optimize.evidence import EvidencePack

# --- LLM backends (folded from backends.py) ---------------------------------

TIMEOUT_S = 120

_CLI_BACKENDS: tuple[tuple[str, str, list[str]], ...] = (
    ("claude-cli", "claude", ["-p", "--output-format", "json"]),
    ("codex-cli", "codex", ["exec", "--sandbox", "read-only", "-"]),
    ("gemini-cli", "gemini", ["-p", "--output-format", "json"]),
)


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
    import json as _json

    stripped = stdout.strip()
    if stripped.startswith("{"):
        try:
            obj = _json.loads(stripped)
        except _json.JSONDecodeError:
            return stripped
        for key in ("result", "response", "text", "content", "message"):
            val = obj.get(key)
            if isinstance(val, str):
                return val
        return stripped
    return stripped


def _provider_config(name: str) -> tuple[str, str, str] | None:
    if name in ("provider:http", "provider:openai"):
        base = os.environ.get("CAIRN_LLM_BASE_URL")
        if not base:
            return None
        model = os.environ.get("CAIRN_LLM_MODEL", "gpt-4o-mini")
        return base, model, os.environ.get("CAIRN_LLM_API_KEY", "")
    spec = name[len("provider:") :]
    if "|" in spec:
        base, model = spec.split("|", 1)
    else:
        base, model = spec, os.environ.get("CAIRN_LLM_MODEL", "gpt-4o-mini")
    if not base:
        return None
    return base, model, os.environ.get("CAIRN_LLM_API_KEY", "")


def _run_provider(name: str, prompt: str, *, timeout: int) -> BackendResult:
    cfg = _provider_config(name)
    if cfg is None:
        return BackendResult(backend=name, ok=False, error="no CAIRN_LLM_BASE_URL configured")
    base, model, key = cfg
    try:
        import httpx
    except ImportError:
        return BackendResult(backend=name, ok=False, error="httpx not installed")
    url = base.rstrip("/")
    if not url.endswith("/chat/completions"):
        url = url + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You are Cairn's optimization reflector. Output valid JSON only.",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
    }
    try:
        resp = httpx.post(url, json=payload, headers=headers, timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        return BackendResult(backend=name, ok=False, error=f"httpx request failed: {exc}")
    if resp.status_code != 200:
        return BackendResult(
            backend=name, ok=False, error=f"HTTP {resp.status_code}: {resp.text[:300]}"
        )
    try:
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, ValueError) as exc:
        return BackendResult(backend=name, ok=False, error=f"malformed response: {exc}")
    return BackendResult(backend=name, ok=True, text=str(content))


# --- reflector --------------------------------------------------------------

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


def resolve_evidence(proposal: Proposal) -> dict[str, Any]:
    """Convert a reflector Proposal's evidence_refs into a measurable evidence dict.

    ``measure_metric`` expects keys like ``path``, ``bad``/``tool_name``/``name``, or
    nothing (for repo_map).  The LLM sometimes returns paths or command names in
    ``evidence_refs``; we map them based on the proposal kind.
    """
    refs = proposal.evidence_refs
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
        refs = raw.get("evidence_refs", [])
        out.append(
            Proposal(
                op=op,
                kind=kind,
                entry_id=entry_id,
                content=content,
                rationale=str(raw.get("rationale", "")),
                confidence=max(0.0, min(1.0, confidence)),
                evidence_refs=[str(r) for r in refs] if isinstance(refs, list) else [],
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
    return parse_proposals(retry.text)  # may raise ReflectorError -> caller falls to Tier 1


def _require_ok(result: BackendResult) -> None:
    if not result.ok:
        raise ReflectorError(result.error or "backend failed")
