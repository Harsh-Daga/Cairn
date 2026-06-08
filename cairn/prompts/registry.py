"""Versioned prompt registry backed by ledger + CAS."""

from __future__ import annotations

import difflib
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from cairn.cache.cas import ContentAddressableStore
from cairn.ledger.schema import migrate
from cairn.ledger.storage import (
    PromptRecord,
    get_prompt,
    list_prompts,
    register_prompt,
)
from cairn.loader.prompts import load_prompt
from cairn.util.canonical import hash_bytes

_PROMPT_REF_RE = re.compile(r"^([a-zA-Z0-9_.-]+)(?:@(.+))?$")


@dataclass(frozen=True)
class PromptEntry:
    name: str
    version: str
    path_rel: str
    content_hash: str
    body: str
    model_override: str | None
    params: dict[str, object]
    description: str | None
    created_at: str
    deprecated: bool

    @property
    def prompt_ref(self) -> str:
        return f"{self.name}@{self.version}"

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "version": self.version,
            "prompt_ref": self.prompt_ref,
            "path_rel": self.path_rel,
            "content_hash": self.content_hash,
            "model_override": self.model_override,
            "params": self.params,
            "description": self.description,
            "created_at": self.created_at,
            "deprecated": self.deprecated,
            "body_preview": self.body[:200],
        }


def parse_prompt_ref(ref: str) -> tuple[str, str | None]:
    match = _PROMPT_REF_RE.match(ref.strip())
    if not match:
        msg = f"invalid prompt ref: {ref!r}"
        raise ValueError(msg)
    return match.group(1), match.group(2)


class PromptRegistry:
    """Registers immutable prompt versions from project prompts/."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        cairn_dir = self.project_root / ".cairn"
        cairn_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = cairn_dir / "ledger.db"
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        migrate(self._conn)
        self.cas = ContentAddressableStore(cairn_dir)

    @property
    def connection(self) -> sqlite3.Connection:
        return self._conn

    def close(self) -> None:
        self._conn.close()

    def sync(self) -> list[PromptEntry]:
        """Scan prompts/**/*.md and register new versions when content changes."""
        registered: list[PromptEntry] = []
        prompts_dir = self.project_root / "prompts"
        if not prompts_dir.is_dir():
            return registered
        for path in sorted(prompts_dir.rglob("*.md")):
            if not path.is_file():
                continue
            entry = self._register_file(path)
            if entry is not None:
                registered.append(entry)
        return registered

    def list_entries(self) -> list[PromptEntry]:
        return [self._entry_from_record(r) for r in list_prompts(self._conn)]

    def get(self, name: str, version: str | None = None) -> PromptEntry | None:
        record = get_prompt(self._conn, name, version)
        if record is None:
            return None
        return self._entry_from_record(record)

    def diff(self, left_ref: str, right_ref: str) -> str:
        left_name, left_ver = parse_prompt_ref(left_ref)
        right_name, right_ver = parse_prompt_ref(right_ref)
        left = self.get(left_name, left_ver)
        right = self.get(right_name, right_ver)
        if left is None:
            msg = f"prompt not found: {left_ref}"
            raise KeyError(msg)
        if right is None:
            msg = f"prompt not found: {right_ref}"
            raise KeyError(msg)
        lines = difflib.unified_diff(
            left.body.splitlines(keepends=True),
            right.body.splitlines(keepends=True),
            fromfile=left.prompt_ref,
            tofile=right.prompt_ref,
        )
        return "".join(lines)

    def _register_file(self, path: Path) -> PromptEntry | None:
        prompt = load_prompt(path, self.project_root)
        rel = str(path.relative_to(self.project_root))
        name = path.stem
        content_hash = hash_bytes(path.read_bytes())
        latest = get_prompt(self._conn, name)
        if latest is not None and latest.content_hash == content_hash:
            return None
        version = _next_version(latest.version if latest else None)
        body_hash = self.cas.put(prompt.template_body_bytes)
        description = prompt.front_matter.get("description")
        desc = str(description) if description is not None else None
        record = register_prompt(
            self._conn,
            name=name,
            version=version,
            path_rel=rel,
            content_hash=content_hash,
            body_cas_hash=body_hash,
            model_override=prompt.model_override,
            params=dict(prompt.params_override),
            description=desc,
        )
        return self._entry_from_record(record)

    def _entry_from_record(self, record: PromptRecord) -> PromptEntry:
        body_bytes = self.cas.read(record.body_cas_hash)
        body = body_bytes.decode("utf-8") if body_bytes is not None else ""
        return PromptEntry(
            name=record.name,
            version=record.version,
            path_rel=record.path_rel,
            content_hash=record.content_hash,
            body=body,
            model_override=record.model_override,
            params=record.params,
            description=record.description,
            created_at=record.created_at,
            deprecated=record.deprecated,
        )


def _next_version(latest: str | None) -> str:
    if latest is None:
        return "v1"
    if latest.startswith("v") and latest[1:].isdigit():
        return f"v{int(latest[1:]) + 1}"
    return f"{latest}-next"
