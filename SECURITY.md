# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 2.0.x   | Yes |
| < 2.0   | No |

## Reporting a Vulnerability

**Do not file public issues for security vulnerabilities.**

Instead, please report security issues by emailing the maintainers privately. Include:

1. A description of the vulnerability
2. Steps to reproduce
3. Potential impact
4. Any suggested mitigation

We aim to respond within 48 hours and provide a fix or mitigation within 7 days.

## Security Features

Cairn is designed with these security properties:

- **Local-first**: All data stays on your machine by default
- **No network required**: The static dashboard works at `file://` with zero CDN dependencies
- **Secret scrubbing**: Bundle exports and share bundles scrub secrets via `cairn/render/scrub.py`
- **Managed blocks only**: `cairn optimize --apply` only writes inside managed blocks in `AGENTS.md`
- **Git safety**: Writes are refused when the target file has uncommitted changes outside managed blocks
- **Encryption**: `cairn advanced decrypt` uses AES-256-GCM for encrypted bundles
- **XSS prevention**: Dashboard JS uses `createElement` + `textContent`, never `innerHTML` for API data

## Known Considerations

- The live dashboard server (`cairn dash`) binds to `127.0.0.1` by default and should not be exposed to the internet
- SSE endpoints (`/v2/events`) are localhost-only
- The `~/.cairn/config.toml` file may contain backend preferences — avoid committing it to public repos