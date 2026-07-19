# Dependency vulnerability suppression policy

Cairn does not carry blanket scanner ignores. `pip-audit`, `npm audit`, dependency review, CodeQL,
and Scorecard run from pinned workflows. A finding may be suppressed only when a maintainer records
all of the following in this file:

- package, advisory, affected versions, and scanner;
- evidence that the vulnerable behavior is unreachable or otherwise mitigated;
- named owner and tracking issue;
- approval date and an expiry no later than 90 days;
- the exact narrow configuration or advisory identifier being suppressed.

Expired suppressions fail review and must be removed or renewed with new evidence. Development-only
dependencies are not automatically exempt because their servers and build hooks process repository
content. There are no active suppressions as of 2026-07-17.
