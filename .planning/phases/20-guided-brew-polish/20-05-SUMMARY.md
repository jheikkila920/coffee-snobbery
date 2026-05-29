---
phase: 20-guided-brew-polish
plan: 05
subsystem: guided-brew-ui
tags: [alpine, guided-brew, timer, wall-clock, coaching, first-drip, bloom, safe-area, mobile-first, GBREW-01, GBREW-02, GBREW-03]

requires:
  - phase: 20-guided-brew-polish
    plan: 02
    provides: StepSchema with type/note/water_temp_c fields consumed by coaching getters
  - phase: 20-guided-brew-polish
    plan: 03
    provides: first_drip/bloom_time query params parsed in /brew/new (finishBrewing() target)
  - phase: 20-guided-brew-polish
    plan: 04
    provides: Typed steps (Bloom/Pour/Wait/Action) + notes + water_temp_c from step builder

provides:
  - Wall-clock-truth timer in guided-brew-mode.js (_startTimestamp/_resync/_syncStateFromElapsed)
  - Coaching getters: coachingLine, stepTypeBadge, stepNote, stepWaterTemp, preCueCountdown, isPreCue
  - Bloom auto-derive: bloomTimeSeconds set when Bloom step transitions in _syncStateFromElapsed
  - Tap-to-mark: markFirstDrip()/clearFirstDrip() with firstDripSeconds state
  - finishBrewing() carries first_drip + bloom_time + brew_time into /brew/new
  - Full coach view in brew_guided.html: pre-cue countdown, coach card, tap-to-mark, bloom indicator, safe-area

affects:
  - 20-06 (validation checkpoint: timer accuracy + coach-feel + 375px layout verified on device)

tech-stack:
  added: []
  patterns:
    - "Wall-clock timer: Date.now()-_startTimestamp in _tick(); _resync() on visibilitychange with isPaused guard before requestWakeLock (Pitfall 7)"
    - "_syncStateFromElapsed walks steps[i].time_seconds as CUMULATIVE offsets (Pitfall 5); fires cues only on newly crossed transitions (Pitfall 2)"
    - "Pause accounting: _pausedAt timestamp + _pausedOffset accumulator; resume adds floor((now-_pausedAt)/1000) to offset before restarting timer"
    - "coachingLine getter: switch on step.type; Pour counts 1-indexed pour sequence from steps.slice(0, idx+1).filter('Pour')"
    - "data-steps SINGLE-quoted with |tojson (project memory: tojson attr quoting); no |safe on user content; x-text not x-html for coaching/note/label"
    - "Safe-area: pb-[max(env(safe-area-inset-bottom),_16px)] on mt-auto cancel section; full-screen fixed inset-0 z-50 owns its own safe-area, NOT .content-nav-safe-area"

key-files:
  created: []
  modified:
    - app/static/js/alpine-components/guided-brew-mode.js
    - app/templates/pages/brew_guided.html

key-decisions:
  - "Wall-clock timer uses Date.now()-_startTimestamp (not elapsedTotalSeconds++ counter) — survives iOS screen sleep without drift"
  - "_syncStateFromElapsed replaces _advanceStep: walks cumulative offsets, handles multiple missed transitions in a single resync, auto-derives bloomTimeSeconds on Bloom step completion"
  - "Pre-cue is visual-only (isPreCue/preCueCountdown getters); chime fires at the transition in _syncStateFromElapsed, not at pre-cue start (Pitfall 2)"
  - "nextStep_action() updated to also check and auto-derive bloomTimeSeconds on manual skip (consistent with _syncStateFromElapsed behavior)"
  - "Done screen shows firstDripSeconds and bloomTimeSeconds summary for user confirmation before logging"

duration: 20min
completed: 2026-05-29
---

# Phase 20 Plan 05: Guided Brew Coach View Summary

**Wall-clock-truth timer with silent catch-up on screen sleep, full coaching card with pre-cue countdown, tap-to-mark first drip, auto-recorded bloom time, and all timing carried into the brew form — GBREW-01, GBREW-02, and live-capture half of GBREW-03 delivered**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-05-29T16:49:32Z
- **Completed:** 2026-05-29T17:09:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

### Task 1: guided-brew-mode.js wall-clock timer + coaching getters + capture

- Replaced `_tick()` `elapsedTotalSeconds++` counter with `Date.now() - _startTimestamp` computation — timer is now wall-clock-truth (D-15, GBREW-01)
- `_startTimer()` sets `_startTimestamp = Date.now() - (elapsedTotalSeconds * 1000)` on first call and persists to `localStorage 'snobbery:gbm:start'`
- Added `_resync()` with guard `if (!_startTimestamp || !isRunning || isPaused) return` (Pitfall 7); recomputes elapsed from wall clock; called from visibilitychange handler BEFORE `requestWakeLock()` so missed phase transitions auto-advance silently on wake
- Added `_syncStateFromElapsed(elapsed)` walking `steps[i].time_seconds` as CUMULATIVE offsets (Pitfall 5); computes `stepIdx` as count of steps whose `time_seconds <= elapsed`; when `stepIdx >= steps.length`, stops timer + sets `isDone` without double-cue; fires chime/vibrate and auto-derives `bloomTimeSeconds` only on newly crossed transitions (Pitfall 2)
- Extended `pause()` to record `_pausedAt = Date.now()` and `resume()` to accumulate `_pausedOffset += floor((now-_pausedAt)/1000)` before restarting timer
- Extended `destroy()` to `localStorage.removeItem('snobbery:gbm:start')`
- Added computed getters: `coachingLine` (Bloom/Pour/Wait/Action composition), `stepTypeBadge` (uppercased type), `stepNote` (step.note), `stepWaterTemp` ('at Xc'), `preCueCountdown` (1-3 when remainingSeconds in 1-3 range, else 0), `isPreCue` (preCueCountdown > 0)
- Added `markFirstDrip()` (sets `firstDripSeconds = elapsedTotalSeconds` once, D-14) and `clearFirstDrip()` (sets null)
- Extended `finishBrewing()` to append `&first_drip=` and `&bloom_time=` when non-null (D-15, GBREW-03)
- Updated `nextStep_action()` to also auto-derive `bloomTimeSeconds` on manual skip (consistency with `_syncStateFromElapsed`)

### Task 2: brew_guided.html full coach view

- Start-screen step preview updated to show `{{ step.type or 'Pour' }} — {{ step.label or 'Step N' }}`
- Pre-cue countdown block inserted before main countdown: `x-show="isPreCue"` + `aria-live="polite"` + "Get ready…" text + `x-text="preCueCountdown"` digit
- Current step card replaced with full coach card: `bg-espresso-700 text-cream-50 rounded-lg px-4 py-5 flex flex-col gap-1` + `aria-live="assertive"`; type badge `x-text="stepTypeBadge"` (text-xs uppercase tracking-wide opacity-70); coaching line `x-text="coachingLine"` (text-xl font-semibold); per-step note `x-show="stepNote" x-text="stepNote"`; per-step temp `x-show="stepWaterTemp" x-text="stepWaterTemp"`
- Bloom auto-record indicator: `x-show` on Bloom type + "Bloom will auto-record"; bloom recorded display: `x-show="bloomTimeSeconds !== null"` + "Bloom: {time}"
- Cumulative water target line, total elapsed line, next-step preview with type in label
- First-drip tap-to-mark: `x-show="firstDripSeconds === null"` full-width `min-h-[56px]` primary button with `aria-label="Mark first drip time"`; marked state shows "First drip: {time}" + "Clear" `min-h-[44px]` link with `aria-label="Clear first drip time"`
- Bottom cancel area: `pb-[max(env(safe-area-inset-bottom),_16px)]` applied to `mt-auto` section (Phase 15 technique, commit 982c0e6, D-16)
- Done screen extended with firstDripSeconds/bloomTimeSeconds summary before "Log this brew" CTA
- `data-steps` stays `'{{ recipe.steps | tojson }}'` (single-quoted); no `|safe` on user content; x-text not x-html throughout

## Task Commits

1. **Task 1: wall-clock timer + coaching getters + first-drip/bloom capture** — `7332568`
2. **Task 2: full coach view, pre-cue, tap-to-mark, bloom indicator, safe-area** — `5d45b69`

## Test Results

All 18 Phase 20 in-scope tests GREEN:

- `tests/test_phase20_mobile.py::test_brew_guided_loads` — PASS (guided page 200 with guidedBrewMode root)
- `tests/test_phase20_mobile.py::test_brew_form_loads` — PASS (continues)
- `tests/test_phase20_brew_session.py::test_gbm_finish_url_has_brew_time` — PASS (continues)
- `tests/test_phase20_brew_session.py::test_timing_fields_schema` — PASS (continues)
- `tests/test_phase20_brew_session.py::test_water_profile_id_schema` — PASS (continues)
- `tests/test_phase20_brew_session.py::test_timing_columns` — PASS (continues)
- `tests/test_phase20_step_schema.py` — 6 tests PASS (continues)
- `tests/test_phase20_water_profiles.py` — 6 tests PASS (continues)

Manual-only verifications (closed at 20-06 device checkpoint):
- Timer accuracy across screen sleep on iPhone PWA
- Coach-feel and pre-cue timing on physical device
- 375px layout polish

## Files Created/Modified

- `app/static/js/alpine-components/guided-brew-mode.js` — wall-clock timer + coaching getters + capture (D-15, D-08..D-11, D-12..D-14, GBREW-01/02/03)
- `app/templates/pages/brew_guided.html` — full coach view redesign (D-10, D-11, D-12..D-14, D-16, GBREW-02/03)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] nextStep_action() did not auto-derive bloomTimeSeconds**
- **Found during:** Task 1 implementation review
- **Issue:** The plan's `_syncStateFromElapsed` auto-derives `bloomTimeSeconds` on automatic step transitions, but `nextStep_action()` (manual skip) bypassed this logic — a user manually skipping past a Bloom step would not record bloom time.
- **Fix:** Extended `nextStep_action()` to check `(completedStep.type || 'Pour') === 'Bloom'` and set `this.bloomTimeSeconds = this.elapsedTotalSeconds` before firing cues, mirroring `_syncStateFromElapsed` behavior.
- **Files modified:** `app/static/js/alpine-components/guided-brew-mode.js`
- **Commit:** `7332568`

## Known Stubs

None — all production code is fully wired. The coaching getters compose real step data. The tap-to-mark captures real elapsed seconds. The `finishBrewing()` URL carries the real captured values. No placeholder data flows to any UI surface.

## Threat Flags

All threats from the plan's threat model are mitigated:

| Flag | File | Description |
|------|------|-------------|
| T-20-15 mitigated | brew_guided.html | x-text (not x-html) for coachingLine/stepNote; data-steps via \|tojson in SINGLE-quoted attr; Jinja autoescape ON; no \|safe |
| T-20-16 mitigated | brew.py (20-03) | first_drip/bloom_time/brew_time query params only pre-fill form; BrewSessionCreate ge=0 le=86400 bounds validate on POST |
| T-20-17 mitigated | brew.py | Existing require_user on guided brew route unchanged; this plan touches JS/template only |
| T-20-18 accepted | guided-brew-mode.js | localStorage key cleared on destroy(); per-origin client state; no server impact |

## Self-Check

- [x] app/static/js/alpine-components/guided-brew-mode.js — exists, `_syncStateFromElapsed`, `_startTimestamp`, `coachingLine`, `markFirstDrip`, `first_drip=` all present
- [x] app/templates/pages/brew_guided.html — contains `x-text="coachingLine"`, `x-text="stepTypeBadge"`, `x-text="preCueCountdown"`, `markFirstDrip()`, "Bloom will auto-record", `pb-[max(env(safe-area-inset-bottom),_16px)]`
- [x] data-steps is `'{{ recipe.steps | tojson }}'` (single-quoted); no `|safe` on user content
- [x] aria-live="polite" on pre-cue container; aria-live="assertive" on coach card
- [x] First-drip button: `min-h-[56px]`, `aria-label="Mark first drip time"`
- [x] Clear link: `min-h-[44px]`, `aria-label="Clear first drip time"`
- [x] No `elapsedTotalSeconds++` in guided-brew-mode.js (grep returns 0)
- [x] _resync() guards `if (!_startTimestamp || !isRunning || isPaused) return`
- [x] visibilitychange calls `_resync()` before `requestWakeLock()`
- [x] Task 1 commit: 7332568
- [x] Task 2 commit: 5d45b69
- [x] 18 Phase 20 tests GREEN
- [x] test_brew_guided_loads PASS against rebuilt image

## Self-Check: PASSED
