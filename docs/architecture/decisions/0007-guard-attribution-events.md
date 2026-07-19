# ADR 0007: Guard attribution and instruction-file events

Status: accepted for 1.2.0

## Context

Experiments measure managed edits, but arbitrary instruction-file history and attribution are not
stored.

## Decision

- Store scrubbed, repository-relative instruction events in a numbered migration: file identity,
  before/after hashes, bounded diff summary, git/worktree evidence, source, and timestamp.
- Associate sessions by UTC event boundaries and explicit instruction hashes where available.
- Use “associated with” or “observed after” for before/after comparisons unless the method
  supports causal language.
- Renames, reverts, merges, dirty/no-git workspaces, insufficient windows, and confounders are
  first-class states.
- Optimize experiments link to Guard events without rewriting historical verdicts.

## Consequences

Git inspection stays local/read-only. Raw instruction text is not exported by default.
