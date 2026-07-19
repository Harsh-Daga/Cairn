# GitHub and PyPI maintainer settings

These are external maintainer actions. Check them against the live repository; do not mark them
complete from a local checkout.

## Repository and ruleset

- [ ] Set the homepage to `https://harsh-daga.github.io/Cairn/` after verifying Pages.
- [ ] Protect `main` with a ruleset that requires pull requests, one non-author approval,
      conversation resolution, and the current CI/security status checks.
- [ ] Block force pushes and branch deletion. Decide and document whether linear history and signed
      commits are required; do not enable either without a contributor migration plan.
- [ ] Require actions to be pinned to full commit SHAs and restrict allowed actions to GitHub,
      Astral, PyPA, and OpenSSF actions used by the checked-in workflows where practical.
- [ ] Keep workflow-token permissions read-only by default.
- [ ] Choose GitHub Discussions or the wiki only if maintainers will operate it; otherwise keep
      issues and checked-in docs as the single support path.
- [ ] Create and maintain the labels referenced by issue forms:
      `bug`, `enhancement`, `documentation`, `adapter`, `needs-triage`, `security`.

## Security

- [ ] Require MFA for every collaborator with sensitive access and review access periodically.
- [ ] Enable Dependabot alerts and security updates.
- [ ] Enable secret scanning and push protection.
- [ ] Enable the checked-in CodeQL workflow and Scorecard SARIF upload; avoid duplicate default
      CodeQL analysis unless intentionally reviewed.
- [ ] Enable private vulnerability reporting and verify that the security-policy link opens it.

## Pages

Canonical URL: `https://harsh-daga.github.io/Cairn/` (see [pages.md](../pages.md)).
PR builds upload a `pages-preview` artifact; only `workflow_dispatch` deploys.

- [ ] Set GitHub Pages source to GitHub Actions.
- [ ] Dispatch `Demo Pages`, verify the project-site URL and offline/static limitations, then set
      the repository homepage. Pages failure must not block package releases.

## PyPI Trusted Publishing

- [ ] Create GitHub environment `pypi`, restrict it to release tags, and require release approval.
- [ ] In the PyPI `cairn-workspace` project, add a Trusted Publisher for owner `Harsh-Daga`,
      repository `Cairn`, workflow `publish.yml`, environment `pypi`.
- [ ] Confirm no long-lived PyPI API token is stored in GitHub.
- [ ] Run the release workflow only from an existing annotated version tag and review its
      attestation, checksums, SBOM, GitHub Release, and post-publish install.
