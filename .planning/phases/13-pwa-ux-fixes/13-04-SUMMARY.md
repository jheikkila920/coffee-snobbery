---
phase: 13-pwa-ux-fixes
plan: "04"
subsystem: frontend-templates
tags: [c6, c7, guided-brew, cue-controls, ratio-recalc, rating-stars, alpine, htmx, mobile]
dependency_graph:
  requires: []
  provides: [C6-cue-controls, C7a-ratio-resync, C7b-single-line-stars]
  affects: [brew_guided.html, brew_prefill_fields.html, brew_form.html]
tech_stack:
  added: []
  patterns: [alpine-x-init-resync, on-off-button-pair, flex-nowrap-mobile]
key_files:
  modified:
    - app/templates/pages/brew_guided.html
    - app/templates/fragments/brew_prefill_fields.html
    - app/templates/pages/brew_form.html
decisions:
  - "C6: On/Off button pairs use aria-pressed (not aria-checked/role=switch); toggleChime/toggleVibrate guard with cuePrefs.chime||/&& so only the opposite-state button fires the toggle, not both"
  - "C7a: x-init on #brew-prefill-region reads x-ref'd inputs; Alpine.initTree (htmx:afterSettle) re-runs x-init on each swap — no new JS file needed"
  - "C7b: flex-nowrap on role=group star row; each star is w-14 (56px) so 5 stars + gap-1 fits 375px"
metrics:
  duration: ~15 min
  completed_date: "2026-05-25"
  tasks_completed: 3
  files_modified: 3
---

# Phase 13 Plan 04: C6/C7 Cue Controls + Ratio Recalc + Star Row Summary

**One-liner:** Template-only fixes: labeled On/Off cue buttons (C6), Alpine x-init prefill re-sync for live ratio (C7a), flex-nowrap star row at 375px (C7b).

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | C6 — redesign guided-brew cue controls | 2997f7f | app/templates/pages/brew_guided.html |
| 2 | C7a — re-sync brewRatio on programmatic prefill | 89606c1 | app/templates/fragments/brew_prefill_fields.html |
| 3 | C7b — rating stars fit one line at 375px | 73f9c2c | app/templates/pages/brew_form.html |
| 4 | Manual verify checkpoint | (deferred to orchestrator batch verification) | — |

## What Changed

### C6: Guided-Brew Cue Controls

**Start screen** (lines 91-119 → replaced): Two `role="switch"` toggle pill buttons (with translate-x knob spans and `:aria-checked`) replaced with clearly-labeled On/Off button pairs using `aria-pressed`. Each button is visually active (espresso-700 fill) when it matches the current cue state. The toggle logic: the On button fires `toggleChime()` only when chime is currently off (`cuePrefs.chime || toggleChime()`), and Off only when chime is on — so clicking the already-active button is a no-op.

**In-brew section** (lines 207-224 → replaced): Emoji-only icon buttons (🔔/🔕, 📳) replaced with text buttons reading `'Chime: On' / 'Chime: Off'` and `'Vibrate: On' / 'Vibrate: Off'` via `x-text`. Background fills to espresso-700 when the cue is active, outlined otherwise.

Both handlers (`toggleChime()`, `toggleVibrate()`) and localStorage persistence (`snobbery:gbm:cues`) are **unchanged** — template-only change.

### C7a: brewRatio Re-sync on Prefill

The `#brew-prefill-region` wrapper gets `x-init` that calls `setDose($refs.doseInput?.value)` and `setWater($refs.waterInput?.value)`. The dose and water inputs get `x-ref="doseInput"` and `x-ref="waterInput"` respectively.

When a user selects a coffee or recipe, HTMX swaps `#brew-prefill-region` outerHTML with new server-rendered values. After the swap, `htmx:afterSettle` fires → `Alpine.initTree(evt.target)` in `htmx-listeners.js` → Alpine re-runs `x-init` on the new wrapper → `setDose`/`setWater` propagate the server-prefilled values into the `brewRatio` scope → the `1:N.NN` readout recalculates immediately without user input.

The existing `x-on:input="setDose($el.value)"` / `setWater` bindings on the inputs are preserved — manual typing still works.

### C7b: Rating Stars Single-Line

The `role="group"` star row container changed from `flex flex-wrap` to `flex flex-nowrap`. Each star is `w-14 h-14` (56px). Five stars × 56px + 4 × `gap-1` (4px) = 296px, which fits within 375px minus ~16px form horizontal padding (359px available). `min-h-[56px]` and tap zones unchanged; `rating-stars.js` not modified.

## Deviations from Plan

None — plan executed exactly as written. The start-screen On/Off buttons use inline conditional guards (`cuePrefs.chime || toggleChime()`) rather than always calling `toggleChime()` on both buttons; this is a UX improvement (idempotent clicks) within the plan's intent and remains CSP-clean (named method call, no inline arithmetic).

## Verification Results

All three automated checks passed:
- `role="switch"` absent from brew_guided.html; `toggleChime()`/`toggleVibrate()` present; no `x-model`
- `setDose`/`setWater` present in brew_prefill_fields.html; no `x-model`
- `flex-nowrap` present (not `flex-wrap`) on rating group container

JS components untouched: `guided-brew-mode.js`, `brew-ratio.js`, `rating-stars.js` — zero git diff.

## Checkpoint Deferred

**Task 4 (checkpoint:human-verify)** is deferred to the orchestrator's consolidated batch verification pass. Manual steps:
1. C6: Start /brew/guided — cue On/Off buttons read clearly; toggle and reload confirm localStorage persistence.
2. C7a: Open /brew/new, select a recipe/coffee — ratio readout updates immediately on prefill without typing; type in dose to confirm regression-free.
3. C7b: At 375px DevTools, /brew/new rating stars sit on one line (no 4+1 wrap); each star tap target >= 44px.

## Known Stubs

None.

## Threat Flags

None — template + client-side only; no auth/CSRF/route changes. T-13-09 mitigated: `x-init` uses only named scope methods (`setDose`/`setWater`), no eval, no inline arithmetic, no `x-model`.

## Self-Check

**Files exist:**
- app/templates/pages/brew_guided.html: modified in-place
- app/templates/fragments/brew_prefill_fields.html: modified in-place
- app/templates/pages/brew_form.html: modified in-place

**Commits exist:**
- 2997f7f: C6 cue controls
- 89606c1: C7a prefill re-sync
- 73f9c2c: C7b flex-nowrap stars

## Self-Check: PASSED
