---
status: partial
phase: 11-pwa-mobile-polish
source: [11-VERIFICATION.md]
started: 2026-05-23T00:00:00Z
updated: 2026-05-23T00:00:00Z
---

## Current Test

[awaiting human testing on the next VPS deploy — local instance is bound to 127.0.0.1:8080 and is not reachable from a phone]

## Tests

### 1. Real-device iOS Safari installability (MOB-12)
expected: |
  Deploy to the VPS. On a real iPhone in Safari, log in and use the iOS install banner (Share -> Add to
  Home Screen). Confirm: the Home Screen icon is the circular mascot badge (not a screenshot), the app
  launches standalone (no Safari chrome), and the install banner was dismissible and did not reappear once
  dismissed. The manifest link tag is now wired into <head> (verified in served HTML), so the manifest is
  discoverable.
result: [pending]

### 2. Android Chrome installability (Lighthouse) (MOB-12)
expected: |
  Deploy to the VPS. In Chrome DevTools -> Lighthouse -> PWA audit, confirm installability criteria pass
  and the Add to Home Screen prompt appears while logged in. (Automated Lighthouse/Playwright coverage is
  Phase 12 / TEST-06.)
result: [pending]

### 3. Guided Brew Mode wake lock on a real device (BREW-13)
expected: |
  Deferred by user at the 11-04 checkpoint. On a real iPhone (note iOS version): install as PWA, start a
  guided brew, confirm the screen stays on for the full brew; the "Screen stays on" indicator is green
  (native wake lock, iOS >= 18.4) or yellow (NoSleep.js fallback, older iOS); backgrounding for ~10s then
  reopening re-acquires the lock; the chime plays on a step transition. Repeat on Android Chrome (native
  wake lock, green indicator + chime + vibration). Record the device/OS versions and which wake-lock path
  engaged.
result: [pending]

## Summary

total: 3
passed: 0
issues: 0
pending: 3
skipped: 0
blocked: 0

## Gaps

(none — these are real-device confirmations of code that is verified-in-code and green in automated tests; to be completed on the next VPS deploy)
