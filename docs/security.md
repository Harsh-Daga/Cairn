# Cairn Security

## Defaults

- Provider credentials resolve from environment variables only (never committed to `cairn.toml`).
- Capture bundles and reports pass through `render/scrub.py` to redact common secret patterns.
- `cairn api serve` and `cairn live serve` bind to `127.0.0.1` by default.

## API authentication

Set a bearer token before exposing the HTTP API beyond localhost:

```bash
export CAIRN_API_TOKEN="your-local-token"
cairn api serve
```

Clients must send `Authorization: Bearer <token>` on every request when the token is set.

## Report encryption

Encrypt exported artifacts for private sharing:

```bash
export CAIRN_ENCRYPTION_KEY="passphrase"
cairn security encrypt outputs/bundle.zip outputs/bundle.zip.enc
cairn security decrypt outputs/bundle.zip.enc outputs/bundle.zip
```

## Audit

```bash
cairn security audit
cairn security audit --json
```

Checks for inline secrets in config, `.env` presence, unscrubbed session mirrors, and API token configuration.

## Hook subprocess guidelines

- Hooks run with the invoking user's privileges; install only from trusted Cairn releases.
- Hook handlers must never write provider credentials to the ledger or session mirrors.
- Prefer `cairn watch install` over manual hook edits so uninstall stays clean.
