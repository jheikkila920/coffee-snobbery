---
status: issues_found
phase: 04-shared-catalog
source: [04-VERIFICATION.md]
started: 2026-05-19T20:00:00Z
updated: 2026-05-19T21:30:00Z
tested_by: Claude (Playwright, headless chromium against running container 127.0.0.1:8080)
---

## Current Test

[browser UAT complete — see results + Gaps]

## Tests

### 1. Recipe step builder live reactivity
expected: Open /recipes/new, add a "Bloom" step (50g / 45s) and a second step (150g / 120s). Step 2's delta row shows "+100g · +1:15"; the pour-timeline preview shows proportional vertical segments. Removing step 1 collapses the preview.
result: ISSUE — Alpine @alpinejs/csp build cannot interpret the template expressions the step-builder uses (`idx === steps.length - 1`, `totalTime > 0`, `formatDelta(idx)`, `'Remove step ' + (idx + 1)`, `'Total: ' + totalWater + 'g over ' + ...`). Console: "Alpine is unable to interpret the following expression using the CSP-friendly build" + pageerror "Cannot read properties of undefined (reading 'length - 1')". Delta readouts, timeline preview, and step controls do not function in the browser. See Gap G-04-CSP.

### 2. Autocomplete-on-create-on-save (roaster)
expected: type 2+ chars in roaster field → dropdown; "+ Create new roaster" → modal → save → pre-select.
result: PARTIAL — basic HTMX dropdown population + click-to-select works (a coffee was created end-to-end with a roaster selected via the dropdown). However the coffee form raises 9 Alpine CSP expression errors; the "+ Create new" → mini-modal → pre-select chain depends on Alpine expressions affected by G-04-CSP. Needs re-test after the CSP fix.

### 3. Flavor note chip widget
expected: type → select → chip appears; submit → both IDs in advertised_flavor_note_ids.
result: BLOCKED — depends on Alpine chip rendering (flavorNoteChips x-for + computed expressions) affected by G-04-CSP. Could not confirm chips render or hidden inputs populate.

### 4. Mini-modal dirty check
expected: open modal, type, ESC → confirm prompt; cancel keeps it open.
result: BLOCKED — mini-modal open/dirty logic depends on Alpine expressions affected by G-04-CSP.

### 5. Coffee list responsive layout at 375px
expected: at 375px the desktop table is hidden, card list visible, no horizontal scroll.
result: PASS — verified via Playwright. @375px: table hidden, cards visible, no horizontal scroll. @1280px: table visible. (Required the Tailwind build fix first — see Bug 2 below; before that the responsive utilities were absent.)

### 6. Bag photo upload with device camera (mobile)
expected: capture="environment" present so mobile opens the rear camera.
result: PASS (attribute) — `capture="environment"` now present on both bag photo inputs (commit 71b6774); verified in template. Actual on-device camera open still needs a real phone (cannot be driven headless).

## Summary

total: 6
passed: 2
issues: 1
blocked: 2
partial: 1
pending: 0
skipped: 0

## Gaps

### G-04-CSP — Phase 4 Alpine templates incompatible with the @alpinejs/csp build (BLOCKER)
The project mandates the Alpine CSP build (no unsafe-eval; docs/decisions/0001). That build only supports simple member access and bare method calls — NOT operators (`===`, `>`, `+`, `-`), arithmetic, string concatenation, ternaries, or method calls with arguments. The Phase 4 templates (plans 04-08 recipe step builder, 04-11 autocomplete/chips/mini-modal) were authored with regular-Alpine expressions and are rejected at runtime. pytest never caught this because the in-process TestClient does not execute browser JS.

Affected (non-exhaustive, observed in console):
- `idx === 0`, `idx === steps.length - 1`
- `totalTime === 0`, `totalTime > 0`
- `formatDelta(idx)` (method call with an argument)
- `'Remove step ' + (idx + 1)`
- `'Total: ' + totalWater + 'g over ' + formatTime(totalTime)`

Fix direction: refactor the Phase 4 Alpine templates so every binding is a bare property/getter or no-arg method. Move all comparisons/arithmetic/concatenation into the component as computed getters or no-arg methods (e.g. expose `isFirst`/`isLast` per row via an x-for child component or index helpers, a `deltaLabel` getter array, a `totalLine` getter that returns the full string). Verify zero "CSP-friendly build" console errors after the fix.

Impacts success criteria: SC-1 (autocomplete-on-create), SC-3 (recipe step builder live reactivity). These are NOT met in the browser despite passing code-level verification.

### Foundational bugs found during this UAT (both FIXED — pre-date Phase 4)
- Bug 1 (Phase 1, commit 52bde31): base.html HTMX CDN URL corrupted to `[email protected]` (email-obfuscation mangle of `htmx.org@2.0.10`). HTMX never loaded in any browser. FIXED — commit ac3d328.
- Bug 2 (Phase 0): Dockerfile downloaded Tailwind v4.3.0 CLI but the source uses v3 directives + v3 JS config → ~4KB near-empty stylesheet (palette + most utilities missing). FIXED — commit f806855 (pin v3.4.17 + copy app/static/js into builder).
