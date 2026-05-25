---
status: passed
phase: 13-pwa-ux-fixes
source: [13-VERIFICATION.md]
started: 2026-05-25T11:20:00Z
updated: 2026-05-25T18:00:00Z
---

## Current Test

[APPROVED by John 2026-05-25 — all items resolved across 3 rounds; #12 Start-brew
+ Cancel-move verified via live browser, icons/nav/layout confirmed on-device.]

## Tests

### 1. C9 — SW cache bumps per build
expected: cache name bumps on a front-end change; SW lifecycle preserved.
result: pass ("not sure how to test, but seems fine")

### 2. C10 — Icon visual quality
expected: full undistorted mascot, readable against background.
result: issue→fix-pending-redeploy — mascot much better, but background blended with the mascot. John updated hero.jpg; icons regenerated from it (commit pending push). Re-verify after deploy.

### 3. C1 — iOS standalone top-strip safe-area
result: pass ("safe area on iOS is good")

### 4. C4 — Dark toggle: instant switch, no FOUC, persistence
result: pass ("dark toggle works well")

### 5. C4/D-02 — Light wins on dark system; login always dark
result: pass

### 6. C6 — Guided-brew cue controls read clearly
result: pass ("Audio & haptic cue controls much easier to understand now")

### 7. C7 — Ratio recalc on prefill; single-line stars
result: ISSUE — ratio does NOT auto-populate when dose & water have prefilled values (the x-init re-sync fix did not work). Stars single-line: OK (not called out).

### 8. C2/C5/C8 — Create flow + navigation
result: pass (create valid/invalid + Guided Brew links + data-tools all good)

## Summary

total: 8
passed: 8
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

| # | Type | Item | Status |
|---|------|------|--------|
| C10 | gap (fix-pending) | Icon background blended with mascot; hero.jpg updated + icons regenerated — re-verify after deploy | fixed-pending-verify |
| C7 | gap (bug) | Brew ratio does not recalc when a recipe/coffee prefills dose & water programmatically; x-init re-sync did not fire/pick up values | open |
| NEW-09 | enhancement | Log page: put Guided Brew + Log Session + Filters on ONE row (Filters on its own row lengthens the page) | open |
| NEW-10 | enhancement | Home page: make Admin, Guided Brew, Log Session buttons all the same size | open |
| NEW-11 | enhancement | Equipment + coffee cards still tall; move edit/archive buttons to top-right corner (smaller ok) | open |
| NEW-12 | bug + UX | "Start Guided Brew" button does nothing (tried cues on/off) — pre-existing, likely iOS unlockAudio/wakeLock throwing before isRunning=true OR steps JSON server/client mismatch (needs browser/on-device debug). Also: move the Cancel button to the BOTTOM, under Start Guided Brew | open |
| NEW-13 | bug | Log/sessions page still shows the bottom nav raised up (982c0e6 bottom safe-area); config page is correct now | open |

## Round 3 resolutions (2026-05-25)

| # | Resolution | Status |
|---|------------|--------|
| NEW-12 | ROOT CAUSE: `data-steps="{{ recipe.steps\|tojson }}"` used a double-quoted attribute; tojson doesn't escape `"`, so the JSON truncated to `[{` → client `steps=[]` → `start()` no-op (all platforms). Fixed by single-quoting. VERIFIED via live authed browser repro: stepCount 3, Start → isRunning=true. | fixed-VERIFIED |
| C7 | per-input `x-init="setDose($el.value)"` (CSP-safe; the prior `$nextTick(()=>…)` arrow was rejected by the @alpinejs/csp build) | fixed-pending-verify |
| NEW-09/10/11 | sessions one-row / equal home buttons / card edit-archive top-right | fixed-pending-verify |
| NEW-13 | min-height:100dvh on mobile content wrapper so short pages fill the viewport (iOS standalone fixed-nav float). Not reproducible off-device. | fixed-pending-device |
| C10/#2 | cache-bust icon URLs (?v=build_hash) so iOS re-fetches the regenerated (darkened-hero) icons | fixed-pending-device |
