---
phase: 20-guided-brew-polish
plan: 03
subsystem: brew-form-ui
tags: [water-profiles, brew-form, alpine, htmx, timing-fields, GBREW-03, GBREW-04]

requires:
  - phase: 20-guided-brew-polish
    plan: 02
    provides: WaterProfile model/router/service, BrewSessionCreate extended fields, migration

provides:
  - water_profiles context in _hydrate_form_context (feeds all brew form routes)
  - waterProfileSelect Alpine component (select-or-create, HX-Trigger listener)
  - brew_prefill_fields.html water profile select replacing water_type datalist
  - Brew timing (optional) fieldset with first_drip_seconds + bloom_time_seconds inputs
  - GBM query params ?first_drip= / ?bloom_time= seeded into new_brew_form
  - water_profile_id + timing fields in edit_brew_form values dict
  - create_brew_session + update_brew_session persist all three new fields

affects:
  - 20-04 (guided brew UI — template changes co-live with these form fields)
  - 20-05 (GBM tap-to-mark — finishBrewing() URL feeds these seeded fields)
  - 20-06 (validation checkpoint — these form fields are part of the checkpoint)

tech-stack:
  added: []
  patterns:
    - "waterProfileSelect Alpine component mirrors flavor-tag-input.js lifecycle exactly (init/destroy body event listener, _onCreated de-dupe, htmx.ajax CSRF injection)"
    - "water_profiles injected in _hydrate_form_context — single helper feeds /brew/new, /brew/prefill, edit, error re-render with no per-handler duplication"
    - "GBM query-param seeding pattern: _int_or_none(qp.get()) + str() seed into values dict after _stringify_prefill"
    - "Brew timing fieldset grouped in <fieldset> with <legend> for semantic grouping"

key-files:
  created:
    - app/static/js/alpine-components/water-profile-select.js
  modified:
    - app/routers/brew.py
    - app/services/brew_sessions.py
    - app/templates/fragments/brew_prefill_fields.html
    - app/templates/base.html

key-decisions:
  - "water-profile-select.js loaded globally in base.html (not brew_form.html head_extra) — consistent with all other Alpine components; no page-specific loading needed"
  - "Timing fieldset rendered in brew_prefill_fields.html (not brew_form.html) so it appears in both the initial render and dynamic re-prefill swap"
  - "_WRITABLE_FIELDS extended with water_profile_id/first_drip_seconds/bloom_time_seconds so update_brew_session passes them through its kwargs API"
  - "water_type field left in form parsing and service — deprecated but not removed; plan states leave-as-is for backward compat"

duration: 14min
completed: 2026-05-29
---

# Phase 20 Plan 03: Brew Form Wiring Summary

**Water-profile select-or-create replacing freetext water_type, plus optional first-drip/bloom-time inputs on any brew session — GBREW-04 and the form half of GBREW-03 delivered and tested**

## Performance

- **Duration:** ~14 min
- **Started:** 2026-05-29T16:35:00Z
- **Completed:** 2026-05-29T16:49:00Z
- **Tasks:** 2
- **Files modified:** 5 (1 new, 4 modified)

## Accomplishments

- Added `water_profiles_service` import to `app/routers/brew.py` and injected `water_profiles` list into `_hydrate_form_context` — single helper feeds `/brew/new`, `/brew/prefill`, edit, and error re-render
- Extended `new_brew_form` to parse `?first_drip=` and `?bloom_time=` query params and seed `first_drip_seconds` / `bloom_time_seconds` into form values (D-12, D-14 GBM completion path)
- Extended `edit_brew_form` values dict with `water_profile_id`, `first_drip_seconds`, `bloom_time_seconds` for pre-fill on edit
- Added `water_profile_id`, `first_drip_seconds`, `bloom_time_seconds` to `_FORM_FIELDS` and `_EMPTY_TO_NONE_FIELDS` so empty-string coerces to `None` before Pydantic (Pitfall 6)
- Extended `create_brew_session` and `update_brew_session` (via `_WRITABLE_FIELDS`) to persist the three new fields
- Replaced the water_type datalist in `brew_prefill_fields.html` with Alpine `waterProfileSelect` select-or-create: native `<select name="water_profile_id">` with dynamic profile options + "Add new..." inline create form; `data-initial-profiles='{{ water_profiles | tojson }}'` (single-quoted per memory)
- Added "Brew timing (optional)" `<fieldset>` with `first_drip_seconds` and `bloom_time_seconds` number inputs (text-base 16px, tabular-nums, inputmode=numeric, min=0)
- Created `app/static/js/alpine-components/water-profile-select.js`: `Alpine.data('waterProfileSelect')` with `init()` / `destroy()` / `onSelectChange()` / `saveProfile()`; `_onCreated` body listener for `water-profile-created` HX-Trigger; `htmx.ajax('POST', '/water-profiles', { swap: 'none' })` for CSRF-safe create (htmx-listeners.js injects token)
- Registered `water-profile-select.js` in `base.html` before Alpine boots (nonce-tagged, consistent with all other Alpine components)

## Task Commits

1. **Task 1: water_profiles context + form parsing + service persistence** — `bf887b5`
2. **Task 2: water-profile select-or-create UI + timing fieldset** — `4066c0e`

## Test Results

All 17 Phase 20 in-scope tests GREEN:

- `tests/test_phase20_brew_session.py::test_gbm_finish_url_has_brew_time` — now passes (was RED in 20-02)
- `tests/test_phase20_mobile.py::test_brew_form_loads` — now passes (was RED in 20-02)
- `tests/test_phase20_water_profiles.py::test_create_water_profile` — continues to pass
- All 14 remaining Phase 20 tests — continues to pass

Existing brew tests: 111 passed, 4 skipped — no regressions.

## Files Created/Modified

- `app/static/js/alpine-components/water-profile-select.js` — waterProfileSelect Alpine component (D-02, GBREW-04)
- `app/routers/brew.py` — water_profiles_service import, _hydrate_form_context water_profiles key, new_brew_form first_drip/bloom_time seeding, edit_brew_form values dict extension, _FORM_FIELDS/_EMPTY_TO_NONE_FIELDS additions, create/update service call extensions
- `app/services/brew_sessions.py` — create_brew_session signature extended, _WRITABLE_FIELDS extended with three new fields
- `app/templates/fragments/brew_prefill_fields.html` — water_type datalist replaced with waterProfileSelect Alpine block, Brew timing fieldset added
- `app/templates/base.html` — water-profile-select.js script tag added before Alpine boots

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — all production code is fully wired. The water profile select renders from the live DB-seeded catalog. The timing fields accept and persist real values. No placeholder data.

## Threat Flags

All threats from the plan's threat model are mitigated:

| Flag | File | Description |
|------|------|-------------|
| T-20-08 mitigated | water-profile-select.js | htmx.ajax uses htmx:configRequest → X-CSRF-Token injected; endpoint not exempt from starlette-csrf |
| T-20-09 mitigated | brew_prefill_fields.html | data-initial-profiles uses \|tojson in SINGLE-quoted attr; x-text (not x-html) for option labels; Jinja2 autoescape ON; no \|safe |
| T-20-10 mitigated | brew.py + brew_sessions.py | _EMPTY_TO_NONE_FIELDS coerces empty water_profile_id to None; BrewSessionCreate ge=1 / ge=0 bounds; FK constraint |
| T-20-11 accepted | brew_prefill_fields.html | water_profiles list is household-shared by design (ASVS V4) |

## Self-Check

- [x] app/static/js/alpine-components/water-profile-select.js — exists, Alpine.data('waterProfileSelect'), init/destroy/onSelectChange/saveProfile
- [x] app/templates/fragments/brew_prefill_fields.html — contains name="water_profile_id", data-initial-profiles='{{ water_profiles | tojson }}' (single-quoted), name="first_drip_seconds", name="bloom_time_seconds"
- [x] app/templates/base.html — water-profile-select.js script tag present
- [x] app/routers/brew.py — water_profiles_service import, water_profiles in _hydrate_form_context, first_drip/bloom_time seeding in new_brew_form
- [x] app/services/brew_sessions.py — water_profile_id/first_drip_seconds/bloom_time_seconds in _WRITABLE_FIELDS and create_brew_session signature
- [x] Task 1 commit: bf887b5
- [x] Task 2 commit: 4066c0e
- [x] 17 Phase 20 tests GREEN
- [x] 111 existing brew tests GREEN (no regressions)

## Self-Check: PASSED
