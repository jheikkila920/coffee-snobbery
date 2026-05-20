---
phase: 05-brew-sessions
plan: 05
subsystem: ui
tags: [htmx, alpinejs, csp, jinja2, tailwind, brew-form, draft, rating, mobile-first]

# Dependency graph
requires:
  - phase: 05-brew-sessions (plan 04)
    provides: brew form router + locked context contract (values/errors/touched/pill_sources/advertised_chips/server_draft) + pages/brew_form.html & fragments/brew_prefill_fields.html scaffolds + GET /brew/prefill re-prefill fragment
  - phase: 05-brew-sessions (plan 01)
    provides: BrewSessionCreate/Update schemas (Decimal rating multiple_of=0.25, GENERATED extraction_yield_pct never an input)
  - phase: 04-shared-catalog
    provides: CSP-build Alpine registration convention (recipe-step-builder.js), flavorNoteChips factory (autocomplete.js), autocomplete_list.html fragment, htmx-listeners.js global X-CSRF-Token injection, coffee_form.html field/label/error pattern
  - phase: 01-middleware
    provides: CSP nonce (csp_nonce), @alpinejs/csp core, base.html script block, double-submit CSRF, Tailwind base layer (tailwind.src.css with the 16px floor)
provides:
  - "Four CSP-strict Alpine components: ratingStars (tap-on-stars 0.5 steps + hidden rating input), observedFlavorNotes (D-09 hx-post auto-create + D-11 advertised quick-add, bound to flavor_note_ids_observed), brewRatio (live 1:N.NN + client-side EY compute), brewDraft (localStorage snobbery:draft:brew:<user_id> + hx-post autosave + reconciliation + Discard)"
  - "pages/brew_form.html fleshed out: full UI-SPEC field order, prefill pills, tap-stars, tag input, live ratio, Advanced disclosure (read-only EY), sticky equalized Save/Discard bar, draft-restore notice"
  - "fragments/brew_prefill_fields.html fleshed out: #brew-prefill-region wrapper, coffee+recipe <select> hx-get to /brew/prefill, D-07 water-type <datalist>, D-11 advertised chip region"
  - "POST /brew/draft/clear route (CSRF-enforced, 204) on app/routers/brew.py to back the Discard affordance"
  - "App-wide readable form-control contrast fix in tailwind.src.css @layer base (fixes /login and every form, not just brew)"
affects: [brew-sessions-list (Plan 06), analytics (Phase 6), pwa-mobile-polish (Phase 11)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "CSP-strict Alpine component idiom extended to four new factories: alpine:init -> Alpine.data(name), data-* config read in init(), :value + x-on:* only (no x-model), no inline hx-on:, programmatic htmx.ajax/hx-post for token-bearing writes (never raw fetch)"
    - "D-09 auto-create via htmx.ajax POST so the global htmx-listeners.js injects X-CSRF-Token automatically — no manually attached token"
    - "App-wide form-control contrast pinned in tailwind.src.css @layer base (root cause: Preflight color:inherit + darkMode:'media' flipping body ink while UA input bg stays white) — fixes contrast once for every form rather than per-field utilities"
    - "Native <datalist> (D-07) for water type: select-like suggestions + free-typed Other in one field, CSP-safe, no extra Alpine component"
    - "Draft-restore notice hidden pre-hydration via inline style=display:none + x-show (no [x-cloak] CSS rule exists; UI-SPEC forbids new CSS)"

key-files:
  created: []
  modified:
    - app/static/js/alpine-components/rating-stars.js
    - app/static/js/alpine-components/flavor-tag-input.js
    - app/static/js/alpine-components/brew-ratio.js
    - app/static/js/alpine-components/brew-draft.js
    - app/templates/base.html
    - app/templates/pages/brew_form.html
    - app/templates/fragments/brew_prefill_fields.html
    - app/static/css/tailwind.src.css
    - app/routers/brew.py

key-decisions:
  - "Star colors deviate from the literal UI-SPEC per explicit user preference: selected = bright amber, unselected = dark espresso (UI-SPEC called fill-espresso-700 / text-espresso-300)"
  - "App-wide input-contrast fix lives in tailwind.src.css @layer base and intentionally fixes ALL forms (a cross-cutting bug broader than this plan's files) — the per-input utility attempt was a no-op because Preflight + darkMode:'media' override it"
  - "D-07 water type = native <datalist> (suggestions + free-typed Other) instead of select+toggle — CSP-safe, no 5th Alpine component"
  - "Added POST /brew/draft/clear (CSRF-enforced, 204) to app/routers/brew.py — a cross-plan touch (router owned by Plan 04) needed to back the Discard affordance with a real server-side draft delete"

patterns-established:
  - "Tap-on-stars: per-half <button type=button> tap zones drive a hidden name=rating input via :value; half-fill via SVG; arrow-key ±0.5 parity"
  - "Observed flavor notes bound to name=flavor_note_ids_observed (parallel x-for hidden inputs) — NEVER advertised_flavor_note_ids; D-11 quick-add chips read advertised_chips but write observed"
  - "Discard contract: brew-draft.js wipes the namespaced localStorage key AND POSTs /brew/draft/clear so a later open does not restore stale server content"

requirements-completed: [BREW-02, BREW-03, BREW-04, BREW-05, BREW-06, BREW-07, BREW-08, MOB-05, MOB-06]

# Metrics
duration: ~3 rounds (multi-session)
completed: 2026-05-20
---

# Phase 5 Plan 05: Brew Form UI Summary

**The daily-use brew form goes live: four CSP-strict Alpine components (tap-on-stars rating, observed-flavor tag input with auto-create + advertised quick-add, live 1:N.NN ratio with client-side extraction yield, and localStorage+server draft persistence) mounted on a mobile-first add/edit page with prefill pills, an Advanced disclosure, and a sticky Save/Discard bar — human-verified by John at 375px after three fix rounds, including an app-wide form-contrast fix that also repaired the sign-in page.**

## Performance

- **Duration:** ~3 fix rounds across multiple sessions (initial build + round 2 + round 3)
- **Started:** 2026-05-20
- **Completed:** 2026-05-20
- **Tasks:** 3 of 3 (Task 3 = blocking human-verify checkpoint, PASSED)
- **Files modified:** 9 (0 created — all targets were Plan-04 scaffolds or pre-existing component/CSS/router files)

## Accomplishments

- **Four CSP-strict Alpine components** (`rating-stars.js`, `flavor-tag-input.js`, `brew-ratio.js`, `brew-draft.js`), each registering its named factory on `alpine:init`, configured via `data-*` read in `init()`, `:value` + `x-on:*` only (no `x-model`, no inline `hx-on:`), wired into `base.html` with a nonce BEFORE the `@alpinejs/csp` core.
- **`ratingStars`** — per-half `<button type="button">` tap zones set 0.5-step values into a hidden `name="rating"` input; SVG half-fill; Clear affordance; arrow-key ±0.5 parity; numeric echo.
- **`observedFlavorNotes`** — flavorNoteChips factory cloned and bound to `name="flavor_note_ids_observed"` (never advertised); D-09 auto-create on no-match via `htmx.ajax` POST (token via the global listener, never a manual `fetch`), pushing a chip with the "new" badge; D-11 advertised quick-add chips read `advertised_chips` and add to the observed list.
- **`brewRatio`** — `dose`/`water` report in via `x-on:input`; live `1:N.NN` with tabular-nums; dose 0/empty → `1:—` (no NaN/Infinity). Round 2 added a client-side extraction-yield compute so the Advanced disclosure shows a live read-only EY.
- **`brewDraft`** — localStorage key `snobbery:draft:brew:<user_id>`; write on input; `hx-post` autosave to `/brew/draft` on blur (token via global listener); `init()` reconciles localStorage-primary / server-fallback (BREW-07); clears the namespaced key on submit; Discard wipes localStorage AND POSTs `/brew/draft/clear`.
- **`pages/brew_form.html`** fleshed out to the full UI-SPEC: field order, prefill pills from the `touched` map, tap-stars, tag input, live ratio, the closed-by-default Refractometer/Advanced disclosure (read-only EY, never an input), the sticky equalized Save/Discard bar (BREW-08), and the draft-restore notice. Per-attempt fields (rating/observed/notes) live OUTSIDE `#brew-prefill-region` so a re-prefill swap never clobbers them.
- **`fragments/brew_prefill_fields.html`** fleshed out with the `#brew-prefill-region` wrapper, coffee + recipe `<select>` `hx-get="/brew/prefill"` (D-04 coffee re-prefill, D-05 recipe-wins, D-11 advertised-chip refresh), and the D-07 water-type `<datalist>`.
- **Human-verify checkpoint (Task 3) PASSED** — John approved the <30s logging flow at a 375px viewport after three fix rounds.

## Task Commits

1. **Task 1: Four Alpine components + base.html wiring** — `e491e13` (feat)
2. **Task 2: brew_form.html + prefill fragment fleshed out** — `4c8f814` (feat)
3. **Task 3: human-verify checkpoint** — PASSED (John approved); no code commit (verification gate)

**Round 2 fixes (after first checkpoint feedback):**
- `97ecf20` (fix) — wire Discard to a real route: new CSRF-enforced `POST /brew/draft/clear` (204) + navigate home; was a 405 before.
- `94f5188` (fix) — live extraction yield (client-side compute in brewRatio), first input-text-contrast attempt, sticky-bar vertical centering, 375px field-cutoff fixes (`min-w-0`/`w-full`, rating `flex-wrap`).

**Round 3 fixes (root-cause + polish):**
- `06a0488` (fix) — app-wide readable form-control contrast via `@layer base` rule on `input/select/textarea` in `tailwind.src.css` (root cause: Preflight `color:inherit` + `darkMode:'media'` flipping body ink while the UA input bg stayed white; the per-input utility was a no-op). Also fixes `/login` and every form.
- `1fadeb3` (fix) — ratio label corrected to "(coffee : water)" (was inverted).
- `d0e7fc3` (fix) — star colors corrected (unselected dark espresso, selected bright amber); save-bar buttons equalized (both `flex-1`, equal height).

**Plan metadata:** committed with this SUMMARY + tracking.

## Files Created/Modified

- `app/static/js/alpine-components/rating-stars.js` — tap-on-stars (0.5 steps) → hidden `name="rating"`; SVG half-fill; Clear; arrow-key parity
- `app/static/js/alpine-components/flavor-tag-input.js` — `observedFlavorNotes` bound to `flavor_note_ids_observed`; D-09 hx-post auto-create + "new" badge; D-11 advertised quick-add
- `app/static/js/alpine-components/brew-ratio.js` — live `1:N.NN` ratio + client-side read-only extraction-yield compute
- `app/static/js/alpine-components/brew-draft.js` — localStorage `snobbery:draft:brew:<user_id>` + hx-post autosave + reconciliation + Discard (wipe + POST /brew/draft/clear)
- `app/templates/base.html` — four `<script defer nonce>` component tags before the Alpine core
- `app/templates/pages/brew_form.html` — full UI-SPEC add/edit page; prefill pills; tap-stars; tag input; live ratio; Advanced disclosure (read-only EY); sticky equalized Save/Discard bar; draft-restore notice
- `app/templates/fragments/brew_prefill_fields.html` — `#brew-prefill-region`; coffee+recipe `<select>` hx-get to `/brew/prefill`; D-07 water-type `<datalist>`; D-11 advertised chip region
- `app/static/css/tailwind.src.css` — `@layer base` app-wide form-control contrast (light + `prefers-color-scheme: dark`); the existing 16px floor stays
- `app/routers/brew.py` — added `POST /brew/draft/clear` (CSRF-enforced, 204) backing the Discard affordance

## Decisions Made

- **Star colors deviate from the literal UI-SPEC per John's explicit preference.** UI-SPEC specified `fill-espresso-700` (selected) / `text-espresso-300` (empty); shipped selected = bright amber, unselected = dark espresso for better tap-feedback contrast on the cream surface. User-approved at the checkpoint.
- **App-wide contrast fix in `tailwind.src.css @layer base`, not a per-input utility.** Root cause: Tailwind Preflight resets controls to `color: inherit; background: transparent`, so under `darkMode: 'media'` the body ink flips to cream while the UA input background stays white → light-on-white unreadable typed text on `/login` and every form. The round-2 per-input utility was a no-op against Preflight + inheritance; pinning explicit palette ink/surface on the controls themselves fixes it once, app-wide. (Note: this is the file that already owns the MX-1 16px rule — `custom.css` is intentionally NOT created, per the plan's MX-1 lock.)
- **D-07 water type = native `<datalist>`** (suggestions + free-typed Other in one `water_type` field) instead of a select+Other-toggle — CSP-safe and avoids a fifth Alpine component.
- **Discard backed by a new route.** `POST /brew/draft/clear` (CSRF-enforced, 204) added to `app/routers/brew.py` so Discard deletes the server backstop draft (not just localStorage), preventing a later open from restoring stale content. The router file is owned by Plan 04 — documented below as a cross-plan touch.
- **Restore notice hidden via inline `style="display:none"` + `x-show`** (no `[x-cloak]` CSS rule exists and the UI-SPEC forbids new CSS for this).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Discard hit a 405 — added `POST /brew/draft/clear`**
- **Found during:** Round 2 (after the first checkpoint)
- **Issue:** The Discard affordance had no server route to clear the backstop draft, producing a 405; localStorage-only clearing would let a later open restore stale server content (breaks BREW-07).
- **Fix:** Added `POST /brew/draft/clear` (CSRF-enforced, returns 204, per-user keyed) to `app/routers/brew.py`; brew-draft.js now wipes localStorage AND POSTs this route on Discard, then navigates home.
- **Files modified:** app/routers/brew.py, app/static/js/alpine-components/brew-draft.js
- **Cross-plan note:** `app/routers/brew.py` is owned by Plan 04 (its `files_modified`). This plan touched it to back the UI affordance — a justified cross-plan addition, not a router rewrite.
- **Committed in:** `97ecf20`

**2. [Rule 1 - Bug] Unreadable typed-text contrast on every form (incl. /login)**
- **Found during:** Round 2 → root-caused in Round 3
- **Issue:** Tailwind Preflight (`color: inherit; background: transparent`) + `darkMode: 'media'` flipped body ink to cream while the UA input background stayed white, rendering typed text light-on-white across all forms.
- **Fix:** `@layer base` rule on `input/select/textarea` in `tailwind.src.css` pinning explicit palette ink/surface/border for light and dark schemes (round 2's per-input utility was a no-op). Cross-cutting by design — repairs `/login` and every form, broader than this plan's `files_modified`.
- **Files modified:** app/static/css/tailwind.src.css
- **Verification:** Human-verified at the checkpoint (typed text readable on the brew form and the sign-in page in both color schemes).
- **Committed in:** `94f5188` (first attempt), `06a0488` (root-cause fix)

**3. [Rule 1 - Bug] 375px field cutoff + inverted ratio label + star/button polish**
- **Found during:** Rounds 2–3
- **Issue:** Some fields overflowed at 375px (no `min-w-0`/`w-full`, rating row didn't wrap); the ratio label read inverted; star colors and save-bar button sizing needed polish.
- **Fix:** `min-w-0`/`w-full` on inputs, `flex-wrap` on the rating row, sticky-bar vertical centering; ratio label → "(coffee : water)"; selected stars amber / unselected dark espresso; both save-bar buttons `flex-1` equal height.
- **Files modified:** app/templates/pages/brew_form.html, app/templates/fragments/brew_prefill_fields.html, app/static/js/alpine-components/brew-ratio.js
- **Verification:** Human-verified at the checkpoint (no horizontal scroll / cutoff at 375px; correct ratio orientation; legible stars; equal buttons).
- **Committed in:** `94f5188`, `1fadeb3`, `d0e7fc3`

**4. [Plan-intent deviation] D-07 water type as `<datalist>` + prefill region id + restore-notice mechanism**
- **D-07:** native `<datalist>` (suggestions + free-typed Other) instead of select+toggle — CSP-safe, no 5th Alpine component.
- **Prefill wrapper id:** `#brew-prefill-fields` (Plan-04 SUMMARY wording) → `#brew-prefill-region` to match the hx-target contract the fragment and selects actually use.
- **Restore notice:** inline `style="display:none"` + `x-show` (no `[x-cloak]` rule exists; UI-SPEC forbids new CSS).
- **Star colors:** selected amber / unselected dark espresso, per explicit user preference (deviates from the literal UI-SPEC tokens).

---

**Total deviations:** 4 (1 blocking-route addition, 2 contrast/layout bug fixes, 1 set of plan-intent UI choices)
**Impact on plan:** All necessary for correctness, mobile usability, and the BREW-07 draft contract. The contrast fix is intentionally cross-cutting (a real app-wide bug). One cross-plan router touch (`POST /brew/draft/clear`), documented. No scope creep beyond backing the planned Discard affordance.

## Issues Encountered

- **Three checkpoint rounds.** The first human-verify surfaced the 405 Discard, unreadable input contrast, 375px cutoffs, and an inverted ratio label. Round 2 addressed them but the per-input contrast utility was a no-op; Round 3 root-caused the contrast to Preflight + `darkMode:'media'` and fixed it in the base layer, then polished star colors and equalized the save-bar buttons. John approved after Round 3.
- **Prompt vs disk discrepancy on the contrast file.** The finalization brief referenced `app/static/css/custom.css`; the on-disk truth is `app/static/css/tailwind.src.css` — `custom.css` does not exist and is intentionally NOT created (the plan's MX-1 lock). This SUMMARY records the actual file.

## Known Stubs

None — all four components are functional and wired; the form renders the full field set against the Plan-04 context contract. The Advanced-disclosure Extraction Yield is render-only by design (GENERATED column, never an input).

## Threat Flags

None — no security surface outside the plan's `<threat_model>`. All five registered threats are mitigated as designed: T-05-19 (autoescape, no `|safe`), T-05-20 (CSP-build only — no `x-model`/inline `hx-on:`/`hx-vals='js:'`, nonce'd scripts), T-05-21 (CSRF on draft autosave AND the new `/brew/draft/clear` via the global htmx listener), T-05-22 (localStorage namespaced `snobbery:draft:brew:<user_id>`, cleared on submit/Discard), T-05-23 (EY read-only, never submitted). The new `POST /brew/draft/clear` is CSRF-enforced and per-user keyed — no new unguarded surface.

## Known Follow-ups / Out of Scope (not implemented)

- **Post-save success redirect → `GET /brew`** (sessions list) is built in Plan 06; until then a 405 on that redirect is expected. The brew itself saves (HTTP 204 — verified, rows 50/51 in the DB during checkpoint testing).
- **"Add new coffee" inline from the coffee select** — requested enhancement; catalog CRUD is Phase 4 scope. Captured as a pending todo (see below).
- **A "log a brew" navigation entry point after login** arrives with Phase 6 (home page) / Plan 06.
- **Test data** (roaster/coffee/bag/equipment/recipe/2 brews) was seeded at runtime for verification only — NOT committed as code.

### Pending Todo Captured

The repo has no `.planning/todos/` directory or todo format, so the "add new coffee" enhancement is recorded here (and in STATE.md Accumulated Context) rather than as a todo file. **Enhancement:** while logging a brew, allow adding a coffee not yet in the shared catalog without leaving the form (inline create from the coffee `<select>`). Cross-cutting UX; catalog CRUD lives in Phase 4. Does NOT belong to Phase 5.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- The brew add/edit form is human-verified and live. **Plan 06** (sessions list) provides the `GET /brew` redirect target the create/update success path expects, the "Brew again" / "Edit" deep links into this router, and the CSV export/import surface.
- **Phase 6** (home page) supplies the post-login "log a brew" entry point.
- The app-wide contrast fix in `tailwind.src.css` benefits every existing and future form; the four Alpine components are available for reuse.

## Self-Check: PASSED

All 9 modified files exist on disk; all 7 implementation commits (`e491e13`, `4c8f814`, `97ecf20`, `94f5188`, `06a0488`, `1fadeb3`, `d0e7fc3`) are present in `git log`; `POST /brew/draft/clear` is in `app/routers/brew.py` (returns 204); the `@layer base` contrast rule is in `app/static/css/tailwind.src.css`; `#brew-prefill-region` is the hx-target in `fragments/brew_prefill_fields.html`; the D-07 `<datalist>` and the sticky equalized Save/Discard bar are in `pages/brew_form.html`; Task 3 human-verify PASSED (John approved). `custom.css` confirmed absent (intentional, per MX-1 lock).

---
*Phase: 05-brew-sessions*
*Completed: 2026-05-20*
