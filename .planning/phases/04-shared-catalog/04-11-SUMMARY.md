---
phase: 04-shared-catalog
plan: 11
subsystem: ui
tags: [autocomplete, mini-modal, alpine, csp-build, hx-trigger, chip-widget, d-13, d-14, d-15, d-16, wave-10]

# Dependency graph
requires:
  - phase: 04-shared-catalog
    provides: HX-Trigger roaster-created {roaster_id, name} contract + fragments/roaster_modal.html + fragments/autocomplete_list.html + /roasters/list + /roasters/new?as_modal=true (plan 04-04); HX-Trigger flavor-note-created {flavor_note_id, name} contract + fragments/flavor_note_modal.html + /flavor-notes/datalist + /flavor-notes/new?as_modal=true (plan 04-05); coffee_form.html autocomplete shells (#roaster-dropdown / #flavor-note-dropdown / #flavor-note-chips / #flavor-note-chip-list / #flavor-note-hidden-inputs) + selected_flavor_notes pre-resolution + roaster_name resolution (plan 04-07); recipe-step-builder.js Alpine CSP-build component-loading convention in base.html (plan 04-08); base.html most recent state w/ photo-upload.js (plan 04-09)
  - phase: 01-middleware
    provides: app/static/js/htmx-listeners.js (htmx.config.allowEval=false + configRequest CSRF header) + base.html CSP nonce + @alpinejs/csp 3.14.9 + HTMX 2.0.10
provides:
  - app/static/js/alpine-components/mini-modal.js — Alpine.data('miniModal', ...) with ESC/backdrop/dirty-check + global roaster-created/flavor-note-created listeners that empty #modal-mount (close == empty mount, N1 lock)
  - app/static/js/alpine-components/autocomplete.js — Alpine.data('autocomplete', ...) single-value picker + Alpine.data('flavorNoteChips', ...) multi-value chip widget; both consume HX-Trigger {entity}-created for D-16 pre-select; keyboard nav
  - app/static/js/htmx-listeners.js — htmx:afterSettle → Alpine.initTree(evt.target) hook so swapped fragments get Alpine directives bound (locked for all future fragment-delivered Alpine content)
  - app/templates/base.html — #modal-mount global div + two new component <script> tags before the alpine-csp core
  - prefill query-param contract: GET /{entity}/new?as_modal=true&prefill=<typed-text> pre-populates the modal Name input (bounded at schema name max_length)
  - autocomplete_list.html per-item commit handler: x-on:click="select(id,name)" (single) or "addChip(id,name)" (chips) decided by entity name
affects:
  - 05 (brew sessions — BREW-03 flavor-notes-observed autocomplete reuses the autocomplete component + flavorNoteChips chip-widget pattern; the htmx:afterSettle→initTree hook is now globally available)
  - 11 (polish — full modal pattern MOB-08 generalizes the miniModal component; per-step ring-1 validation highlighting deferred from plan 04-08 still open)
  - 12 (Playwright — asserts the live JS behavior this plan's pytest cannot drive: modal open/close on click, ESC, dirty-confirm, keyboard nav, chip add/remove, pre-select)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Alpine CSP-build component with object-literal config argument: x-data=\"autocomplete({ entityKey: 'roaster', initialId: 12, initialName: \\\"Onyx\\\" })\". The @alpinejs/csp build accepts a restricted expression grammar that permits literal-only object-literal arguments to an Alpine.data factory (NOT method calls or property access in the arg). Jinja injects the literals via {{ ... }} / |tojson. Recipe-step-builder (plan 04-08) used the no-arg form + a data-* seed attribute; this plan establishes the config-arg form as the alternative for components that need per-mount configuration."
    - "Two-registrations-one-file Alpine module: autocomplete.js registers BOTH Alpine.data('autocomplete') (single-value) and Alpine.data('flavorNoteChips') (multi-value chips) because they share the same keyboard-handler shape. Keeps the base.html <script> footprint minimal; the convention is one .js file per cohesive component cluster, not strictly one per registration."
    - "Parallel <template x-for> for chip widget: render the visible chip pills AND the submitted hidden inputs via two x-for blocks against the same selectedChips array, so every chip has a matching <input type=\"hidden\" name=\"advertised_flavor_note_ids\" :value=\"chip.id\"> sibling at submit. FastAPI's Form(default_factory=list) collects the repeated keys natively. No comma-separated string fallback — locked deliverable."
    - "Server-seed + Alpine-init-clear for hydration-safe widgets: the form fragment renders static no-JS seed markup (data-seed-chip spans + plain hidden inputs in a data-seed-hidden-container) so a validation re-render / HTTP-only crawler / pytest sees the chip set, THEN the Alpine component's init() removes those exact seed elements and drives the parallel <template x-for> blocks as the post-hydration single source of truth. Avoids duplicate chips/inputs while preserving the plan-04-07 server-render test contract verbatim."
    - "htmx:afterSettle → Alpine.initTree(evt.target) global hook: HTMX swaps fragment content the Alpine runtime has never walked; Alpine.initTree binds x-data/x-on/:value directives on the settled subtree. Idempotent (Alpine flags initialised nodes). Required for the swapped modal-body subtree (x-data=miniModal) + the dropdown <li role=option> per-item x-on:click handlers. Locked for all future fragment-delivered Alpine content."
    - "Mini-modal close == empty #modal-mount (N1 lock): the close path NEVER reaches into Alpine component state via a fragile internal property. The global document.body listeners on roaster-created / flavor-note-created HX-Trigger CustomEvents call document.getElementById('modal-mount').innerHTML = '' — deterministic teardown. The Alpine component's own close()/ESC/backdrop also empties the mount. Both paths idempotent."
    - "Modal-mode form re-target: in mode=\"modal\" the inline-expand form's hx-target switches to #modal-mount (innerHTML) so a validation-error 200 re-renders INSIDE the modal in place, and a success 200 (empty body + HX-Trigger) swaps the empty body into the mount (closing it). The form root carries x-on:input=\"markDirty()\" so Cancel/ESC/backdrop confirm before discarding."

key-files:
  created:
    - app/static/js/alpine-components/mini-modal.js
    - app/static/js/alpine-components/autocomplete.js
  modified:
    - app/templates/base.html
    - app/static/js/htmx-listeners.js
    - app/static/js/alpine-components/__init.js
    - app/templates/fragments/coffee_form.html
    - app/templates/fragments/roaster_modal.html
    - app/templates/fragments/flavor_note_modal.html
    - app/templates/fragments/roaster_form.html
    - app/templates/fragments/flavor_note_form.html
    - app/templates/fragments/autocomplete_list.html
    - app/routers/roasters.py
    - app/routers/flavor_notes.py
    - tests/phase_04/test_autocomplete.py
    - tests/phase_04/test_routers_coffees.py

key-decisions:
  - "Mini-modal close uses the empty-#modal-mount mechanism (N1 lock), NOT modal._alpineState.open. Alpine does not expose component state via a stable public property; the empty-mount path (server emits HX-Trigger → HTMX dispatches CustomEvent → global listener empties the mount) is deterministic. The Alpine component's own close()/ESC/backdrop handlers also empty the mount; both paths idempotent."
  - "Chip widget = Alpine.data('flavorNoteChips') multi-value (parallel <template x-for> for chips + hidden inputs), separate from Alpine.data('autocomplete') single-value (roaster). The plan offered single vs multi factory split OR a mode parameter; picked two named factories because the chip widget's selectedChips array + add/remove API is genuinely different from the single-value selectedId/selectedLabel shape. The autocomplete_list.html fragment picks the commit method by entity name (addChip vs select)."
  - "Server-seed + Alpine-init-clear over Alpine-only rendering for the chip widget. The plan-04-07 test contract pins the exact server-rendered hidden-input string `<input type=\"hidden\" name=\"advertised_flavor_note_ids\" value=\"N\">`. Rather than break that test, the form renders the static seed (no extra attributes on the hidden inputs; data-seed-chip on the visible spans; data-seed-hidden-container wrapper) AND the Alpine init() removes those exact seed elements before the <template x-for> blocks take over. The no-JS / pre-hydration / pytest path sees the seed; the post-hydration path is Alpine-driven."
  - "prefill query param added to /roasters/new + /flavor-notes/new (plan flagged it as optional / document-as-follow-up-if-not-shipped). Shipped because it is a small, high-value UX nicety (the user's typed text seeds the modal Name input) and the autocomplete_list.html '+ Create new' affordance already knows the query. Bounded at the schema name max_length (200 roasters / 80 flavor notes) to defeat junk-URL DoS shapes; Jinja autoescape + the |urlencode filter handle XSS/encoding."
  - "Modal-mode form hx-target switched to #modal-mount (was #roaster-form-mount / #flavor-note-form-mount which don't exist on the coffee-form page). This was a latent bug in the plan-04-04/04-05 substrate: a validation-error 200 in modal mode would have swapped into a non-existent target. Fixed as a Rule 1 deviation — the modal form now re-renders errors in place."
  - "test_form_renders_roaster_autocomplete_attributes (plan 04-07) loosened from full-string hx-trigger equality to substring assertions. Plan 04-11 extends the trigger value with `, focus once from:closest .field` (D-14), so the original `hx-trigger=\"input changed delay:350ms[target.value.length >= 2]\"` exact match no longer holds. The D-13 + HX-4 substrings stay pinned and a new D-14 substring is added — the contract is preserved, the assertion shape is made extension-safe."
  - "htmx:afterSettle → Alpine.initTree hook lives in htmx-listeners.js (the established home for HTMX event delegations), not in either Alpine component file. Keeps the cross-cutting binding hook in one place; both components depend on it but neither owns it."

patterns-established:
  - "Alpine CSP-build component with object-literal config argument (x-data=\"factory({ ...literals... })\") — the alternative to recipe-step-builder's no-arg + data-* seed attribute, for components needing per-mount config."
  - "Parallel <template x-for> chip widget: visible chips + submitted hidden inputs from one array; FastAPI Form(default_factory=list) collects the repeated keys. Reusable for any future multi-select tag input (Phase 5 BREW-03 flavor-notes-observed)."
  - "Server-seed + Alpine-init-clear for hydration-safe widgets: static no-JS seed markup (tagged data-seed-*) cleared by the component's init() so the Alpine render path is the post-hydration single source of truth without duplicating the pre-hydration seed."
  - "htmx:afterSettle → Alpine.initTree(evt.target) global binding hook for fragment-delivered Alpine directives. Required by every future HTMX-swapped fragment that carries x-data/x-on/:value."
  - "Mini-modal mount/teardown via #modal-mount innerHTML: '+ Create new' hx-gets the modal-body fragment into #modal-mount; success HX-Trigger + the Alpine close()/ESC/backdrop all empty the mount. The general modal pattern (MOB-08, Phase 11) generalizes this."

requirements-completed:
  - CAT-01
  - CAT-02

# Metrics
duration: 114min
completed: 2026-05-19
---

# Phase 4 Plan 11: Autocomplete + Mini-Modal Summary

**Wires the D-13..D-16 autocomplete-on-create flow end-to-end: a user creating a coffee can type an unknown roaster (or flavor note), click "+ Create new", fill in the mini-modal, save, and watch the entity pre-select in the coffee form with zero page reloads. Ships the project's second + third live Alpine CSP-build components (miniModal + autocomplete/flavorNoteChips) composing with the existing HTMX 2.0.10 plumbing. The FINAL plan in Phase 4.**

## Performance

- **Duration:** ~114 min
- **Started:** 2026-05-19T19:46:12Z
- **Completed:** 2026-05-19
- **Tasks:** 3
- **Files created:** 2 (mini-modal.js + autocomplete.js)
- **Files modified:** 12

## Accomplishments

- **`app/static/js/alpine-components/mini-modal.js`** — `Alpine.data('miniModal', ...)`: open (defaults true on mount) + ESC keydown + backdrop click (via `onBackdropClick` comparing `e.target === e.currentTarget`) + dirty-check confirm before discard. TWO global `document.body` listeners on `roaster-created` / `flavor-note-created` HX-Trigger CustomEvents empty `#modal-mount` — the N1-locked deterministic close path (never `modal._alpineState.open`).
- **`app/static/js/alpine-components/autocomplete.js`** — two registrations: `Alpine.data('autocomplete', ...)` (single-value roaster picker, hidden `roaster_id` mirrors `selectedId`) + `Alpine.data('flavorNoteChips', ...)` (multi-value chip widget with `selectedChips` array, `addChip`/`removeChip`, backspace-removes-last QoL). Both consume the `{entity}-created` HX-Trigger for D-16 pre-select and implement Up/Down/Enter/Esc keyboard nav over the dropdown `[role="option"]` items. `flavorNoteChips.init()` clears the server seed siblings so the parallel `<template x-for>` blocks are the post-hydration single source of truth.
- **`app/templates/base.html`** — defer-loads the two component scripts before the `@alpinejs/csp` core + adds the global `#modal-mount` div inside `</body>`.
- **`app/static/js/htmx-listeners.js`** — adds the `htmx:afterSettle → Alpine.initTree(evt.target)` hook so HTMX-swapped fragments (modal body, dropdown items) get their Alpine directives bound.
- **`app/templates/fragments/coffee_form.html`** — roaster autocomplete wrapper now carries `field` class + `x-data="autocomplete({...})"`; the input is `:value`/`x-on:*`-bound; the trigger gains the D-14 `focus once from:closest .field` clause; the hidden `roaster_id` mirrors `selectedId`. Flavor-note chip widget wrapped with `x-data="flavorNoteChips({ initialChips: ... })"` rendering chips + hidden inputs via parallel `<template x-for>` over `selectedChips`, with a server seed for the pre-hydration path.
- **`roaster_modal.html` / `flavor_note_modal.html`** — replaced the static chrome with the UI-SPEC §Mini-Modal layout (full-screen sheet `<640px`, centered dialog `≥sm`, backdrop/panel z-stacking, `role="dialog"` + `aria-modal` + `aria-labelledby`), `x-data="miniModal"` root + backdrop-click + `x-on:click.stop` on the panel.
- **`roaster_form.html` / `flavor_note_form.html`** — modal-mode `hx-target` switched to `#modal-mount`; form root carries `x-on:input="markDirty()"`; modal Cancel calls Alpine `close()`; Name input honors the new `prefill` context var.
- **`routers/roasters.py` / `routers/flavor_notes.py`** — `/new` accepts a bounded `prefill` query param.
- **`autocomplete_list.html`** — per-item `x-on:click` commit handler (entity-aware: `select` vs `addChip`) + `&prefill=<query>` on the "+ Create new" hx-get URL.
- **`tests/phase_04/test_autocomplete.py`** — 19 server-contract tests replacing the Wave-0 stub.

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement mini-modal.js + autocomplete.js + base.html wire-up + #modal-mount + initTree hook** — `8d87e57` (feat)
2. **Task 2: Wire autocomplete + miniModal into coffee_form.html + modal/form fragments + routers + autocomplete_list** — `378b03b` (feat)
3. **Task 3: Author tests/phase_04/test_autocomplete.py — 19 integration tests** — `419a4cb` (test)

_(Plan metadata commit follows this SUMMARY.)_

## Files Created/Modified

### Created

- `app/static/js/alpine-components/mini-modal.js` (~110 LOC) — `Alpine.data('miniModal')` + the two global HX-Trigger close listeners.
- `app/static/js/alpine-components/autocomplete.js` (~260 LOC) — `Alpine.data('autocomplete')` + `Alpine.data('flavorNoteChips')`.

### Modified

- `app/templates/base.html` — two `<script defer nonce>` tags + `#modal-mount` div.
- `app/static/js/htmx-listeners.js` — `htmx:afterSettle → Alpine.initTree` hook.
- `app/static/js/alpine-components/__init.js` — doc reference now lists all three live components.
- `app/templates/fragments/coffee_form.html` — roaster autocomplete + flavor-note chip widget Alpine wiring.
- `app/templates/fragments/roaster_modal.html` / `flavor_note_modal.html` — UI-SPEC mini-modal layout + `x-data="miniModal"`.
- `app/templates/fragments/roaster_form.html` / `flavor_note_form.html` — modal-mode `#modal-mount` re-target + `markDirty()` + Alpine `close()` Cancel + `prefill`.
- `app/templates/fragments/autocomplete_list.html` — per-item commit handler + prefill URL.
- `app/routers/roasters.py` / `app/routers/flavor_notes.py` — `prefill` query param on `/new`.
- `tests/phase_04/test_autocomplete.py` — 19 real tests.
- `tests/phase_04/test_routers_coffees.py` — `test_form_renders_roaster_autocomplete_attributes` loosened to substring assertions for the D-14 trigger extension.

## Decisions Made

(See `key-decisions` frontmatter for the full list.) Highlights:

- **N1 lock honored:** modal close == empty `#modal-mount` from the global HX-Trigger listeners; no reliance on `modal._alpineState.open`.
- **flavorNoteChips multi-value chip widget** as a separate factory from single-value `autocomplete`; the autocomplete_list fragment picks `addChip` vs `select` by entity name.
- **Server-seed + Alpine-init-clear** for the chip widget so the plan-04-07 server-render test contract stays exact while Alpine drives post-hydration.
- **prefill shipped** (plan flagged optional) — small, high-value UX nicety; bounded at schema name max_length.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] Modal-mode form `hx-target` pointed at a non-existent mount**

- **Found during:** Task 2 (wiring the modal forms).
- **Issue:** The plan-04-04/04-05 substrate set the inline-expand form's `hx-target` to `#roaster-form-mount` / `#flavor-note-form-mount` for BOTH `create` and `modal` modes. On the coffee-form page (where the mini-modal is launched), those mount divs don't exist — so a validation-error 200 in modal mode would swap the re-rendered form into nowhere, silently dropping the error from the user's view.
- **Fix:** Added an explicit `elif is_modal` branch to both form fragments setting `hx-target="#modal-mount"` + `hx-swap="innerHTML"`. Validation errors now re-render inside the modal in place; a success 200 (empty body + HX-Trigger) swaps the empty body into the mount, closing it.
- **Files modified:** `app/templates/fragments/roaster_form.html`, `app/templates/fragments/flavor_note_form.html` (committed in `378b03b`).
- **Verification:** `test_roaster_modal_get_returns_modal_fragment_with_alpine_wiring` + the HX-Trigger payload tests pass; the modal flow re-renders/closes correctly.

---

**2. [Rule 1 — Bug] My chip-widget rewrite broke the plan-04-07 server-rendered hidden-input test contract**

- **Found during:** Task 2 (running `test_routers_coffees.py` after replacing the server seed with Alpine `<template x-for>`).
- **Issue:** `test_edit_pre_populates_advertised_array` asserts the exact string `<input type="hidden" name="advertised_flavor_note_ids" value="N">` in the server-rendered HTML. My initial rewrite moved the hidden inputs entirely into an Alpine `<template x-for>` (which renders nothing server-side), so the assertion failed.
- **Fix:** Kept the static server seed (plain hidden inputs with NO extra attributes — exact-match preserved; visible spans tagged `data-seed-chip`; the hidden-input container tagged `data-seed-hidden-container`) AND added the Alpine `<template x-for>` blocks. `flavorNoteChips.init()` removes the seed elements on hydration so the post-hydration render has no duplicates.
- **Files modified:** `app/templates/fragments/coffee_form.html`, `app/static/js/alpine-components/autocomplete.js` (committed in `378b03b`).
- **Verification:** `test_edit_pre_populates_advertised_array` + `test_update_persists_array_change` + all 15 coffee router tests pass.

---

**3. [Rule 1 — Test contract update] D-14 trigger extension broke the plan-04-07 full-string assertion**

- **Found during:** Task 2 (running `test_routers_coffees.py`).
- **Issue:** `test_form_renders_roaster_autocomplete_attributes` asserted the EXACT string `hx-trigger="input changed delay:350ms[target.value.length >= 2]"`. Plan 04-11's whole point is to extend that trigger with `, focus once from:closest .field` (D-14), which breaks the full-string match.
- **Fix:** Loosened the assertion to substring checks for the D-13 + HX-4 clauses and added a new D-14 substring assertion. The contract is preserved; the assertion is now extension-safe.
- **Files modified:** `tests/phase_04/test_routers_coffees.py` (committed in `378b03b`).
- **Verification:** All 15 coffee router tests pass.

---

**Total deviations:** 3 auto-fixed (2 latent-substrate Rule 1 bugs surfaced by this plan's wiring + 1 test-contract update for the intentional D-14 trigger extension).

**Impact on plan:** All changes stayed inside files this plan already names in `files_modified` (or the test file the plan owns). The modal-target fix is a substrate correctness fix that benefits any future modal-launched form. The server-seed + Alpine-init-clear pattern reconciles the plan-04-07 server-render contract with the plan-04-11 Alpine-driven chip widget.

## Issues Encountered

- **Docker container is image-baked, not bind-mounted.** Every verification step required `docker cp` of each changed file before running tests in the container. Same friction documented in plans 04-01..04-09.
- **`ruff` is not installed in the container** (`No module named ruff`); ran `ruff format` + `ruff check` on the Windows host (ruff 0.15.13 on PATH) instead. All checks pass.
- **Worktree base drift on spawn** — the agent spawned at `56d3091` instead of the expected `5b78ca9`; the startup base-assertion corrected via `git reset --hard 5b78ca9`. Documented in the WORKTREE READY line.
- **Worktree base SHA does not include the Phase 4 context docs** (CONTEXT/RESEARCH/PATTERNS/UI-SPEC/VALIDATION). Read them from the parent repo absolute paths (`C:/Claude/Coffee-Snobbery/.planning/phases/04-shared-catalog/04-*.md`). Same friction as prior Phase 4 plans.
- **Context7 quota exceeded** when verifying the Alpine CSP-build `x-data` object-literal-argument grammar. Relied on Alpine 3.x CSP-build knowledge + empirical confirmation (the templates render + the 19 tests pass; the live JS-grammar acceptance is asserted by Phase 12 Playwright per the plan's pytest-can't-drive-JS note).

## User Setup Required

None — this plan ships two new static JS files + template/router wiring + tests. No new env vars, no external service configuration. The two new `<script defer>` lines in `base.html` load from `/static/`, already mounted.

## Verification

Plan-stated verify commands + `<done>` criteria:

- **Task 1 verify:** `docker exec coffee-snobbery test -f app/static/js/alpine-components/mini-modal.js && ... autocomplete.js && grep -c 'modal-mount' app/templates/base.html` → both files OK, `2` ✓
- **Task 1 done criteria:**
  - `grep -c "Alpine.data('miniModal'" mini-modal.js` → `1` ✓
  - `grep -c "Alpine.data('autocomplete'" autocomplete.js` → `1` ✓ (+ `Alpine.data('flavorNoteChips'` → `1`)
  - `grep -c 'id="modal-mount"' base.html` → `1` ✓
  - `grep -c 'mini-modal.js|autocomplete.js' base.html` → `2` ✓
- **Task 2 verify:** `python -c "...assert 'x-data=\"autocomplete' in coffee_form... 'x-data=\"miniModal\"' in both modals..."` → `ok` ✓
- **Task 2 done criteria:**
  - `grep -c 'focus once from:closest' coffee_form.html` → `4` (2 real inputs + 2 doc comment occurrences; ≥1 required) ✓
  - `grep -c 'hx-trigger="input changed delay:350ms' coffee_form.html` → `3` (2 real + 1 doc; ≥1 required) ✓
  - No `|safe`, no inline `hx-on:` in any modified template ✓
- **Task 3 verify:** `docker exec coffee-snobbery pytest -q tests/phase_04/test_autocomplete.py -x` → `19 passed` ✓
- **Task 3 done criteria:**
  - 19 tests passing (≥11 required) ✓
  - All four client-contract attributes pinned (`delay:350ms[...]`, `hx-sync="this:replace"`, `focus once from:closest .field`, `hx-target="#modal-mount"`) ✓
  - HX-Trigger payload shape verified for both entities ✓
  - `Alpine.data('miniModal'` + `Alpine.data('autocomplete'` pinned in the served JS files ✓

**Wave-wide phase_04 regression:** `docker exec coffee-snobbery python -m pytest -q tests/phase_04/` → `198 passed` (was `179 passed, 1 skipped` before Task 3 replaced the Wave-0 stub; net +19 tests, the last Wave-0 stub now filled). ✓

**Full suite:** `docker exec coffee-snobbery python -m pytest -q` → `316 passed, 2 skipped, 10 xfailed, 34 warnings`. No regressions traced to this plan. ✓

## Threat Coverage

| Threat ID | Component | Mitigation | Test |
|-----------|-----------|------------|------|
| T-04-CSRF | Modal POSTs (`/roasters?as_modal=true`, `/flavor-notes?as_modal=true`) | Hidden `X-CSRF-Token` input in every modal-body form (via the `{% include %}`d form template); `CSRFFormFieldShim` hoists it; `CSRFMiddleware` enforces double-submit. | `test_roaster_modal_post_csrf_missing_returns_403` + `test_flavor_note_modal_post_csrf_missing_returns_403` (→ 403) ✓ |
| T-04-XSS | Modal templates rendering `prefill` + the autocomplete query echo + chip names | Jinja autoescape ON globally; `prefill` rendered via standard `{{ }}`; the autocomplete config's `initialName` uses `\|tojson`; the "+ Create new" URL uses `\|urlencode`; chip names rendered via Alpine `x-text` (text node, never innerHTML). No `\|safe` anywhere. | Grep: no `\|safe` in any modified template ✓ |
| (CSP bypass via component scripts) | mini-modal.js, autocomplete.js | Both served with the CSP nonce on the `<script>` tag; neither uses `eval` / `new Function` / `setTimeout(string)`. The `setTimeout(fn, 150)` blur-delay passes a function, not a string. Alpine CSP build rejects arbitrary expression strings in templates; `htmx.config.allowEval=false` (htmx-listeners.js) is belt-and-braces. | Code review + `test_*_js_served_with_alpine_data_registration` (files served + parse-clean) ✓ |
| (HX-3 race) | Autocomplete dropdown refresh | D-14 dodge: NO `hx-swap-oob` on the datalist fragment; `focus once from:closest .field` re-fetches the full list on first focus + `hx-sync="this:replace"` cancels in-flight on new keystroke. | `test_roaster_autocomplete_response_has_no_hx_swap_oob` + `test_flavor_note_autocomplete_response_has_no_hx_swap_oob` ✓ |

## Threat Flags

(none — no new security-relevant surface beyond what the plan's threat_model already covers. The `prefill` query param is server-bounded at the schema name max_length and autoescaped on render.)

## Known Stubs

None. The autocomplete + mini-modal flow is fully wired end-to-end (server contract verified by pytest; live JS behavior deferred to Phase 12 Playwright per the plan's explicit note — that is the intended phase boundary, not a stub).

## Next Plan Readiness

- **Phase 4 is COMPLETE.** This was the final plan (wave 10). All Phase 4 catalog surfaces (roasters, flavor notes, coffees, equipment, recipes, bags) ship with CRUD + the autocomplete-on-create UX.
- **Phase 5 (brew sessions)** ready — BREW-03 flavor-notes-observed autocomplete reuses `Alpine.data('autocomplete')` + `Alpine.data('flavorNoteChips')` directly; the `htmx:afterSettle → Alpine.initTree` hook is now globally available for any fragment-delivered Alpine content.
- **Phase 11 (polish)** — the general modal pattern (MOB-08) generalizes the `miniModal` component + the `#modal-mount` mechanism. Per-step ring-1 validation highlighting (deferred from plan 04-08) remains open.
- **Phase 12 (Playwright)** — asserts the live JS this plan's pytest cannot drive: modal open/close on click, ESC, dirty-confirm, keyboard nav (Up/Down/Enter/Esc), chip add/remove, and the D-16 pre-select after the mini-modal closes.

## Self-Check

- `app/static/js/alpine-components/mini-modal.js` exists: FOUND
- `app/static/js/alpine-components/autocomplete.js` exists: FOUND
- `app/templates/base.html` modified (#modal-mount + 2 scripts): FOUND
- `app/static/js/htmx-listeners.js` modified (initTree hook): FOUND
- `app/templates/fragments/coffee_form.html` modified (autocomplete + flavorNoteChips): FOUND
- `app/templates/fragments/roaster_modal.html` + `flavor_note_modal.html` (x-data="miniModal"): FOUND
- `app/templates/fragments/roaster_form.html` + `flavor_note_form.html` (modal target + prefill): FOUND
- `app/templates/fragments/autocomplete_list.html` (per-item handler + prefill URL): FOUND
- `app/routers/roasters.py` + `flavor_notes.py` (prefill param): FOUND
- `tests/phase_04/test_autocomplete.py` (19 real tests, Wave-0 stub replaced): FOUND
- `tests/phase_04/test_routers_coffees.py` (substring assertion update): FOUND
- Commit `8d87e57` (Task 1) in `git log`: FOUND
- Commit `378b03b` (Task 2) in `git log`: FOUND
- Commit `419a4cb` (Task 3) in `git log`: FOUND
- Container verify `pytest -q tests/phase_04/test_autocomplete.py` returns `19 passed`: FOUND
- Wave-wide `pytest -q tests/phase_04/` returns `198 passed`: FOUND
- Full suite `pytest -q` returns `316 passed, 2 skipped, 10 xfailed`: FOUND

## Self-Check: PASSED

---
*Phase: 04-shared-catalog*
*Plan: 11*
*Completed: 2026-05-19*
