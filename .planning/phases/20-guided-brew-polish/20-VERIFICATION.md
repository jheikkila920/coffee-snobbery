---
status: partial
phase: 20-guided-brew-polish
source: [20-06-PLAN.md]
started: 2026-05-29
updated: 2026-05-29
requirements: [GBREW-01, GBREW-02, GBREW-04, GBREW-05, GBREW-06]
---

# Phase 20 — Guided Brew Polish: Phase-Close Verification

## Automated Gate (Task 1) — PASS

Run in the baked `coffee-snobbery-test` dev image (pytest + playwright + chromium,
`SNOB_CI=1`, sibling `snobbery_test` DB). `tests/e2e/` excluded — see note below.

| Check | Result |
|-------|--------|
| Full suite run 1 | **1355 passed, 3 skipped, 10 xfailed, 0 failed, 0 errors** (246s) |
| Full suite run 2 (consecutive, no DB reset) | **1355 passed, 3 skipped, 10 xfailed, 0 failed, 0 errors** (224s) |
| Phase 20 tests skipped | **None** (`-rs` confirmed no `test_phase20*` skips) |
| `ruff format --check .` | **clean (exit 0)** |
| `ruff check .` | **clean (exit 0)** |

Two consecutive green runs with no reset confirm no cross-module isolation pollution
(the documented `full-suite-test-isolation-gaps` hazard). The 3 remaining skips are
pre-existing and legitimate, none mask Phase 20 behavior:
- `tests/middleware/test_session.py:261` — FK-CASCADE-prevented state, documented skip.
- `tests/routers/test_cafe_logs.py:703` — requires the live dev container (localhost-only).
- `tests/services/test_sessions.py:22` — Phase 7 async-session fixture (sync-only era).

### Regressions found and fixed during the gate
1. **Recipe step round-trip (Phase 20 cross-plan regression).** 20-02's `StepSchema`
   extension made `model_dump()` inject defaulted keys (`type`/`note`/`water_temp_c`)
   into the steps JSONB, breaking the Phase 4 exact-equality contract
   (`test_create_recipe_steps_jsonb_round_trip_via_post`, `test_update_persists_steps_change`).
   Fix: `model_dump(exclude_unset=True)` at both write sites in `app/routers/recipes.py`
   — persist only user-provided keys, default-at-read per the StepSchema design (D-04).
   Commit `1be8088`.
2. **Admin version assertion (pre-existing, not Phase 20).** Local dev builds bake
   `APP_VERSION=dev` (Dockerfile default); the test ignored `APP_VERSION` and asserted
   the pyproject version. Fix: mirror the app's resolution order (`APP_VERSION` env first).
   Commit `3fb41a3`.
3. **Ruff drift (`executors-skip-ruff-ci-gates-both`).** 5 files needed formatting + 3
   import-sort fixes; both CI gates now clean. Commit `d619fe9`.

### Finding — e2e responsive-smoke NOT executed in this gate (documented, deferred)
`tests/e2e/test_responsive_smoke.py` (10 Playwright tests) was **excluded** from the
automated gate. Reasons:
- It requires a live app server at `SNOB_E2E_BASE_URL` (default `127.0.0.1:8080`,
  unreachable inside the `docker compose run` test container) and seeds auth via `/setup`
  against the **real** `snobbery` DB — it needs a dedicated virgin-DB temp app, not the
  shared stack (matches the `snobbery-test-gate-runtime` note).
- The running prod container is the pre-Phase-20 GHCR image, so pointing e2e at it would
  test stale UI and mutate real data.
- **Infra hazard:** when its app is unreachable, the Playwright sync API leaks a running
  event loop on the failure path, which poisons every later `asyncio.run()` in
  `_seed_user` (produced 387 setup-errors + 51 phantom failures before exclusion). Worth a
  follow-up to make e2e seeding fail closed without leaking the loop.
- Coverage: the responsive-smoke assertions (no horizontal scroll, bottom-nav at mobile
  viewports) are a strict subset of the human 375px on-device verification (Task 2, item 3),
  which is the authoritative check for GBREW-05.

## Manual Device Verification (Task 2) — PENDING (blocking-human)

Awaiting on-device confirmation on John's physical iPhone PWA. **Clear site data /
fresh-install first** so the service worker serves the rebuilt assets. Note: the VPS/PWA
must be running a Phase-20 build for this.

### 1. Timer accuracy across screen sleep (GBREW-01 / D-15)
expected: Start a Guided Brew on a multi-step recipe; sleep the screen ~30s mid-bloom,
then wake. Elapsed matches wall-clock within 1s (no deficit), the active step advanced if
its time passed, and no double-count or skipped/duplicated cue.
result: [pending]

### 2. Coach feel (GBREW-02 / D-10/D-11)
expected: 3-2-1 pre-cue before every transition; audio + vibration + visual all fire AT
the transition; coach view shows step type, coaching line, per-step note/temp when present,
cumulative water target, total elapsed, next-step preview; bloom auto-records; first-drip
tap records and clears.
result: [pending]

### 3. 375px polish (GBREW-05 / D-16)
expected: On coach view, recipe step builder (type/note/temp, Wait/Action dimming),
inline water-profile create, and tap-to-mark — 44px secondary / 56px primary touch targets,
px-6 padding, Phase 15 safe-area clear of the home indicator, and ZERO horizontal scroll on
every surface.
result: [pending]

### 4. Water profile round-trip (GBREW-04)
expected: On the brew form, "Add new..." creates and auto-selects a profile; it persists
across reload; a saved session retains it.
result: [pending]

## Summary

total: 4
passed: 0
issues: 0
pending: 4

## Gaps

(none recorded yet — any FAIL routes to `/gsd-plan-phase 20 --gaps`)
