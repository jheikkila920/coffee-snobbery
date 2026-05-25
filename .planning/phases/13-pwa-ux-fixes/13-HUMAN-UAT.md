---
status: partial
phase: 13-pwa-ux-fixes
source: [13-VERIFICATION.md]
started: 2026-05-25T11:20:00Z
updated: 2026-05-25T11:20:00Z
---

## Current Test

[awaiting human testing]

## Preconditions

- Local stack rebuilt this session; running at http://localhost:8080 (cache `snobbery-v20260525111723`).
- For your INSTALLED iOS PWA: deploy to the VPS first (`git pull && docker compose build coffee-snobbery && docker compose up -d coffee-snobbery`). C9 fixes FUTURE auto-updates; the currently-installed pre-C9 service worker should self-replace on next launch (the `/sw.js` bytes changed), but do ONE "Clear site data" (Settings > Safari, or DevTools > Application > Clear storage) on the first post-deploy load to remove any doubt. Subsequent deploys won't need it — that is the whole point of C9.
- Visual/375px checks: use DevTools responsive mode at 375px against localhost.

## Tests

### 1. C9 — SW cache bumps per build (already machine-verified)
expected: Two consecutive builds with a template change yield DIFFERENT `snobbery-v...` cache names; no-op rebuild stays stable; `skipWaiting` + `clients.claim` preserved.
result: [pending] — orchestrator confirmed locally (snobbery-v20260525024520 -> ...105505). Listed for your audit/sign-off.

### 2. C10 — Icon visual quality
expected: `app/static/img/logo-badge.png` and `icon-512.png` show the FULL mascot (bean + top-hat + monocle + cup + steam) inscribed in the circle, undistorted (not squished, not zoomed to the face). `icon-512-maskable.png` keeps ~10% safe-zone padding on cream. In-app at 375px, the top-left nav badge is a clean circle with the full undistorted mascot.
result: [pending]

### 3. C1 — iOS standalone top-strip safe-area (REAL IPHONE REQUIRED)
expected: On the installed iOS PWA, the top strip (logo + search) is NOT obscured by the status bar / Dynamic Island.
result: [pending] — NOTE: this reuses the UNVERIFIED safe-area technique from the bottom-nav fix (commit 982c0e6). If the top strip is still obscured, the technique needs a revised approach for BOTH top and bottom — report that.

### 4. C4 — Dark toggle: instant switch, no FOUC, persistence
expected: Config hub shows an Auto/Light/Dark toggle near Sign out (Auto default). Choosing Dark -> app goes dark immediately; reload -> still dark with NO flash of light first. Choosing Light -> light; reload -> still light. Choosing Auto -> follows the OS/DevTools prefers-color-scheme.
result: [pending]

### 5. C4/D-02 — Light wins on dark system; login always dark
expected: With the OS set to dark, choosing Light keeps the app LIGHT (proves the old @media blocks are now `.dark`-class-scoped). Signed-out `/login` (and `/setup`) stay espresso-dark regardless of toggle/system.
result: [pending]

### 6. C6 — Guided-brew cue controls read clearly
expected: On `/brew/guided`, the Audio & haptic cue controls read as clear On/Off (no ambiguous `role=switch`). Toggle Chime + Vibrate, reload -> choices persist (localStorage `snobbery:gbm:cues`). In-brew cue buttons also read clearly.
result: [pending]

### 7. C7 — Ratio recalc on prefill; single-line stars at 375px
expected: On `/brew/new`, selecting a recipe/coffee that prefills dose & water updates the "1:N.NN" ratio IMMEDIATELY without typing; typing dose still updates it. The 0-5 rating stars sit on a SINGLE line at 375px (no 4+1 wrap), each star >= 44px tap target.
result: [pending]

### 8. C2/C5/C8 — Create flow + navigation (browser, 375px)
expected:
- C2 (the fixed-this-session blocker): creating a coffee/equipment with VALID data adds it to the list and collapses the form (no refresh). Creating with INVALID data re-shows the form with errors and leaves the list intact (does NOT wipe the catalog).
- C5: Home and Log/sessions pages show a "Guided Brew" action -> `/recipes`.
- C8: Log/sessions view has NO inline Export/Import; config hub links to `/data-tools`; on `/data-tools`, Export downloads a CSV and Import accepts a CSV (CSRF enforced).
result: [pending]

## Summary

total: 8
passed: 0
issues: 0
pending: 8
skipped: 0
blocked: 0

## Gaps
