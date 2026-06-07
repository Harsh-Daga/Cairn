"""Unit tests for escape_json_for_html_embedding."""

from __future__ import annotations

import json

from cairn.render.embedding import escape_json_for_html_embedding
from cairn.util.canonical import canonical_json


def test_canonical_json_unchanged_by_embedding_escaper_on_safe_content() -> None:
    obj = {"safe": "hello", "n": 1}
    raw = canonical_json(obj)
    escaped = escape_json_for_html_embedding(raw)
    assert json.loads(escaped) == obj
    assert raw == escaped
