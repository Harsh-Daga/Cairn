"""Prompt loading with YAML front matter (ADR 0005)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from cairn.model.project import Prompt

_FRONT_MATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_BEHAVIOR_KEYS = frozenset({"model", "params", "temperature", "max_tokens"})


def _parse_front_matter(block: str) -> dict[str, Any]:
    if not block.strip():
        return {}
    data = yaml.safe_load(block)
    if data is None:
        return {}
    if not isinstance(data, dict):
        msg = "prompt front matter must be a YAML mapping"
        raise ValueError(msg)
    return {str(k): v for k, v in data.items()}


def split_front_matter(text: str) -> tuple[dict[str, Any], str]:
    match = _FRONT_MATTER_RE.match(text)
    if not match:
        return {}, text
    front_matter = _parse_front_matter(match.group(1))
    body = text[match.end() :]
    return front_matter, body


def _extract_overrides(front_matter: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
    model_override = front_matter.get("model")
    model = str(model_override) if model_override is not None else None
    params: dict[str, Any] = {}
    if "params" in front_matter and isinstance(front_matter["params"], dict):
        params.update(front_matter["params"])
    for key in ("temperature", "max_tokens"):
        if key in front_matter:
            params[key] = front_matter[key]
    return model, params


def load_prompt(path: Path, project_root: Path) -> Prompt:
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    front_matter, body = split_front_matter(text)
    model_override, params_override = _extract_overrides(front_matter)
    rel = str(path.relative_to(project_root))
    return Prompt(
        path=rel,
        template_body=body,
        template_body_bytes=body.encode("utf-8"),
        front_matter=front_matter,
        model_override=model_override,
        params_override=params_override,
    )


def render_template(template_body: str, context: dict[str, Any]) -> str:
    import jinja2

    env = jinja2.Environment(
        undefined=jinja2.StrictUndefined,
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    return env.from_string(template_body).render(**context)
