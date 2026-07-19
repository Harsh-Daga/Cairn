from __future__ import annotations

from server.analyze.tool_identity import classify_tool, percentile, tool_family
from server.api.payload_domains.files import is_ignored_path, scrub_path_rel
from server.ingest.constants import normalize_tool_name


def test_readfile_alias_normalizes_to_read() -> None:
    assert normalize_tool_name("ReadFile", source="cursor") == "read"
    assert classify_tool("ReadFile", source="cursor")[1:] == ("read", "builtin")


def test_tool_families_distinguish_mcp_shell_and_unknown() -> None:
    assert tool_family("mcp:docs/search", "mcp:docs/search") == "mcp"
    assert tool_family("bash", "Bash") == "shell"
    assert tool_family("custom_probe", "custom_probe") == "unknown"
    assert tool_family("edit", "Edit") == "builtin"


def test_percentile_nearest_rank() -> None:
    assert percentile([], 50) is None
    assert percentile([10], 95) == 10.0
    assert percentile([10, 20, 30, 40, 50], 50) == 30.0


def test_file_path_scrub_and_ignore_prefixes() -> None:
    assert scrub_path_rel("/Users/me/repo/server/cli.py") is None
    assert scrub_path_rel("~/repo/server/cli.py") is None
    assert scrub_path_rel("./server/cli.py") == "server/cli.py"
    assert is_ignored_path("node_modules/lodash/index.js")
    assert not is_ignored_path("server/cli.py")
