# Security

Cairn is designed for local development and trusted environments. This page covers defaults,
credential handling, and safe sharing.

## Defaults

| Behavior | Detail |
|----------|--------|
| **Local bind** | `cairn api serve` and `cairn live serve` listen on `127.0.0.1` |
| **No cloud** | Ledger and CAS stay under `.cairn/` on disk |
| **Env-only credentials** | API keys are read from environment variables, never `cairn.toml` |
| **Scrubbed exports** | Bundles pass through `render/scrub.py` to redact common secret patterns |

## Provider credentials

Set keys in your shell or a local `.env` (never commit):

```bash
export OPENAI_API_KEY=...
export ANTHROPIC_API_KEY=...
export GEMINI_API_KEY=...
export OPENROUTER_API_KEY=...
```

Run `cairn doctor` to verify configuration before spending tokens.

## API authentication

When exposing the HTTP API beyond localhost, require a bearer token:

```bash
export CAIRN_API_TOKEN="your-local-token"
cairn api serve
```

Clients must send:

```
Authorization: Bearer your-local-token
```

## Encrypting shared bundles

For reports that may leave your machine:

```bash
export CAIRN_ENCRYPTION_KEY="strong-passphrase"
cairn security encrypt outputs/bundle.zip outputs/bundle.zip.enc
cairn security decrypt outputs/bundle.zip.enc outputs/bundle.zip
```

## Security audit

```bash
cairn security audit
cairn security audit --json
```

Checks include inline secrets in config, `.env` presence, unscrubbed session mirrors, and API
token configuration.

## Capture hooks

`cairn watch install` adds hook handlers that run as **your user**. Only install from trusted
Cairn releases. Hooks must not write provider credentials to the ledger. Prefer
`cairn watch install` over manual hook edits so `uninstall` restores backups cleanly.

## Threat model (summary)

Cairn assumes:

- You control the machine running Cairn
- Project directories may contain secrets you choose to scrub before sharing
- Network exposure of `api serve` / `live serve` is your responsibility

Cairn does **not** provide multi-tenant isolation, remote attestation, or managed key storage.
