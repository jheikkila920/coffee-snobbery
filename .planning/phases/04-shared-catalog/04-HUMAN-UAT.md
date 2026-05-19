---
status: passed
phase: 04-shared-catalog
source: [04-VERIFICATION.md]
started: 2026-05-19T20:00:00Z
updated: 2026-05-19T23:45:00Z
tested_by: Claude (Playwright, headless chromium against running container 127.0.0.1:8080)
---

## Current Test

[browser UAT complete — all items pass after G-04-CSP fix]

## Tests

### 1. Recipe step builder live reactivity
expected: add steps, see live cumulative deltas + proportional pour-timeline.
result: PASS — deltas render live ("Δ +50g · +0:45"), totals line ("Total water: 100g · Total time: 1:15"), timeline segments proportional. Zero CSP errors.

### 2. Autocomplete-on-create-on-save (roaster)
expected: type → dropdown → select sets the hidden FK; "+ Create new" → modal → save → pre-select.
result: PASS — typing "Onyx" shows the match; clicking sets hidden roaster_id=14. "+ Create new" opens the mini-modal with the typed text prefilled.

### 3. Flavor note chip widget
expected: type → select/create → chip appears + hidden input submits the id.
result: PASS — create-new flow: typed "Jasmine" → "+ Create new" → modal (prefill "Jasmine") → save → chip "Jasmine ×" rendered and hidden input advertised_flavor_note_ids=18 present (D-16 HX-Trigger pre-select).

### 4. Mini-modal dirty check
expected: type in modal, ESC/backdrop → confirm prompt; cancel keeps it open.
result: PASS — confirm dialog fires on ESC when dirty; modal stays open after cancel.

### 5. Coffee list responsive layout at 375px
expected: at 375px the desktop table is hidden, card list visible, no horizontal scroll.
result: PASS — @375px table hidden, cards visible, no horizontal scroll; @1280px table visible. (Required the Tailwind build fix — see Bug 2.)

### 6. Bag photo upload with device camera (mobile)
expected: capture="environment" present so mobile opens the rear camera.
result: PASS (attribute) — present on both bag photo inputs (commit 71b6774). On-device camera open still warrants a real-phone spot check, but the attribute + pipeline are correct.

## Summary

total: 6
passed: 6
issues: 0
blocked: 0
pending: 0
skipped: 0

## Gaps

### G-04-CSP — RESOLVED (commit 13f67c5)
Phase 4 Alpine UI was non-functional in the browser; pytest could not catch it (in-process TestClient runs no JS). Root causes + fixes:
- @alpinejs/csp pinned at 3.14.9 (old CSP evaluator: bare member access + no-arg calls only). Bumped to 3.15.12 (rewritten evaluator supports operators/arithmetic/concat/method-args; still eval-free).
- pour_timeline used the `Math` global (forbidden in CSP templates) → precomputed barStyle/shadeClass/summary in the component getter.
- coffee_form autocomplete + flavorNoteChips passed config as an object-literal x-data arg via |tojson → unparseable by the CSP build AND broke the double-quoted attribute. Switched to bare x-data + data-* attributes (recipeStepBuilder pattern).
- autocomplete_list per-item handler used inline select(id,"name") (quote-nesting + string-literal arg) → uniform commitItem($el) reading data-item-id/name.
- /roasters/list + /flavor-notes/datalist read q= but the inputs send roaster_query / flavor_note_query → dropdowns always empty. Aligned handlers + tests to the template param names.

Verified end-to-end via Playwright with zero CSP console errors; full pytest suite 316 passed.

### Foundational bugs found during this UAT (all FIXED — pre-date Phase 4)
- Bug 1 (Phase 1, 52bde31): base.html HTMX CDN URL corrupted to `[email protected]`. HTMX never loaded in any browser. FIXED — ac3d328.
- Bug 2 (Phase 0): Dockerfile pulled Tailwind v4.3.0 CLI against v3 source → ~4KB near-empty CSS (palette + utilities missing). FIXED — f806855 (pin v3.4.17 + copy app/static/js into builder).
