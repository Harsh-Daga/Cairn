# ADR 0009: Self-contained, framework-free provenance bundle

**Status:** Accepted  
**Date:** 2026-06-07  
**Charter:** R15, §10 (`cairn render`), Phase 2 §5

## Context

Phase 2’s differentiator is **legibility to a stranger**: someone who has never run Cairn should
open one artifact offline and trace any output to its inputs, prompt, model, and params.

Options considered:

1. **SPA / framework viewer** (React, Vue, etc.) — requires a build step, ships larger assets,
   and often loads data via `fetch`, which browsers block on `file://` URLs.
2. **Server-hosted viewer** — needs hosting; fails the “email a zip” portability bar.
3. **Inline JSON + plain DOM** — one `index.html` embeds all data; one CSS + one JS manipulate
   the DOM with no network, no bundler, no framework.

## Decision

1. Default bundle layout (R15):

   ```
   outputs/bundle/
   ├── index.html      # <script type="application/json" id="cairn-data">…</script>
   ├── assets/app.css
   └── assets/app.js
   ```

2. **All run data is inlined** in `index.html` by default so the bundle opens via `file://`
   without a server.
3. **No framework, no build step** for viewer assets; CSS/JS ship in the wheel.
4. **No `localStorage` / `sessionStorage`** — pure view over embedded data.
5. **`--split`** writes external `data/` for very large runs (opt-in; may require a server for
   `fetch`). **`--zip`** packages the directory for sharing.
6. JSON payload uses **sorted keys** (`canonical_json`) so identical runs produce byte-stable
   bundles (golden-tested).

## Consequences

- Viewer UX stays intentionally simple: node list, lineage links, prompt/output panels.
- Large outputs are truncated inline (R17 #14); full blobs remain in CAS.
- Phase 4 can add a `trajectory` field per node without changing the bundle shell.
- Security: `render` strips secrets and absolute home paths before inlining (R16).
