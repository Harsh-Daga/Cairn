# Time ranges and timezones

Cairn uses one time-range contract across the dashboard and applicable read APIs. A resolved range
is two UTC instants in a half-open interval: `start <= timestamp < end`. An event exactly at
`start` is included; an event exactly at `end` is not.

## Request forms

Choose exactly one form:

- `preset=24h|7d|30d|90d` with an optional IANA `timezone`;
- complete `start`, `end`, and `timezone` values for a custom calendar range;
- legacy `days=1..365`.

Preset and legacy ranges are rolling durations ending when the request is resolved. `24h` means
the preceding 24 hours, not “today.” Naive custom timestamps are interpreted in the declared IANA
timezone before conversion to UTC; timestamps with an explicit offset retain that instant.
Combinations such as `days` plus `start`/`end`, partial custom bounds, unknown timezones, reversed
bounds, and ranges longer than 365 days return an `invalid_time_range` error.

Applicable responses contain `resolved_range` with:

- UTC `start` and exclusive `end`;
- `prior_start` and `prior_end`, the immediately preceding equal-duration interval;
- the requested timezone and preset or legacy-days provenance;
- `rolling_duration` or `custom_calendar` semantics;
- a display-oriented duration in days.

The dashboard stores the selected range in the URL. Custom controls are unavailable in a static
snapshot because a snapshot contains only explicitly captured presets. Its capability manifest
declares `captured_at`, the available data bounds, captured day values, supported query fields, and
`custom_range_behavior: "rejected"`. An unavailable custom range fails visibly; Cairn does not
substitute another preset.

Static export is a curated dashboard snapshot, not the complete portability archive. It captures
detail/replay payloads for at most the 1,000 most recent traces and publishes both that ceiling and
the full trace count in `capture_limits`; list pages only link into the captured recent set.

Examples:

```text
GET /api/overview?preset=24h&timezone=Asia/Kolkata
GET /api/analytics/usage?start=2026-07-01T00:00&end=2026-07-02T00:00&timezone=Europe/Berlin
GET /api/traces?days=30&limit=50&offset=0
```
