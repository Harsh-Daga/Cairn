# GitHub Pages demo site

Canonical interactive demo URL: **https://harsh-daga.github.io/Cairn/**

The site is a **static export** of the deterministic demo workspace (`cairn demo` →
`cairn export --static`). It is read-only: no mutations, no SSE, no live sync. Docs remain in
the repository (`docs/`); the site does not duplicate a second documentation source.

## Hosting contract

| Concern | Behavior |
|---------|----------|
| Project base path | Hosted under `/Cairn/`; export rewrites assets to `./…` |
| SPA refresh | Static UI uses `HashRouter` (`#/…`) |
| Path-style misses | Export writes `404.html` (copy of `index.html`) for Pages |
| Jekyll | Export writes `.nojekyll` |
| Local product | Unchanged — runtime stays CDN-free / offline-capable |

## Workflows

- **Deploy:** dispatch `.github/workflows/demo-pages.yml` (maintainer opt-in).
- **PR preview:** the same workflow builds `_site` and uploads a `pages-preview` artifact; it does
  **not** deploy to the public site.

Pages failures must not block package releases. After verifying the live URL, set the GitHub
repository homepage to the canonical demo URL (see
[maintainer settings](maintainers/github-settings.md)).

## Local check

```bash
uv run python scripts/build_ui.py build
uv run cairn demo --reset
uv run cairn export --static _site --workspace "$HOME/.cairn-demo"
# Serve under a /Cairn/ prefix to mimic the project site, or open via file:// e2e.
```
