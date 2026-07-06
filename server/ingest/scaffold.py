"""Scaffold a new ingest adapter."""

from __future__ import annotations

import re
from pathlib import Path

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def scaffold_adapter(repo_root: Path, name: str) -> list[Path]:
    """Create adapter module, fixture, and test stub under repo_root."""
    if not _NAME_RE.match(name):
        msg = "adapter name must be lowercase snake_case"
        raise ValueError(msg)

    created: list[Path] = []
    module = repo_root / "server" / "ingest" / "adapters" / f"{name}_adapter.py"
    fixture = repo_root / "tests" / "fixtures" / "ingest" / f"{name}_mini.jsonl"
    test_file = repo_root / "tests" / f"test_ingest_{name}.py"

    module.parent.mkdir(parents=True, exist_ok=True)
    fixture.parent.mkdir(parents=True, exist_ok=True)
    test_file.parent.mkdir(parents=True, exist_ok=True)

    class_name = "".join(part.capitalize() for part in name.split("_")) + "Adapter"
    module.write_text(
        f'''"""{class_name} ingest adapter (scaffold)."""

from __future__ import annotations

from pathlib import Path

from server.ingest.adapters.base import FileAdapterBase, _wrap_parse
from server.ingest.adapters.agent_jsonl import parse_agent_jsonl
from server.ingest.map import ParsedSession


class {class_name}(FileAdapterBase):
    adapter_id = "{name}"
    legacy_source = "{name}"

    def _discover(self) -> list[Path]:
        return []

    def parse_path(self, path: Path) -> ParsedSession | None:
        parsed = parse_agent_jsonl(path, source=self.legacy_source, repo_root=self.workspace_root)
        return _wrap_parse(self.legacy_source, parsed)
''',
        encoding="utf-8",
    )
    created.append(module)

    if not fixture.exists():
        fixture.write_text(
            '{"role":"user","message":{"content":[{"type":"text","text":"hello"}]}}\n',
            encoding="utf-8",
        )
        created.append(fixture)

    if not test_file.exists():
        test_file.write_text(
            f'''"""Ingest tests for {name} adapter."""

from __future__ import annotations

from pathlib import Path

from server.ingest.adapters.{name}_adapter import {class_name}


def test_{name}_adapter_parses_fixture(tmp_path: Path) -> None:
    adapter = {class_name}(tmp_path, "ws-test")
    fixture = Path(__file__).resolve().parent / "fixtures" / "ingest" / "{name}_mini.jsonl"
    assert fixture.is_file()
    parsed = adapter.parse_path(fixture)
    assert parsed is not None
    assert parsed.external_id
''',
            encoding="utf-8",
        )
        created.append(test_file)

    return created
