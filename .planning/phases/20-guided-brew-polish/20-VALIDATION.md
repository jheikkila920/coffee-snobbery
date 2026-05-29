---
phase: 20
slug: guided-brew-polish
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-29
---

# Phase 20 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: derived from 20-RESEARCH.md "Validation Architecture".

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x + httpx TestClient (in-process FastAPI) |
| **Config file** | none — `tests/conftest.py` provides transactional fixtures |
| **Quick run command** | `docker compose exec coffee-snobbery python -m pytest -q tests/test_phase20_water_profiles.py tests/test_phase20_step_schema.py tests/test_phase20_brew_session.py -x` |
| **Full suite command** | `docker compose exec coffee-snobbery python -m pytest -q` |
| **Estimated runtime** | ~5s quick / full suite per existing baseline |

> NOTE: pytest is not baked into the production image. Wave 0 installs it into the
> running container (`pip install --user pytest pytest-asyncio respx`) or uses the
> `coffee-snobbery-test` compose profile, and copies changed files in with
> `docker compose cp` before re-running. See CLAUDE.md "Working with the code".

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest -q tests/test_phase20_*.py -x`
- **After every plan wave:** Run `python -m pytest -q` (full suite)
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~10 seconds

---

## Per-Task Verification Map

> Task IDs are assigned during planning/execution. This map is keyed by requirement
> until plans exist; the Nyquist audit fills Task ID / Plan / Wave columns.

| Req ID | Behavior | Threat Ref | Test Type | Automated Command | File Exists | Status |
|--------|----------|------------|-----------|-------------------|-------------|--------|
| GBREW-01 | Elapsed computed from `Date.now() - _startTimestamp` (not counter increment); `_resync()` on `visibilitychange` | — | unit (JS) / manual | Manual browser verification on iPhone PWA (timer accuracy on wake) | ❌ W0 | ⬜ pending |
| GBREW-01 | `finishBrewing()` URL carries brew_time from elapsed | — | unit (Python) | `pytest tests/test_phase20_brew_session.py::test_gbm_finish_url_has_brew_time -x` | ❌ W0 | ⬜ pending |
| GBREW-02 | Coaching line auto-composed correctly per step type | — | unit (Python) | `pytest tests/test_phase20_step_schema.py::test_coaching_line_by_type -x` | ❌ W0 | ⬜ pending |
| GBREW-03 | `first_drip_seconds` + `bloom_time_seconds` accepted by BrewSession schema | T-V5 | unit | `pytest tests/test_phase20_brew_session.py::test_timing_fields_schema -x` | ❌ W0 | ⬜ pending |
| GBREW-03 | New nullable columns present after migration | — | migration | `pytest tests/test_phase20_brew_session.py -k timing_columns -x` | ❌ W0 | ⬜ pending |
| GBREW-04 | POST `/water-profiles` creates profile and fires `HX-Trigger` | T-V4 / CSRF | integration | `pytest tests/test_phase20_water_profiles.py::test_create_water_profile -x` | ❌ W0 | ⬜ pending |
| GBREW-04 | Migration seeds profiles from DISTINCT normalized `water_type` | — | migration | `pytest tests/test_phase20_water_profiles.py::test_migration_seeds_profiles -x` | ❌ W0 | ⬜ pending |
| GBREW-04 | Migration links historical sessions to correct profile FK | — | migration | `pytest tests/test_phase20_water_profiles.py::test_migration_links_sessions -x` | ❌ W0 | ⬜ pending |
| GBREW-04 | Blank/NULL `water_type` → NULL `water_profile_id` (no "Unknown" seed) | — | migration | `pytest tests/test_phase20_water_profiles.py::test_migration_null_water_type -x` | ❌ W0 | ⬜ pending |
| GBREW-05 | Guided Brew pages load without error at 375px | — | smoke | `pytest tests/test_phase20_mobile.py::test_brew_guided_loads -x` | ❌ W0 | ⬜ pending |
| GBREW-06 | StepSchema accepts Wait step with `water_grams=None` | T-V5 | unit | `pytest tests/test_phase20_step_schema.py::test_wait_step_no_water -x` | ❌ W0 | ⬜ pending |
| GBREW-06 | StepSchema validates `water_temp_c` range (50–100) | T-V5 | unit | `pytest tests/test_phase20_step_schema.py::test_step_water_temp_range -x` | ❌ W0 | ⬜ pending |
| GBREW-06 | Old step dicts without `type` still validate (backward compat) | — | unit | `pytest tests/test_phase20_step_schema.py::test_backward_compat_no_type -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

**Highest-value automated tests (build these first):**
1. **Migration data-seed/link** — insert synthetic `brew_sessions` with varied `water_type` (blank, NULL, cased variants like "third wave" vs "Third Wave"), run migration, assert correct `water_profiles` rows + FK links + NULL handling.
2. **StepSchema backward compatibility** — old `{water_grams: 100, time_seconds: 45, label: "Bloom"}` dict must validate after the schema extension (defaults applied, no error).
3. **Water-profile inline create** — POST `/water-profiles` returns 200 + `HX-Trigger` header with the new profile payload; CSRF-protected.

---

## Wave 0 Requirements

- [ ] `tests/test_phase20_water_profiles.py` — GBREW-04 migration seed/link/null + POST endpoint + HX-Trigger
- [ ] `tests/test_phase20_step_schema.py` — GBREW-06 schema (optional water_grams, type, temp range, note) + backward compat
- [ ] `tests/test_phase20_brew_session.py` — GBREW-03 timing fields schema + columns + GBREW-01 finish URL
- [ ] `tests/test_phase20_mobile.py` — GBREW-05 smoke: guided brew pages load at 375px
- [ ] `tests/conftest.py` — reuse existing transactional fixtures; add water-profile / recipe-step factories if absent

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Timer stays accurate across phone screen sleep (no drift, silent catch-up of missed phase transitions on wake) | GBREW-01 / D-15 | iOS suspends JS (and Web Workers) on screen sleep; cannot be reproduced in a headless harness — only on a real iPhone PWA | Start a Guided Brew on the installed iPhone PWA, sleep the screen ~30s mid-bloom, wake: elapsed must equal wall-clock, current step must have advanced if its time passed, no double-count |
| Pre-cue countdown + coach view feel ("3-2-1" before transitions, full coach view legible mid-pour) | GBREW-02 / D-10/D-11 | Subjective UX / cue timing judged in real use | Run a multi-step recipe in Guided Brew on iPhone; confirm pre-cue fires a few seconds before each transition, audio+vibration+visual all fire, coach view shows step/target/next/elapsed |
| 375px mobile polish bar (touch targets, safe-area, no horizontal scroll) on all new UI | GBREW-05 / D-16 | Safe-area + PWA chrome only correct on physical device; Phase 15 fix was device-verified | Inspect at 375px + on iPhone PWA: 44px/56px targets, `px-6`, Phase 15 safe-area technique, no horizontal scroll on coach view / builder / inline water-profile create / tap-to-mark |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
