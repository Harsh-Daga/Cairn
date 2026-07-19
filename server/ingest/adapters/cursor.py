"""Compatibility facade for Cursor discovery, decoding, and normalization stages."""

from server.ingest.adapters.cursor_models import (
    ParsedCursorSession as ParsedCursorSession,
)
from server.ingest.adapters.cursor_models import (
    normalize_cursor_tool_name as normalize_cursor_tool_name,
)
from server.ingest.adapters.cursor_transcript import (
    parse_transcript_file as parse_transcript_file,
)
from server.ingest.adapters.cursor_vscdb import (
    locate_cursor_vscdb as locate_cursor_vscdb,
)
from server.ingest.adapters.cursor_vscdb import (
    parse_cursor_vscdb as parse_cursor_vscdb,
)

__all__ = [
    "ParsedCursorSession",
    "locate_cursor_vscdb",
    "normalize_cursor_tool_name",
    "parse_cursor_vscdb",
    "parse_transcript_file",
]
