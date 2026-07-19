# Cairn threat model

Status: maintained for the 1.2 architecture. This document describes intended boundaries and tested
mitigations; it is not a security certification.

## Assets and trust boundaries

Protected assets include source and prompt content, tool input/output, filesystem paths, trace and
span metadata, local configuration and provider credentials, the SQLite database and sidecars,
backups, exports, receipts, regression bundles, and the integrity of repository instructions.

The principal boundaries are:

1. agent log files, OTLP clients, imported archives, and MCP peers into Cairn parsers;
2. SQLite data into API responses and browser rendering;
3. the browser into the loopback HTTP service;
4. Cairn into the workspace filesystem and managed instruction blocks;
5. local analysis into an optional remote model provider;
6. the build environment into installed packages and release artifacts;
7. a private workspace into a user-approved export.

All imported prompts, responses, tool descriptions/results, file excerpts, attributes, adapter
fields, archive values, model output, and MCP-provided values are untrusted data. Local users and
processes may be benign, mistaken, or malicious. An attacker may control a web page visited in the
same browser, an imported log/archive, an instrumented OTLP client, an MCP peer, a dependency, or
content inside a repository. Cairn does not defend against an administrator or full compromise of
the current OS account.

## Threats and controls

| Threat | Current controls | Residual risk |
|---|---|---|
| Local log poisoning and malicious/deep traces | Bounded request/query sizes, typed validation, deterministic analyzers, explicit project-path attribution, and parse-error isolation | Plausible but false telemetry can still bias findings; adapter-specific file budgets continue to be expanded |
| XSS or executable content rendering | JSON serialization, React text rendering, CSP, MIME-sniffing and frame denial, no remote static dependencies | A future unsafe rendering component or compromised dependency could reintroduce script execution |
| Path traversal or symlink escape | Export roots are resolved, protected destinations and symlinks are refused, filenames are controlled | New import/export surfaces require the same containment checks |
| SQL injection | Parameterized SQLite queries and typed/bounded public query fields | Hand-built future query fragments remain a review target |
| CSRF and cross-origin mutation | Same-origin browser checks, SameSite token cookie, explicit preflight policy, bearer authentication on exposed binds | A compromised same-origin page/browser context can act with that user's authority |
| Token leakage | Query bootstrap is GET/HEAD-only, immediately redirects to a token-free URL, uses no-store, and stores an HttpOnly SameSite cookie | The initial URL can be observed by local process inspection, browser history/extensions, proxies, or terminal capture |
| DNS rebinding and Host-header abuse | Arbitrary DNS Host values are rejected; browser Origin must exactly match Host | Wildcard non-loopback binds accept IP-literal hosts and remain unsuitable for hostile networks |
| Unsafe static/session exports | Known-secret/path scrubbing, CSP/self-contained output, private default modes, and explicit user action | Pattern-based scrubbing cannot recognize every private value; users must review before sharing |
| Provider prompt exfiltration | Provider use is optional; deterministic local behavior remains available; trace content is data, not policy | Any selected remote provider receives the fields in its request; egress preview/ledger coverage is tracked separately |
| Indirect prompt injection | Untrusted content cannot authorize actions; analysis policy and content must remain structurally separate; model output is data | Human operators can still follow malicious suggestions without review |
| MCP peer manipulation | Local MCP uses stdio; peer descriptions/annotations are hints, and tools validate bounded typed input | The launching client and current OS account remain trusted for process access |
| Dependency or release compromise | Frozen lockfiles, pinned workflow actions, tests, artifact verification, and planned checksums/SBOM/provenance | Scanners and provenance cannot prove source or dependency safety |
| Local disclosure at rest | Owner-only Unix modes, doctor detection/repair, and no telemetry account | Data is not encrypted; same-user processes and administrators can read it |

## Optional model-analysis boundary

Any current or future LLM analysis must keep trusted policy and user-approved intent in separate
message fields from delimited, provenance-labelled trace data. It must have no shell, tool,
filesystem-write, secret, or additional network capability by default. Inputs and outputs require
size, nesting, time, and token limits; output must validate against a narrow typed schema and render
as inert data, never as executable HTML, Markdown, SQL, or shell. A suggested command or mutation
requires a separate explicit approval. The UI must disclose whether a model is local or remote and
which field classes were sent. Failure or disablement must preserve deterministic non-LLM
analysis.

## Verification and review

Security regression coverage includes public API bounds and error envelopes, OTLP size rejection,
scrubber fixtures, export containment and modes, Host/Origin/token/preflight/header behavior,
project-attribution privacy, and permissive-umask/doctor repair cases. The release gate must run
these tests from a clean install. Changes to ingestion, rendering, SQL construction, HTTP/MCP
transport, provider calls, filesystem writes, archives, or exports require threat-model review.
