"""cairn.archive.v1 constants and OTLP-loss contract."""

from __future__ import annotations

ARCHIVE_SCHEMA_VERSION = "cairn.archive.v1"
SUPPORTED_READ_SCHEMAS = frozenset({ARCHIVE_SCHEMA_VERSION})

# Allowlisted ZIP members for workspace archives.
DOMAIN_FILES = (
    "manifest.json",
    "privacy.json",
    "workspace.json",
    "traces.json",
    "spans.json",
    "span_links.json",
    "outcomes.json",
    "data_quality.json",
    "diagnostics.json",
    "verification_receipts.json",
    "session_corrections.json",
    "policy.json",
)

ALLOWED_MEMBERS = frozenset(DOMAIN_FILES)

# Cairn-specific evidence that cannot round-trip through OTLP/OTel GenAI alone.
OTLP_LOSS_FIELDS: tuple[dict[str, str], ...] = (
    {
        "field": "verification_receipts / claims",
        "reason": "Cairn receipts and claim graphs are not OTel GenAI attributes.",
    },
    {
        "field": "session_corrections / relabels",
        "reason": "Local supervision labels are Cairn-native.",
    },
    {
        "field": "outcomes / quality_score / human_label",
        "reason": "Outcome ledger fields are not standard OTLP span attrs.",
    },
    {
        "field": "diagnostics / failure localization",
        "reason": "Cascade and failure-origin analysis is Cairn-computed.",
    },
    {
        "field": "data_quality / cost_source / estimate_kind",
        "reason": "Honesty provenance is Cairn-specific.",
    },
    {
        "field": "span_links (handoffs)",
        "reason": "Non-tree causality kinds may not map 1:1 to OTel links.",
    },
    {
        "field": "policy / regressions / privacy manifests",
        "reason": "Workspace policy and portable regressions are outside OTLP.",
    },
    {
        "field": "storage retention mode / scrub state",
        "reason": "Content-retention policy is a Cairn config concern.",
    },
)
