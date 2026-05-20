---
phase: 05-brew-sessions
plan: 04
subsystem: api
tags: [fastapi, htmx, router, csrf, idor, prefill, draft, sec-06, jinja2]

# Dependency graph
requires:
  - phase: 05-brew-sessions (plan 02)
    provides: brew_sessions service (create/update/get/list, resolve_prefill D-04/05/06/08, usage_count maintenance) + brew_drafts service (upsert/get/clear ON CONFLICT)
  - phase: 05-brew-sessions (plan 01)
    provides: BrewSessionCreate/Update schemas (Decimal rating, extra=forbid, EY+user_id absent), BrewSession + BrewDraft models
  - phase: 04-shared-catalog
    provides: coffees/recipes/equipment list services + flavor_note_name_map; coffee_form.html SEC-06 router pattern; require_user + get_session deps; CSRFFormFieldShim
  - phase: 02-auth
    provides: request.state.user per-user scoping, seeded_regular_user/seeded_admin_user test fixtures
provides:
  - "app/routers/brew.py — dedicated brew form router: GET /brew/new (prefilled), GET /brew/prefill (dynamic re-prefill fragment), POST /brew/draft (autosave), POST /brew (create), GET /brew/{id}/edit, POST /brew/{id} (update)"
  - "Locked context contract for pages/brew_form.html + fragments/brew_prefill_fields.html (prefill values, touched-state map, pill captions, advertised chips, selectables, server_draft) — Plan 05 renders against it"
  - "pages/brew_form.html + fragments/brew_prefill_fields.html scaffolds (CSP-strict, CSRF hidden field) that Plan 05 fleshes out with the four Alpine components"
  - "brew router registered in app/main.py (6 routes)"
affects: [brew-form-ui (Plan 05), brew-sessions-list (Plan 06), analytics, ai-recommendations]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "First per-user ROUTER: every handler require_user-gated + scoped by request.state.user.id; cross-user session_id -> HTTPException(404) via the service None sentinel (T-05-05 IDOR existence non-leak, not 403)"
    - "Dedicated-page form router (D-01): GET renders a full pages/*.html (extends base.html); success responds 204 + HX-Redirect instead of swapping a row fragment (diverges from the Phase-4 inline-expand pattern)"
    - "Dynamic re-prefill fragment endpoint (GET /brew/prefill): a coffee/recipe <select> hx-get swaps a prefill-DEPENDENT subset, reusing resolve_prefill — per-attempt fields (rating/observed/notes) deliberately ABSENT so an in-progress entry is never clobbered"

key-files:
  created:
    - app/routers/brew.py
    - app/templates/pages/brew_form.html
    - app/templates/fragments/brew_prefill_fields.html
    - tests/routers/test_brew_router.py
  modified:
    - app/main.py

key-decisions:
  - "Success path responds HTTP 204 + HX-Redirect to /brew (the sessions list, Plan 06) — 204 (not 200) makes the no-body redirect explicit and matches HTMX's HX-Redirect contract; the plan allowed full-nav too but the form is hx-boosted"
  - "POST /brew/draft returns 204 (silent autosave per UI-SPEC) and is NOT CSRF-exempt — it carries session_id so starlette-csrf enforces the double-submit token like every state-changing route"
  - "GET /brew/new exposes the server draft as both server_draft (dict) and server_draft_json (JSON string) in create-mode context; the Alpine layer (Plan 05) owns the localStorage-primary / server-fallback reconciliation order (BREW-07)"
  - "The whole router (all 6 routes incl. /brew/draft and /brew/prefill) + both templates landed in the Task-1 GREEN commit because they share app/routers/brew.py + the templates; Task 2/3 commits would have re-touched the same files. This is the file-organization the plan's <files> fields prescribe (each task lists app/routers/brew.py), not a scope deviation — same consolidation Plan 02 documented."

patterns-established:
  - "Per-user router scoping with the service None/False sentinel mapped to 404 (the router-404 IDOR contract, first applied at the router layer)"
  - "Prefill-fields fragment shared between the initial server render ({% include %}) and the hx-get re-prefill swap so both produce identical DOM for the prefill region"
  - "Mass-assignment defense at the router boundary: _parse_form_payload never reads extraction_yield_pct / user_id; BrewSessionCreate extra=forbid folds any extra into the _form sentinel and re-renders at HTTP 200"

requirements-completed: [BREW-02, BREW-03, BREW-05, BREW-07, BREW-09]

# Metrics
duration: ~14min
completed: 2026-05-20
---

# Phase 5 Plan 04: Brew Form Router Summary

**Dedicated per-user brew form router (D-01) with SEC-06 validation-to-200, prefill-driven GET, brew-again deep link, a dynamic re-prefill fragment (D-04/D-05/D-11), and a CSRF-enforced draft autosave — 16 router tests green in-container, full real test tree 370 passed / 0 failed.**

## Performance

- **Duration:** ~14 min
- **Started:** 2026-05-20T02:12:03Z
- **Completed:** 2026-05-20T02:26:48Z
- **Tasks:** 3 of 3
- **Files modified:** 5 (4 created, 1 modified)

## Accomplishments

- `app/routers/brew.py` — the app's first per-user ROUTER. Every handler is `require_user`-gated and scoped by `request.state.user.id`; a cross-user `session_id` returns **404** (the service `None` sentinel mapped to `HTTPException(404)`) — IDOR existence non-leak, not 403 (T-05-15). `user_id` is set server-side from `request.state.user.id`; `extraction_yield_pct` and `user_id` are NEVER read from the form (T-05-16) — `extra="forbid"` folds any posted extra into the `_form` sentinel and re-renders at HTTP 200.
- **SEC-06 path:** `POST /brew` and `POST /brew/{id}` parse via `_parse_form_payload` → `BrewSessionCreate/Update` → on `ValidationError` re-render `pages/brew_form.html` at **HTTP 200** (not 422) with `values` + `errors`; on success `create/update_brew_session`, `clear_draft`, and respond `204 + HX-Redirect` to the sessions list.
- **Prefill GET (`/brew/new`):** calls `resolve_prefill` (D-04 hybrid, D-05 recipe-wins, D-06 newest-open-bag, D-08 brew-again via `?from=`), layers the per-field touched-state map (all `False` = prefilled-untouched) + pill captions ("from last brew" / "from recipe" / "from this brew") + D-11 advertised chips, and exposes the server draft for client reconciliation.
- **Dynamic re-prefill fragment (`GET /brew/prefill`):** the coffee/recipe `<select>` hx-get target — reuses `resolve_prefill` (no duplicate prefill logic), renders ONLY the prefill-dependent subset + the D-11 advertised-chip region (rating/observed/notes deliberately ABSENT), scoped to `user.id` (T-05-18b no cross-user leak). Declared among the LITERAL paths before `/{session_id}` (route-order gotcha).
- **Draft autosave (`POST /brew/draft`):** upserts the one-per-user draft (BREW-07) under CSRF (NOT exempt — a tokenless POST 403s), returns silent 204, accepts form-encoded OR JSON. `clear_draft` fires on a successful create.
- Brew router registered in `app/main.py` (6 routes; no middleware changes). `pages/brew_form.html` + `fragments/brew_prefill_fields.html` scaffolds ship the locked context contract so Plan 05 renders against concrete keys.

## Task Commits

1. **Task 1: brew router — GET new/edit + POST create/update + register (TDD)**
   - `19e8198` (test) [RED — collectable; skips until app.routers.brew lands]
   - `3cc2cf6` (feat) [GREEN — also lands the Task 2 `/brew/draft` + Task 3 `/brew/prefill` routes and both templates, which share the same files]
2. **Task 2: Draft autosave endpoint + restore wiring** — verified green within `3cc2cf6` (the `POST /brew/draft` route + `server_draft` context live in the shared `brew.py` / `brew_form.html`); tests `test_draft_*` + `test_brew_new_includes_server_draft` pass.
3. **Task 3: GET /brew/prefill dynamic re-prefill fragment** — verified green within `3cc2cf6` (the `/brew/prefill` route + `fragments/brew_prefill_fields.html` live in the shared files); tests `-k prefill` (7) pass.

_TDD gate satisfied: a `test(...)` RED commit (`19e8198`) precedes the `feat(...)` GREEN commit (`3cc2cf6`)._

## Files Created/Modified

- `app/routers/brew.py` — the 6-route brew form router (new/prefill/draft/create/edit/update), `_parse_form_payload`, `_normalize_errors` + `_FORM_FIELDS` fold, `_hydrate_form_context`, prefill pill/touched helpers
- `app/templates/pages/brew_form.html` — dedicated create/edit page (extends base.html); CSRF hidden field; includes the prefill fragment; per-attempt fields (rating/observed/notes); D-02 disclosure; sticky save bar; server-draft surface
- `app/templates/fragments/brew_prefill_fields.html` — the prefill-DEPENDENT subset (coffee/recipe/equipment selects + dose/water/temp/grind + pills + D-11 advertised chips); the hx-get swap target
- `app/main.py` — `from app.routers import brew as brew_router` + `app.include_router(brew_router.router)`
- `tests/routers/test_brew_router.py` — 16 tests across all three tasks (SEC-06, IDOR 404, mass-assignment, prefill, brew-again, draft upsert/CSRF/per-user, re-prefill D-04/D-05/D-11, user-scoping, require_user gate)

### Locked context contract for Plan 05 (the form template renders against these)

`pages/brew_form.html` (and the `{% include %}`d `fragments/brew_prefill_fields.html`) receive:

| Key | Shape | Meaning |
|-----|-------|---------|
| `values` | `{field: str}` (or `list[str]` for `flavor_note_ids_observed`) | prefilled / submitted form values; `None` rendered as `""` |
| `errors` | `{field: message}` | per-field SEC-06 errors; `_form` sentinel for folded extras |
| `mode` | `"create" \| "edit"` | drives title, submit label, draft surface |
| `session_id` | `int \| None` | edit mode only |
| `form_action` | `str` | `/brew` (create) or `/brew/{id}` (edit) |
| `touched` | `{field: bool}` | `False` = prefilled-untouched → render the pill; empty in edit mode (no ghosting) |
| `pill_sources` | `{field: caption}` | "from last brew" / "from recipe" / "from this brew" |
| `advertised_chips` | `list[{id, name}]` | D-11 quick-add suggestion chips for the selected coffee |
| `selected_flavor_notes` | `list[{id, name}]` | seeded observed chips (per-session; NEVER advertised) |
| `coffees` / `recipes` / `brewers` / `grinders` / `kettles` | `list[ORM]` | dropdown sources |
| `equipment_name_map` | `{id: "brand model"}` | equipment label lookup |
| `server_draft` / `server_draft_json` | `dict \| None` / JSON str | the server draft for client reconciliation (create mode only) |
| `disclosure_open` | `bool` | edit mode auto-opens the D-02 disclosure when yield/tds non-null |

Carryable prefill fields (the `touched` / `pill_sources` keys): `coffee_id, bag_id, recipe_id, brewer_id, grinder_id, kettle_id, water_type, dose_grams_actual, water_grams_actual, yield_grams_actual, tds_pct, water_temp_c_actual, grind_setting_actual`. The four D-05 recipe-template fields are `dose_grams_actual, water_grams_actual, water_temp_c_actual, grind_setting_actual`.

## Decisions Made

- **Success → 204 + HX-Redirect.** The plan allowed a full-nav redirect or HX-Redirect; the form is hx-boosted, so the create/update success path returns `Response(204, headers={"HX-Redirect": "/brew"})`. 204 (not 200) makes the empty-body redirect explicit and avoids HTMX trying to swap a non-existent body.
- **`/brew/draft` is silent 204 and never CSRF-exempt.** Autosave is silent per UI-SPEC (no body needed). The route carries `session_id`, so starlette-csrf enforces the double-submit token — confirmed by `test_draft_requires_csrf` (tokenless POST → 403). The payload is opaque JSON the service stores verbatim.
- **Server draft exposed in two shapes.** `server_draft` (the dict) drives the conditional restore notice; `server_draft_json` (a `json.dumps` string) is the `data-server-draft` attribute the Plan-05 Alpine `brewDraft` component reads. Reconciliation ORDER (localStorage-primary) stays client-side per BREW-07.
- **Whole router landed in the Task-1 GREEN commit.** All 6 routes + both templates share `app/routers/brew.py` and the two template files (every task's `<files>` lists `app/routers/brew.py`). Implementing them together avoids re-touching the same files across three commits; the RED→GREEN gate is preserved (`19e8198` test precedes `3cc2cf6` feat). Same file-organization consolidation Plan 02 documented.

## Deviations from Plan

None — plan executed exactly as written. The three tasks were implemented into the shared `app/routers/brew.py` + the two templates in a single GREEN commit (file-organization, not scope); the RED test commit precedes it, and each task's verify command passes (`test_form_validation_200` + `test_ey_not_writable`; full file; `-k prefill`).

## Issues Encountered

- **CSRF in tests needed a real signed token.** The first run of the named tests 403'd: starlette-csrf signs the `csrftoken`, so a literal placeholder fails the double-submit check. Adopted the established Phase-4 `_prime_csrf` pattern (GET `/` to mint a real signed token, wire it onto the client cookie + `X-CSRF-Token` header). Fixed in the RED→GREEN iteration before the GREEN commit.
- **Test-isolation bug in my own fixture (auto-fixed before commit).** `test_prefill_fragment_advertised_chips` created a citext-UNIQUE `flavor_notes` row that the cleanup fixture didn't delete, so a second run hit `DuplicateNameError`. Fixed by renaming the seed to a `RouterNote%` prefix and adding `DELETE FROM flavor_notes WHERE name LIKE 'RouterNote%'` to the `clean_brew_router` fixture, and cleared the stale row. All 16 tests green; not a production-code issue.
- **Stale nested `tests/tests/` duplicate.** The documented `docker compose cp tests/ ...` idiom nests into `/app/tests/tests/` (a root-owned duplicate predating this plan; see 05-01-SUMMARY). One spurious `test_credentials.py` failure surfaced from that copy during the full-suite run. The canonical `tests/services/test_credentials.py` passes 13/13; the real test tree is green (`pytest --ignore=tests/tests` → 370 passed, 2 skipped, 10 xfailed, 0 failed). Not a code issue — a test-iteration artifact.
- **Context7 not consulted.** Prior Phase-5 plans hit the monthly quota; this plan reused the planner-verified FastAPI/Starlette/HTMX patterns already on disk (coffees.py router, CSRFFormFieldShim, htmx-listeners.js) and validated behavior directly against the live in-container app (16 router tests). No version-specific API uncertainty remained.

## Known Stubs

The two templates are **intentional Plan-05 scaffolds**, documented in the plan (`<action>`: "If brew_form.html does not yet exist when this task runs, scaffold brew_prefill_fields.html ... and have Plan 05 {% include %} it; coordinate the include in 05-04-SUMMARY"). They render the full locked context contract and the real prefill/per-attempt/disclosure/sticky-bar field structure; what Plan 05 adds is the four Alpine components (ratingStars, observedFlavorNotes, brewRatio, brewDraft), the tap-on-stars control, the autocomplete tag input wiring, and the sticky-bar in-flight polish. The router (this plan's deliverable) is fully wired — no router stubs. The "Extraction yield —" in the disclosure is render-only by design (GENERATED column, never an input).

## Threat Flags

None — the router introduces no security surface outside the plan's `<threat_model>`. All five registered threats are mitigated as designed: T-05-15 (IDOR → 404 via user-scoped service), T-05-16 (mass assignment → `_parse_form_payload` + `extra="forbid"` + server-set `user_id`), T-05-17 (CSRF on every POST incl. `/brew/draft`, no exemption), T-05-18 (`get_draft` keyed by `user_id`), T-05-18b (`resolve_prefill` scoped by `user.id`).

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- The brew form server contract is locked and tested. **Plan 05** mounts the four Alpine components on `pages/brew_form.html` + `fragments/brew_prefill_fields.html` and wires the coffee/recipe `<select>` hx-get to `GET /brew/prefill` (target `#brew-prefill-fields`); the field markup is consistent between the initial render and the swap.
- **Plan 06** (sessions list) links into this router: "Brew again" → `/brew/new?from={id}` (D-08), "Edit" → `/brew/{id}/edit`, and the success redirect target `/brew` is the list route Plan 06 owns.
- App boots with the brew router registered (6 routes); `GET /brew/new` returns 200 for an authed user. Real test tree green.

## Self-Check: PASSED

All 4 created files + the 1 modified file + this SUMMARY exist on disk; both task commits (`19e8198` test RED, `3cc2cf6` feat GREEN) are present in git history; the 16 router tests pass in-container; the app imports with 6 `/brew` routes registered.

---
*Phase: 05-brew-sessions*
*Completed: 2026-05-20*
