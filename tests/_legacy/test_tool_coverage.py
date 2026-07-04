"""Tool normalization coverage — every parser tool must map (Phase 0)."""

from __future__ import annotations

from cairn.metrics.constants import PARSER_TOOL_NAMES, is_mapped_tool


def test_all_parser_tools_are_mapped() -> None:
    unmapped: list[str] = []
    for name in sorted(PARSER_TOOL_NAMES):
        for source in (
            "claude-code",
            "codex",
            "cursor",
            "hermes",
            "aider",
            "opencode",
            "goose",
        ):
            if not is_mapped_tool(name, source=source):
                unmapped.append(f"{source}:{name}")
                break
    assert not unmapped, f"unmapped parser tools: {unmapped}"
