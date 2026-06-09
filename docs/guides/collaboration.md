# Collaboration

Share ledger state with snapshots, file-based sync bundles, and encrypted exports.

## Snapshots

Point-in-time captures of sessions and CAS objects:

```bash
cairn snapshot create --label e2e-checkpoint
cairn snapshot list
cairn snapshot diff <before-id> <after-id>
# cairn snapshot restore <snapshot-id>   # rewinds ledger — use with care
```

Example create output:

```
Snapshot snap-20260609092242-c0f07c5d
  label: e2e-checkpoint
  sessions: 2
  cas objects: 20
```

## Collab export and import

Export a sync bundle with optional ACL token:

```bash
cd ~/cairn-e2e-test
cairn collab export /tmp/cairn-sync-out --generate-token
```

```
Exported 2 sessions to /tmp/cairn-sync-out
Ledger sha256: 2f05278a60769f49…
Access token (share with importer): PeOD2ADpfnrwT0j2XXR2tIlnJy3bnJ1wuTse7dFLXM8
```

Import on another machine or directory:

```bash
mkdir -p /tmp/cairn-e2e-import && cd /tmp/cairn-e2e-import
git init
cairn collab import /tmp/cairn-sync-out --token '<paste-token>'
cairn collab status
```

```
Imported 2 runs, 0 events, 2 session mirrors.
Last sync: 2026-06-09T09:25:55.331524+00:00
Sessions tracked: 2
```

## Encrypt bundles before sharing

```bash
export CAIRN_ENCRYPTION_KEY='demo-passphrase'
cairn security encrypt outputs/bundle-live.zip outputs/bundle-live.zip.enc
cairn security decrypt outputs/bundle-live.zip.enc /tmp/bundle-restored.zip
```

## Security audit

```bash
cairn security audit
```

Example findings (informational):

```
[info] scrub.enabled: Bundle scrubbing is enabled via render/scrub.py for exports.
[warn] api.token.missing: Set CAIRN_API_TOKEN before exposing cairn api serve beyond localhost.
[info] session.mirrors: Checked 2 session mirror(s); no obvious secret patterns.
```

See [Security](../security.md) for credential handling and scrubbing.

## Related

- [CLI reference](../reference/cli.md) — snapshot and collab commands
- [Security](../security.md) — encryption and audit details
