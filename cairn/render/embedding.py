"""Escape JSON for safe embedding inside HTML <script> blocks (embedding-only)."""

from __future__ import annotations

# Applied only when inlining into index.html — canonical_json stays byte-stable for hashing.


def escape_json_for_html_embedding(json_str: str) -> str:
    """Escape HTML-significant and JS-line-separator chars in serialized JSON.

    The result remains valid JSON; parsers decode \\uXXXX escapes to the original
    characters. No literal <, >, or & remain in the embedded string.
    """
    return (
        json_str.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
