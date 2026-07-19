# Generated HTTP API index

Generated from FastAPI OpenAPI. Do not edit by hand.

| Method | Path | Operation ID | Success schema |
|---|---|---|---|
| GET | `/api/actions` | `actions_manifest` | `ActionsManifestResponse` |
| GET | `/api/actions/jobs/{job_id}` | `get_job` | `inline/stream` |
| POST | `/api/actions/jobs/{job_id}/cancel` | `cancel_job` | `inline/stream` |
| POST | `/api/actions/{name}` | `run_action` | `ActionResultResponse` |
| GET | `/api/agents` | `agents` | `AgentsResponse` |
| GET | `/api/analytics/budget` | `analytics_budget` | `BudgetBurnResponse` |
| GET | `/api/analytics/compare` | `analytics_compare` | `CompareAnalyticsResponse` |
| GET | `/api/analytics/files` | `analytics_files` | `FilesAnalyticsResponse` |
| GET | `/api/analytics/guard` | `analytics_guard` | `GuardAnalyticsResponse` |
| GET | `/api/analytics/regions` | `analytics_regions` | `RegionsAnalyticsResponse` |
| GET | `/api/analytics/tail` | `analytics_tail` | `TailAnalyticsResponse` |
| GET | `/api/analytics/tools` | `analytics_tools` | `ToolsAnalyticsResponse` |
| GET | `/api/analytics/usage` | `analytics_usage` | `UsageAnalyticsResponse` |
| GET | `/api/analytics/waste` | `analytics_waste` | `WasteAnalyticsResponse` |
| GET | `/api/behavior` | `behavior` | `BehaviorResponse` |
| GET | `/api/experiments` | `list_experiments` | `ExperimentsResponse` |
| GET | `/api/experiments/{experiment_id}` | `get_experiment` | `ExperimentDetailResponse` |
| GET | `/api/health` | `health` | `inline/stream` |
| GET | `/api/insights` | `list_insights` | `InsightsResponse` |
| GET | `/api/insights/{insight_id}/evidence` | `insight_evidence` | `EvidenceChainResponse` |
| GET | `/api/live/events` | `live_events` | `inline/stream` |
| GET | `/api/overview` | `overview` | `OverviewResponse` |
| GET | `/api/quality` | `quality` | `QualityResponse` |
| GET | `/api/recap` | `recap` | `RecapResponse` |
| GET | `/api/search` | `search` | `SearchResponse` |
| GET | `/api/traces` | `list_traces` | `TracesListResponse` |
| GET | `/api/traces/diff` | `diff_traces` | `TraceDiffResponse` |
| GET | `/api/traces/{trace_id}` | `get_trace` | `TraceDetailResponse` |
| GET | `/api/traces/{trace_id}/corrections` | `get_corrections` | `CorrectionsResponse` |
| PUT | `/api/traces/{trace_id}/corrections/{correction_id}/relabel` | `relabel_correction` | `CorrectionsResponse` |
| GET | `/api/traces/{trace_id}/handoff` | `get_handoff` | `HandoffResponse` |
| PUT | `/api/traces/{trace_id}/human-label` | `set_human_label` | `HumanLabelResponse` |
| GET | `/api/traces/{trace_id}/postmortem` | `get_postmortem` | `PostmortemResponse` |
| GET | `/api/traces/{trace_id}/receipt` | `get_receipt` | `ReceiptResponse` |
| GET | `/api/traces/{trace_id}/replay` | `replay_trace` | `ReplayResponse` |
| GET | `/api/workspace` | `workspace` | `WorkspaceResponse` |
| POST | `/v1/traces` | `otlp_traces` | `inline/stream` |
| GET | `/{full_path}` | `spa_fallback` | `inline/stream` |
