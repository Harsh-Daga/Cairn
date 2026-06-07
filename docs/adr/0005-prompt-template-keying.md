# ADR 0005: Prompt template keying (no double-counting)

**Status:** Accepted  
**Date:** 2026-06-07  
**Charter:** §9 (cache-key algorithm), R1, R17 #1–#3

## Context

The Phase 0 spike action key included both `prompt_hash` (raw file bytes, including YAML
front matter) and `prompt_front_matter` (parsed key/value pairs). That double-counts the
same information: front-matter edits change both fields. The spike also used a fragile
line-based YAML parser.

## Decision

1. **Parse front matter with PyYAML** (restricted to scalar values in v1).
2. **`prompt_hash` in the action key** is `sha256(utf-8 bytes of the Jinja template body
   only** — everything after the closing `---` of the front-matter block. Front matter is
   excluded from this hash.
3. **Remove `prompt_front_matter` from the action key payload.** Behavior-affecting
   front-matter keys are merged into the node's **resolved config** before keying:
   - `model` → resolved `model` field
   - `params` / scalar tuning keys → merged into `params` (same merge rules as `cairn.toml`)
4. **Descriptive-only front matter** (e.g. `description`) does not enter the action key.
5. **Input completeness:** only `source()` / `ref()` declared in `over` / `inputs` may
   appear in templates; `validate` fails on undeclared references (R17 input-completeness).

## Consequences

- Editing only a `description:` line in front matter does **not** invalidate the cache
  (intentional — metadata is not behavior).
- Editing the template body or a behavior-affecting front-matter override invalidates
  correctly, once.
- Deviates from the illustrative §9 field list (`prompt_front_matter`); Part I principle
  #3 (determinism on real inputs) wins. Golden-hash tests pin the Phase 1 payload shape.
