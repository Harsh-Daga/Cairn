# OpenSSF security posture gap report — 2026-07-17

This is a repository-grounded gap assessment, not a compliance claim or badge application. It
pins the [OSPS Baseline v2026.02.19](https://baseline.openssf.org/versions/2026-02-19.html)
(upstream tag `e67ae247ebfb2fd758c9d186335e60cad0a74e78`) and reviews every control in
its checklist. Remote GitHub/PyPI settings are recorded as maintainer actions unless their state is
observable from checked-in files. “Local evidence” means the repository contains evidence; it does
not claim that an external ruleset is enabled.

## OSPS Baseline mapping

| Level | Controls | State | Evidence or smallest remaining action |
|---|---|---|---|
| 1 | OSPS-AC-01.01, OSPS-AC-02.01, OSPS-AC-03.01, OSPS-AC-03.02 | maintainer setting | Require MFA, least-privilege collaborator grants, and the protected-main ruleset in `docs/maintainers/github-settings.md`; remote state was not changed or asserted. |
| 1 | OSPS-BR-01.01, OSPS-BR-01.03 | local evidence | Workflows do not interpolate PR titles/bodies into commands, use read-only defaults, disable persisted checkout credentials, and expose no publishing secret to PR jobs. |
| 1 | OSPS-BR-03.01, OSPS-BR-03.02 | local evidence | Official repository, issue, documentation, and package links use authenticated HTTPS; publishing is being moved to Trusted Publishing. |
| 1 | OSPS-BR-07.01 | partial | Checked-in secret/vulnerability automation and the threat model cover prevention; enable GitHub secret scanning and push protection per the settings checklist. |
| 1 | OSPS-DO-01.01, OSPS-DO-02.01 | local evidence | `README.md`, `docs/getting-started.md`, generated CLI/API docs, `CONTRIBUTING.md`, issue forms, and `SECURITY.md`. |
| 1 | OSPS-GV-02.01, OSPS-GV-03.01 | local evidence | Public issues/pull requests and `CONTRIBUTING.md`. A Discussions-versus-wiki choice remains a maintainer setting, not a second implied support surface. |
| 1 | OSPS-LE-02.01, OSPS-LE-02.02, OSPS-LE-03.01, OSPS-LE-03.02 | local evidence | Apache-2.0 `LICENSE`; artifact inclusion remains covered by the packaging/release gate tracker row. |
| 1 | OSPS-QA-01.01, OSPS-QA-01.02 | externally observable | The configured origin is the public static GitHub URL and Git is the change record. No claim is made about retention settings outside the repository. |
| 1 | OSPS-QA-02.01 | local evidence | `pyproject.toml`, `uv.lock`, `ui/package.json`, and `ui/package-lock.json`. |
| 1 | OSPS-QA-04.01 | not applicable | Cairn is delivered from one source repository; external package registries are distribution channels, not project codebases. |
| 1 | OSPS-QA-05.01, OSPS-QA-05.02 | local evidence | Source repository excludes build output and executables; committed screenshots/fonts are reviewable product/docs assets with license review tracked by T00-04. |
| 1 | OSPS-VM-02.01 | local evidence | `SECURITY.md` identifies the private reporting route and security contact process. |
| 2 | OSPS-AC-04.01 | local evidence | Every workflow declares top-level permissions; invariant tests reject missing permissions. |
| 2 | OSPS-BR-02.01, OSPS-BR-04.01 | local evidence | Semantic versions and `CHANGELOG.md`; final 1.2.0 version/changelog consistency remains a release-gate item. |
| 2 | OSPS-BR-05.01 | local evidence | Frozen uv/npm locks and standardized build/publish tooling. |
| 2 | OSPS-BR-06.01 | local evidence | T01-06 supplies checksums and GitHub artifact attestation from the single tested build; the live emitted attestation remains release-time evidence. |
| 2 | OSPS-DO-06.01 | partial | Lockfiles, Dependabot, dependency review, and scanner workflow are present; add the maintainer dependency-selection prose required by T07-03. |
| 2 | OSPS-DO-07.01 | local evidence | `CONTRIBUTING.md`, `pyproject.toml`, lockfiles, and the frozen CI commands. |
| 2 | OSPS-GV-01.01, OSPS-GV-01.02 | in progress | T00-03 must add accurate `MAINTAINERS.md` and `GOVERNANCE.md`; sensitive-access membership is a maintainer-confirmed fact and must not be invented. |
| 2 | OSPS-GV-03.02 | local evidence | `CONTRIBUTING.md` defines development and acceptance expectations; the contributor map is tracked by T07-03. |
| 2 | OSPS-LE-01.01 | maintainer decision | No DCO/CLA assertion is currently evidenced. Maintainers must choose and enforce one before claiming Level 2. |
| 2 | OSPS-QA-03.01 | maintainer setting | Enable the required main ruleset/status checks listed in `docs/maintainers/github-settings.md`. |
| 2 | OSPS-QA-06.01 | local evidence | CI runs Python, UI, generated, browser, package, and migration checks; workflow invariant tests prevent silent removal of core gates. |
| 2 | OSPS-SA-01.01, OSPS-SA-02.01 | local evidence | Architecture ADRs, threat model, generated OpenAPI/API documentation, CLI docs, MCP docs, and data model. |
| 2 | OSPS-SA-03.01 | local evidence | `docs/security/threat-model.md` is the dated 1.2 security assessment and documents actors, assets, boundaries, threats, mitigations, and non-goals. |
| 2 | OSPS-VM-01.01 | partial | `SECURITY.md` provides coordinated disclosure and scope; exact acknowledgement/remediation targets must remain honest and are tracked by T00-02/T00-03. |
| 2 | OSPS-VM-03.01 | maintainer setting | Enable GitHub private vulnerability reporting. The documentation must not imply that it is enabled before verification. |
| 2 | OSPS-VM-04.01 | local evidence | Security fixes are recorded in changelog/release notes; advisories belong in GitHub Security Advisories when applicable. |
| 3 | OSPS-AC-04.02 | local evidence | Job-level write permissions exist only for Pages, SARIF/Scorecard, and release identity/provenance surfaces. |
| 3 | OSPS-BR-01.04 | local evidence | Manual release inputs are being constrained to a validated tag; Pages has no free-form command input. |
| 3 | OSPS-BR-02.02 | local evidence | T01-06 binds wheel, sdist, checksums, SBOM, attestation, and release entry to the same validated version/tag. |
| 3 | OSPS-BR-07.02 | partial | Threat model and settings checklist cover storage and use; maintainer rotation/revocation practice is not locally verifiable. |
| 3 | OSPS-DO-03.01, OSPS-DO-03.02 | local evidence | Release docs provide checksum and GitHub attestation verification commands and the expected workflow identity. |
| 3 | OSPS-DO-04.01, OSPS-DO-05.01 | gap | A support/EOL policy is not yet complete; T07-03 owns it. |
| 3 | OSPS-GV-04.01 | maintainer setting | Document and apply collaborator review before sensitive access; no external state is asserted. |
| 3 | OSPS-QA-02.02 | local evidence | T01-06 attaches a CycloneDX SBOM generated from the exact installed release wheel environment. |
| 3 | OSPS-QA-04.02 | not applicable | Single source repository. |
| 3 | OSPS-QA-06.02, OSPS-QA-06.03 | local evidence | `CONTRIBUTING.md`, `docs/ci.md`, canonical 1.2 specification, and tracker require behavior tests with changes and define the gates. |
| 3 | OSPS-QA-07.01 | maintainer setting | Require at least one non-author approval in the main ruleset. |
| 3 | OSPS-SA-03.02 | local evidence | `docs/security/threat-model.md` covers attack surfaces and critical local/browser/provider/MCP boundaries. |
| 3 | OSPS-VM-04.02 | policy ready, no active VEX | `docs/security/dependency-suppressions.md` requires evidence for non-exploitability. No current finding needs a VEX statement. |
| 3 | OSPS-VM-05.01, OSPS-VM-05.02, OSPS-VM-05.03 | local evidence | Moderate-or-higher dependency review blocks PRs; `pip-audit` and `npm audit` currently report no known vulnerabilities; narrow time-bounded suppressions are documented. |
| 3 | OSPS-VM-06.01, OSPS-VM-06.02 | partial | CodeQL evaluates Python and JavaScript/TypeScript and uploads SARIF. A severity/remediation SLA and remote branch requirement remain maintainer/process work. |

## OpenSSF Best Practices Badge assessment

No badge or passing status is claimed. The repository has strong local evidence for a documented
license, version control, contribution and vulnerability-reporting instructions, automated tests,
warnings-as-failures, hardened HTTPS links, and dependency tracking. The following badge/process
areas still require closure or external confirmation:

- governance/maintainer identity and access roles;
- branch protection, review enforcement, MFA, and private vulnerability reporting;
- release checksums, SBOM, provenance, and consumer verification;
- support/EOL and dependency-selection policies;
- observed public CI/security results after these workflows run on the remote repository;
- any badge application assertions, which must be reviewed by a maintainer against the live
  project state.

Scorecard is treated as a set of diagnostic findings uploaded to SARIF and retained as an artifact,
not as an aggregate vanity score. This report should be refreshed when the pinned OSPS version
changes or before a security posture claim.
