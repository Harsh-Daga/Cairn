# Release process

Cairn releases are explicit, tag-driven, and build once. A merge to `main` cannot publish.

## Release preparation

1. Complete the release PR: version sources and lockfiles, changelog sections and compare links,
   generated API/CLI/accuracy assets, notices, screenshots, and documentation.
2. Run the **single local release gate** (lint, types, pytest, UI, Playwright, generated drift,
   packaging, clean-wheel doctor, reproducibility):

   ```bash
   uv run python scripts/release_check.py
   ```

   Faster packaging-only path (CI packaging jobs / wheel metadata):  
   `uv run python scripts/release_check.py --packaging-only`
3. Require the normal CI/security checks and review the produced evidence.
4. After merge, a maintainer creates an **annotated** `vMAJOR.MINOR.PATCH` tag. The workflow also
   supports an approved manual dispatch, but only for an already-existing annotated tag.

The release workflow validates that tag against package metadata. It builds one wheel and one
sdist, creates a CycloneDX runtime SBOM, changelog-derived release notes, and `SHA256SUMS`, and
attests those subjects. A separate job downloads and tests those exact artifacts before the
protected `pypi` environment can approve Trusted Publishing. The GitHub Release consumes the same
downloaded artifact set. A final clean `uvx` install verifies the public PyPI version.

Do not rebuild an artifact manually to “fix” a failed publication. Correct the source under a new
version. PyPI filenames are immutable, and the release workflow intentionally fails instead of
silently skipping a version collision.

## Consumer verification

Download the wheel, `SHA256SUMS`, and SBOM from the GitHub Release, then run:

```bash
sha256sum --check SHA256SUMS
gh attestation verify cairn_workspace-1.2.0-py3-none-any.whl \
  --repo Harsh-Daga/Cairn \
  --signer-workflow Harsh-Daga/Cairn/.github/workflows/publish.yml
```

Inspect `cairn-1.2.0.cdx.json` for the resolved Python runtime inventory. See
[the reproducible-build assessment](reproducible-builds.md) for the scope and non-claims.

## Maintainer-only configuration

Before the first use, configure the GitHub `pypi` environment with required reviewers and add the
PyPI Trusted Publisher for repository `Harsh-Daga/Cairn`, workflow `publish.yml`, environment
`pypi`. Enable artifact attestations and give only the release jobs the checked-in permissions.
These are external maintainer actions; local implementation does not change or claim their state.
