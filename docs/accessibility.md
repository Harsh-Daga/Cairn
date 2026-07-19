# Accessibility

Cairn targets WCAG 2.2 AA for its primary local journeys. Automated checks are regression evidence,
not a certification or substitute for manual assistive-technology review.

## Appearance and color

Settings → Appearance offers System, Light, and Dark. System is the default for new browser state
and follows operating-system changes while Cairn is open. An explicit choice is stored only in that
browser's local storage; it does not enter the workspace database or leave the device.

A synchronous same-origin script applies the stored or system preference in the document head
before React and the main stylesheet load. It accepts the current `themePreference` field and the
legacy `theme`/`colorScheme` fields, treats malformed or unknown state as System, and works in the
strict-CSP `file://` static snapshot. Both production UI builds package the script.

The theme contract in `ui/src/theme.css` separates:

- canvas, base, raised, overlay, and hover surfaces;
- primary, muted, and disabled text;
- default/strong borders, selection, focus, and overlay scrims;
- seven chart series;
- success plus info, warning, high, and critical severity;
- confidence and estimate semantics;
- spacing, radii, shadows, type scale, and motion durations.

Legacy geological palette names remain compatibility aliases, but their values resolve through the
semantic tokens in both themes. Tailwind opacity modifiers also use those CSS variables; component
source has no hard-coded hexadecimal colors.

Automated tests calculate contrast in both palettes. Primary text meets at least 7:1; muted and
disabled text, the primary accent, and severity colors meet at least 4.5:1 against their intended
surface; the focus token meets at least 3:1. Estimate and confidence states use dashed/dotted
structure, and severity/status presentation retains visible text or icons rather than relying only
on hue. Forced-colors mode restores system focus and border colors, while reduced-motion mode
disables nonessential animation.

## Automated matrix

The seeded Chromium gate runs axe's WCAG 2 A/AA, 2.1 A/AA, and 2.2 AA rules on every application
route in both themes and fails on any violation. Component-level axe checks cover modal primitives;
browser tests cover skip navigation, modal focus trap/restore/Escape, session and waterfall
keyboard traversal, the complete mobile route set, 320-CSS-pixel/200% reflow, touch targets,
reduced motion, and forced colors. Color contrast stays in the real-browser axe run because jsdom
cannot calculate rendered colors.

Tagged core journeys also run in repository-pinned Firefox and WebKit. This is compatibility
evidence, not a substitute for the manual assistive-technology matrix or a claim that every native
Safari/browser/operating-system combination passed. See [Browser support](browser-support.md).

Automated success does not establish conformance. Before a 1.2 release candidate is approved, a
maintainer must run this manual matrix on a seeded workspace and record operating-system,
browser/assistive-technology versions, date, failures, and evidence in the release report:

| Journey                                    | Keyboard check                                                                                                 | Screen-reader check                                                                                             |
| ------------------------------------------ | -------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| Global shell                               | Tab reaches Skip to main content first; focus is never obscured; every desktop and mobile route is reachable   | Landmarks are announced once; current route and workspace status are understandable                             |
| Command palette / shortcuts / custom range | Trigger, Tab/Shift+Tab trap, field labels, validation, Escape, backdrop close, and focus restoration           | Dialog name, modal state, controls, errors, and close result are announced without reading background content   |
| Sessions                                   | Filters and saved views expose selected state; `j`/`k` move the selected row; Enter opens; compare is operable | Table name/caption, headers, selected row, result count, sort/filter state, and page changes are announced      |
| Session detail                             | `j`/`k` and arrows traverse waterfall rows; Enter/Space select; replay has a pointer-free alternative          | Trace heading, replay value, span kind/name/status, estimates, errors, and inspector updates are understandable |
| Charts and metrics                         | Data and explanations are reachable without hover or dragging                                                  | Text summary and table alternative convey the same conclusion and units as each chart                           |
| Errors/live updates                        | Retry and pause controls work; focus remains stable                                                            | Field errors use their labels; status updates are useful and neither silent nor repetitive                      |
| Reflow and preferences                     | Repeat at 320 px, 200% zoom, reduced motion, and forced colors                                                 | Reading/navigation order remains logical in each mode                                                           |

The automated 2026-07-18 run covers the keyboard assertions listed above but is not recorded as a
manual VoiceOver, NVDA, or JAWS run. Cairn therefore does not claim whole-product WCAG conformance.

Maintainers record the manual matrix in
[`plans/v1.2.0-a11y-manual-receipt.md`](plans/v1.2.0-a11y-manual-receipt.md) before approving a 1.2
release candidate.
