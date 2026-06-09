"""Generic JSONL parser for Aider, OpenHands, and Goose exports."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cairn.ingest.normalizer import args_payload, result_payload, text_payload
from cairn.ingest.parsers.claude_code import FileArtifactDraft, ToolCallDraft
from cairn.ingest.project_paths import path_rel_to_repo
from cairn.ingest.types import AgentSourceId, ParsedAgentSession
from cairn.ingest.usage import UsageAccumulator, extract_usage_dict
from cairn.util.canonical import hash_obj


@dataclass
class _State:
    source: AgentSourceId
    repo_root: Path | None
    external_id: str | None = None
    cwd: str | None = None
    git_branch: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    model: str | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[ToolCallDraft] = field(default_factory=list)
    file_artifacts: list[FileArtifactDraft] = field(default_factory=list)
    usage: UsageAccumulator = field(default_factory=UsageAccumulator)
    _seq: int = 0

    def finish(self) -> ParsedAgentSession | None:
        if not self.external_id or not self.events:
            return None
        return ParsedAgentSession(
            source=self.source,
            external_id=self.external_id,
            cwd=self.cwd,
            git_branch=self.git_branch,
            started_at=self.started_at,
            ended_at=self.ended_at,
            model=self.model,
            events=self.events,
            tool_calls=self.tool_calls,
            file_artifacts=self.file_artifacts,
            usage=self.usage,
        )

    def consume(self, obj: dict[str, Any]) -> None:
        session_id = obj.get("session_id")
        if isinstance(session_id, str) and session_id:
            self.external_id = session_id
        cwd = obj.get("cwd")
        if isinstance(cwd, str):
            self.cwd = cwd
        branch = obj.get("git_branch") or obj.get("gitBranch")
        if isinstance(branch, str):
            self.git_branch = branch
        ts = obj.get("timestamp")
        if isinstance(ts, str):
            if self.started_at is None:
                self.started_at = ts
            self.ended_at = ts
        model = obj.get("model")
        if isinstance(model, str):
            self.model = model
        usage = obj.get("usage")
        if isinstance(usage, dict):
            self.usage.usage.add(extract_usage_dict(usage))

        event_type = str(obj.get("type", ""))
        self._seq += 1
        seq = self._seq

        if event_type in ("user_message", "user"):
            text = _text_content(obj)
            self.events.append({"type": "user_prompt", "seq": seq, **text_payload(text)})
            return
        if event_type in ("assistant_message", "assistant"):
            text = _text_content(obj)
            self.events.append(
                {"type": "assistant_message", "seq": seq, **text_payload(text)}
            )
            return
        if event_type == "tool_call":
            tool_id = str(obj.get("tool_id") or obj.get("id") or f"tool-{seq}")
            name = str(obj.get("name") or "tool")
            tool_input = obj.get("input")
            if not isinstance(tool_input, dict):
                tool_input = {}
            path_rel = _path_from_input(tool_input, self.repo_root)
            args_hash = hash_obj(tool_input)
            self.tool_calls.append(
                ToolCallDraft(
                    tool_use_id=tool_id,
                    name=name,
                    args_hash=args_hash,
                    seq_hint=seq,
                    path_rel=path_rel,
                )
            )
            self.events.append(
                {
                    "type": "tool_call",
                    "seq": seq,
                    "tool_use_id": tool_id,
                    "name": name,
                    **args_payload(tool_input),
                }
            )
            if path_rel:
                self.file_artifacts.append(
                    FileArtifactDraft(
                        path_rel=path_rel,
                        first_seq_hint=seq,
                        last_seq_hint=seq,
                        op="edit",
                    )
                )
            return
        if event_type == "tool_result":
            tool_id = str(obj.get("tool_id") or obj.get("id") or "")
            content = obj.get("content", "")
            text = content if isinstance(content, str) else str(content)
            self.events.append(
                {
                    "type": "tool_result",
                    "seq": seq,
                    "tool_use_id": tool_id,
                    **result_payload(text),
                }
            )


def parse_agent_jsonl(
    path: Path,
    *,
    source: AgentSourceId,
    repo_root: Path | None = None,
) -> ParsedAgentSession | None:
    state = _State(source=source, repo_root=repo_root)
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                obj = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                state.consume(obj)
    return state.finish()


def _text_content(obj: dict[str, Any]) -> str:
    content = obj.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    return ""


def _path_from_input(tool_input: dict[str, Any], repo_root: Path | None) -> str | None:
    for key in ("path", "file_path", "filePath", "filename"):
        value = tool_input.get(key)
        if isinstance(value, str):
            if repo_root is not None:
                return path_rel_to_repo(repo_root, value)
            return value
    return None
