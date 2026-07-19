"""Search, workspace, action, and error-envelope schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from server.api.schema.query import QueryFilterError, QueryFilterToken


class SearchHit(BaseModel):
    trace_id: str
    span_id: str | None
    title: str | None
    snippet: str
    kind: Literal["trace", "span"]


class SearchFacet(BaseModel):
    value: str
    count: int


class SearchResponse(BaseModel):
    q: str
    filter_phrase: str = ""
    hits: list[SearchHit]
    total: int
    limit: int = 20
    offset: int = 0
    filter_tokens: list[QueryFilterToken] = Field(default_factory=list)
    filter_errors: list[QueryFilterError] = Field(default_factory=list)
    search_mode: Literal["fts", "scan"] = "scan"
    search_limitation: str | None = (
        "FTS is unavailable; Cairn used a bounded local compatibility scan."
    )
    facets: dict[str, list[SearchFacet]] = Field(default_factory=dict)


class WorkspaceAdapter(BaseModel):
    source: str
    streams: int
    cursor_updated_at: str | None
    attempts: int
    fully_parsed: int
    degraded: int
    skipped: int
    parse_coverage: float | None
    unknown_fields: dict[str, int]
    last_success_at: str | None
    warning: bool
    issue_url: str


class PlanWindowGauge(BaseModel):
    window_hours: int
    total_tokens: int
    by_source: dict[str, int]
    limit: int | None
    exceeded: bool


class AdapterWarning(BaseModel):
    adapter_id: str
    message: str
    issue_url: str


class HumanLabelAgreement(BaseModel):
    labeled_sessions: int
    agreements: int
    rate: float | None


class WorkspaceHealth(BaseModel):
    trace_count: int
    insight_count: int
    fts_available: bool
    adapter_warnings: list[AdapterWarning]
    human_label_agreement: HumanLabelAgreement


class CollectionStatus(BaseModel):
    """Backend auto-sync mode — independent of browser Live updates (SSE)."""

    mode: Literal["manual", "efficient", "live"]
    label: str
    auto_sync_active: bool
    watcher_enabled: bool
    refresh_enabled: bool
    poll_interval_sec: float
    refresh_interval_sec: float
    limitation: str
    live_updates_note: str = (
        "Browser Live updates (SSE) are a separate client control and do not start "
        "or stop backend auto-sync."
    )


class ResourceBudgetStatus(BaseModel):
    status: Literal["ok", "warn", "over", "unknown"]
    soft_budget_bytes: int | None = None
    ratio: float | None = None
    message: str


class ResourceDiskInventory(BaseModel):
    cairn_dir: str
    total_bytes: int
    database_bytes: int | None = None
    wal_bytes: int | None = None
    exports_bytes: int | None = None
    backups_bytes: int | None = None
    regressions_bytes: int | None = None


class ResourceForecast(BaseModel):
    window_days: int
    traces_ingested: int
    estimated_bytes_per_day: int
    projected_total_in_30d: int | None = None
    kind: Literal["descriptive"] = "descriptive"
    limitation: str


class ResourceStatus(BaseModel):
    """Honest local disk / process inventory (partial; expands with later T06 work)."""

    disk: ResourceDiskInventory
    budget: ResourceBudgetStatus
    forecast: ResourceForecast
    process_rss_bytes: int | None = None
    collection_mode: Literal["manual", "efficient", "live"] | None = None
    limitation: str


class WorkspaceResponse(BaseModel):
    workspace_id: str
    root_path: str
    name: str
    adapters: list[WorkspaceAdapter]
    health: WorkspaceHealth
    gauge: PlanWindowGauge | None = None
    collection: CollectionStatus | None = None
    resources: ResourceStatus | None = None


class ActionManifestEntry(BaseModel):
    name: str
    title: str
    category: str
    params_schema: dict[str, JsonValue]
    async_job: bool


class ActionsManifestResponse(BaseModel):
    actions: list[ActionManifestEntry]


class ActionResultResponse(BaseModel):
    ok: bool
    result: dict[str, JsonValue] | None = None
    job_id: str | None = None


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: JsonValue | None = None


class ErrorResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "error": {
                        "code": "validation_error",
                        "message": "Request parameters are invalid",
                        "details": [
                            {
                                "location": ["query", "days"],
                                "message": "Input should be less than or equal to 365",
                                "type": "less_than_equal",
                            }
                        ],
                    }
                }
            ]
        }
    )

    error: ErrorDetail
