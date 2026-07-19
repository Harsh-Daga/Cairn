# ADR 0003: OpenAPI schema and generated TypeScript types

Status: accepted for 1.2.0

## Context

Transport types are handwritten, generation is optional, errors vary, and domain models leak into
responses.

## Decision

- FastAPI OpenAPI is the HTTP source of truth with stable operation IDs, bounded inputs, examples,
  and named success/error responses.
- API DTOs are separate from stored domain models.
- A deterministic in-repository generator commits TypeScript transport types and curated API
  documentation. CI fails on drift.
- A compatibility snapshot rejects removed routes, methods, fields, and enum values. Additive
  fields remain permitted.
- Application errors use one envelope; legacy nested shapes remain readable during migration.

## Consequences

DTO changes require regeneration and compatibility review. UI view models map from generated
transport types.
