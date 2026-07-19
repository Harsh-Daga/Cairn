# API domain boundaries

Cairn keeps its historical Python import surfaces stable while grouping API models and payload
builders by product domain. Routers, extensions, and tests may continue importing public names
from `server.api.schemas` and `server.api.payloads`.

## Compatibility facades

- `server.api.schemas` re-exports every public Pydantic model from `server.api.schema`.
- `server.api.payloads` re-exports every public payload builder from
  `server.api.payload_domains`.
- A re-export is the original class or function object, not a wrapper. Signatures, model identity,
  exception behavior, and generated OpenAPI therefore remain unchanged.
- New public models or builders must be added to the owning domain module and to the facade's
  explicit `__all__`. Compatibility tests fail if a facade name is missing or points elsewhere.

## Ownership

| Domain | Schemas | Payload builders |
|---|---|---|
| Overview | overview, recap, money, tail-risk and data-note models | overview, recap |
| Traces | lists, detail, diff, replay, labels and span-tree models | trace list/detail/diff/replay/checkpoints |
| Analytics | agents, behavior, quality, usage, regions, tools, files, compare, waste and tail models | matching analytics endpoints |
| Improvement | insights, evidence and experiment models | insights, evidence and experiments |
| Query | shared typed Sessions/Search filter tokens and errors | — |
| System | actions, errors, search and workspace models | search and workspace |

The canonical grammar and evaluator metadata live in `server.query_filters`; type generation
commits the matching UI operator manifest and API JSON reference. Shared range and data-note
calculations live in `server.api.payload_domains.common`. Domain modules may depend on shared
store/model/analyzer layers. Cross-domain payload dependencies should be explicit and acyclic;
currently tail analytics reuses the overview tail-risk calculation.

## Change procedure

1. Change the owning domain model or builder.
2. Preserve or deliberately extend the compatibility facade.
3. Regenerate OpenAPI, TypeScript types, the compatibility snapshot, and API index.
4. Run API behavior, compatibility, static-export, strict type, and generated-drift checks.

Do not put request parsing, authentication/authorization, or untrusted-input execution in payload
builders. Routers own HTTP concerns; payload builders only query local repositories and construct
typed response data.
