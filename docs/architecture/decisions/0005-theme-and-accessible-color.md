# ADR 0005: Theme and accessible color tokens

Status: accepted for 1.2.0

## Context

The UI is dark-only and uses palette names/hard-coded colors that do not encode semantics.

## Decision

- Support `system`, `light`, and `dark`; `system` is the new-state default.
- A synchronous same-origin bootstrap in `<head>` applies preference before CSS/React to avoid
  flash. It remains external so the local server and `file://` snapshot keep `script-src 'self'`
  without permitting arbitrary inline script.
- CSS variables describe surfaces, text, borders, focus, overlays, charts, severity, confidence,
  and estimate semantics; Tailwind consumes them.
- Status always includes text/icon/pattern meaning and never relies on color alone.
- Both themes define `color-scheme`, forced-colors behavior, reduced motion, and AA targets.

## Consequences

Existing state is migrated. Hard-coded component colors move incrementally to semantic tokens.
