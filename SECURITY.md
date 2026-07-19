# Security policy

## Supported releases

Security fixes are maintained for the latest released minor line. The unreleased `main` branch is
tested but is not a supported release.

| Release line | Status |
|---|---|
| 1.1.x | Supported |
| 1.0.x and older | Unsupported |

Upgrade to the newest patch before reporting an issue. This table will move to 1.2.x when 1.2.0 is
released.

## Report a vulnerability privately

Do not include vulnerabilities, tokens, traces, databases, or private paths in a public issue.
Use GitHub's private vulnerability report for this repository:

<https://github.com/Harsh-Daga/Cairn/security/advisories/new>

Include the affected version, impact, minimal reproduction, and any suggested mitigation. If the
private-report form is unavailable, ask the maintainer for a private channel in a public issue
without disclosing security details. The project is maintainer-run and cannot promise a response or
fix deadline; reports will be acknowledged and handled on a best-effort basis.

## Security and privacy boundaries

Cairn stores coding-agent telemetry locally. Prompts, responses, tool input/output, file excerpts,
paths, repository metadata, and inferred findings may contain source code, personal data, and
secrets. Workspace data is normally under `<workspace>/.cairn/`; user configuration can be under
`~/.cairn/`. Back up, share, and delete these paths as sensitive data.

The live server binds to `127.0.0.1` by default. A non-loopback bind is refused unless a token is
configured. When configured, the token protects HTTP, API, OTLP, static assets, and SSE routes.
Cairn also validates Host and browser Origin headers. A command may open a one-time URL containing
the token; the server removes it with a no-store redirect and sets an HttpOnly, SameSite cookie.
URLs can still be captured by browser history, process inspection, extensions, proxies, or logs
before the redirect, so use this bootstrap only on a trusted machine and rotate a disclosed token.

Cairn is designed to work without a provider connection. Features that contact a model provider
must be explicitly selected and configured; their request can disclose selected trace content to
that provider. Provider credentials and provider privacy controls remain the user's responsibility.
See the [threat model](docs/security/threat-model.md) for the required analysis boundary.

Static and session exports are self-contained local artifacts intended for explicit sharing.
Exporters remove known credentials and absolute workspace roots and use restrictive Unix modes,
but scrubbing is pattern-based and cannot prove that arbitrary private text is safe. Review an
export before sharing it. Do not open an untrusted export with elevated local privileges.

Instruction-file changes are restricted to Cairn-managed blocks and use backups and content
checks. Suggestions, imported instructions, model output, and MCP descriptions are untrusted data;
they do not grant approval to execute a command or mutate a repository.

Dependencies are locked for development and release checks. Release artifacts are expected to be
built by the reviewed release workflow with checksums and provenance; verify published artifacts
against the release record once available. A lock file, scanner, signature, or provenance record
reduces risk but does not guarantee a dependency is safe.

On Unix-like systems Cairn creates sensitive directories as `0700` and sensitive files as `0600`.
Run `cairn doctor` to detect broader existing modes and
`cairn doctor --repair-permissions` to restrict Cairn-owned trees. On Windows, keep Cairn paths in
a user-private profile and verify that their ACL is limited to the intended account.

## What Cairn does not protect against

Cairn does not:

- encrypt its database or exports at rest;
- isolate data from an administrator, the same OS account, malware, a compromised dependency, or a
  compromised browser;
- guarantee that secret scrubbing finds every credential or sensitive passage;
- make an internet-facing deployment safe or provide multi-user authorization;
- treat imported logs, archives, HTML, MCP metadata, or model output as trusted;
- guarantee that agent logs are complete, accurate, causally attributable, or free of poisoning;
- replace repository review, backups, endpoint security, provider controls, or OS access control.

The maintained threat analysis is in
[`docs/security/threat-model.md`](docs/security/threat-model.md).
