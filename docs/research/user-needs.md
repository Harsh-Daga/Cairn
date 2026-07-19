# Research note: user needs

Status: **research note** — synthesis of intended jobs-to-be-done for Cairn’s local evidence loop.
Not a survey dataset and not a commitment that every need ships in 1.2.

## Primary jobs

| Actor | Job | Evidence Cairn aims to provide |
|-------|-----|--------------------------------|
| Individual developer | Understand why a session was expensive or wrong | Session waterfall, waste, outcome, receipt/debt |
| Individual developer | Decide whether an instruction edit helped | Optimize experiment with before/after and CI notes |
| Reviewer | Trust an AI-assisted change without reading the full transcript | Scrubbed receipt, review risk, next checks |
| Maintainer / CI | Gate regressions in quality or cost | `cairn check`, insights, deterministic demo fixtures |
| Privacy-conscious user | Keep telemetry local and inspectable | Storage modes, privacy/resource CLI, egress ledger |

## Time-to-first-evidence (product bar)

Getting started should not stop at “a chart appeared.” In the deterministic demo path, a new user
should be able to:

1. find one meaningful verification or quality finding;
2. open its evidence on Session Detail;
3. view or rebuild a receipt;
4. see a concrete next verification action.

## Needs that stay out of scope (for now)

- Hosted multi-tenant analytics or silent team telemetry.
- Executing inferred verification/setup commands from regressions.
- Cryptographic attestation of receipts (hashing ≠ signing).
- Observing network egress from unrelated agent processes.

## Feedback loop

Product claims in public docs should map to an executable surface (API, CLI, action, UI route, or
fixture). When a need lacks evidence, docs must say unavailable rather than invent a metric.

Related: [audit](../plans/v1.2.0-audit.md), [roadmap](../roadmap.md), [privacy](../privacy.md).
