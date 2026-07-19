"""Versioned local regression artifact schema (no execution)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

REGRESSION_SCHEMA_VERSION = "cairn.regression.v1"


class RepoStartRef(BaseModel):
    commit: str | None = None
    commit_source: Literal["outcome", "trace", "missing"] = "missing"
    fixture: str | None = None
    limitation: str | None = None


class CommandHint(BaseModel):
    command: str
    source: Literal["inferred", "manual"] = "inferred"
    span_id: str | None = None


class ExpectedOutcome(BaseModel):
    outcome_label: str | None = None
    tests_run: int | None = None
    tests_passed: int | None = None
    tests_failed: int | None = None
    build_status: str | None = None
    quality_score: float | None = None
    failure_signature: str | None = None


class Provenance(BaseModel):
    source_trace_id: str
    agent_source: str | None = None
    created_at: str
    producer: str = "cairn"
    producer_version: str


class PrivacyInventory(BaseModel):
    scrubbed: bool = True
    included: list[str] = Field(default_factory=list)
    redacted: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class RegressionRun(BaseModel):
    """Observed outcome recorded from an ingested session — never executed by Cairn."""

    run_id: str
    recorded_at: str
    source_trace_id: str
    agent_source: str | None = None
    observed: ExpectedOutcome = Field(default_factory=ExpectedOutcome)
    repo_ref: str | None = None
    executed_commands: bool = False
    limitations: list[str] = Field(default_factory=list)


class RegressionArtifact(BaseModel):
    schema_version: str = REGRESSION_SCHEMA_VERSION
    regression_id: str
    scrubbed_task: str | None = None
    task_source: Literal["user_msg", "receipt_intent", "missing"] = "missing"
    repo_start_ref: RepoStartRef = Field(default_factory=RepoStartRef)
    setup_commands: list[CommandHint] = Field(default_factory=list)
    verification_commands: list[CommandHint] = Field(default_factory=list)
    expected_outcome: ExpectedOutcome = Field(default_factory=ExpectedOutcome)
    prohibited_changes: list[str] = Field(default_factory=list)
    required_paths: list[str] = Field(default_factory=list)
    resource_limit: dict[str, Any] | None = None
    provenance: Provenance
    privacy_inventory: PrivacyInventory = Field(default_factory=PrivacyInventory)
    attachments: list[str] = Field(default_factory=list)
    runs: list[RegressionRun] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    content_hash: str = ""


class RegressionManifest(BaseModel):
    schema_version: str = REGRESSION_SCHEMA_VERSION
    regression_id: str
    created_at: str
    source_trace_id: str
    content_hash: str
    title: str | None = None
