# ADR 0008: Release build, publish, and provenance

Status: accepted for 1.2.0

## Context

Every `main` push can publish a fresh build, actions use movable tags, and artifacts lack SBOM,
checksums, and provenance.

## Decision

- A release PR updates version/changelog/docs/generated assets and passes normal CI.
- An annotated semantic tag or approved manual dispatch starts one least-privilege build.
- Wheel, sdist, and static assets build once; those exact artifacts are inspected and tested.
- PyPI uses a protected Trusted Publishing environment. GitHub Release consumes the tested
  artifacts and adds checksums, SBOM, and GitHub artifact attestation.
- Actions pin reviewed full SHAs. Untrusted PR jobs get no secrets/write tokens.
- Claimed SLSA level is limited to evidence the hosted workflow actually supports.

## Consequences

Normal `main` pushes never publish. Maintainers apply the documented remote settings separately.
