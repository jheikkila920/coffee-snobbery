---
phase: 20-guided-brew-polish
plan: 04
subsystem: recipe-step-builder
tags: [alpine, step-builder, recipe, gbrew-06, type-select, note, water-temp, wait-action]

requires:
  - phase: 20-guided-brew-polish
    plan: 02
    provides: StepSchema extension (type/note/water_temp_c/Optional water_grams) already in recipe.py

provides:
  - recipeStepBuilder Alpine component with setType/setNote/setWaterTemp + showNote state
  - recipe_step_builder.html with Type select, Temp input, per-step note, Wait/Action dimming
  - test_recipe_roundtrip_wait_action round-trip test proving UI-produced shape validates through StepSchema

affects:
  - 20-05 (guided-brew coaching — reads step.type/step.note/step.water_temp_c from builder output)

tech-stack:
  added: []
  patterns:
    - "Alpine CSP-build setter pattern: :value + x-on:input pairs; no x-model; method calls only"
    - "showNote dict pattern: keyed by step index to toggle per-step textarea visibility"
    - "D-07 Wait/Action water dimming: :class opacity-40 + :disabled on the Water (g) label/input"

key-files:
  created: []
  modified:
    - app/static/js/alpine-components/recipe-step-builder.js
    - app/templates/fragments/recipe_step_builder.html
    - tests/test_phase20_step_schema.py

key-decisions:
  - "showNote state is a plain object ({}) keyed by step index; x-show checks step.note || showNote[idx] so existing notes always show their textarea on load"
  - "setType clears water_grams to null (not 0) for Wait/Action — null maps cleanly to StepSchema Optional[int] = None"
  - "label fallback in timelineSegments uses step.type as secondary fallback (label || type || 'Step N') so Wait/Action segments are readable in the pour-timeline preview"
  - "Water (g) dimming applied to the <label> wrapper (opacity-40 on label) so both the label text and the input dim together — consistent with disabled appearance without custom CSS"

duration: 15min
completed: 2026-05-29
---

# Phase 20 Plan 04: Recipe Step Builder Extensions Summary

**Extended step builder with typed steps (Bloom/Pour/Wait/Action), per-step notes, per-step temperature, and Wait/Action waterless dimming, proven by a full round-trip schema test**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-05-29T16:31:00Z
- **Completed:** 2026-05-29T16:46:42Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- Extended `recipe-step-builder.js` with `showNote: {}` state dict + `setType`/`setNote`/`setWaterTemp` setters
- `setType('Wait')` / `setType('Action')` clears `water_grams` to `null` (D-07)
- `init()` default step is now `{ type: 'Bloom', ..., note: null, water_temp_c: null }` — consistent with step shape
- `addStep()` pushes `{ type: 'Pour', ..., note: null, water_temp_c: null }` — additive default, no regressions
- `timelineSegments` label fallback updated: `label || type || 'Step N'` so Wait/Action steps show their type in the timeline preview
- `recipe_step_builder.html` extended with:
  - Type select (`w-32`, before Label, `setType(idx,...)`, `aria-label` per accessibility contract)
  - Water (g) field dimming: `:class opacity-40` on `<label>` wrapper + `:disabled` on input when Wait or Action
  - Temp (°C) number input (`w-24`, after Time, min=50 max=100, placeholder `—`, `setWaterTemp(idx,...)`)
  - Per-step note: "Add note" text trigger (`showNote[idx] = true`) + `<textarea rows=2 maxlength=200>` (`setNote(idx,...)`)
- Added `test_recipe_roundtrip_wait_action`: Bloom + Pour (with water_temp_c) + Wait (water_grams=None) + Action (with note) all validate through `RecipeCreate`/`StepSchema`
- All 6 tests in `test_phase20_step_schema.py` pass (5 existing + 1 new)

## Task Commits

1. **Task 1: recipe-step-builder.js type/note/temp state + setters** — `78f0d1c`
2. **Task 2: recipe_step_builder.html + round-trip test** — `43306cf`

## Test Results

```
tests/test_phase20_step_schema.py — 6 passed (1 warning: alembic path_separator)
  test_backward_compat_no_type     PASS
  test_wait_step_no_water          PASS
  test_step_water_temp_range       PASS
  test_coaching_line_by_type       PASS
  test_extra_field_rejected        PASS
  test_recipe_roundtrip_wait_action PASS  (NEW — Plan 20-04)
```

All pre-existing assertions preserved and passing. No test weakening.

## Files Created/Modified

- `app/static/js/alpine-components/recipe-step-builder.js` — showNote state + setType/setNote/setWaterTemp + extended init/addStep defaults
- `app/templates/fragments/recipe_step_builder.html` — Type select + Temp input + note affordance + Wait/Action dimming
- `tests/test_phase20_step_schema.py` — test_recipe_roundtrip_wait_action added

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — the builder fully emits type/note/water_temp_c fields into `stepsJson`. The hidden `<input name="steps">` already carries the full JSON shape. No placeholder data flows to any UI surface.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| T-20-12 mitigated | app/schemas/recipe.py (unchanged) | StepSchema Literal type + note max_length + water_temp_c range + extra=forbid already in place from 20-02 |
| T-20-13 mitigated | app/templates/fragments/recipe_step_builder.html | note rendered via `:value` (not x-html/|safe); textarea is autoescaped by Jinja; no XSS vector |

## Self-Check

- [x] app/static/js/alpine-components/recipe-step-builder.js — setType, setNote, setWaterTemp, showNote all present
- [x] app/templates/fragments/recipe_step_builder.html — Type select (setType(idx,...)), Temp input (setWaterTemp(idx,...)), note textarea (setNote(idx,...)), Water dimming (opacity-40 + :disabled)
- [x] tests/test_phase20_step_schema.py — test_recipe_roundtrip_wait_action defined; 6/6 tests pass
- [x] No |safe in recipe_step_builder.html
- [x] All inputs text-base (no iOS zoom)
- [x] maxlength=200 on note textarea
- [x] Task 1 commit: 78f0d1c
- [x] Task 2 commit: 43306cf

## Self-Check: PASSED
