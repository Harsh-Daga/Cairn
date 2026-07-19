"""Taxonomy constants reused across metrics modules."""

from __future__ import annotations

# Tool categories
READ_TOOLS: frozenset[str] = frozenset(
    {
        "Read",
        "read_file",
        "open_file",
        "cat",
        "view",
        "NotebookRead",
        "list_dir",
    }
)

WRITE_TOOLS: frozenset[str] = frozenset(
    {
        "Edit",
        "Write",
        "MultiEdit",
        "apply_patch",
        "str_replace",
        "create_file",
        "NotebookEdit",
        "write_file",
        "patch",
        "StrReplace",
        "EditNotebook",
    }
)

ORIENTATION_TOOLS: frozenset[str] = frozenset(
    {
        "Glob",
        "Grep",
        "LS",
        "ls",
        "find",
        "search",
        "codebase_search",
        "WebSearch",
        "WebFetch",
        "search_files",
        "grep",
    }
)

SHELL_TOOLS: frozenset[str] = frozenset(
    {
        "Bash",
        "run_command",
        "shell",
        "execute_command",
        "exec_command",
        "terminal",
        "execute_code",
        "Shell",
    }
)

# Normalized tool taxonomy (Phase 0 single registry)
NORM_READ = "read"
NORM_SEARCH = "search"
NORM_EDIT = "edit"
NORM_BASH = "bash"
NORM_DELETE = "delete"
NORM_SUB_AGENT = "sub_agent"
NORM_META = "meta"

CANONICAL_NORMS: frozenset[str] = frozenset(
    {
        NORM_READ,
        NORM_SEARCH,
        NORM_EDIT,
        NORM_BASH,
        NORM_DELETE,
        NORM_SUB_AGENT,
        NORM_META,
    }
)

# Universal alias map: lower-case raw name -> normalized name
_TOOL_ALIASES: dict[str, str] = {
    "read": NORM_READ,
    "read_file": NORM_READ,
    "readfile": NORM_READ,
    "open_file": NORM_READ,
    "cat": NORM_READ,
    "view": NORM_READ,
    "notebookread": NORM_READ,
    "list_dir": NORM_READ,
    "glob": NORM_SEARCH,
    "grep": NORM_SEARCH,
    "search": NORM_SEARCH,
    "codebase_search": NORM_SEARCH,
    "websearch": NORM_SEARCH,
    "webfetch": NORM_SEARCH,
    "search_files": NORM_SEARCH,
    "find": NORM_SEARCH,
    "ls": NORM_SEARCH,
    "edit": NORM_EDIT,
    "write": NORM_EDIT,
    "multiedit": NORM_EDIT,
    "str_replace": NORM_EDIT,
    "strreplace": NORM_EDIT,
    "apply_patch": NORM_EDIT,
    "create_file": NORM_EDIT,
    "notebookedit": NORM_EDIT,
    "write_file": NORM_EDIT,
    "patch": NORM_EDIT,
    "editnotebook": NORM_EDIT,
    "bash": NORM_BASH,
    "shell": NORM_BASH,
    "run_command": NORM_BASH,
    "execute_command": NORM_BASH,
    "exec_command": NORM_BASH,
    "terminal": NORM_BASH,
    "execute_code": NORM_BASH,
    "run_terminal_cmd": NORM_BASH,
    "delete": NORM_DELETE,
    "task": NORM_SUB_AGENT,
    "sub_agent": NORM_SUB_AGENT,
    "skills_list": NORM_META,
    "todo": NORM_META,
    "plan": NORM_META,
    "tool": NORM_META,
}

# Source-specific overrides (checked before universal aliases)
_SOURCE_OVERRIDES: dict[str, dict[str, str]] = {
    "cursor": {
        "grep": NORM_SEARCH,
        "glob": NORM_READ,
        "read": NORM_READ,
        "write": NORM_EDIT,
        "strreplace": NORM_EDIT,
        "editnotebook": NORM_EDIT,
        "shell": NORM_BASH,
        "delete": NORM_DELETE,
        "task": NORM_SUB_AGENT,
    },
    "codex": {
        "apply_patch": NORM_EDIT,
        "shell": NORM_BASH,
        "exec_command": NORM_BASH,
        "read_file": NORM_READ,
        "list_dir": NORM_READ,
    },
    "hermes": {
        "browser_navigate": NORM_READ,
        "browser_click": NORM_READ,
        "browser_type": NORM_READ,
        "browser_snapshot": NORM_READ,
    },
}

# All raw tool names emitted by parsers — coverage test fails if unmapped.
PARSER_TOOL_NAMES: frozenset[str] = frozenset(
    {
        # claude-code
        "Read",
        "Write",
        "Edit",
        "MultiEdit",
        "Bash",
        "Glob",
        "Grep",
        "Task",
        "NotebookRead",
        "NotebookEdit",
        "WebSearch",
        "WebFetch",
        "Delete",
        # cursor (raw + pre-normalized)
        "StrReplace",
        "EditNotebook",
        "Shell",
        # codex
        "apply_patch",
        "exec_command",
        "read_file",
        "list_dir",
        "shell",
        # hermes
        "write_file",
        "patch",
        "search_files",
        "terminal",
        "execute_code",
        "skills_list",
        "todo",
        "plan",
        # agent_jsonl (aider/goose/opencode)
        "write",
        "read",
        "run_terminal_cmd",
        # gemini
        # cline / openclaw (via generic names)
        "tool",
    }
)


def normalize_tool_name(name: str, *, source: str) -> str:
    """Map a parser-emitted tool name to the canonical normalized taxonomy."""
    if not name:
        return "unknown"
    if name.startswith("mcp:") or name.startswith("mcp__"):
        suffix = name.split(":", 1)[-1] if ":" in name else name[5:]
        return f"mcp:{suffix.lower()}"
    src_map = _SOURCE_OVERRIDES.get(source, {})
    lower = name.lower()
    if name in src_map:
        return src_map[name]
    if lower in src_map:
        return src_map[lower]
    if lower.startswith("browser_"):
        return NORM_READ
    if lower in _TOOL_ALIASES:
        return _TOOL_ALIASES[lower]
    return lower


def is_mapped_tool(name: str, *, source: str) -> bool:
    """Return True when ``name`` maps to a known normalized category."""
    norm = normalize_tool_name(name, source=source)
    if norm.startswith("mcp:"):
        return True
    return norm in CANONICAL_NORMS or norm in _TOOL_ALIASES.values()


# Thresholds
OVERSIZE_RESULT_BYTES: int = 16384
BYTES_PER_TOKEN: int = 4
CONTEXT_WINDOW_DEFAULT: int = 200_000

# Known model context windows (longest-prefix match elsewhere)
MODEL_CONTEXT_WINDOWS: dict[str, int] = {
    "claude-opus": 200_000,
    "claude-3-opus": 200_000,
    "claude-sonnet": 200_000,
    "claude-3-5-sonnet": 200_000,
    "claude-haiku": 200_000,
    "claude-3-5-haiku": 200_000,
    "claude": 200_000,
    "gpt-4o": 128_000,
    "gpt-4.1": 1_000_000,
    "gpt-4.1-mini": 1_000_000,
    "gpt-4.1-nano": 1_000_000,
    "o3": 200_000,
    "o3-mini": 200_000,
    "o4-mini": 200_000,
    "gemini-2.5-pro": 1_000_000,
    "gemini-2.5-flash": 1_000_000,
    "gemini-2.0-flash": 1_000_000,
    "deepseek": 128_000,
    "kimi": 128_000,
    "qwen": 128_000,
    "llama": 128_000,
    "mistral": 128_000,
    "grok": 128_000,
}

# Managed instruction-block caps (Phase F). Over either cap the block is consolidated:
# near-duplicate entries merge and the lowest-confidence/lowest-impact entries drop.
MANAGED_BLOCK_MAX_LINES = 120
MANAGED_BLOCK_MAX_CHARS = 6_000

# Managed block token budgets
MANAGED_BLOCK_BUDGETS: dict[str, int] = {
    "system": 8_000,
    "tool_results": 80_000,
    "recent_turns": 40_000,
    "files": 40_000,
    "optimization_cache": 20_000,
}
