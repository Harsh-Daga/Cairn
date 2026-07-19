# Browser support

Cairn serves a local, account-free application from its loopback server and also produces a
self-contained read-only `file://` snapshot. It targets current evergreen desktop browsers; it
does not support Internet Explorer, legacy EdgeHTML, embedded webviews, or JavaScript-disabled
operation.

## Release policy

| Surface      | Release coverage                                                                                                                    | Support statement                                                                                                                      |
| ------------ | ----------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| Chromium     | Complete seeded route, keyboard, axe, responsive, static-file, and preference suite using the repository-pinned Playwright Chromium | Primary tested engine; current Chrome and Edge issues are release-relevant when reproducible                                           |
| Firefox      | Targeted Overview, custom-range, session-detail, and `file://` snapshot journeys using repository-pinned Playwright Firefox         | Supported for core journeys; engine-specific issues outside the targeted matrix must be reproduced before a guarantee is made          |
| WebKit       | Targeted Overview, custom-range, session-detail, and `file://` snapshot journeys using repository-pinned Playwright WebKit          | Compatibility proxy for current Safari, not a claim that every shipping Safari/OS combination was exercised                            |
| Mobile/touch | 390×844 touch context plus 320-CSS-pixel/200% reflow, with every current route in the mobile dock                                   | Responsive browser UI is supported; Cairn is not a native iOS/Android app and the automated run is not a physical-device certification |

The exact engine builds come from the locked `@playwright/test` dependency. CI installs all three
engines and does not silently skip missing browsers. The full Chromium matrix and the tagged
Firefox/WebKit journeys must all pass for release readiness.

## Operating-system preferences

Automated Chromium journeys exercise `prefers-color-scheme`, `prefers-reduced-motion`, and
`forced-colors`. Reduced motion removes nonessential running animation. Forced colors retains
system-visible focus outlines, card/navigation boundaries, text labels, and non-color estimate
and severity cues. Touch tests require at least 44×44 CSS-pixel route targets and tap navigation
without hover.

The WebKit run on Linux or macOS is still Playwright WebKit; it does not prove macOS VoiceOver or
iOS Safari behavior. Manual assistive-technology and native-device results must be recorded
separately and are never inferred from this automation.

## Network and privacy

The runtime UI bundles its fonts, scripts, and styles. Browser support does not depend on a CDN,
remote account, analytics endpoint, or telemetry. Loopback, Host/Origin, token, and static-snapshot
security boundaries are the same across supported engines.
