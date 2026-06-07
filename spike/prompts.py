"""Prompt loading and Jinja rendering for the spike."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import jinja2

from spike.keys import PromptRef

_FRONT_MATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _parse_front_matter(text: str) -> tuple[dict[str, Any], str]:
    match = _FRONT_MATTER_RE.match(text)
    if not match:
        return {}, text
    block = match.group(1)
    body = text[match.end() :]
    front_matter: dict[str, Any] = {}
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped or ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        front_matter[key.strip()] = value.strip()
    return front_matter, body


def load_prompt(path: Path) -> PromptRef:
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    front_matter, body = _parse_front_matter(text)
    return PromptRef(path=str(path), body=raw, front_matter=front_matter)


def prompt_body(path: Path | PromptRef) -> str:
    """Return prompt template text without YAML front matter."""
    if isinstance(path, PromptRef):
        text = path.body.decode("utf-8")
        _, body = _parse_front_matter(text)
        return body
    text = path.read_text(encoding="utf-8")
    _, body = _parse_front_matter(text)
    return body


def render_prompt(template_text: str, context: dict[str, Any]) -> str:
    env = jinja2.Environment(
        undefined=jinja2.StrictUndefined,
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.from_string(template_text)
    return template.render(**context)
