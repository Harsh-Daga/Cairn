# Releasing

Canonical maintainer release process: **[release.md](release.md)**.

Single local gate before a release PR:

```bash
uv run python scripts/release_check.py
```

That page also covers tag-driven publish, SBOM + SHA256SUMS, attestation verification, and what is
maintainer-only. Companion notes:

- [Reproducible builds](reproducible-builds.md) — rebuild scope and non-claims
- [SECURITY.md](../SECURITY.md) — supported release lines
- [CHANGELOG.md](../CHANGELOG.md) — user-facing notes

Do not treat a merge to `main` as a publish. Package version and badges must match until an
annotated release tag is cut.
