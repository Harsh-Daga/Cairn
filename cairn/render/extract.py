"""Extract embedded cairn-data JSON from a rendered bundle."""

from __future__ import annotations

import json
from typing import Any

_CAIRN_DATA_OPEN = '<script type="application/json" id="cairn-data">'


def extract_cairn_data_json(html: str) -> str:
    """Return the raw JSON text inside the cairn-data script block."""
    start = html.find(_CAIRN_DATA_OPEN)
    if start == -1:
        msg = "cairn-data script block not found"
        raise ValueError(msg)
    content_start = start + len(_CAIRN_DATA_OPEN)
    end = html.find("</script>", content_start)
    if end == -1:
        msg = "cairn-data script block not closed"
        raise ValueError(msg)
    return html[content_start:end]


def parse_cairn_data(html: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(extract_cairn_data_json(html))
    return data
