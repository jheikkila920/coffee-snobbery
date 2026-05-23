---
phase: 11-pwa-mobile-polish
plan: "04"
subsystem: brew-guided
tags: [guided-brew-mode, timer, wake-lock, nosleep, audio, brew-time, alpine-csp]
dependency_graph:
  requires: [brew-time-seconds-column, head-extra-block, persistent-nav]
  provides: [guided-brew-mode, brew-time-field, gbm-entry-points, wake-lock-fallback]
  affects: [app/routers/brew.py, app/services/brew_sessions.py, app/main.py, app/templates/pages/brew_form.html]
tech_stack:
  added:
    - "NoSleep.js v0.12.0 (self-hosted UMD, app/static/js/vendor/NoSleep.min.js)"
  patterns:
    - Alpine CSP guidedBrewMode component (timer setInterval, AudioContext chime, navigator.vibrate, wakeLock + NoSleep fallback, visibilitychange re-acquire)
    - Full-screen GBM page fixed inset-0 z-50 covering the bottom nav (D-20)
    - head_extra block loads NoSleep.js only on the GBM page (nonce-tagged)
    - brew_guided_router registered BEFORE brew_router (FastAPI registration-order routing)
    - GBM completion redirect to /brew/new?recipe_id&coffee_id&brew_time&gbm=1
key_files:
  created:
    - app/routers/brew_guided.py
    - app/templates/pages/brew_guided.html
    - app/static/js/alpine-components/guided-brew-mode.js
    - app/static/js/vendor/NoSleep.min.js
    - tests/routers/test_gbm.py
  modified:
    - app/templates/pages/brew_form.html
    - app/templates/fragments/recipe_row.html
    - app/routers/brew.py
    - app/services/brew_sessions.py
    - app/main.py
decisions:
  - "NoSleep.js v0.12.0 UMD self-hosted under /static/js/vendor (satisfies script-src 'self' + connect-src 'self'; verified eval-free, Assumption A5) — no CDN runtime dependency"
  - "GBM page is fixed inset-0 z-50 so it fully covers the z-40 bottom nav (D-20: GBM is its own full-screen surface)"
  - "wakeLockState tracks held/fallback/none; native navigator.wakeLock tried first, NoSleep.js fallback on throw, re-acquired on visibilitychange→visible while running"
  - "audio unlocked + wake lock requested inside the Start tap (both need a user gesture on iOS); AudioContext.resume() also called on each step advance (Pitfall 4 re-suspension)"
  - "DEVIATION (Rule-1 bug): brew_time_seconds existed in model+schema (11-02) but was never plumbed through the write path; added the param to create_brew_session and the brew.py create call so it actually persists"
  - "DEVIATION: test file placed at tests/routers/test_gbm.py (matches the existing tests/routers/ layout) rather than the plan's tests/test_gbm.py"
metrics:
  duration_minutes: 18
  completed_date: "2026-05-23"
  tasks_completed: 4
  files_changed: 10
requirements_met: [BREW-12]
requirements_pending_human: [BREW-13]
---

# Phase 11 Plan 04: Guided Brew Mode Summary

Shipped Guided Brew Mode: a full-screen, recipe-driven timer with large countdown, current-step highlight (cumulative water + elapsed), audio chime + vibration cues (live-toggleable, localStorage-backed), pause/resume, manual next-step skip alongside auto-advance, cancel-without-logging, wake lock with self-hosted NoSleep.js iOS fallback, and a "Done brewing" flow returning to a prefilled session form carrying elapsed brew time. Both entry points wired and the editable `brew_time_seconds` field added to the brew form.

## Tasks Completed

| # | Task | Commit | Key Files |
|---|------|--------|-----------|
| 1 | guidedBrewMode component + self-hosted NoSleep.js | e8f8aed | guided-brew-mode.js, NoSleep.min.js |
| 2 | GBM router + full-screen page + main.py registration | ee629b7 | brew_guided.py, brew_guided.html, main.py |
| 3 | Brew-form integration (button + brew_time field + sticky offset) + recipe-row entry | 24d7727 | brew_form.html, recipe_row.html, brew.py |
| 4 | GBM smoke tests + brew_time_seconds persistence fix | d3ead1d | tests/routers/test_gbm.py, brew.py, brew_sessions.py |
| 5 | Real-device wake-lock validation | DEFERRED | (pending — see below) |

## Verification

Automated (in-container, no skips): `tests/routers/test_gbm.py` — **6 passed**:
- GET /brew/guided?recipe_id=N (with steps) → 200, body has guidedBrewMode + data-steps
- GET /brew/guided?recipe_id=<missing> → 404; anonymous → 401
- GET /brew/guided?recipe_id=<stepless> → 200 with "no steps" message
- brew_time_seconds=300 round-trips to the persisted session; 86401 rejected (validation)

Grep gates (all pass): Alpine.data('guidedBrewMode'), snobbery:gbm:cues, /brew/new redirect, no eval/new Function in component or NoSleep.min.js, include_router(brew_guided) registered before brew_router.

## Deferred — Human Verification (BREW-13 wake lock)

Per user decision at the checkpoint, the **real-device wake-lock test is deferred to the next VPS deploy** (the local instance is bound to 127.0.0.1:8080 and is not phone-reachable). The wake-lock code path (native navigator.wakeLock → NoSleep.js fallback → visibilitychange re-acquire), the AudioContext chime, and the prefill round-trip on a physical device remain UNVERIFIED on hardware. Test plan: install to iOS Home Screen, start a guided brew, confirm screen stays on + indicator color (green native ≥iOS 18.4 / yellow fallback), chime on step advance, re-acquire after backgrounding; repeat on Android Chrome. This is the carried multi-phase research flag.

## Deviations from Plan

1. **brew_time_seconds write-path bug fix** (Rule-1) — added `brew_time_seconds` param to `create_brew_session` (app/services/brew_sessions.py) and the brew.py create call. The column/schema existed (11-02) but was never passed to the model constructor, so the value never persisted. Fixed the wiring (NOT the schema). Adds app/services/brew_sessions.py to this plan's touched files (not in original files_modified).
2. **Test path** — tests at `tests/routers/test_gbm.py` to match the existing `tests/routers/` layout (plan said `tests/test_gbm.py`).
3. **Task 5 deferred** — real-device gate not executed (user decision); tracked above + at phase verification.

## Known Stubs

None in code. Real-device behavior unverified (deferred, above).

## Threat Flags

None new. T-11-12 (require_user on /brew/guided — 401 tested), T-11-13 (brew_time validated ge=0/le=86400 — 86401 rejected), T-11-14 (NoSleep self-hosted + nonce-tagged, component eval-free — grep-gated) all mitigated.

## Self-Check: PASSED

Files confirmed: app/routers/brew_guided.py, app/templates/pages/brew_guided.html, app/static/js/alpine-components/guided-brew-mode.js, app/static/js/vendor/NoSleep.min.js (eval-free), tests/routers/test_gbm.py; modified brew_form.html, recipe_row.html, brew.py, brew_sessions.py, main.py.

Commits confirmed: e8f8aed, ee629b7, 24d7727, d3ead1d.
