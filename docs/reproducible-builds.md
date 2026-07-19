# Reproducible-build assessment

`uv run python scripts/check_reproducibility.py` rebuilds the public static assets, wheel, and
source distribution twice from the same checkout. It derives `SOURCE_DATE_EPOCH` from the source
commit, uses frozen dependencies, compares filenames and SHA-256 digests, and fails with the exact
files that differ.

This is a same-platform assessment, not a claim that archives are byte-identical across operating
systems or independent hosted builders. GitHub-hosted release provenance identifies the workflow,
source tag, and subjects; `SHA256SUMS` identifies the exact wheel, sdist, and CycloneDX SBOM.
Consumers should verify both:

```bash
sha256sum --check SHA256SUMS
gh attestation verify cairn_workspace-1.2.0-py3-none-any.whl \
  --repo Harsh-Daga/Cairn \
  --signer-workflow Harsh-Daga/Cairn/.github/workflows/publish.yml
```

The release workflow builds once, tests a downloaded copy of that artifact, then passes that same
artifact to PyPI Trusted Publishing and the GitHub Release. A rerun may rebuild the same tag, but
the reproducibility gate must produce identical bytes and PyPI will not accept a different file
under an existing filename.

SLSA statement: Cairn targets the provenance properties available from GitHub-hosted Actions and
GitHub artifact attestations. It does not claim a SLSA Build level until the live repository
settings and emitted provenance have been reviewed against SLSA v1.2.
