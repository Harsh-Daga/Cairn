# Beta — technical constraints

Proposed architecture: local SQLite ledger + content-addressable blobs.

- Must work at `file://` with no CDN for reports.
- Capture hooks must never block the agent (fail open).
- Pipeline builds must fail loud on missing credentials (`doctor` before spend).
- Target laptop-first; no cloud account required for v1.

Risk: large sessions (10k+ events) need streaming render caps.
