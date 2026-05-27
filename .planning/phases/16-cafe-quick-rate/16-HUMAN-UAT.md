---
status: partial
phase: 16-cafe-quick-rate
source: [16-VERIFICATION-AUTO.md]
started: 2026-05-27T20:55:00Z
updated: 2026-05-27T20:55:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. 20-second log path timing on mobile (CAFE-01)
expected: A returning user, on a phone at 375px viewport, can navigate from /brew → Quick rate → /cafe-logs/new, fill cafe_name + rating, and tap Save in under 20 seconds.
result: [pending]

### 2. Playwright sticky-Save assertion at 375×667 (CAFE-03)
expected: `tests/routers/test_cafe_logs.py::test_cafe_form_save_visible_at_375x667` passes against a Playwright-capable host (the container env skips with "playwright not installed"). Save bar remains visible at the bottom of the viewport on iPhone SE dimensions.
result: [pending]

### 3. Visual cafe-vs-brew card distinction (CAFE-03)
expected: When toggling between the Sessions brew tab and the cafe tab, the cards/rows render with a clear visual difference so the user can tell at a glance which kind of session they're looking at. (Verifier audited the templates — no visual diff possible without a browser.)
result: [pending]

### 4. Dark-mode rendering (CAFE-02, CAFE-03)
expected: Toggling system/app dark mode, /cafe-logs/new (form) and /brew?tab=cafe (list) render legibly — text contrast, border colors, chip backgrounds, dropdown highlight states. Spot-check `bg-cream-200`, `bg-espresso-700/800`, etc. inverted classes are applied correctly.
result: [pending]

## Summary

total: 4
passed: 0
issues: 0
pending: 4
skipped: 0
blocked: 0

## Gaps
